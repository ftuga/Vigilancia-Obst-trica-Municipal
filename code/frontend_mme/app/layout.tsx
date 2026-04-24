import type { Metadata } from "next";
import type { ReactNode } from "react";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Vigilancia Obstétrica Municipal",
  description:
    "Sistema de predicción de vulnerabilidad obstétrica municipal en Colombia.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="es">
      <body className="min-h-screen antialiased">
        <header className="border-b bg-background">
          <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4">
            <Link
              href="/"
              className="text-sm font-semibold tracking-tight"
            >
              Vigilancia Obstétrica Municipal
            </Link>
            <nav className="flex items-center gap-5 text-sm">
              <Link href="/mme" className="text-muted-foreground hover:text-foreground">
                Mapa
              </Link>
              <Link
                href="/mme/explorar"
                className="text-muted-foreground hover:text-foreground"
              >
                Explorar
              </Link>
              <Link href="/health" className="text-muted-foreground hover:text-foreground">
                Salud
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-8">{children}</main>
        <footer className="border-t py-6 text-center text-xs text-muted-foreground">
          Datos: SIVIGILA · INS · DANE · MinSalud Colombia · Modelo C3 LightGBM Poisson
        </footer>
      </body>
    </html>
  );
}
