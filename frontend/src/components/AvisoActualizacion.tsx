import { CheckCircle2, RefreshCw, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type EstadoPvpc } from "../api";

/** Evento que avisa a las páginas de que hay precios nuevos. */
export const EVENTO_PVPC = "pvpc-actualizado";

type Fase = { tipo: "oculto" } | { tipo: "actualizando"; dias: number | null; progreso: string | null } | { tipo: "hecho" | "error"; texto: string };

/**
 * Al abrir la aplicación pide al servidor que complete los precios del PVPC que falten
 * desde el último uso. No bloquea: muestra el progreso en una franja superior.
 */
export default function AvisoActualizacion() {
  const [fase, setFase] = useState<Fase>({ tipo: "oculto" });

  useEffect(() => {
    let vivo = true;
    let temporizador: number | undefined;

    const vigilar = async () => {
      try {
        const e = await api.get<EstadoPvpc>("/pvpc/estado");
        if (!vivo) return;
        if (e.en_curso) {
          setFase((f) => ({ tipo: "actualizando", dias: f.tipo === "actualizando" ? f.dias : null, progreso: e.progreso }));
          temporizador = window.setTimeout(vigilar, 2000);
        } else if (e.ultimo_error) {
          setFase({ tipo: "error", texto: "No se han podido actualizar los precios del PVPC. Se reintentará la próxima vez." });
        } else {
          setFase({ tipo: "hecho", texto: "Precios del PVPC al día." });
          window.dispatchEvent(new Event(EVENTO_PVPC));
          temporizador = window.setTimeout(() => vivo && setFase({ tipo: "oculto" }), 3000);
        }
      } catch {
        /* sin conexión con el servidor: no molestar */
      }
    };

    api
      .post<{ actualizando: boolean; dias: number | null }>("/pvpc/al-entrar", {})
      .then((r) => {
        if (!vivo || !r.actualizando) return;
        setFase({ tipo: "actualizando", dias: r.dias, progreso: null });
        vigilar();
      })
      .catch(() => {});

    return () => {
      vivo = false;
      window.clearTimeout(temporizador);
    };
  }, []);

  if (fase.tipo === "oculto") return null;
  const estilos = {
    actualizando: "bg-acento-600 text-white",
    hecho: "bg-emerald-600 text-white",
    error: "bg-amber-500 text-amber-950",
  }[fase.tipo];

  return (
    <div role="status" className={`fixed bottom-4 left-1/2 z-50 flex w-max max-w-[calc(100vw-2rem)] -translate-x-1/2 items-center gap-2 rounded-full px-4 py-2 text-sm shadow-lg ${estilos}`}>
      {fase.tipo === "actualizando" && (
        <>
          <RefreshCw size={14} className="animate-spin" />
          Actualizando precios del PVPC{fase.dias ? ` (${fase.dias} día${fase.dias === 1 ? "" : "s"})` : ""}
          {fase.progreso && ` · ${fase.progreso}`}…<span className="hidden sm:inline"> Puedes seguir usando la aplicación.</span>
        </>
      )}
      {fase.tipo === "hecho" && (<><CheckCircle2 size={14} /> {fase.texto}</>)}
      {fase.tipo === "error" && (<><TriangleAlert size={14} /> {fase.texto}</>)}
    </div>
  );
}
