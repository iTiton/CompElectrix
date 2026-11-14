import { BarChart3, Play, Trophy } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api, type Comparativa, type Desglose, type Domicilio, type ResultadoTarifa } from "../api";
import { Aviso, Cabecera, Campo, eur, fecha, mes, num, useDatos, Vacio } from "../components/ui";

const COLORES = ["#0d9488", "#6366f1", "#f59e0b", "#ec4899", "#0ea5e9"];
const GRIS = "#a1a1aa";
const EJE = { fill: "#71717a", fontSize: 12 };

const CONCEPTOS: [keyof Desglose, string][] = [
  ["potencia_p1", "Potencia P1"],
  ["potencia_p2", "Potencia P2"],
  ["energia_p1", "Energía P1"],
  ["energia_p2", "Energía P2"],
  ["energia_p3", "Energía P3"],
  ["descuento_energia", "Descuento energía"],
  ["cuota_fija", "Cuota fija / servicios"],
  ["bono_social", "Financiación bono social"],
  ["iee", "Impuesto eléctrico"],
  ["alquiler_contador", "Alquiler contador"],
  ["iva", "IVA"],
  ["total", "Total"],
];

export default function ComparativaPage() {
  const [params, setParams] = useSearchParams();
  const { datos: domicilios } = useDatos<Domicilio[]>("/domicilios");
  const [domId, setDomId] = useState(params.get("domicilio") ?? "");
  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");
  const [res, setRes] = useState<Comparativa | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);
  const [detalle, setDetalle] = useState<number | null>(null);

  useEffect(() => {
    if (!domId && domicilios?.length) setDomId(String(domicilios[0].id));
  }, [domicilios, domId]);

  const ejecutar = async () => {
    if (!domId) return;
    setCargando(true);
    setError(null);
    setParams({ domicilio: domId });
    try {
      const r = await api.post<Comparativa>("/comparativa", {
        domicilio_id: Number(domId), desde: desde || null, hasta: hasta || null,
      });
      setRes(r);
      setDetalle(r.tarifas[0]?.tarifa_id ?? null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setCargando(false);
    }
  };

  // Lanzar automáticamente al llegar con ?domicilio=
  useEffect(() => {
    if (params.get("domicilio") && domId && !res) ejecutar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [domId]);

  return (
    <>
      <Cabecera titulo="Comparativa" sub="Simula tus facturas reales con cada tarifa del catálogo, con todos los conceptos e impuestos." />
      <div className="tarjeta mb-6 grid items-end gap-4 sm:grid-cols-4">
        <Campo etiqueta="Domicilio">
          <select className="entrada" value={domId} onChange={(e) => (setDomId(e.target.value), setRes(null))}>
            {domicilios?.map((d) => <option key={d.id} value={d.id}>{d.nombre}</option>)}
          </select>
        </Campo>
        <Campo etiqueta="Desde (opcional)"><input className="entrada" type="date" value={desde} onChange={(e) => setDesde(e.target.value)} /></Campo>
        <Campo etiqueta="Hasta (opcional)"><input className="entrada" type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} /></Campo>
        <button className="btn-primario" onClick={ejecutar} disabled={!domId || cargando}><Play size={16} /> {cargando ? "Calculando…" : "Comparar"}</button>
      </div>

      {error && <Aviso tipo="error">{error}</Aviso>}
      {domicilios?.length === 0 && <Vacio icono={<BarChart3 />} titulo="Crea primero un domicilio">Necesitas un domicilio con facturas y al menos una tarifa en el catálogo.</Vacio>}
      {res && <Resultado res={res} detalle={detalle} setDetalle={setDetalle} />}
    </>
  );
}

function Resultado({ res, detalle, setDetalle }: { res: Comparativa; detalle: number | null; setDetalle: (n: number) => void }) {
  const r = res.resumen;
  const mejor = res.tarifas[0];
  const actual = res.tarifas.find((t) => t.es_actual);
  const top = useMemo(() => {
    const lista = res.tarifas.slice(0, 3);
    if (actual && !lista.includes(actual)) lista.push(actual);
    return lista;
  }, [res, actual]);

  const serieMensual = res.facturas.map((f, i) => {
    const fila: Record<string, number | string | null> = { mes: mes(f.fecha_fin), real: f.importe_real };
    top.forEach((t) => (fila[`t${t.tarifa_id}`] = t.por_factura[i]));
    return fila;
  });

  return (
    <div className="space-y-6">
      {res.avisos.map((a) => <Aviso key={a}>{a}</Aviso>)}
      {r && mejor && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Kpi t="Periodo analizado" v={`${r.num_facturas} facturas`} s={`${fecha(r.fecha_inicio)} – ${fecha(r.fecha_fin)} · ${r.dias} días`} />
            <Kpi
              t={r.referencia === "tarifa_actual" ? "Coste anual con tu tarifa" : "Coste anual real"}
              v={eur(r.referencia_anual)}
              s={r.cobertura_anual ? "Datos de un año completo" : "Extrapolado a 12 meses"}
            />
            <Kpi t="Mejor opción" v={mejor.nombre} s={`${mejor.comercializadora} · ${eur(mejor.anual_estimado)}/año`} icono={<Trophy size={16} className="text-amber-500" />} />
            <Kpi
              t="Ahorro potencial"
              v={mejor.ahorro_anual != null ? `${eur(mejor.ahorro_anual)}/año` : "—"}
              s={mejor.ahorro_mensual != null ? `${eur(mejor.ahorro_mensual)}/mes · ${num(mejor.ahorro_pct, 1)} %` : undefined}
              destacar={(mejor.ahorro_anual ?? 0) > 0}
            />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <div className="tarjeta">
              <h3 className="mb-4 font-semibold">Coste anual estimado por tarifa</h3>
              <ResponsiveContainer width="100%" height={Math.max(200, res.tarifas.length * 36)}>
                <BarChart data={res.tarifas} layout="vertical" margin={{ left: 8, right: 16 }}>
                  <CartesianGrid horizontal={false} strokeOpacity={0.15} />
                  <XAxis type="number" tick={EJE} tickFormatter={(v) => `${v} €`} />
                  <YAxis type="category" dataKey="nombre" width={130} tick={EJE} />
                  <Tooltip formatter={(v: number) => eur(v)} contentStyle={{ borderRadius: 12 }} />
                  <Bar dataKey="anual_estimado" name="€/año" radius={[0, 6, 6, 0]}>
                    {res.tarifas.map((t, i) => (
                      <Cell key={t.tarifa_id} fill={i === 0 ? COLORES[0] : t.es_actual ? COLORES[1] : GRIS} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <p className="mt-2 text-xs text-zinc-500"><span className="text-acento-600">■</span> Mejor · <span className="text-indigo-500">■</span> Actual</p>
            </div>
            <div className="tarjeta">
              <h3 className="mb-4 font-semibold">Coste por factura</h3>
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={serieMensual} margin={{ right: 16 }}>
                  <CartesianGrid strokeOpacity={0.15} />
                  <XAxis dataKey="mes" tick={EJE} />
                  <YAxis tick={EJE} tickFormatter={(v) => `${Math.round(v)} €`} width={60} domain={["auto", "auto"]} />
                  <Tooltip formatter={(v: number) => eur(v)} contentStyle={{ borderRadius: 12 }} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Line dataKey="real" name="Importe real" stroke={GRIS} strokeDasharray="4 4" dot={false} connectNulls />
                  {top.map((t, i) => (
                    <Line
                      key={t.tarifa_id}
                      dataKey={`t${t.tarifa_id}`}
                      name={t.es_actual ? `${t.nombre} (actual)` : t.nombre}
                      stroke={i === 0 ? COLORES[0] : t.es_actual ? COLORES[1] : COLORES[i + 1]}
                      strokeWidth={t.es_actual || i === 0 ? 2.5 : 1.5}
                      dot={false}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <Ranking tarifas={res.tarifas} conAhorro={r.referencia !== null} seleccion={detalle} elegir={setDetalle} />
          {detalle != null && <DetalleConceptos tarifa={res.tarifas.find((t) => t.tarifa_id === detalle)!} actual={actual} />}
          <Validacion res={res} />
        </>
      )}
    </div>
  );
}

function Kpi({ t, v, s, icono, destacar }: { t: string; v: string; s?: string; icono?: React.ReactNode; destacar?: boolean }) {
  return (
    <div className={`tarjeta ${destacar ? "border-acento-400 bg-acento-50 dark:border-acento-700 dark:bg-acento-700/15" : ""}`}>
      <p className="flex items-center gap-1 text-xs text-zinc-500">{icono}{t}</p>
      <p className={`mt-1 truncate text-xl font-semibold tabular-nums ${destacar ? "text-acento-700 dark:text-acento-400" : ""}`}>{v}</p>
      {s && <p className="truncate text-xs text-zinc-500">{s}</p>}
    </div>
  );
}

function Ranking({ tarifas, conAhorro, seleccion, elegir }: { tarifas: ResultadoTarifa[]; conAhorro: boolean; seleccion: number | null; elegir: (n: number) => void }) {
  return (
    <div className="tarjeta overflow-x-auto p-0">
      <h3 className="px-5 pt-5 font-semibold">Ranking</h3>
      <p className="px-5 pb-3 text-xs text-zinc-500">Pulsa una fila para ver su desglose por conceptos.</p>
      <table className="tabla">
        <thead>
          <tr>
            <th>#</th><th>Tarifa</th><th className="num">Periodo</th><th className="num">Anual</th><th className="num">Mensual</th>
            <th className="num">€/kWh medio</th>{conAhorro && <><th className="num">Ahorro anual</th><th className="num">%</th></>}
          </tr>
        </thead>
        <tbody>
          {tarifas.map((t) => (
            <tr
              key={t.tarifa_id}
              onClick={() => elegir(t.tarifa_id)}
              className={`cursor-pointer ${seleccion === t.tarifa_id ? "bg-acento-50 dark:bg-acento-700/15" : "hover:bg-zinc-50 dark:hover:bg-zinc-800/40"}`}
            >
              <td className="tabular-nums text-zinc-500">{t.posicion}</td>
              <td>
                <span className="font-medium">{t.nombre}</span>
                {t.es_actual && <span className="ml-2 rounded-full bg-indigo-100 px-2 py-0.5 text-xs text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">actual</span>}
                <span className="block text-xs text-zinc-500">{t.comercializadora}</span>
              </td>
              <td className="num">{eur(t.total_periodo)}</td>
              <td className="num font-medium">{eur(t.anual_estimado)}</td>
              <td className="num">{eur(t.mensual_medio)}</td>
              <td className="num">{num(t.precio_medio_kwh, 4)}</td>
              {conAhorro && (
                <>
                  <td className={`num font-medium ${(t.ahorro_anual ?? 0) > 0 ? "text-acento-600" : (t.ahorro_anual ?? 0) < 0 ? "text-red-500" : ""}`}>{eur(t.ahorro_anual)}</td>
                  <td className="num">{num(t.ahorro_pct, 1)}</td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DetalleConceptos({ tarifa, actual }: { tarifa: ResultadoTarifa; actual?: ResultadoTarifa }) {
  const comparar = actual && actual.tarifa_id !== tarifa.tarifa_id;
  return (
    <div className="tarjeta overflow-x-auto p-0">
      <h3 className="px-5 pb-3 pt-5 font-semibold">Desglose del periodo · {tarifa.nombre}</h3>
      <table className="tabla">
        <thead>
          <tr><th>Concepto</th><th className="num">{tarifa.nombre}</th>{comparar && <><th className="num">{actual.nombre} (actual)</th><th className="num">Diferencia</th></>}</tr>
        </thead>
        <tbody>
          {CONCEPTOS.map(([k, etiqueta]) => {
            const a = tarifa.desglose_total[k];
            const b = actual?.desglose_total[k] ?? 0;
            const signo = k === "descuento_energia" ? -1 : 1;
            if (!a && !b) return null;
            const total = k === "total";
            return (
              <tr key={k} className={total ? "font-semibold" : ""}>
                <td>{etiqueta}</td>
                <td className="num">{eur(signo * a)}</td>
                {comparar && <><td className="num">{eur(signo * b)}</td><td className={`num ${b - a > 0 ? "text-acento-600" : b - a < 0 ? "text-red-500" : ""}`}>{eur(signo * (a - b))}</td></>}
              </tr>
            );
          })}
        </tbody>
      </table>
      {tarifa.avisos.map((a) => <p key={a} className="px-5 py-2 text-xs text-amber-600">{a}</p>)}
    </div>
  );
}

function Validacion({ res }: { res: Comparativa }) {
  const filas = res.facturas.filter((f) => f.importe_simulado_actual != null && f.importe_real != null);
  if (!filas.length) return null;
  const media = filas.reduce((a, f) => a + Math.abs(f.desviacion_pct ?? 0), 0) / filas.length;
  return (
    <details className="tarjeta">
      <summary className="cursor-pointer font-semibold">
        Fiabilidad del cálculo: desviación media {num(media, 1)} % frente a tus facturas reales
      </summary>
      <p className="mt-2 text-sm text-zinc-500">
        Compara lo que pagaste con lo que calcula la aplicación usando tu tarifa actual. Si la diferencia es grande, revisa los precios de la tarifa,
        los consumos o los parámetros regulados en Ajustes (por ejemplo, la rebaja temporal de IVA e impuesto eléctrico de 2026).
      </p>
      <table className="tabla mt-4">
        <thead><tr><th>Periodo</th><th className="num">Real</th><th className="num">Calculado</th><th className="num">Desviación</th></tr></thead>
        <tbody>
          {filas.map((f) => (
            <tr key={f.id}>
              <td>{fecha(f.fecha_inicio)} – {fecha(f.fecha_fin)}</td>
              <td className="num">{eur(f.importe_real)}</td>
              <td className="num">{eur(f.importe_simulado_actual)}</td>
              <td className={`num ${Math.abs(f.desviacion_pct ?? 0) > 3 ? "text-amber-600" : ""}`}>{num(f.desviacion_pct, 1)} %</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
