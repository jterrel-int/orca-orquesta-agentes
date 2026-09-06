import Encuesta from "./Encuesta";

export default function PaginaEncuesta() {
  return (
    <>
      <header className="cabecera">
        <h1>Encuesta de satisfacción</h1>
        <span className="sub">puntaje de 1 a 5 con resultados agregados en vivo</span>
      </header>

      <main className="contenido">
        <p className="apagado" style={{ maxWidth: "52ch" }}>
          Dejá tu puntaje y un comentario opcional. Tras una corrida de
          agentes, este componente lo sirve el <code>FrontendAgent</code>.
        </p>
        <Encuesta />
      </main>
    </>
  );
}
