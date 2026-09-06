import Calculadora from "./Calculadora";

export default function PaginaCalculadora() {
  return (
    <>
      <header className="cabecera">
        <h1>Calculadora</h1>
        <span className="sub">login, historial por usuario y operaciones básicas</span>
      </header>

      <main className="contenido">
        <p className="apagado" style={{ maxWidth: "52ch" }}>
          Registrate o iniciá sesión para guardar tu historial de operaciones.
          Tras una corrida de agentes, este componente lo sirve el{" "}
          <code>FrontendAgent</code>.
        </p>
        <Calculadora />
      </main>
    </>
  );
}
