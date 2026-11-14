import { X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { urlApi } from "../api";

export const eur = (v: number | null | undefined, dec = 2) =>
  v == null ? "—" : v.toLocaleString("es-ES", { style: "currency", currency: "EUR", minimumFractionDigits: dec, maximumFractionDigits: dec });

export const num = (v: number | null | undefined, dec = 0) =>
  v == null ? "—" : v.toLocaleString("es-ES", { minimumFractionDigits: dec, maximumFractionDigits: dec });

export const fecha = (iso: string | null | undefined) =>
  iso ? new Date(iso + "T00:00:00").toLocaleDateString("es-ES", { day: "2-digit", month: "short", year: "numeric" }) : "—";

export const mes = (iso: string) =>
  new Date(iso + "T00:00:00").toLocaleDateString("es-ES", { month: "short", year: "2-digit" });

export function Cabecera({ titulo, sub, children }: { titulo: string; sub?: string; children?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{titulo}</h1>
        {sub && <p className="mt-1 text-sm text-zinc-500">{sub}</p>}
      </div>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  );
}

export function Modal({ titulo, abierto, cerrar, children, ancho = "max-w-2xl" }: {
  titulo: string; abierto: boolean; cerrar: () => void; children: ReactNode; ancho?: string;
}) {
  useEffect(() => {
    if (!abierto) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && cerrar();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [abierto, cerrar]);
  if (!abierto) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 backdrop-blur-sm" onMouseDown={cerrar}>
      <div className={`tarjeta my-8 w-full ${ancho}`} onMouseDown={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">{titulo}</h2>
          <button className="btn p-1" onClick={cerrar} aria-label="Cerrar"><X size={18} /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Campo({ etiqueta, ayuda, children, className = "" }: { etiqueta: string; ayuda?: string; children: ReactNode; className?: string }) {
  return (
    <label className={`block ${className}`}>
      <span className="etiqueta">{etiqueta}</span>
      {children}
      {ayuda && <span className="mt-1 block text-xs text-zinc-500">{ayuda}</span>}
    </label>
  );
}

export function Aviso({ tipo = "info", children }: { tipo?: "info" | "error" | "ok"; children: ReactNode }) {
  const c = {
    info: "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200",
    error: "border-red-300 bg-red-50 text-red-900 dark:border-red-800 dark:bg-red-950/40 dark:text-red-200",
    ok: "border-acento-400 bg-acento-50 text-acento-700 dark:border-acento-700 dark:bg-acento-700/20 dark:text-acento-100",
  }[tipo];
  return <div className={`rounded-xl border px-4 py-3 text-sm ${c}`}>{children}</div>;
}

export function Vacio({ icono, titulo, children }: { icono: ReactNode; titulo: string; children?: ReactNode }) {
  return (
    <div className="tarjeta flex flex-col items-center gap-3 py-12 text-center">
      <div className="rounded-2xl bg-acento-50 p-3 text-acento-600 dark:bg-acento-700/20 dark:text-acento-400">{icono}</div>
      <h3 className="font-semibold">{titulo}</h3>
      <div className="max-w-md text-sm text-zinc-500">{children}</div>
    </div>
  );
}

/** Carga datos de la API con estado de carga y error. Con `eventos`, se recarga cuando ocurren. */
export function useDatos<T>(ruta: string | null, deps: unknown[] = [], eventos: string[] = []) {
  const [datos, setDatos] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [n, setN] = useState(0);
  useEffect(() => {
    const r = () => setN((x) => x + 1);
    eventos.forEach((e) => window.addEventListener(e, r));
    return () => eventos.forEach((e) => window.removeEventListener(e, r));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventos.join()]);
  useEffect(() => {
    if (!ruta) return;
    let vivo = true;
    fetch(urlApi(ruta))
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`Error ${r.status}`))))
      .then((d) => vivo && (setDatos(d), setError(null)))
      .catch((e) => vivo && setError(e.message));
    return () => {
      vivo = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ruta, n, ...deps]);
  return { datos, error, recargar: () => setN((x) => x + 1) };
}
