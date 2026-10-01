// Los avatares de public/agentes/ se generan al compilar (npm run avatares).
// Si alguien cambia una opción en scripts/generar-avatares.mjs y no los
// regenera, esta prueba lo dice.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { DESTINO, OPCIONES_AVATAR, svgDe } from "../scripts/generar-avatares.mjs";

describe("avatares de los agentes", () => {
  for (const agente of Object.keys(OPCIONES_AVATAR)) {
    it(`public/agentes/${agente}.svg está al día`, () => {
      expect(readFileSync(join(DESTINO, `${agente}.svg`), "utf8")).toBe(svgDe(agente));
    });
  }

  it("hay un avatar por cada uno de los siete agentes", () => {
    expect(Object.keys(OPCIONES_AVATAR).sort()).toEqual(
      ["despliegue", "diagnosticador", "especificador", "implementador", "lider", "revisor", "verificador"],
    );
  });
});
