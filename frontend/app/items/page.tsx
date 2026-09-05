import ListaItems from "./ListaItems";

export default function PaginaItems() {
  return (
    <>
      <header className="cabecera">
        <h1>Items</h1>
        <span className="sub">CRUD servido por el backend</span>
      </header>

      <main className="contenido">
        <p className="apagado" style={{ maxWidth: "52ch" }}>
          Esta lista consume los endpoints de FastAPI. Tras una corrida de
          agentes, los sirve el router que generó el <code>BackendAgent</code>.
        </p>
        <ListaItems />
      </main>
    </>
  );
}
