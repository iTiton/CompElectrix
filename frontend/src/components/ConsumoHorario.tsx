import { Activity, CloudDownload, FileUp, FilePlus2, ShieldCheck, Trash2 } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";
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

interface Cred {
  usuario: string;
  clave: string;
}

/**
 * Formulario de acceso estándar (usuario + contraseña con sus atributos `autocomplete`) para que
 * 1Password, Bitwarden o el propio navegador lo rellenen. Nada se guarda en el servidor.
 */
function Acceso({ servicio, etiquetaUsuario, tipoUsuario, nombre, ayuda, enviar }: {
  servicio: string; etiquetaUsuario: string; tipoUsuario: "text" | "email"; nombre: string; ayuda: string;
  enviar: (c: Cred) => Promise<void>;
}) {
  const [usuario, setUsuario] = useState("");
  const [clave, setClave] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const alEnviar = async (e: FormEvent) => {
    e.preventDefault();
    setOcupado(true);
    setError(null);
    try {
      await enviar({ usuario, clave });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setOcupado(false);
    }
  };
  return (
    <form onSubmit={alEnviar} className="space-y-4" name={nombre} action="#" method="post">
      <p className="text-sm text-zinc-500">{ayuda}</p>
      <div className="grid gap-4 sm:grid-cols-2">
        <Campo etiqueta={etiquetaUsuario}>
          <input className="entrada" name={`${nombre}-usuario`} id={`${nombre}-usuario`} type={tipoUsuario} autoComplete="username" required value={usuario} onChange={(e) => setUsuario(e.target.value)} />
        </Campo>
        <Campo etiqueta="Contraseña">
          <input className="entrada" name={`${nombre}-clave`} id={`${nombre}-clave`} type="password" autoComplete="current-password" required value={clave} onChange={(e) => setClave(e.target.value)} />
        </Campo>
      </div>
      {error && <Aviso tipo="error">{error}</Aviso>}
      <div className="flex items-center gap-2">
        <button className="btn-primario" disabled={ocupado}>{ocupado ? "Conectando…" : `Entrar en ${servicio}`}</button>
        <span className="ml-auto flex items-center gap-1 text-xs text-zinc-500"><ShieldCheck size={14} /> No se guarda: se usa solo para esta importación.</span>
      </div>
    </form>
  );
}

function Fechas({ desde, hasta, setDesde, setHasta }: { desde: string; hasta: string; setDesde: (s: string) => void; setHasta: (s: string) => void }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Campo etiqueta="Desde"><input className="entrada" type="date" value={desde} onChange={(e) => setDesde(e.target.value)} /></Campo>
      <Campo etiqueta="Hasta"><input className="entrada" type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} /></Campo>
    </div>
  );
}

function Opcion({ elegida, alElegir, children }: { elegida: boolean; alElegir: () => void; children: React.ReactNode }) {
  return (
    <label className={`flex cursor-pointer gap-3 rounded-xl border p-3 text-sm ${elegida ? "border-acento-500 bg-acento-50 dark:bg-acento-700/15" : "border-zinc-200 dark:border-zinc-700"}`}>
      <input type="radio" name="suministro" checked={elegida} onChange={alElegir} />
      <span>{children}</span>
    </label>
  );
}

/** Paso 2 común: elegir suministro, fechas e importar. */
function useImportacion() {
  const [desde, setDesde] = useState(haceUnAnio());
  const [hasta, setHasta] = useState(ayer());
  const [error, setError] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const ejecutar = async (fn: () => Promise<void>) => {
    setOcupado(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setOcupado(false);
    }
  };
  return { desde, hasta, setDesde, setHasta, error, ocupado, ejecutar };
}

function Pie({ cerrar, puede, ocupado, importar }: { cerrar: () => void; puede: boolean; ocupado: boolean; importar: () => void }) {
  return (
    <div className="flex justify-end gap-2">
      <button className="btn-secundario" onClick={cerrar}>Cancelar</button>
      <button className="btn-primario" disabled={!puede || ocupado} onClick={importar}>{ocupado ? "Descargando…" : "Importar"}</button>
    </div>
  );
}

function ImportarDatadis({ domicilio, cerrar, hecho }: { domicilio: Domicilio; cerrar: () => void; hecho: (r: ResultadoImportacion) => void }) {
  const [cred, setCred] = useState<Cred | null>(null);
  const [lista, setLista] = useState<SuministroDatadis[]>([]);
  const [elegido, setElegido] = useState<SuministroDatadis | null>(null);
  const imp = useImportacion();

  if (!cred)
    return (
      <Acceso
        servicio="Datadis" nombre="datadis" etiquetaUsuario="Usuario (NIF/NIE)" tipoUsuario="text"
        ayuda="Tus datos de acceso a datadis.es. Si aún no tienes cuenta, regístrate gratis allí con tu DNI."
        enviar={async (c) => {
          const l = await api.post<SuministroDatadis[]>("/datadis/suministros", c);
          setLista(l);
          setElegido(l.find((s) => domicilio.cups && s.cups?.startsWith(domicilio.cups.slice(0, 20))) ?? null);
          setCred(c);
        }}
      />
    );

  return (
    <div className="space-y-4">
      {lista.length === 0 && <p className="text-sm text-zinc-500">Datadis no muestra suministros para tu usuario.</p>}
      {lista.map((s) => (
        <Opcion key={s.cups} elegida={elegido?.cups === s.cups} alElegir={() => setElegido(s)}>
          <span className="font-mono text-xs">{s.cups}</span>
          {domicilio.cups && s.cups?.startsWith(domicilio.cups.slice(0, 20)) && <span className="ml-2 rounded-full bg-acento-100 px-2 text-xs text-acento-700">este domicilio</span>}
          <span className="block text-zinc-500">{s.direccion} · {s.distribuidora}</span>
        </Opcion>
      ))}
      {elegido && <Fechas {...imp} />}
      {imp.error && <Aviso tipo="error">{imp.error}</Aviso>}
      <p className="text-xs text-zinc-500">Datadis limita las consultas diarias: pide periodos largos de una vez. Cada mes tarda unos segundos.</p>
      <Pie cerrar={cerrar} puede={!!elegido} ocupado={imp.ocupado} importar={() => imp.ejecutar(async () => {
        hecho(await api.post<ResultadoImportacion>(`/domicilios/${domicilio.id}/consumo/datadis`, {
          credenciales: cred, cups: elegido!.cups, codigo_distribuidora: elegido!.codigo_distribuidora,
          tipo_punto: elegido!.tipo_punto, desde: imp.desde, hasta: imp.hasta,
        }));
      })} />
    </div>
  );
}

function ImportarOctopus({ domicilio, cerrar, hecho }: { domicilio: Domicilio; cerrar: () => void; hecho: (r: ResultadoImportacion) => void }) {
  const [cred, setCred] = useState<Cred | null>(null);
  const [lista, setLista] = useState<SuministroOctopus[]>([]);
  const [elegido, setElegido] = useState<SuministroOctopus | null>(null);
  const imp = useImportacion();

  if (!cred)
    return (
      <Acceso
        servicio="Octopus" nombre="octopus" etiquetaUsuario="Email" tipoUsuario="email"
        ayuda="Los mismos datos con los que entras en la web o la app de Octopus Energy."
        enviar={async (c) => {
          const l = await api.post<SuministroOctopus[]>("/octopus/suministros", c);
          setLista(l);
          setElegido(l.find((s) => domicilio.cups && s.cups_luz.some((x) => x.startsWith(domicilio.cups!.slice(0, 20)))) ?? (l.length === 1 ? l[0] : null));
          setCred(c);
        }}
      />
    );

  return (
    <div className="space-y-4">
      {lista.map((s) => (
        <Opcion key={s.propiedad_id} elegida={elegido?.propiedad_id === s.propiedad_id} alElegir={() => setElegido(s)}>
          {s.direccion ?? `Propiedad ${s.propiedad_id}`}
          <span className="block font-mono text-xs text-zinc-500">
            {s.cups_luz.map((c) => `Luz ${c}`).join(" · ")}{s.cups_gas.length ? ` · Gas ${s.cups_gas.join(", ")}` : ""}
          </span>
        </Opcion>
      ))}
      {elegido && <Fechas {...imp} />}
      {imp.error && <Aviso tipo="error">{imp.error}</Aviso>}
      <Pie cerrar={cerrar} puede={!!elegido} ocupado={imp.ocupado} importar={() => imp.ejecutar(async () => {
        hecho(await api.post<ResultadoImportacion>(`/domicilios/${domicilio.id}/consumo/octopus`, {
          credenciales: cred, propiedad_id: elegido!.propiedad_id, desde: imp.desde, hasta: imp.hasta,
        }));
      })} />
    </div>
  );
}
