import FormularioLeads from "./FormularioLeads";

export default function PaginaLeadsZapatillas() {
  return (
    <>
      <header className="cabecera">
        <h1>Leads de zapatillas</h1>
        <span className="sub">formulario público de captación</span>
      </header>

      <main className="contenido">
        <p className="apagado" style={{ maxWidth: "52ch" }}>
          Demo pública sin autenticación. Tras una corrida de agentes, este
          componente lo sirve el <code>FrontendAgent</code>.
        </p>
        <FormularioLeads />
      </main>
    </>
  );
}
