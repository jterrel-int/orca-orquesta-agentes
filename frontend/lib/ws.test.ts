import { describe, expect, it } from "vitest";
import { urlWebSocket } from "./ws";

describe("urlWebSocket", () => {
  it("convierte http a ws en local", () => {
    expect(urlWebSocket("http://localhost:8000")).toBe("ws://localhost:8000/ws");
  });

  it("convierte https a wss cuando el backend está en un hosting público (Render)", () => {
    expect(urlWebSocket("https://orquesta-backend.onrender.com")).toBe(
      "wss://orquesta-backend.onrender.com/ws"
    );
  });
});

describe("urlWebSocket con token", () => {
  it("agrega el token como parámetro cuando el backend lo exige", () => {
    expect(urlWebSocket("http://localhost:8000", "a b")).toBe("ws://localhost:8000/ws?token=a%20b");
  });
});
