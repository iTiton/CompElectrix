import { ChevronLeft, ChevronRight, RefreshCw, Zap } from "lucide-react";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type DiaPvpc, type EstadoPvpc } from "../api";
import { Aviso, Cabecera, num, useDatos, Vacio } from "../components/ui";
import { COLOR_PERIODO, NOMBRE_PERIODO } from "../periodos";
import { EVENTO_PVPC } from "../components/AvisoActualizacion";

const EJE = { fill: "#71717a", fontSize: 12 };

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const sumar = (s: string, n: number) => {
  const d = new Date(s + "T12:00:00");
  d.setDate(d.getDate() + n);
  return iso(d);
};
const cent = (eurKwh: number | undefined | null) => (eurKwh == null ? "—" : `${num(eurKwh * 100, 2)} c€/kWh`);

export default function Precios() {
  const hoy = iso(new Date());
  const [dia, setDia] = useState(hoy);
  const { datos, error } = useDatos<DiaPvpc>(`/pvpc/dia?dia=${dia}`, [], [EVENTO_PVPC]);
  const estado = useDatos<EstadoPvpc>("/pvpc/estado", [], [EVENTO_PVPC]);
  const [lanzado, setLanzado] = useState(false);

  const actualizar = async () => {
    await api.post("/pvpc/sincronizar", {});
    setLanzado(true);
    setTimeout(() => estado.recargar(), 1500);
  };

  const ahora = new Date().getHours();
  const titulo = dia === hoy ? "Hoy" : dia === sumar(hoy, 1) ? "Mañana" : dia === sumar(hoy, -1) ? "Ayer" : new Date(dia + "T12:00").toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long" });

  return (
    <>
      <Cabecera titulo="Precio PVPC" sub="Precio horario oficial de la tarifa regulada (2.0TD), publicado por Red Eléctrica. Incluye peajes y cargos, sin impuestos.">
        <button className="btn-secundario" onClick={actualizar} disabled={estado.datos?.en_curso}>
          <RefreshCw size={16} className={estado.datos?.en_curso ? "animate-spin" : ""} /> Actualizar
        </button>
      </Cabecera>
      {lanzado && <div className="mb-4"><Aviso tipo="ok">Actualización en marcha. Puede tardar unos segundos por cada mes que falte.</Aviso></div>}
      {error && <Aviso tipo="error">{error}</Aviso>}

      <div className="mb-4 flex items-center gap-2">
        <button className="btn-secundario p-2" onClick={() => setDia(sumar(dia, -1))} aria-label="Día anterior"><ChevronLeft size={18} /></button>
        <input className="entrada w-auto" type="date" value={dia} onChange={(e) => e.target.value && setDia(e.target.value)} />
        <button className="btn-secundario p-2" onClick={() => setDia(sumar(dia, 1))} aria-label="Día siguiente"><ChevronRight size={18} /></button>
        {dia !== hoy && <button className="btn text-sm text-acento-600" onClick={() => setDia(hoy)}>Hoy</button>}
        <span className="ml-2 text-lg font-semibold capitalize">{titulo}</span>
      </div>

      {datos && datos.horas.length === 0 ? (
        <Vacio icono={<Zap />} titulo="Sin precios para este día">
          {dia > hoy
            ? "Los precios de mañana se publican cada día hacia las 20:30."
            : "Pulsa «Actualizar» para descargarlos. La aplicación también completa los que falten cada vez que la abres."}
        </Vacio>
      ) : datos ? (
        <>
          <div className="mb-6 grid gap-4 sm:grid-cols-3">
            <Kpi t="Hora más barata" v={cent(datos.minimo?.precio)} s={datos.minimo ? `${datos.minimo.hora} h` : ""} color="text-emerald-600 dark:text-emerald-400" />
            <Kpi t="Precio medio" v={cent(datos.media)} s={`${datos.horas.length} horas`} />
            <Kpi t="Hora más cara" v={cent(datos.maximo?.precio)} s={datos.maximo ? `${datos.maximo.hora} h` : ""} color="text-red-600 dark:text-red-400" />
          </div>
          <div className="tarjeta">
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={datos.horas} margin={{ right: 8 }}>
                <CartesianGrid vertical={false} strokeOpacity={0.15} />
                <XAxis dataKey="hora" tick={EJE} interval={1} tickFormatter={(h: string) => h.slice(0, 2)} />
                <YAxis tick={EJE} width={48} tickFormatter={(v: number) => num(v * 100, 0)} label={{ value: "c€/kWh", angle: -90, position: "insideLeft", fill: "#71717a", fontSize: 12 }} />
                <Tooltip
                  formatter={(v: number) => [cent(v), "Precio"]}
                  labelFormatter={(h: string, p) => {
                    // Al salir del gráfico la etiqueta puede llegar sin barra asociada
                    const periodo = (p?.[0]?.payload as { periodo?: keyof typeof NOMBRE_PERIODO } | undefined)?.periodo;
                    return periodo ? `${h} h · ${NOMBRE_PERIODO[periodo]}` : `${h} h`;
                  }}
                  contentStyle={{ borderRadius: 12 }}
                />
                <Bar dataKey="precio" radius={[4, 4, 0, 0]}>
                  {datos.horas.map((h) => (
                    <Cell key={h.hora + h.precio} fill={COLOR_PERIODO[h.periodo]} fillOpacity={dia === hoy && Number(h.hora.slice(0, 2)) === ahora ? 1 : 0.75} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <div className="mt-3 flex flex-wrap gap-4 text-xs text-zinc-500">
              {(["p1", "p2", "p3"] as const).map((p) => (
                <span key={p} className="flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: COLOR_PERIODO[p] }} /> {NOMBRE_PERIODO[p]} ({p.toUpperCase()})</span>
              ))}
            </div>
          </div>
        </>
      ) : null}

      {estado.datos && (
        <p className="mt-4 text-xs text-zinc-500">
          {estado.datos.horas
            ? `Histórico guardado: ${estado.datos.desde} → ${estado.datos.hasta} (${num(estado.datos.horas)} horas).`
            : "Aún no hay precios guardados."}
          {estado.datos.ultima_sync && ` Última actualización: ${new Date(estado.datos.ultima_sync).toLocaleString("es-ES")}.`}
          {estado.datos.en_curso && ` Actualizando… ${estado.datos.progreso ?? ""}`}
          {estado.datos.ultimo_error && <span className="block text-amber-600">Último error: {estado.datos.ultimo_error}</span>}
        </p>
      )}
    </>
  );
}

function Kpi({ t, v, s, color = "" }: { t: string; v: string; s: string; color?: string }) {
  return (
    <div className="tarjeta">
      <p className="text-xs text-zinc-500">{t}</p>
      <p className={`mt-1 text-xl font-semibold tabular-nums ${color}`}>{v}</p>
      <p className="text-xs text-zinc-500">{s}</p>
    </div>
  );
}
