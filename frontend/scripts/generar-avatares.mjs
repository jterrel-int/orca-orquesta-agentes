// Genera los avatares de los agentes en public/agentes/<agente>.svg.
//
//   npm run avatares
//
// Se hace al compilar y no en el navegador: DiceBear + el estilo Notionists
// pesan ~120 kB, y las siete caras nunca cambian. Si tocas una opción de
// acá, corre de nuevo el script (lib/avatares.test.ts falla si te olvidas).
//
// Estilo "Notionists" de Zoish, licencia CC0 1.0 (uso libre, sin
// atribución obligatoria): https://www.dicebear.com/styles/notionists/
import { createAvatar } from "@dicebear/core";
import * as notionists from "@dicebear/notionists";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// Fondo: un tinte claro del color de cada agente (ver --agente-* en globals.css).
export const OPCIONES_AVATAR = {
  lider: { seed: "lider-c", backgroundColor: ["fbe3ec"], gesture: ["pointLongArm"], glassesProbability: 0, beardProbability: 0 },
  especificador: { seed: "especificador-b", backgroundColor: ["d9efd9"], gesture: ["hand"], glasses: ["variant11"], glassesProbability: 100, beardProbability: 0 },
  implementador: { seed: "implementador-c", backgroundColor: ["dbe8f8"], gesture: ["handPhone"], glassesProbability: 0, beardProbability: 100 },
  revisor: { seed: "revisor-c", backgroundColor: ["fde4d8"], gesture: ["point"], glasses: ["variant08"], glassesProbability: 100, beardProbability: 0 },
  diagnosticador: { seed: "diagnosticador-d", backgroundColor: ["fcefcf"], gesture: ["ok"], glasses: ["variant03"], glassesProbability: 100, beardProbability: 100 },
  verificador: { seed: "verificador-b", backgroundColor: ["d6f2e7"], gesture: ["okLongArm"], glassesProbability: 0, beardProbability: 0 },
  despliegue: { seed: "despliegue-c", backgroundColor: ["e3e0f5"], gesture: ["waveLongArm"], bodyIcon: ["electric"], bodyIconProbability: 100, glassesProbability: 0, beardProbability: 0 },
};

export function svgDe(agente) {
  return createAvatar(notionists, { gestureProbability: 100, ...OPCIONES_AVATAR[agente] }).toString();
}

export const DESTINO = join(dirname(fileURLToPath(import.meta.url)), "..", "public", "agentes");

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  mkdirSync(DESTINO, { recursive: true });
  for (const agente of Object.keys(OPCIONES_AVATAR)) {
    writeFileSync(join(DESTINO, `${agente}.svg`), svgDe(agente));
    console.log(`public/agentes/${agente}.svg`);
  }
}
