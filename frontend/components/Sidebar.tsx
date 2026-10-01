"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ENLACES = [
  { href: "/fabrica", etiqueta: "Fábrica" },
  { href: "/fabrica/ejecuciones", etiqueta: "Ejecuciones" },
  { href: "/fabrica/salud", etiqueta: "Salud" },
  { href: "/configuracion", etiqueta: "Configuración" },
] as const;

/** "Fábrica" queda marcada también dentro de un encargo (/fabrica/<id>). */
function activo(pathname: string, href: string): boolean {
  if (href === "/fabrica") {
    const otras = ["/fabrica/salud", "/fabrica/ejecuciones"];
    return pathname === "/fabrica" || (pathname.startsWith("/fabrica/") && !otras.includes(pathname));
  }
  return pathname === href;
}

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sidebar">
      <div className="marca">
        <img src="/logo-inteligenze.webp" alt="inteligenze" className="marca-logo" />
        <strong>Orquesta</strong>
        <span className="sub">fábrica de software</span>
      </div>
      <nav className="nav-lateral" aria-label="Secciones">
        {ENLACES.map((enlace) => (
          <Link
            key={enlace.href}
            href={enlace.href}
            className={activo(pathname, enlace.href) ? "activo" : ""}
          >
            {enlace.etiqueta}
          </Link>
        ))}
      </nav>
    </aside>
  );
}
