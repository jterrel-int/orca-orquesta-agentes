import type { Metadata } from "next";
import Sidebar from "@/components/Sidebar";
import ToastUsoAnthropic from "@/components/ToastUsoAnthropic";
import "./globals.css";

export const metadata: Metadata = {
  title: "Orquesta — fábrica de software",
  description:
    "Fábrica de software agéntica: del pedido a la especificación, el código probado y el despliegue.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <head>
        {/*
          Se usa <link> en vez de next/font/google a propósito: next/font
          descarga las fuentes durante el build y hace fallar la compilación si
          no hay red. Con <link>, sin conexión la página cae al stack del
          sistema y sigue funcionando.
        */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600&family=JetBrains+Mono:wght@400;600&family=Source+Serif+4:wght@400;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <div className="app-shell">
          <Sidebar />
          <div className="app-main">{children}</div>
        </div>
        <ToastUsoAnthropic />
      </body>
    </html>
  );
}
