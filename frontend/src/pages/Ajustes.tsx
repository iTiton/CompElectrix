import { Download, HardDrive, Pencil, Plus, RefreshCw, ShieldCheck, Trash2, Upload } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";
import { api, urlApi, type EstadoPvpc, type Vigencia } from "../api";
import { Aviso, Cabecera, Campo, fecha, Modal, num, useDatos } from "../components/ui";

export default function Ajustes() {
  const { datos, recargar } = useDatos<Vigencia[]>("/vigencias");
  const [editar, setEditar] = useState<Vigencia | "nueva" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const borrar = async (v: Vigencia) => {
    if (!confirm("¿Borrar este periodo de parámetros?")) return;
    try {
      await api.del(`/vigencias/${v.id}`);
      recargar();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <>
      <Cabecera titulo="Ajustes" sub="Fuentes de datos, conexiones y parámetros regulados." />
      <div className="mb-6 grid gap-6 lg:grid-cols-2">
        <TarjetaPvpc />
        <div className="tarjeta">
          <h3 className="flex items-center gap-2 font-semibold"><ShieldCheck size={16} className="text-acento-600" /> Datadis y Octopus</h3>
          <p className="mt-2 text-sm text-zinc-500">
            CompElectrix <strong>no guarda tus contraseñas</strong>. Cuando importas consumos desde un domicilio te las pide en un
            formulario normal de inicio de sesión, que tu gestor de contraseñas (1Password, Bitwarden, el del navegador…) puede
            rellenar. Se usan solo para esa importación y se descartan.
          </p>
          <p className="mt-2 text-sm text-zinc-500">
            Consejo: guarda en tu gestor una entrada para Datadis y otra para Octopus con la dirección de tu Raspberry, y llámalas
            «CompElectrix · Datadis» y «CompElectrix · Octopus» para distinguirlas.
          </p>
        </div>
      </div>
      <div className="mb-6 grid gap-6 lg:grid-cols-2">
        <TarjetaCopia />
        <TarjetaAlmacenamiento />
      </div>
      <h2 className="mb-1 text-lg font-semibold">Impuestos y cargos regulados</h2>
      <p className="mb-4 text-sm text-zinc-500">Se aplican a todas las tarifas. Cambian por ley, así que se guardan con fechas de vigencia.</p>
      <div className="mb-4">
        <Aviso>
          Comprueba estos valores con tus facturas. Si una factura cruza dos periodos, se prorratea por días.
          El IEE no puede bajar de su mínimo en €/MWh aunque el porcentaje sea menor.
        </Aviso>
      </div>
      {error && <div className="mb-4"><Aviso tipo="error">{error}</Aviso></div>}
      <div className="tarjeta overflow-x-auto p-0">
        <div className="flex items-center justify-between px-5 pt-5">
          <h3 className="font-semibold">Periodos de vigencia</h3>
          <button className="btn-primario" onClick={() => setEditar("nueva")}><Plus size={16} /> Nuevo periodo</button>
        </div>
        <table className="tabla mt-3">
          <thead>
            <tr>
              <th>Vigencia</th><th className="num">IEE %</th><th className="num">IEE mín.<br />€/MWh</th><th className="num">IVA %</th>
              <th className="num">Contador<br />€/día</th><th className="num">Bono social<br />€/año</th><th />
            </tr>
          </thead>
          <tbody>
            {datos?.map((v) => (
              <tr key={v.id}>
                <td>
                  {fecha(v.fecha_desde)} – {v.fecha_hasta ? fecha(v.fecha_hasta) : "actualidad"}
                  {v.nota && <span className="block max-w-md text-xs text-zinc-500">{v.nota}</span>}
                </td>
                <td className="num">{num(v.iee_pct, 4)}</td>
                <td className="num">{num(v.iee_minimo_eur_mwh, 2)}</td>
                <td className="num">{num(v.iva_pct, 0)}</td>
                <td className="num">{num(v.alquiler_contador_eur_dia, 6)}</td>
                <td className="num">{num(v.bono_social_eur_anio, 6)}</td>
                <td className="whitespace-nowrap text-right">
                  <button className="btn p-1.5" onClick={() => setEditar(v)} aria-label="Editar"><Pencil size={15} /></button>
                  <button className="btn-peligro p-1.5" onClick={() => borrar(v)} aria-label="Borrar"><Trash2 size={15} /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Modal titulo={editar === "nueva" ? "Nuevo periodo" : "Editar periodo"} abierto={editar !== null} cerrar={() => setEditar(null)}>
        {editar !== null && <FormVigencia inicial={editar === "nueva" ? undefined : editar} cerrar={() => setEditar(null)} hecho={() => (setEditar(null), recargar())} />}
      </Modal>
    </>
  );
}

function FormVigencia({ inicial, cerrar, hecho }: { inicial?: Vigencia; cerrar: () => void; hecho: () => void }) {
  const [v, setV] = useState({
    fecha_desde: inicial?.fecha_desde ?? "",
    fecha_hasta: inicial?.fecha_hasta ?? "",
    iee_pct: String(inicial?.iee_pct ?? 5.11269632),
    iee_minimo_eur_mwh: String(inicial?.iee_minimo_eur_mwh ?? 1),
    iva_pct: String(inicial?.iva_pct ?? 21),
    alquiler_contador_eur_dia: String(inicial?.alquiler_contador_eur_dia ?? 0.02663),
    bono_social_eur_anio: String(inicial?.bono_social_eur_anio ?? 0),
    iee_incluye_bono_social: inicial?.iee_incluye_bono_social ?? true,
    nota: inicial?.nota ?? "",
  });
  const [error, setError] = useState<string | null>(null);
  const c = (k: keyof typeof v) => ({ value: v[k] as string, onChange: (e: React.ChangeEvent<HTMLInputElement>) => setV({ ...v, [k]: e.target.value }) });
  const n = (x: string) => Number(x.replace(",", "."));

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const cuerpo = {
      ...v,
      fecha_hasta: v.fecha_hasta || null,
      nota: v.nota || null,
      iee_pct: n(v.iee_pct), iee_minimo_eur_mwh: n(v.iee_minimo_eur_mwh), iva_pct: n(v.iva_pct),
      alquiler_contador_eur_dia: n(v.alquiler_contador_eur_dia), bono_social_eur_anio: n(v.bono_social_eur_anio),
    };
    try {
      if (inicial) await api.put(`/vigencias/${inicial.id}`, cuerpo);
      else await api.post("/vigencias", cuerpo);
      hecho();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <form onSubmit={enviar} className="grid gap-4 sm:grid-cols-2">
      <Campo etiqueta="Desde *"><input className="entrada" type="date" required {...c("fecha_desde")} /></Campo>
      <Campo etiqueta="Hasta" ayuda="Vacío = sigue vigente"><input className="entrada" type="date" {...c("fecha_hasta")} /></Campo>
      <Campo etiqueta="Impuesto eléctrico (%)"><input className="entrada num" type="number" step="any" {...c("iee_pct")} /></Campo>
      <Campo etiqueta="Mínimo IEE (€/MWh)"><input className="entrada num" type="number" step="any" {...c("iee_minimo_eur_mwh")} /></Campo>
      <Campo etiqueta="IVA (%)"><input className="entrada num" type="number" step="any" {...c("iva_pct")} /></Campo>
      <Campo etiqueta="Alquiler contador (€/día)" ayuda="0,81 €/mes ≈ 0,026630 €/día"><input className="entrada num" type="number" step="any" {...c("alquiler_contador_eur_dia")} /></Campo>
      <Campo etiqueta="Financiación bono social (€/año)"><input className="entrada num" type="number" step="any" {...c("bono_social_eur_anio")} /></Campo>
      <label className="flex items-center gap-2 self-center text-sm">
        <input type="checkbox" checked={v.iee_incluye_bono_social} onChange={(e) => setV({ ...v, iee_incluye_bono_social: e.target.checked })} />
        El bono social forma parte de la base del IEE
      </label>
      <Campo etiqueta="Nota" className="sm:col-span-2"><input className="entrada" {...c("nota")} /></Campo>
      <div className="space-y-3 sm:col-span-2">
        {error && <Aviso tipo="error">{error}</Aviso>}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-secundario" onClick={cerrar}>Cancelar</button>
          <button className="btn-primario">Guardar</button>
        </div>
      </div>
    </form>
  );
}

function TarjetaPvpc() {
  const { datos, recargar } = useDatos<EstadoPvpc>("/pvpc/estado");
  const [desde, setDesde] = useState("");
  const [error, setError] = useState<string | null>(null);

  const lanzar = async () => {
    setError(null);
    try {
      await api.post("/pvpc/sincronizar", desde ? { desde } : {});
      const vigilar = setInterval(async () => {
        const e = await api.get<EstadoPvpc>("/pvpc/estado");
        recargar();
        if (!e.en_curso) clearInterval(vigilar);
      }, 3000);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="tarjeta">
      <h3 className="flex items-center gap-2 font-semibold"><RefreshCw size={16} className="text-acento-600" /> Precios del PVPC</h3>
      <p className="mt-1 text-sm text-zinc-500">
        Cada vez que abres la aplicación se descargan de Red Eléctrica los días que falten desde el último uso.
        No necesitan clave y en reposo no se consulta nada.
      </p>
      {datos && (
        <dl className="mt-4 grid grid-cols-2 gap-2 text-sm">
          <dt className="text-zinc-500">Histórico</dt>
          <dd>{datos.horas ? `${fecha(datos.desde)} – ${fecha(datos.hasta)}` : "vacío"}</dd>
          <dt className="text-zinc-500">Horas guardadas</dt>
          <dd className="tabular-nums">{num(datos.horas)}</dd>
          <dt className="text-zinc-500">Última actualización</dt>
          <dd>{datos.ultima_sync ? new Date(datos.ultima_sync).toLocaleString("es-ES") : "—"}</dd>
        </dl>
      )}
      {datos?.en_curso && <div className="mt-3"><Aviso tipo="ok">Actualizando… {datos.progreso}</Aviso></div>}
      {datos?.ultimo_error && !datos.en_curso && <div className="mt-3"><Aviso>{datos.ultimo_error}</Aviso></div>}
      {error && <div className="mt-3"><Aviso tipo="error">{error}</Aviso></div>}
      <div className="mt-4 flex flex-wrap items-end gap-2">
        <Campo etiqueta="Descargar desde (opcional)" ayuda="Para comparar facturas antiguas. Desde junio de 2021.">
          <input className="entrada" type="date" min="2021-06-01" value={desde} onChange={(e) => setDesde(e.target.value)} />
        </Campo>
        <button className="btn-primario mb-5" onClick={lanzar} disabled={datos?.en_curso}>Actualizar ahora</button>
      </div>
    </div>
  );
}


interface Almacenamiento {
  bytes_total: number;
  bytes_libres: number;
  filas: Record<string, number>;
}

const tam = (b: number) => (b < 1024 * 1024 ? `${num(b / 1024, 0)} KB` : `${num(b / 1024 / 1024, 1)} MB`);
const NOMBRES: Record<string, string> = {
  precios_horarios: "Precios horarios PVPC",
  consumos_horarios: "Horas de consumo",
  facturas: "Facturas",
  tarifas: "Tarifas",
  domicilios: "Domicilios",
};

function TarjetaAlmacenamiento() {
  const { datos, recargar } = useDatos<Almacenamiento>("/almacenamiento");
  const [msg, setMsg] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const compactar = async () => {
    setOcupado(true);
    try {
      const r = await api.post<{ antes: number; despues: number }>("/almacenamiento/compactar", {});
      setMsg(`Compactada: de ${tam(r.antes)} a ${tam(r.despues)}.`);
      recargar();
    } finally {
      setOcupado(false);
    }
  };
  if (!datos) return null;
  return (
    <div className="tarjeta">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 font-semibold"><HardDrive size={16} className="text-acento-600" /> Almacenamiento</h3>
          <p className="mt-1 text-sm text-zinc-500">
            Base de datos: <strong className="tabular-nums">{tam(datos.bytes_total)}</strong>. Cada año de precios o de consumo
            horario de un domicilio ocupa menos de 1 MB.
          </p>
        </div>
        <button className="btn-secundario" onClick={compactar} disabled={ocupado} title="Reescribe la base de datos para recuperar el espacio de lo borrado">
          {ocupado ? "Compactando…" : `Compactar${datos.bytes_libres > 0 ? ` (recupera ${tam(datos.bytes_libres)})` : ""}`}
        </button>
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-5">
        {Object.entries(datos.filas).map(([k, v]) => (
          <div key={k}>
            <dt className="text-xs text-zinc-500">{NOMBRES[k] ?? k}</dt>
            <dd className="tabular-nums">{num(v)}</dd>
          </div>
        ))}
      </dl>
      {msg && <div className="mt-3"><Aviso tipo="ok">{msg}</Aviso></div>}
    </div>
  );
}


interface CopiaAuto {
  nombre: string;
  bytes: number;
  fecha: string;
}

function TarjetaCopia() {
  const fichero = useRef<HTMLInputElement>(null);
  const automaticas = useDatos<CopiaAuto[]>("/copia/automaticas");
  const [msg, setMsg] = useState<{ tipo: "ok" | "error"; t: string } | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const restaurar = async (f: File) => {
    if (!confirm(
      `¿Restaurar «${f.name}»?\n\nTodos los datos actuales se sustituirán por los de la copia. ` +
      "Antes se guardará automáticamente una copia de cómo están ahora.",
    )) {
      if (fichero.current) fichero.current.value = "";
      return;
    }
    setOcupado(true);
    setMsg(null);
    try {
      const r = await fetch(urlApi("/copia/restaurar"), {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream" },
        body: f,
      });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail ?? `Error ${r.status}`);
      const c = j.contenido;
      setMsg({ tipo: "ok", t: `Copia restaurada: ${c.domicilio} domicilios, ${c.factura} facturas y ${c.tarifa} tarifas. Recargando…` });
      setTimeout(() => location.reload(), 1800);
    } catch (e) {
      setMsg({ tipo: "error", t: (e as Error).message });
    } finally {
      setOcupado(false);
      if (fichero.current) fichero.current.value = "";
    }
  };

  return (
    <div className="tarjeta">
      <h3 className="flex items-center gap-2 font-semibold"><ShieldCheck size={16} className="text-acento-600" /> Copia de seguridad</h3>
      <p className="mt-1 text-sm text-zinc-500">
        Descarga un archivo <strong>.zip</strong> con todos tus datos: la copia completa para restaurar y tablas que se
        abren con Excel o Numbers. Guárdalo donde quieras (iCloud, el NAS…).
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        <a className="btn-primario" href={urlApi("/copia")} download><Download size={16} /> Descargar copia</a>
        <input ref={fichero} type="file" accept=".zip,.sqlite,application/zip" className="hidden" onChange={(e) => e.target.files?.[0] && restaurar(e.target.files[0])} />
        <button className="btn-secundario" disabled={ocupado} onClick={() => fichero.current?.click()}>
          <Upload size={16} /> {ocupado ? "Restaurando…" : "Restaurar copia"}
        </button>
      </div>
      {msg && <div className="mt-3"><Aviso tipo={msg.tipo}>{msg.t}</Aviso></div>}
      {!!automaticas.datos?.length && (
        <details className="mt-4 text-sm">
          <summary className="cursor-pointer text-zinc-500">Copias guardadas antes de restaurar ({automaticas.datos.length})</summary>
          <ul className="mt-2 space-y-1">
            {automaticas.datos.map((c) => (
              <li key={c.nombre}>
                <a className="text-acento-600 hover:underline" href={urlApi(`/copia/automaticas/${c.nombre}`)} download>
                  {new Date(c.fecha).toLocaleString("es-ES")}
                </a>
                <span className="text-zinc-500"> · {tam(c.bytes)}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
