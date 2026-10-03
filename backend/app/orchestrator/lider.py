"""Líder de la fábrica de software: decide el orden, los reintentos y cuándo
detenerse a preguntarle a una persona.

    pedido → Especificador → [por cada especificación, en orden de dependencias]
             Implementador → Revisor ─rechazo→ Diagnosticador (efímero)
                                 │                ├─ implementación → reintento
                                 │                ├─ especificación → pregunta humana
                                 │                └─ harness → bloqueada, sin reintento
                                 └─aprobado→ Verificador → aprobada
           → Despliegue (cuando todas quedaron aprobadas)

Cada etapa deja tres rastros: un evento en el WebSocket (el contrato
congelado, con run_id = id del encargo), una métrica de costo y tiempo, y un
registro sellado en la bitácora con lo que el harness midió.

El estado vive en el repositorio, no en memoria: una pausa humana termina la
tarea de asyncio, y la acción humana (responder, aprobar, reanudar) lanza una
nueva que retoma desde lo que está guardado. Un reinicio del proceso deja los
encargos activos como "interrumpido", listos para reanudar.

Garantía de terminación — un encargo nunca queda "en curso" para siempre:
- cada etapa tiene un tope de tiempo (politica.timeout_etapa_s);
- un atraso repetido (mismo error, vaivén entre dos errores, mismos archivos
  otra vez) se detecta como en el StuckDetector de OpenHands: primero se
  cambia de estrategia (reescribir desde cero) y, si sigue igual, la
  especificación se cierra como fallida con un informe;
- `rondas` acota los intentos de una especificación sumando los reintentos
  humanos, así "Reintentar" tampoco puede girar sin fin;
- una persona puede detener un encargo o cerrarlo con lo ya aprobado.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import shutil
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Literal, TypeVar

from ..agents.fabrica import (
    LIMITE_CONTEXTO,
    DespliegueFabrica,
    Diagnosticador,
    Especificador,
    Implementador,
    Medidor,
    Revisor,
    Verificador,
)
from ..agents.fabrica.implementador import archivo_seguro
from ..dominio.errores import (
    AccionNoPermitida,
    DespliegueFallido,
    EncargoNoEncontrado,
    EtapaVencida,
)
from ..dominio.fabrica import (
    ESTADOS_ACTIVOS,
    Ejecucion,
    Encargo,
    Especificacion,
    Etapa,
    MetricaEtapa,
    PoliticaFabrica,
    Pregunta,
    ahora_iso,
    aplicar_modo_aprobacion,
    detectar_atasco,
    especificaciones_listas,
    estado_final,
    firma_archivos,
    huella_rechazo,
    presupuesto_agotado,
    sha256_texto,
)
from ..dominio.modelos import Estado, EventoAgente
from ..dominio.puertos import (
    BitacoraInmutable,
    Cerebro,
    Desplegador,
    EjecutorPruebas,
    PublicadorEventos,
    RepositorioEncargos,
    RepositorioMetricas,
)
from .plugins import RegistroPlugins
from .prefect_opcional import en_flujo, en_tarea

log = logging.getLogger(__name__)
T = TypeVar("T")

OPCION_REINTENTAR_PROPUESTA = "Reintentar con la propuesta"
OPCION_REINTENTAR = "Reintentar"
OPCION_DESCARTAR = "Descartar"
MOTIVO_DESCARTADA = "Descartada por decisión humana"
MOTIVO_RECHAZADA = "Rechazada por una persona"
MOTIVO_SIN_TERMINAR = "Sin terminar: el encargo se cerró con lo ya aprobado"
RESPUESTA_CIERRE = "Encargo cerrado por una persona"
ESTRATEGIA_REESCRITURA = "reescritura"


class LiderFabrica:
    name = "lider"

    def __init__(
        self,
        *,
        repositorio: RepositorioEncargos,
        bitacora: BitacoraInmutable,
        metricas: RepositorioMetricas,
        bus: PublicadorEventos,
        politica: PoliticaFabrica,
        dir_espacios: Path,
        cerebro_para: Callable[[str], Awaitable[Cerebro]],
        ejecutor: EjecutorPruebas,
        ejecutor_e2e: EjecutorPruebas | None,
        desplegador_para: Callable[[Path, str, str], Desplegador],
        tablas_existentes: Callable[[], Awaitable[list[str]]],
        timeout_pruebas_s: float = 120.0,
        e2e_url_base: str = "",
        plugins: RegistroPlugins | None = None,
        limite_contexto: int = LIMITE_CONTEXTO,
        paralelismo: int = 3,
        usar_prefect: bool = False,
    ) -> None:
        self._repo = repositorio
        self._bitacora = bitacora
        self._metricas = metricas
        self._bus = bus
        self.politica = politica
        self._dir_espacios = dir_espacios
        self._cerebro_para = cerebro_para
        self._ejecutor = ejecutor
        self._ejecutor_e2e = ejecutor_e2e
        self._desplegador_para = desplegador_para
        self._tablas_existentes = tablas_existentes
        self._timeout_pruebas_s = timeout_pruebas_s
        self._e2e_url_base = e2e_url_base
        self.plugins = plugins or RegistroPlugins()
        self._limite = limite_contexto
        # Tope de especificaciones construyéndose a la vez dentro de un encargo.
        self.paralelismo = max(1, paralelismo)
        self._usar_prefect = usar_prefect
        self._tareas: dict[str, asyncio.Task[None]] = {}

    # --- consultas ---

    @property
    def usa_prefect(self) -> bool:
        return self._usar_prefect

    def corriendo(self, encargo_id: str) -> bool:
        tarea = self._tareas.get(encargo_id)
        return tarea is not None and not tarea.done()

    async def obtener(self, encargo_id: str) -> Encargo:
        encargo = await self._repo.obtener(encargo_id)
        if encargo is None:
            raise EncargoNoEncontrado(encargo_id)
        return encargo

    async def esperar(self, encargo_id: str) -> None:
        """Para pruebas y scripts: espera a que la tarea en curso termine."""
        tarea = self._tareas.get(encargo_id)
        if tarea is not None:
            await tarea

    def espacio(self, encargo_id: str) -> Path:
        return self._dir_espacios / encargo_id

    # --- acciones (humanas o de arranque) ---

    async def crear(self, pedido: str, *, base_id: str | None = None) -> Encargo:
        """Un encargo nuevo. Con `base_id` es una nueva versión de otro: arranca
        con una copia de sus archivos y el Especificador trabaja sobre ese
        código en vez de empezar de cero.
        """
        encargo = Encargo(id=uuid.uuid4().hex[:8], pedido=pedido.strip())
        heredados: list[dict[str, object]] = []
        if base_id is not None:
            base = await self.obtener(base_id)
            encargo.version = await self._siguiente_version(base.linaje)
            encargo.padre_id = base.id
            encargo.raiz_id = base.linaje
            heredados = await asyncio.to_thread(
                _copiar_espacio, self.espacio(base.id), self.espacio(encargo.id)
            )
        await self._repo.guardar(encargo)
        # Lo heredado queda sellado: la línea de base de esta versión.
        await self._bitacora.registrar(
            encargo.id,
            self.name,
            "encargo_recibido",
            {
                "pedido": encargo.pedido,
                "version": encargo.version,
                "padre_id": encargo.padre_id,
                "raiz_id": encargo.raiz_id,
                "archivos_heredados": heredados,
            },
        )
        await self._disparar(encargo.id, "encargo_creado", pedido=encargo.pedido)
        self._lanzar(encargo.id)
        return encargo

    async def reiniciar_linea(self) -> dict[str, list[str]]:
        """Deja la oficina limpia: detiene lo que esté corriendo y archiva
        todos los encargos actuales. No borra nada — la bitácora es inmutable
        y las carpetas quedan para Ejecuciones, desde donde se puede reanudar
        o sacar una nueva versión.
        """
        detenidos: list[str] = []
        for encargo_id, tarea in list(self._tareas.items()):
            if not tarea.done():
                tarea.cancel()
                # La tarea cancelada no guarda nada más; el estado lo fija esto.
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await tarea
                detenidos.append(encargo_id)
        archivados: list[str] = []
        for encargo in await self._repo.listar():
            if encargo.archivado_en is not None:
                continue
            estado_previo = encargo.estado
            if encargo.estado in ESTADOS_ACTIVOS or encargo.id in detenidos:
                encargo.estado = "interrumpido"
                encargo.motivo = "Detenido al reiniciar la línea"
                for e in encargo.especificaciones:
                    if e.estado == "en_curso":
                        e.estado = "pendiente"
            encargo.archivado_en = ahora_iso()
            await self._guardar(encargo)
            await self._bitacora.registrar(
                encargo.id,
                "humano",
                "archivado",
                {"motivo": "reinicio de la línea", "estado_previo": estado_previo},
            )
            archivados.append(encargo.id)
        await self._emitir(
            "linea",
            self.name,
            "done",
            f"Línea reiniciada: {len(archivados)} encargo(s) archivado(s), "
            f"{len(detenidos)} detenido(s)",
        )
        return {"archivados": archivados, "detenidos": detenidos}

    # --- ejecuciones: lo que quedó en disco ---

    async def ejecuciones(self) -> list[Ejecucion]:
        """Cada carpeta de fabrica_espacios/ cruzada con su encargo en la base,
        más los encargos que no llegaron a tener carpeta. La más reciente primero.
        """
        encargos = {e.id: e for e in await self._repo.listar()}
        carpetas = await asyncio.to_thread(_carpetas, self._dir_espacios)
        resultado: list[Ejecucion] = []
        for ejecucion_id in set(encargos) | set(carpetas):
            e = encargos.get(ejecucion_id)
            archivos, tamano, modificado = carpetas.get(ejecucion_id, (0, 0, None))
            resultado.append(
                Ejecucion(
                    id=ejecucion_id,
                    en_base=e is not None,
                    carpeta=ejecucion_id in carpetas,
                    pedido=e.pedido if e else None,
                    estado=e.estado if e else None,
                    version=e.version if e else 1,
                    padre_id=e.padre_id if e else None,
                    raiz_id=e.linaje if e else ejecucion_id,
                    archivado_en=e.archivado_en if e else None,
                    creado_en=e.creado_en if e else modificado,
                    costo_usd=e.costo_usd if e else 0.0,
                    especificaciones=len(e.especificaciones) if e else 0,
                    aprobadas=sum(1 for s in e.especificaciones if s.estado == "aprobada")
                    if e
                    else 0,
                    archivos=archivos,
                    bytes=tamano,
                    modificado_en=modificado,
                )
            )
        resultado.sort(key=lambda x: x.creado_en or "", reverse=True)
        return resultado

    async def archivos(self, encargo_id: str) -> list[dict[str, object]]:
        return await asyncio.to_thread(_listar_archivos, self._espacio_existente(encargo_id))

    async def leer_archivo(self, encargo_id: str, ruta: str) -> str:
        espacio = self._espacio_existente(encargo_id).resolve()
        archivo = (espacio / ruta).resolve()
        if not archivo.is_relative_to(espacio) or not archivo.is_file():
            raise AccionNoPermitida("Ese archivo no existe en la ejecución")
        if archivo.stat().st_size > _MAX_LECTURA:
            raise AccionNoPermitida("El archivo es demasiado grande para mostrarlo")
        return await asyncio.to_thread(archivo.read_text, "utf-8", "replace")

    async def responder(self, encargo_id: str, pregunta_id: str, respuesta: str) -> Encargo:
        encargo = await self._obtener_activo(encargo_id)
        # La abierta con ese id: encargos guardados antes de que los ids de las
        # dudas del Diagnosticador fueran únicos pueden tener dos con el mismo
        # id, una ya respondida.
        pregunta = next(
            (p for p in encargo.preguntas if p.id == pregunta_id and p.respuesta is None), None
        )
        if pregunta is None:
            raise AccionNoPermitida("Esa pregunta no existe o ya fue respondida")
        texto = respuesta.strip()
        if not texto:
            raise AccionNoPermitida("La respuesta no puede estar vacía")
        pregunta.respuesta = texto
        await self._bitacora.registrar(
            encargo.id,
            "humano",
            "respuesta",
            {"pregunta_id": pregunta.id, "pregunta": pregunta.texto, "respuesta": texto},
        )
        if pregunta.origen == "diagnosticador" and pregunta.espec_id:
            espec = encargo.espec(pregunta.espec_id)
            if espec is not None:
                if texto.lower().startswith(OPCION_DESCARTAR.lower()):
                    espec.estado, espec.motivo = "fallida", MOTIVO_DESCARTADA
                else:
                    espec.estado, espec.intentos, espec.motivo = "pendiente", 0, ""
                    if texto.lower().startswith(OPCION_REINTENTAR_PROPUESTA.lower()):
                        if pregunta.propuesta:
                            espec.descripcion += (
                                "\n\nAplicar la propuesta del Diagnosticador (aprobada por "
                                f"una persona): {pregunta.propuesta}"
                            )
                    elif not texto.lower().startswith(OPCION_REINTENTAR.lower()):
                        espec.descripcion += f"\n\nAclaración humana: {texto}"
        await self._continuar_si_corresponde(encargo)
        return encargo

    async def decidir(self, encargo_id: str, espec_id: str, *, aprobar: bool) -> Encargo:
        encargo = await self._obtener_activo(encargo_id)
        espec = encargo.espec(espec_id)
        if espec is None or espec.estado != "esperando_aprobacion":
            raise AccionNoPermitida("Esa especificación no está esperando aprobación")
        if aprobar:
            espec.aprobada_por_humano, espec.estado = True, "pendiente"
        else:
            espec.estado, espec.motivo = "fallida", MOTIVO_RECHAZADA
        await self._bitacora.registrar(
            encargo.id,
            "humano",
            "aprobacion" if aprobar else "rechazo",
            {"espec_id": espec.id, "titulo": espec.titulo},
        )
        await self._continuar_si_corresponde(encargo)
        return encargo

    async def reanudar(self, encargo_id: str) -> Encargo:
        """Carga un encargo en la línea. Si quedó interrumpido o fallido, se
        relanza. Si está archivado esperando una decisión (o ya terminado),
        solo vuelve a la oficina: su foquito reaparece y no se relanza nada.
        """
        encargo = await self._obtener_detenido(encargo_id)
        if encargo.estado not in ("interrumpido", "fallido"):
            if encargo.archivado_en is None:
                raise AccionNoPermitida(f"Un encargo en estado '{encargo.estado}' no se reanuda")
            encargo.archivado_en = None
            await self._bitacora.registrar(
                encargo.id, "humano", "restaurado", {"estado": encargo.estado}
            )
            await self._guardar(encargo)
            return encargo
        for e in encargo.especificaciones:
            if e.estado == "en_curso":
                e.estado = "pendiente"
            # Reanudar un fallido vuelve a intentar lo que falló (y lo que quedó
            # bloqueado por eso), salvo lo que una persona decidió descartar.
            # Es una decisión humana explícita: también limpia el historial de
            # atascos, o la especificación se volvería a cerrar al primer intento.
            elif e.estado in ("fallida", "bloqueada") and e.motivo not in (
                MOTIVO_DESCARTADA,
                MOTIVO_RECHAZADA,
            ):
                e.estado, e.intentos, e.motivo = "pendiente", 0, ""
                e.rondas, e.huellas, e.estrategia = 0, [], ""
            # Una pendiente que ya había agotado sus intentos (quedó así al
            # interrumpirse mientras esperaba una respuesta) arranca de cero:
            # si no, el ciclo saltaría directo a "agotado" con un motivo vacío.
            if e.estado == "pendiente" and e.intentos >= self.politica.max_intentos:
                e.intentos = 0
        encargo.motivo = ""
        # Reanudar un archivado lo devuelve a la línea.
        encargo.archivado_en = None
        await self._bitacora.registrar(encargo.id, "humano", "reanudacion", {})
        if encargo.preguntas_abiertas():
            # Relanzar con una pregunta abierta volvería a correr la
            # especificación que la hizo y duplicaría la pregunta: primero se
            # responde, y la respuesta es la que relanza.
            encargo.estado = "esperando_humano"
            await self._guardar(encargo)
            return encargo
        encargo.estado = "en_curso" if encargo.especificaciones else "especificando"
        await self._guardar(encargo)
        self._lanzar(encargo.id)
        return encargo

    async def detener(self, encargo_id: str) -> Encargo:
        """Corta un encargo que está corriendo. Queda "interrumpido", con todo
        lo hecho guardado, listo para reanudar o cerrar.
        """
        tarea = self._tareas.get(encargo_id)
        if tarea is None or tarea.done():
            raise AccionNoPermitida("El encargo no está corriendo")
        tarea.cancel()
        # La tarea cancelada no guarda nada más; el estado lo fija esto.
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await tarea
        encargo = await self.obtener(encargo_id)
        encargo.estado, encargo.motivo = "interrumpido", "Detenido por una persona"
        for e in encargo.especificaciones:
            if e.estado == "en_curso":
                e.estado = "pendiente"
        await self._guardar(encargo)
        await self._bitacora.registrar(encargo.id, "humano", "detenido", {})
        await self._emitir(
            encargo.id, self.name, "pending", "Detenido por una persona: se puede reanudar o cerrar"
        )
        return encargo

    async def finalizar(self, encargo_id: str) -> Encargo:
        """Cierra el encargo con lo que ya está aprobado: lo que falta queda
        como fallido (sin terminar) y las preguntas abiertas, contestadas con
        el cierre. Es la salida explícita para no dejar un encargo esperando
        para siempre una decisión que nadie va a tomar.
        """
        encargo = await self._obtener_activo(encargo_id)
        if encargo.estado == "terminado":
            raise AccionNoPermitida("El encargo ya terminó")
        for p in encargo.preguntas_abiertas():
            p.respuesta = RESPUESTA_CIERRE
        for e in encargo.especificaciones:
            if e.estado in ("pendiente", "esperando_aprobacion", "en_curso"):
                e.estado, e.motivo = "fallida", MOTIVO_SIN_TERMINAR
        total = len(encargo.especificaciones)
        aprobadas = sum(1 for e in encargo.especificaciones if e.estado == "aprobada")
        encargo.estado = "terminado" if total and aprobadas == total else "fallido"
        encargo.motivo = (
            f"Cerrado por una persona con {aprobadas} de {total} especificaciones aprobadas"
        )
        await self._guardar(encargo)
        await self._bitacora.registrar(
            encargo.id, "humano", "cierre", {"aprobadas": aprobadas, "total": total}
        )
        await self._emitir(
            encargo.id,
            self.name,
            "done" if encargo.estado == "terminado" else "error",
            encargo.motivo,
        )
        await self._disparar(
            encargo.id, "encargo_terminado", estado=encargo.estado, costo_usd=encargo.costo_usd
        )
        return encargo

    async def recuperar_interrumpidos(self) -> list[str]:
        """Al arrancar: nada puede estar corriendo todavía, así que un encargo
        guardado como activo quedó a medias por un reinicio.
        """
        ids: list[str] = []
        for encargo in await self._repo.listar():
            if encargo.estado in ESTADOS_ACTIVOS:
                encargo.estado = "interrumpido"
                encargo.motivo = "El proceso se reinició a mitad del encargo"
                await self._guardar(encargo)
                await self._bitacora.registrar(encargo.id, self.name, "interrumpido", {})
                ids.append(encargo.id)
        return ids

    # --- ciclo principal ---

    def _lanzar(self, encargo_id: str) -> None:
        tarea = asyncio.create_task(self._correr_seguro(encargo_id))
        self._tareas[encargo_id] = tarea

        def _soltar(t: asyncio.Task[None]) -> None:
            # Solo si sigue siendo la misma: una acción humana pudo lanzar otra.
            if self._tareas.get(encargo_id) is t:
                del self._tareas[encargo_id]

        tarea.add_done_callback(_soltar)

    async def _correr_seguro(self, encargo_id: str) -> None:
        try:
            await en_flujo(
                self._usar_prefect,
                "encargo-fabrica",
                f"encargo-{encargo_id}",
                lambda: self._correr(encargo_id),
            )
        except Exception as e:  # noqa: BLE001 — la frontera de fallo del encargo
            log.exception("El encargo %s terminó con una excepción", encargo_id)
            motivo = f"{type(e).__name__}: {e}"
            # Si registrar la falla también falla (p. ej. la base no responde),
            # al menos el panel se entera: nunca un encargo mudo "en curso".
            try:
                encargo = await self._repo.obtener(encargo_id)
                if encargo is not None:
                    encargo.estado, encargo.motivo = "fallido", motivo
                    for espec in encargo.especificaciones:
                        if espec.estado == "en_curso":
                            espec.estado = "pendiente"
                    await self._guardar(encargo)
                    await self._bitacora.registrar(
                        encargo_id, self.name, "error", {"detalle": motivo}
                    )
            except Exception:  # noqa: BLE001
                log.exception("No se pudo registrar la falla del encargo %s", encargo_id)
            with contextlib.suppress(Exception):
                await self._emitir(encargo_id, self.name, "error", f"Error inesperado: {e}")

    async def _correr(self, encargo_id: str) -> None:
        encargo = await self.obtener(encargo_id)
        await self._emitir(encargo.id, self.name, "running", f"Encargo {encargo.id} en marcha")

        if encargo.estado == "especificando" and not await self._especificar(encargo):
            return

        encargo.estado = "en_curso"
        await self._guardar(encargo)
        # Por tandas: todo lo que tiene sus dependencias aprobadas corre a la
        # vez (hasta `paralelismo`); al terminar la tanda se destraba la siguiente.
        limite = asyncio.Semaphore(self.paralelismo)
        while listas := especificaciones_listas(encargo):
            tanda = []
            for espec in listas:
                if espec.requiere_aprobacion and not espec.aprobada_por_humano:
                    if espec.estado != "esperando_aprobacion":
                        await self._compuerta_humana(encargo, espec)
                else:
                    tanda.append(espec)
            if not tanda:
                # Solo quedan cosas esperando a una persona.
                await self._pausar(encargo)
                return
            if len(tanda) > 1:
                await self._emitir(
                    encargo.id,
                    self.name,
                    "running",
                    f"{len(tanda)} especificaciones en paralelo: " + ", ".join(e.id for e in tanda),
                )
                await self._bitacora.registrar(
                    encargo.id,
                    self.name,
                    "tanda_paralela",
                    {"especificaciones": [e.id for e in tanda], "limite": self.paralelismo},
                )

            async def con_limite(espec: Especificacion) -> bool:
                async with limite:
                    try:
                        return await self._ciclo(encargo, espec)
                    except EtapaVencida as vencida:
                        # Se cierra solo esta especificación; las demás siguen.
                        return await self._etapa_vencida(encargo, espec, vencida)

            resultados = await asyncio.gather(*(con_limite(e) for e in tanda))
            if not all(resultados) or encargo.preguntas_abiertas():
                await self._pausar(encargo)
                return

        final = estado_final(encargo) or "fallido"
        if final == "terminado":
            final = await self._desplegar(encargo)
        encargo.estado = final
        if final == "fallido" and not encargo.motivo:
            encargo.motivo = "Una o más especificaciones no se aprobaron"
        await self._guardar(encargo)
        await self._bitacora.registrar(
            encargo.id,
            self.name,
            f"encargo_{final}",
            {"costo_usd": round(encargo.costo_usd, 6), "motivo": encargo.motivo},
        )
        await self._emitir(
            encargo.id,
            self.name,
            "done" if final == "terminado" else "error",
            f"Encargo {final} · USD {encargo.costo_usd:.4f}",
        )
        await self._disparar(
            encargo.id, "encargo_terminado", estado=final, costo_usd=encargo.costo_usd
        )

    async def _especificar(self, encargo: Encargo) -> bool:
        """True si hay especificaciones listas; False si quedó esperando a una
        persona o falló.
        """
        agente = Especificador(await self._cerebro_para("especificador"), self._limite)
        tablas = await self._tablas_existentes()
        respondidas = [p for p in encargo.preguntas if p.origen == "especificador" and p.respuesta]
        await self._emitir(encargo.id, agente.name, "running", "Descomponiendo el pedido")
        medidor = Medidor()
        especs, preguntas, origen = await self._etapa(
            encargo,
            None,
            "especificacion",
            agente.name,
            1,
            medidor,
            agente.especificar(
                encargo.pedido,
                tablas=tablas,
                respondidas=respondidas,
                politica=self.politica,
                medidor=medidor,
                version_base=await self._contexto_version(encargo),
            ),
            lambda _: "ok",
        )
        # Una sola ronda de preguntas: si ya se respondió una, lo que venga
        # después se decide sin volver a frenar — evita un ida y vuelta infinito
        # con un LLM que reformula la misma duda.
        descartadas = len(preguntas) if respondidas else 0
        if not respondidas:
            encargo.preguntas.extend(preguntas)
        encargo.especificaciones = especs
        decisiones = aplicar_modo_aprobacion(encargo, self.politica.aprobacion_humana)
        await self._bitacora.registrar(
            encargo.id,
            agente.name,
            "especificaciones",
            {
                "origen": origen,
                "tablas_existentes": tablas,
                "especificaciones": [
                    {
                        "id": e.id,
                        "titulo": e.titulo,
                        "depende_de": e.depende_de,
                        "archivos": e.archivos,
                        "requiere_aprobacion": e.requiere_aprobacion,
                        "e2e": e.e2e,
                    }
                    for e in especs
                ],
                "preguntas": [p.texto for p in encargo.preguntas_abiertas()],
                "preguntas_descartadas": descartadas,
                "decisiones_automaticas": decisiones,
            },
        )

        if encargo.preguntas_abiertas():
            # El borrador se descarta: con la respuesta, se especifica de nuevo.
            encargo.especificaciones = []
            await self._emitir(
                encargo.id,
                agente.name,
                "pending",
                f"Pregunta para una persona: {encargo.preguntas_abiertas()[0].texto}",
            )
            await self._pausar(encargo)
            return False

        await self._emitir(
            encargo.id,
            agente.name,
            "done",
            f"{len(especs)} especificaciones ({origen}): "
            + ", ".join(f"{e.id}←{'+'.join(e.depende_de) or '∅'}" for e in especs),
        )
        await self._disparar(
            encargo.id, "especificaciones_listas", especificaciones=list(encargo.especificaciones)
        )
        return True

    async def _ciclo(self, encargo: Encargo, espec: Especificacion) -> bool:
        """Implementar → revisar → (diagnosticar) → verificar, con reintentos.
        False si el encargo quedó esperando a una persona.
        """
        espacio = self.espacio(encargo.id)
        implementador = Implementador(await self._cerebro_para("implementador"), self._limite)
        revisor = Revisor(
            await self._cerebro_para("revisor"),
            self._ejecutor,
            self._timeout_pruebas_s,
            self._limite,
        )
        verificador = Verificador(self._ejecutor_e2e, self._e2e_url_base, self._timeout_pruebas_s)
        motivo = ""
        motivos: list[str] = []
        # Resumen compacto de cada intento fallido, para el siguiente.
        historial: list[dict[str, object]] = []
        # Del último rechazo: el error real y el diagnóstico, para el reintento.
        detalle_rechazo: dict[str, object] | None = None
        propuesta = ""
        dependencias = await asyncio.to_thread(_codigo_de_dependencias, encargo, espec, espacio)
        # Lo que escribió el intento anterior: si el siguiente entrega lo mismo
        # y vuelve a fallar, el cerebro está dando vueltas en el mismo lugar.
        firma_previa = ""
        espec.estado = "en_curso"
        await self._guardar(encargo)

        while espec.intentos < self.politica.max_intentos:
            if espec.rondas >= self.politica.max_rondas:
                return await self._cerrar_atascada(
                    encargo,
                    espec,
                    f"alcanzó el tope de {self.politica.max_rondas} intentos en total",
                )

            if presupuesto_agotado(encargo, self.politica):
                espec.estado = "fallida"
                espec.motivo = (
                    f"Presupuesto del encargo agotado (USD {encargo.costo_usd:.4f} de "
                    f"{self.politica.presupuesto_encargo_usd:.2f})"
                )
                encargo.motivo = espec.motivo
                await self._emitir(encargo.id, self.name, "error", espec.motivo)
                return True

            espec.intentos += 1
            espec.rondas += 1
            intento = espec.intentos
            etiqueta = f"{espec.id} · intento {intento}/{self.politica.max_intentos}"
            if espec.estrategia == ESTRATEGIA_REESCRITURA:
                etiqueta += " (reescritura)"

            await self._emitir(
                encargo.id, implementador.name, "running", f"{etiqueta}: {espec.titulo}"
            )
            medidor = Medidor()
            impl = await self._etapa(
                encargo,
                espec.id,
                "implementacion",
                implementador.name,
                intento,
                medidor,
                implementador.implementar(
                    espec,
                    espacio,
                    self.politica,
                    motivo_rechazo=motivo,
                    medidor=medidor,
                    historial=historial,
                    detalle_rechazo=detalle_rechazo,
                    dependencias=dependencias,
                    estrategia=espec.estrategia,
                    inventario=[
                        str(a["ruta"])
                        for a in await asyncio.to_thread(_listar_archivos, espacio)
                        if str(a["ruta"]).startswith(("src/", "tests/", "frontend/", "e2e/"))
                    ],
                ),
                lambda r: "ok" if r.escritos else "vacio",
            )
            await self._bitacora.registrar(
                encargo.id,
                implementador.name,
                "archivos_escritos",
                {
                    "espec_id": espec.id,
                    "intento": intento,
                    "origen": impl.origen,
                    "archivos": impl.escritos,
                    "denegados": impl.denegados,
                    "contexto_compactado": medidor.compactado,
                },
            )
            await self._emitir(
                encargo.id,
                implementador.name,
                "done",
                f"{etiqueta}: {len(impl.escritos)} archivo(s) ({impl.origen})"
                + (f" · {len(impl.denegados)} fuera de la política" if impl.denegados else ""),
                [str(e["ruta"]) for e in impl.escritos],
            )

            if impl.cerebro_fallo:
                # Lo escrito es la plantilla de respaldo, no el trabajo del
                # cerebro: revisarla solo produciría un rechazo engañoso que el
                # Diagnosticador atribuiría a la especificación. Es el entorno.
                return await self._cerebro_sin_respuesta(encargo, espec, intento, etiqueta)

            # Solo con trabajo del cerebro: el guionado repite la plantilla a propósito.
            firma = firma_archivos(impl.escritos)
            sin_cambios = impl.origen == "cerebro" and firma == firma_previa
            firma_previa = firma

            await self._emitir(encargo.id, revisor.name, "running", f"{etiqueta}: revisando")
            medidor = Medidor()
            veredicto = await self._etapa(
                encargo,
                espec.id,
                "revision",
                revisor.name,
                intento,
                medidor,
                revisor.revisar(espec, espacio, impl.escritos, medidor=medidor),
                lambda v: "aprobado" if v.aprobado else "rechazo",
            )
            await self._bitacora.registrar(
                encargo.id,
                revisor.name,
                "revision",
                {
                    "espec_id": espec.id,
                    "intento": intento,
                    "aprobado": veredicto.aprobado,
                    "motivo": veredicto.motivo,
                    "evidencia": veredicto.evidencia,
                },
            )

            if not veredicto.aprobado:
                await self._emitir(
                    encargo.id, revisor.name, "error", f"{etiqueta}: {veredicto.motivo}"
                )
                atasco = self._registrar_huella(espec, veredicto.motivo)
                if atasco is None and sin_cambios:
                    atasco = (
                        "el reintento entregó exactamente los mismos archivos y volvió a fallar"
                    )
                # Efímero: existe solo para este rechazo.
                diagnosticador = Diagnosticador(
                    await self._cerebro_para("diagnosticador"), self._limite
                )
                medidor = Medidor()
                diagnostico = await self._etapa(
                    encargo,
                    espec.id,
                    "diagnostico",
                    diagnosticador.name,
                    intento,
                    medidor,
                    diagnosticador.diagnosticar(espec, veredicto, motivos, medidor=medidor),
                    lambda d: d.causa,
                )
                del diagnosticador
                await self._bitacora.registrar(
                    encargo.id,
                    "diagnosticador",
                    "diagnostico",
                    {
                        "espec_id": espec.id,
                        "intento": intento,
                        "causa": diagnostico.causa,
                        "explicacion": diagnostico.explicacion,
                    },
                )
                await self._emitir(
                    encargo.id,
                    "diagnosticador",
                    "done",
                    f"{etiqueta}: causa «{diagnostico.causa}» — {diagnostico.explicacion}",
                )
                motivos.append(veredicto.motivo)
                motivo = veredicto.motivo
                propuesta = diagnostico.explicacion
                detalle_rechazo = {
                    "motivo": veredicto.motivo,
                    "salida_pruebas": str(veredicto.evidencia.get("salida", ""))[-3000:],
                    "diagnostico": diagnostico.explicacion,
                }
                historial.append(
                    _resumen_intento(
                        intento, veredicto.motivo, diagnostico.causa, impl.escritos, propuesta
                    )
                )
                await self._disparar(
                    encargo.id,
                    "rechazo",
                    espec_id=espec.id,
                    intento=intento,
                    motivo=veredicto.motivo,
                    causa=diagnostico.causa,
                )

                if diagnostico.causa == "harness":
                    espec.estado = "bloqueada"
                    espec.motivo = (
                        f"Problema del entorno, no del código: {diagnostico.explicacion}. "
                        "Necesita que una persona revise el harness."
                    )
                    return True
                if atasco:
                    cierre = await self._atasco(encargo, espec, atasco, etiqueta)
                    if cierre is not None:
                        return cierre
                    # Estrategia nueva: los rechazos previos no deben hacer que
                    # el Diagnosticador culpe a la especificación al primer fallo.
                    motivos.clear()
                    continue
                if diagnostico.causa == "especificacion":
                    if self.politica.aprobacion_humana == "nunca":
                        espec.estado = "fallida"
                        espec.motivo = f"Especificación inviable: {diagnostico.explicacion}"
                        return True
                    return await self._preguntar_por_especificacion(
                        encargo,
                        espec,
                        intento,
                        veredicto.motivo,
                        diagnostico.explicacion,
                        propuesta=diagnostico.explicacion,
                    )
                continue

            await self._emitir(encargo.id, verificador.name, "running", f"{etiqueta}: verificando")
            verificacion = await self._etapa(
                encargo,
                espec.id,
                "verificacion",
                verificador.name,
                intento,
                Medidor(),
                verificador.verificar(espec, espacio),
                lambda v: "ok" if v.aprobado else "rechazo",
            )
            await self._bitacora.registrar(
                encargo.id,
                verificador.name,
                "verificacion",
                {
                    "espec_id": espec.id,
                    "intento": intento,
                    "aprobado": verificacion.aprobado,
                    "motivo": verificacion.motivo,
                    "evidencia": verificacion.evidencia,
                },
            )
            if not verificacion.aprobado:
                await self._emitir(
                    encargo.id, verificador.name, "error", f"{etiqueta}: {verificacion.motivo}"
                )
                motivo = f"Verificación: {verificacion.motivo}"
                motivos.append(motivo)
                detalle_rechazo = {"motivo": motivo, "evidencia": verificacion.evidencia}
                historial.append(_resumen_intento(intento, motivo, "verificacion", impl.escritos))
                await self._disparar(
                    encargo.id,
                    "rechazo",
                    espec_id=espec.id,
                    intento=intento,
                    motivo=motivo,
                    causa="verificacion",
                )
                if atasco := self._registrar_huella(espec, motivo):
                    cierre = await self._atasco(encargo, espec, atasco, etiqueta)
                    if cierre is not None:
                        return cierre
                continue

            # Compuerta de plugins: un veto es un rechazo más.
            veto = await self.plugins.evaluar(
                "antes_de_aprobar",
                encargo_id=encargo.id,
                espec_id=espec.id,
                espacio=espacio,
                archivos=list(espec.archivos),
            )
            if veto:
                await self._bitacora.registrar(
                    encargo.id,
                    "plugins",
                    "veto",
                    {"espec_id": espec.id, "intento": intento, "motivo": veto},
                )
                await self._emitir(encargo.id, self.name, "error", f"{etiqueta}: veto {veto}")
                motivo = f"Veto de un plugin: {veto}"
                motivos.append(motivo)
                detalle_rechazo = {"motivo": motivo}
                historial.append(_resumen_intento(intento, motivo, "plugin", impl.escritos))
                if atasco := self._registrar_huella(espec, motivo):
                    cierre = await self._atasco(encargo, espec, atasco, etiqueta)
                    if cierre is not None:
                        return cierre
                continue

            espec.estado, espec.motivo = "aprobada", ""
            await self._guardar(encargo)
            await self._emitir(
                encargo.id, verificador.name, "done", f"{espec.id} aprobada en {intento} intento(s)"
            )
            await self._disparar(
                encargo.id, "especificacion_aprobada", espec_id=espec.id, intentos=intento
            )
            return True

        agotado = f"Rechazada tras {espec.intentos} intento(s): {motivo}"
        if espec.rondas >= self.politica.max_rondas:
            # Ya no hay margen para otra ronda: preguntar solo dejaría el
            # encargo esperando una respuesta que no puede servir de nada.
            return await self._cerrar_atascada(
                encargo,
                espec,
                f"alcanzó el tope de {self.politica.max_rondas} intentos en total ({motivo})",
            )
        if self.politica.aprobacion_humana != "nunca":
            # No rendirse en silencio: una persona decide, con la propuesta a la vista.
            await self._emitir(encargo.id, self.name, "error", f"{espec.id}: {agotado}")
            return await self._preguntar_por_especificacion(
                encargo,
                espec,
                espec.intentos,
                agotado,
                motivo,
                causa="agotado",
                propuesta=propuesta,
            )
        espec.estado = "fallida"
        espec.motivo = agotado
        await self._emitir(encargo.id, self.name, "error", f"{espec.id}: {espec.motivo}")
        await self._disparar(
            encargo.id, "especificacion_fallida", espec_id=espec.id, motivo=espec.motivo
        )
        return True

    async def _contexto_version(self, encargo: Encargo) -> dict[str, object] | None:
        """Para una iteración: qué pidió la versión anterior, qué especificó y
        qué archivos hay ya en el espacio de trabajo.
        """
        if encargo.padre_id is None:
            return None
        padre = await self._repo.obtener(encargo.padre_id)
        return {
            "version_anterior": encargo.version - 1 if padre is None else padre.version,
            "pedido_anterior": padre.pedido if padre else None,
            "especificaciones_anteriores": [
                {"id": e.id, "titulo": e.titulo, "archivos": e.archivos}
                for e in (padre.especificaciones if padre else [])
            ],
            "archivos_existentes": [
                str(a["ruta"])
                for a in await asyncio.to_thread(_listar_archivos, self.espacio(encargo.id))
            ],
        }

    async def _pausar(self, encargo: Encargo) -> None:
        """Deja el encargo esperando a una persona. El evento "pending" del
        Líder cierra el "running" con que arrancó: sin él, el panel seguiría
        mostrando al Líder trabajando en un encargo que está en pausa.
        """
        encargo.estado = "esperando_humano"
        await self._guardar(encargo)
        await self._emitir(
            encargo.id, self.name, "pending", "En pausa: esperando una decisión humana"
        )

    @staticmethod
    def _registrar_huella(espec: Especificacion, motivo: str) -> str | None:
        """Suma el rechazo al historial de la especificación y devuelve por
        qué está atascada, o None si todavía avanza.
        """
        espec.huellas.append(huella_rechazo(motivo))
        return detectar_atasco(espec.huellas)

    async def _atasco(
        self, encargo: Encargo, espec: Especificacion, razon: str, etiqueta: str
    ) -> bool | None:
        """Primera vez: cambio de estrategia (reescribir desde cero) y al
        menos un intento más — devuelve None para que el ciclo siga. Si ya se
        reescribió y sigue atascada, la cierra como fallida y devuelve True.
        """
        await self._bitacora.registrar(
            encargo.id,
            self.name,
            "atasco",
            {
                "espec_id": espec.id,
                "razon": razon,
                "rondas": espec.rondas,
                "estrategia_previa": espec.estrategia or "normal",
            },
        )
        await self._disparar(encargo.id, "atasco", espec_id=espec.id, razon=razon)
        if espec.estrategia != ESTRATEGIA_REESCRITURA and espec.rondas < self.politica.max_rondas:
            espec.estrategia = ESTRATEGIA_REESCRITURA
            espec.intentos = min(espec.intentos, self.politica.max_intentos - 1)
            await self._guardar(encargo)
            await self._emitir(
                encargo.id,
                self.name,
                "running",
                f"{etiqueta}: atasco detectado ({razon}); cambio de estrategia: "
                "reescribir desde cero",
            )
            return None
        return await self._cerrar_atascada(encargo, espec, razon)

    async def _cerrar_atascada(self, encargo: Encargo, espec: Especificacion, razon: str) -> bool:
        espec.estado = "fallida"
        espec.motivo = (
            f"Atascada: {razon} ({espec.rondas} intento(s) en total). Se cerró para no "
            "seguir gastando; ajusta la especificación o reanuda el encargo para reintentarla."
        )
        encargo.motivo = encargo.motivo or espec.motivo
        await self._guardar(encargo)
        await self._bitacora.registrar(
            encargo.id,
            self.name,
            "especificacion_atascada",
            {"espec_id": espec.id, "razon": razon, "rondas": espec.rondas},
        )
        await self._emitir(encargo.id, self.name, "error", f"{espec.id}: {espec.motivo}")
        await self._disparar(
            encargo.id, "especificacion_fallida", espec_id=espec.id, motivo=espec.motivo
        )
        return True

    async def _etapa_vencida(
        self, encargo: Encargo, espec: Especificacion, error: EtapaVencida
    ) -> bool:
        espec.estado = "fallida"
        espec.motivo = (
            f"{error}: el cerebro o las pruebas quedaron colgados. Reanuda el encargo para "
            "reintentarla (si se repite, sube FABRICA_TIMEOUT_ETAPA_S o revisa el cerebro)."
        )
        await self._guardar(encargo)
        await self._bitacora.registrar(
            encargo.id,
            self.name,
            "etapa_vencida",
            {"espec_id": espec.id, "etapa": error.etapa, "segundos": error.segundos},
        )
        await self._emitir(encargo.id, self.name, "error", f"{espec.id}: {espec.motivo}")
        await self._disparar(
            encargo.id, "especificacion_fallida", espec_id=espec.id, motivo=espec.motivo
        )
        return True

    async def _compuerta_humana(self, encargo: Encargo, espec: Especificacion) -> None:
        espec.estado = "esperando_aprobacion"
        await self._guardar(encargo)
        await self._bitacora.registrar(
            encargo.id, self.name, "compuerta_humana", {"espec_id": espec.id}
        )
        await self._emitir(
            encargo.id,
            self.name,
            "pending",
            f"{espec.id} necesita aprobación humana: {espec.titulo}",
        )

    async def _cerebro_sin_respuesta(
        self, encargo: Encargo, espec: Especificacion, intento: int, etiqueta: str
    ) -> bool:
        explicacion = (
            "el cerebro no produjo esta implementación: no respondió a tiempo o devolvió algo "
            "que no se pudo leer, y quedó la plantilla de respaldo. Si usas claude-cli, sube "
            "CLAUDE_CLI_TIMEOUT_S en backend/.env y reinicia el backend antes de reintentar"
        )
        await self._metricas.registrar(
            MetricaEtapa(
                encargo_id=encargo.id,
                etapa="diagnostico",
                agente="diagnosticador",
                resultado="harness",
                duracion_s=0.0,
                espec_id=espec.id,
                intento=intento,
            )
        )
        await self._bitacora.registrar(
            encargo.id,
            "diagnosticador",
            "diagnostico",
            {
                "espec_id": espec.id,
                "intento": intento,
                "causa": "harness",
                "explicacion": explicacion,
                "regla": "cerebro sin respuesta: la implementación salió de la plantilla",
            },
        )
        await self._emitir(
            encargo.id, "diagnosticador", "error", f"{etiqueta}: causa «harness» — {explicacion}"
        )
        motivo = "El cerebro no respondió; se usó la plantilla de respaldo"
        if self.politica.aprobacion_humana == "nunca":
            espec.estado, espec.motivo = "fallida", motivo
            return True
        return await self._preguntar_por_especificacion(
            encargo, espec, intento, motivo, explicacion, causa="harness"
        )

    async def _preguntar_por_especificacion(
        self,
        encargo: Encargo,
        espec: Especificacion,
        intento: int,
        motivo: str,
        explicacion: str,
        causa: str = "especificacion",
        propuesta: str = "",
    ) -> bool:
        espec.estado, espec.motivo = "pendiente", motivo
        # Numerada por cuántas dudas lleva esta especificación, no por el
        # intento: "Reintentar" vuelve los intentos a cero y el id se repetiría.
        numero = 1 + sum(1 for p in encargo.preguntas if p.espec_id == espec.id)
        encargo.preguntas.append(
            Pregunta(
                id=f"D-{espec.id}-{numero}",
                texto=_texto_pregunta(espec, causa, explicacion, bool(propuesta)),
                opciones=(
                    [OPCION_REINTENTAR_PROPUESTA, OPCION_REINTENTAR, OPCION_DESCARTAR]
                    if propuesta
                    else [OPCION_REINTENTAR, OPCION_DESCARTAR]
                ),
                propuesta=propuesta or None,
                origen="diagnosticador",
                espec_id=espec.id,
            )
        )
        encargo.estado = "esperando_humano"
        await self._guardar(encargo)
        await self._emitir(
            encargo.id, "diagnosticador", "pending", f"{espec.id} necesita una decisión humana"
        )
        return False

    async def _desplegar(self, encargo: Encargo) -> Literal["terminado", "fallido"]:
        agente = DespliegueFabrica()
        espacio = self.espacio(encargo.id)
        desplegador = self._desplegador_para(espacio, encargo.id, f"Fábrica: {encargo.pedido[:60]}")
        lineas: list[str] = []

        async def on_linea(texto: str) -> None:
            lineas.append(texto)
            await self._emitir(encargo.id, agente.name, "running", texto)

        try:
            url = await self._etapa(
                encargo,
                None,
                "despliegue",
                agente.name,
                1,
                Medidor(),
                agente.desplegar(espacio, desplegador, on_linea),
                lambda u: "ok" if u else "simulado",
            )
        except DespliegueFallido as e:
            encargo.motivo = f"Despliegue fallido: {e}"
            await self._bitacora.registrar(
                encargo.id,
                agente.name,
                "despliegue",
                {"ok": False, "detalle": str(e), "lineas": lineas},
            )
            await self._emitir(encargo.id, agente.name, "error", encargo.motivo)
            return "fallido"
        encargo.url_despliegue = url
        await self._bitacora.registrar(
            encargo.id, agente.name, "despliegue", {"ok": True, "url": url, "lineas": lineas}
        )
        await self._emitir(
            encargo.id,
            agente.name,
            "done",
            f"Desplegado en {url}" if url else "Despliegue simulado",
        )
        return "terminado"

    # --- helpers ---

    async def _etapa(
        self,
        encargo: Encargo,
        espec_id: str | None,
        etapa: Etapa,
        agente: str,
        intento: int,
        medidor: Medidor,
        trabajo: Awaitable[T],
        resultado_de: Callable[[T], str],
    ) -> T:
        """Corre una etapa midiendo tiempo y consumo, y lo deja registrado
        incluso si la etapa explota. `medidor` es el mismo que recibió la
        corrutina `trabajo` — así el consumo que acumula queda en la métrica.
        """
        inicio = time.perf_counter()
        resultado_txt = "error"
        tope = self.politica.timeout_etapa_s
        try:
            try:
                valor = await asyncio.wait_for(
                    en_tarea(
                        self._usar_prefect,
                        etapa,
                        f"{espec_id or encargo.id}-{etapa}-{intento}",
                        lambda: trabajo,
                    ),
                    tope if tope > 0 else None,
                )
            except TimeoutError as e:
                resultado_txt = "vencida"
                raise EtapaVencida(etapa, tope) from e
            resultado_txt = resultado_de(valor)
            return valor
        finally:
            await self._metricas.registrar(
                MetricaEtapa(
                    encargo_id=encargo.id,
                    etapa=etapa,
                    agente=agente,
                    resultado=resultado_txt,
                    duracion_s=round(time.perf_counter() - inicio, 3),
                    espec_id=espec_id,
                    intento=intento,
                    modelo=medidor.modelo,
                    tokens_entrada=medidor.tokens_entrada,
                    tokens_salida=medidor.tokens_salida,
                    costo_usd=medidor.costo_usd,
                )
            )
            encargo.costo_usd += medidor.costo_usd or 0.0

    async def _disparar(self, encargo_id: str, evento: str, **datos: object) -> None:
        errores = await self.plugins.disparar(evento, encargo_id=encargo_id, **datos)
        if errores:
            await self._bitacora.registrar(
                encargo_id, "plugins", "plugin_error", {"evento": evento, "errores": errores}
            )

    async def _obtener_activo(self, encargo_id: str) -> Encargo:
        encargo = await self._obtener_detenido(encargo_id)
        if encargo.archivado_en is not None:
            raise AccionNoPermitida(
                "Ese encargo está archivado: reanúdalo o crea una nueva versión desde Ejecuciones"
            )
        return encargo

    async def _siguiente_version(self, linaje: str) -> int:
        versiones = [e.version for e in await self._repo.listar() if e.linaje == linaje]
        return max(versiones, default=0) + 1

    def _espacio_existente(self, encargo_id: str) -> Path:
        # El id llega de una URL: nada de "..", barras ni rutas absolutas.
        if not _ID_VALIDO.fullmatch(encargo_id):
            raise EncargoNoEncontrado(encargo_id)
        espacio = self.espacio(encargo_id)
        if not espacio.is_dir():
            raise EncargoNoEncontrado(encargo_id)
        return espacio

    async def _obtener_detenido(self, encargo_id: str) -> Encargo:
        if self.corriendo(encargo_id):
            raise AccionNoPermitida("El encargo está corriendo; esperá a que se detenga")
        return await self.obtener(encargo_id)

    async def _continuar_si_corresponde(self, encargo: Encargo) -> None:
        esperando = encargo.preguntas_abiertas() or any(
            e.estado == "esperando_aprobacion" for e in encargo.especificaciones
        )
        if not esperando:
            encargo.estado = "en_curso" if encargo.especificaciones else "especificando"
        await self._guardar(encargo)
        if not esperando:
            self._lanzar(encargo.id)

    async def _guardar(self, encargo: Encargo) -> None:
        encargo.actualizado_en = ahora_iso()
        await self._repo.guardar(encargo)

    async def _emitir(
        self,
        encargo_id: str,
        agente: str,
        status: Estado,
        msg: str,
        artifacts: list[str] | None = None,
    ) -> None:
        await self._bus.publicar(
            EventoAgente(
                agent=agente, status=status, msg=msg, run_id=encargo_id, artifacts=artifacts or []
            )
        )


def _resumen_intento(
    intento: int,
    motivo: str,
    causa: str,
    escritos: list[dict[str, object]],
    diagnostico: str = "",
) -> dict[str, object]:
    return {
        "intento": intento,
        "causa": causa,
        "motivo": motivo[:500],
        "diagnostico": diagnostico[:800],
        "archivos": [str(e["ruta"]) for e in escritos],
    }


def _texto_pregunta(
    espec: Especificacion, causa: str, explicacion: str, hay_propuesta: bool
) -> str:
    nombre = f"{espec.id} («{espec.titulo}»)"
    if causa == "harness":
        return f"{nombre} no se pudo construir: {explicacion}. ¿Cómo sigo?"
    cierre = (
        " Puedes reintentar aplicando la propuesta del Diagnosticador (abajo), reintentar tal "
        "cual, descartarla o escribir tu propia aclaración."
        if hay_propuesta
        else " Puedes escribir una aclaración en vez de elegir una opción."
    )
    if causa == "agotado":
        return f"{nombre} no pasó la revisión: {explicacion}.{cierre}"
    return (
        f"{nombre} no pasa la revisión y el Diagnosticador cree que el problema es la "
        f"especificación: {explicacion}.{cierre}"
    )


def _codigo_de_dependencias(
    encargo: Encargo, espec: Especificacion, espacio: Path
) -> dict[str, str]:
    """El código fuente (src/) de todas las especificaciones de las que esta
    depende, directa o indirectamente. armar_contexto lo compacta si es largo.
    """
    por_id = {e.id: e for e in encargo.especificaciones}
    pendientes, vistas = list(espec.depende_de), set()
    while pendientes:
        actual = pendientes.pop()
        if actual in vistas or actual not in por_id:
            continue
        vistas.add(actual)
        pendientes.extend(por_id[actual].depende_de)
    codigo: dict[str, str] = {}
    for dep in sorted(vistas):
        for ruta in por_id[dep].archivos:
            if ruta.startswith("src/") and ruta not in codigo and archivo_seguro(espacio, ruta):
                codigo[ruta] = (espacio / ruta).read_text(encoding="utf-8", errors="replace")
    return codigo


# --- espacios de trabajo en disco ---

_ID_VALIDO = re.compile(r"[A-Za-z0-9_-]{1,64}")
_IGNORAR = {"__pycache__", ".pytest_cache", "node_modules", ".git"}
_MAX_LECTURA = 256 * 1024


def _listar_archivos(espacio: Path) -> list[dict[str, object]]:
    if not espacio.is_dir():
        return []
    archivos: list[dict[str, object]] = []
    for ruta in sorted(espacio.rglob("*")):
        relativa = ruta.relative_to(espacio)
        if ruta.is_file() and not _IGNORAR.intersection(relativa.parts):
            archivos.append({"ruta": relativa.as_posix(), "bytes": ruta.stat().st_size})
    return archivos


def _carpetas(raiz: Path) -> dict[str, tuple[int, int, str | None]]:
    """{id: (archivos, bytes, última modificación ISO)} de cada espacio."""
    from datetime import UTC, datetime

    resultado: dict[str, tuple[int, int, str | None]] = {}
    if not raiz.is_dir():
        return resultado
    for carpeta in raiz.iterdir():
        if not carpeta.is_dir() or not _ID_VALIDO.fullmatch(carpeta.name):
            continue
        archivos = _listar_archivos(carpeta)
        ultima = (
            max((carpeta / str(a["ruta"])).stat().st_mtime for a in archivos) if archivos else None
        )
        resultado[carpeta.name] = (
            len(archivos),
            sum(int(str(a["bytes"])) for a in archivos),
            datetime.fromtimestamp(ultima, UTC).isoformat() if ultima else None,
        )
    return resultado


def _copiar_espacio(origen: Path, destino: Path) -> list[dict[str, object]]:
    """Copia los archivos de una versión a la siguiente y devuelve qué se
    heredó, con el hash de cada archivo, para la bitácora.
    """
    if not origen.is_dir():
        return []

    def ignorar(carpeta: str, nombres: list[str]) -> set[str]:
        # Los enlaces simbólicos no se heredan: copytree copiaría el archivo
        # al que apuntan (p. ej. un .env fuera del espacio) como si fuera propio.
        return {n for n in nombres if n in _IGNORAR or (Path(carpeta) / n).is_symlink()}

    shutil.copytree(origen, destino, ignore=ignorar, dirs_exist_ok=True)
    return [
        {
            "ruta": a["ruta"],
            "sha256": sha256_texto(
                (destino / str(a["ruta"])).read_text(encoding="utf-8", errors="replace")
            ),
        }
        for a in _listar_archivos(destino)
    ]
