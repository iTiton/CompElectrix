import { Activity, CloudDownload, FileUp, FilePlus2, Trash2 } from "lucide-react";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import {
  api, type Domicilio, type ResultadoImportacion, type ResumenConsumo, type SuministroDatadis, type SuministroOctopus,
} from "../api";
import { COLOR_PERIODO, NOMBRE_PERIODO } from "../periodos";
import { Aviso, Campo, fecha, Modal, num, useDatos } from "./ui";

const EJE = { fill: "#71717a", fontSize: 12 };
const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const etiquetaMes = (m: string) => `${MESES[Number(m.slice(5, 7)) - 1]} ${m.slice(2, 4)}`;

const haceUnAnio = () => {
  const d = new Date();
  d.setFullYear(d.getFullYear() - 1);
  d.setDate(1);
  return d.toISOString().slice(0, 10);
};
const ayer = () => new Date(Date.now() - 864e5).toISOString().slice(0, 10);

export default function ConsumoHorario({ domicilio, alCambiar }: { domicilio: Domicilio; alCambiar: () => void }) {
  const { datos, recargar } = useDatos<ResumenConsumo>(`/domicilios/${domicilio.id}/consumo`);
  const fichero = useRef<HTMLInputElement>(null);
  const [mensaje, setMensaje] = useState<{ tipo: "ok" | "error" | "info"; texto: string; extra?: string[] } | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [modal, setModal] = useState<"datadis" | "octopus" | null>(null);

  const tras = (r: ResultadoImportacion, origen: string) => {
    setMensaje({
      tipo: "ok",
      texto: `${num(r.horas)} horas importadas desde ${origen}${r.desde ? ` (${fecha(r.desde)} – ${fecha(r.hasta)})` : ""}.`,
      extra: r.avisos,
    });
    recargar();
  };

  const subir = async (f: File) => {
    setOcupado(true);
    setMensaje(null);
    try {
      const contenido = await leerTexto(f);
      tras(await api.post<ResultadoImportacion>(`/domicilios/${domicilio.id}/consumo/csv`, { contenido, nombre: f.name }), f.name);
    } catch (e) {
      setMensaje({ tipo: "error", texto: (e as Error).message });
    } finally {
      setOcupado(false);
      if (fichero.current) fichero.current.value = "";
    }
  };

  const generar = async () => {
    const r = await api.post<{ creadas: string[]; con_factura: string[]; incompletos: string[] }>(
      `/domicilios/${domicilio.id}/consumo/generar-facturas`, {},
    );
    const extra = [];
    if (r.con_factura.length) extra.push(`Ya tenían factura: ${r.con_factura.join(", ")}.`);
    if (r.incompletos.length) extra.push(`Datos incompletos: ${r.incompletos.join(", ")}.`);
    setMensaje({
      tipo: r.creadas.length ? "ok" : "info",
      texto: r.creadas.length ? `Creadas ${r.creadas.length} facturas mensuales: ${r.creadas.join(", ")}.` : "No había meses completos sin factura.",
      extra,
    });
    alCambiar();
  };

  const borrar = async () => {
    if (!confirm("¿Borrar todo el consumo horario de este domicilio? Las facturas no se tocan.")) return;
    await api.del(`/domicilios/${domicilio.id}/consumo`);
    setMensaje(null);
    recargar();
  };

  const meses = datos?.meses.map((m) => ({ ...m, etiqueta: etiquetaMes(m.mes) })) ?? [];

  return (
    <section className="tarjeta mt-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 font-semibold"><Activity size={18} className="text-acento-600" /> Consumo horario</h2>
          <p className="mt-1 max-w-xl text-sm text-zinc-500">
            Con el consumo hora a hora el PVPC se calcula exacto y los periodos P1/P2/P3 salen de tus datos reales.
            Descárgalo de <a className="text-acento-600 hover:underline" href="https://datadis.es" target="_blank" rel="noreferrer">Datadis</a>, de tu distribuidora o de tu comercializadora.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <input ref={fichero} type="file" accept=".csv,.txt,text/csv" className="hidden" onChange={(e) => e.target.files?.[0] && subir(e.target.files[0])} />
          <button className="btn-primario" onClick={() => fichero.current?.click()} disabled={ocupado}><FileUp size={16} /> {ocupado ? "Importando…" : "Importar CSV"}</button>
          <button className="btn-secundario" onClick={() => setModal("datadis")}><CloudDownload size={16} /> Datadis</button>
          <button className="btn-secundario" onClick={() => setModal("octopus")}><CloudDownload size={16} /> Octopus</button>
        </div>
      </div>

      {mensaje && (
        <div className="mt-4">
          <Aviso tipo={mensaje.tipo}>
            {mensaje.texto}
            {mensaje.extra?.map((a) => <span key={a} className="block text-xs opacity-80">{a}</span>)}
          </Aviso>
        </div>
      )}

      {datos && datos.horas > 0 ? (
        <>
          <p className="mt-4 text-sm">
            <strong className="tabular-nums">{num(datos.horas)}</strong> horas, del {fecha(datos.desde)} al {fecha(datos.hasta)}.
          </p>
          <div className="mt-4">
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={meses} margin={{ right: 8 }}>
                <CartesianGrid vertical={false} strokeOpacity={0.15} />
                <XAxis dataKey="etiqueta" tick={EJE} />
                <YAxis tick={EJE} width={50} tickFormatter={(v: number) => `${num(v)}`} />
                <Tooltip formatter={(v: number, n: string) => [`${num(v, 1)} kWh`, n]} contentStyle={{ borderRadius: 12 }} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                {(["p1", "p2", "p3"] as const).map((p) => (
                  <Bar key={p} dataKey={`kwh_${p}`} name={`${NOMBRE_PERIODO[p]} (${p.toUpperCase()})`} stackId="a" fill={COLOR_PERIODO[p]} maxBarSize={56} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
          {meses.some((m) => !m.completo) && (
            <p className="mt-2 text-xs text-amber-600">
              Meses incompletos: {meses.filter((m) => !m.completo).map((m) => `${m.etiqueta} (${m.horas}/${m.horas_esperadas} h)`).join(", ")}
            </p>
          )}
          <div className="mt-4 flex flex-wrap gap-2 border-t border-zinc-100 pt-4 dark:border-zinc-800">
            <button className="btn-secundario" onClick={generar} title="Crea una factura por cada mes completo que no tenga ya una">
              <FilePlus2 size={16} /> Crear facturas de los meses sin factura
            </button>
            <Link className="btn-secundario" to={`/comparativa?domicilio=${domicilio.id}`}>Ver comparativa</Link>
            <button className="btn-peligro ml-auto" onClick={borrar}><Trash2 size={16} /> Borrar consumo</button>
          </div>
        </>
      ) : (
        datos && <p className="mt-4 text-sm text-zinc-500">Todavía no hay consumo horario importado.</p>
      )}

      <Modal titulo="Importar desde Datadis" abierto={modal === "datadis"} cerrar={() => setModal(null)}>
        {modal === "datadis" && <ImportarDatadis domicilio={domicilio} cerrar={() => setModal(null)} hecho={(r) => (setModal(null), tras(r, "Datadis"))} />}
      </Modal>
      <Modal titulo="Importar desde Octopus Energy" abierto={modal === "octopus"} cerrar={() => setModal(null)}>
        {modal === "octopus" && <ImportarOctopus cerrar={() => setModal(null)} domicilio={domicilio} hecho={(r) => (setModal(null), tras(r, "Octopus"))} />}
      </Modal>
    </section>
  );
}

/** Lee el fichero probando UTF-8 y, si salen caracteres rotos, Windows-1252 (habitual en las distribuidoras). */
async function leerTexto(f: File): Promise<string> {
  const buf = await f.arrayBuffer();
  const utf8 = new TextDecoder("utf-8").decode(buf);
  return utf8.includes("�") ? new TextDecoder("windows-1252").decode(buf) : utf8;
}

function useListado<T>(ruta: string) {
  const [lista, setLista] = useState<T[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);
  const cargar = async () => {
    setCargando(true);
    setError(null);
    try {
      setLista(await api.get<T[]>(ruta));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setCargando(false);
    }
  };
  return { lista, error, cargando, cargar };
}

function Fechas({ desde, hasta, setDesde, setHasta }: { desde: string; hasta: string; setDesde: (s: string) => void; setHasta: (s: string) => void }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Campo etiqueta="Desde"><input className="entrada" type="date" value={desde} onChange={(e) => setDesde(e.target.value)} /></Campo>
      <Campo etiqueta="Hasta"><input className="entrada" type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} /></Campo>
    </div>
  );
}

function SinCredenciales({ servicio }: { servicio: string }) {
  return (
    <Aviso>
      Primero guarda tus datos de acceso a {servicio} en <Link className="font-medium underline" to="/ajustes">Ajustes</Link>.
    </Aviso>
  );
}

function ImportarDatadis({ domicilio, cerrar, hecho }: { domicilio: Domicilio; cerrar: () => void; hecho: (r: ResultadoImportacion) => void }) {
  const { datos: cred } = useDatos<{ usuario: string | null; tiene_clave: boolean }>("/datadis");
  const sum = useListado<SuministroDatadis>("/datadis/suministros");
  const [elegido, setElegido] = useState<SuministroDatadis | null>(null);
  const [desde, setDesde] = useState(haceUnAnio());
  const [hasta, setHasta] = useState(ayer());
  const [error, setError] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  if (cred && !cred.tiene_clave) return <SinCredenciales servicio="Datadis" />;

  const importar = async () => {
    if (!elegido) return;
    setOcupado(true);
    setError(null);
    try {
      hecho(await api.post<ResultadoImportacion>(`/domicilios/${domicilio.id}/consumo/datadis`, {
        cups: elegido.cups, codigo_distribuidora: elegido.codigo_distribuidora, tipo_punto: elegido.tipo_punto, desde, hasta,
      }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setOcupado(false);
    }
  };

  return (
    <div className="space-y-4">
      {!sum.lista && <button className="btn-primario" onClick={sum.cargar} disabled={sum.cargando}>{sum.cargando ? "Conectando…" : "Ver mis suministros"}</button>}
      {sum.error && <Aviso tipo="error">{sum.error}</Aviso>}
      {sum.lista && (
        <div className="space-y-2">
          {sum.lista.length === 0 && <p className="text-sm text-zinc-500">Datadis no muestra suministros para tu usuario.</p>}
          {sum.lista.map((s) => (
            <label key={s.cups} className={`flex cursor-pointer gap-3 rounded-xl border p-3 text-sm ${elegido?.cups === s.cups ? "border-acento-500 bg-acento-50 dark:bg-acento-700/15" : "border-zinc-200 dark:border-zinc-700"}`}>
              <input type="radio" name="sum" checked={elegido?.cups === s.cups} onChange={() => setElegido(s)} />
              <span>
                <span className="font-mono text-xs">{s.cups}</span>
                {domicilio.cups && s.cups?.startsWith(domicilio.cups.slice(0, 20)) && <span className="ml-2 rounded-full bg-acento-100 px-2 text-xs text-acento-700">este domicilio</span>}
                <span className="block text-zinc-500">{s.direccion} · {s.distribuidora}</span>
              </span>
            </label>
          ))}
        </div>
      )}
      {elegido && <Fechas desde={desde} hasta={hasta} setDesde={setDesde} setHasta={setHasta} />}
      {error && <Aviso tipo="error">{error}</Aviso>}
      <p className="text-xs text-zinc-500">Datadis limita las consultas diarias: pide periodos largos de una vez. Cada mes tarda unos segundos.</p>
      <div className="flex justify-end gap-2">
        <button className="btn-secundario" onClick={cerrar}>Cancelar</button>
        <button className="btn-primario" disabled={!elegido || ocupado} onClick={importar}>{ocupado ? "Descargando…" : "Importar"}</button>
      </div>
    </div>
  );
}

function ImportarOctopus({ domicilio, cerrar, hecho }: { domicilio: Domicilio; cerrar: () => void; hecho: (r: ResultadoImportacion) => void }) {
  const { datos: cred } = useDatos<{ email: string | null; tiene_clave: boolean }>("/octopus");
  const sum = useListado<SuministroOctopus>("/octopus/suministros");
  const [elegido, setElegido] = useState<SuministroOctopus | null>(null);
  const [desde, setDesde] = useState(haceUnAnio());
  const [hasta, setHasta] = useState(ayer());
  const [error, setError] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  if (cred && !cred.tiene_clave) return <SinCredenciales servicio="Octopus" />;

  const importar = async () => {
    if (!elegido) return;
    setOcupado(true);
    setError(null);
    try {
      hecho(await api.post<ResultadoImportacion>(`/domicilios/${domicilio.id}/consumo/octopus`, { propiedad_id: elegido.propiedad_id, desde, hasta }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setOcupado(false);
    }
  };

  return (
    <div className="space-y-4">
      {!sum.lista && <button className="btn-primario" onClick={sum.cargar} disabled={sum.cargando}>{sum.cargando ? "Conectando…" : "Ver mis suministros"}</button>}
      {sum.error && <Aviso tipo="error">{sum.error}</Aviso>}
      {sum.lista?.map((s) => (
        <label key={s.propiedad_id} className={`flex cursor-pointer gap-3 rounded-xl border p-3 text-sm ${elegido?.propiedad_id === s.propiedad_id ? "border-acento-500 bg-acento-50 dark:bg-acento-700/15" : "border-zinc-200 dark:border-zinc-700"}`}>
          <input type="radio" name="sum" checked={elegido?.propiedad_id === s.propiedad_id} onChange={() => setElegido(s)} />
          <span>
            {s.direccion ?? `Propiedad ${s.propiedad_id}`}
            <span className="block font-mono text-xs text-zinc-500">
              {s.cups_luz.map((c) => `Luz ${c}`).join(" · ")}{s.cups_gas.length ? ` · Gas ${s.cups_gas.join(", ")}` : ""}
            </span>
          </span>
        </label>
      ))}
      {elegido && <Fechas desde={desde} hasta={hasta} setDesde={setDesde} setHasta={setHasta} />}
      {error && <Aviso tipo="error">{error}</Aviso>}
      <div className="flex justify-end gap-2">
        <button className="btn-secundario" onClick={cerrar}>Cancelar</button>
        <button className="btn-primario" disabled={!elegido || ocupado} onClick={importar}>{ocupado ? "Descargando…" : "Importar"}</button>
      </div>
    </div>
  );
}
