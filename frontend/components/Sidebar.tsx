"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ENLACES = [
  { href: "/", etiqueta: "Panel" },
  { href: "/items", etiqueta: "Items" },
  { href: "/backlog", etiqueta: "Backlog" },
  { href: "/configuracion", etiqueta: "Configuración" },
] as const;

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sidebar">
      <div className="marca">
        <img src="/logo-inteligenze.webp" alt="inteligenze" className="marca-logo" />
        <strong>Orquesta</strong>
        <span className="sub">panel de agentes</span>
      </div>
      <nav className="nav-lateral" aria-label="Secciones">
        {ENLACES.map((enlace) => (
          <Link
            key={enlace.href}
            href={enlace.href}
            className={pathname === enlace.href ? "activo" : ""}
          >
            {enlace.etiqueta}
          </Link>
        ))}
      </nav>
    </aside>
  );
}
