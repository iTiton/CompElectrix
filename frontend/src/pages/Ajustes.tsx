import { KeyRound, Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { api, type EstadoPvpc, type Vigencia } from "../api";
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
        <div className="space-y-6">
          <Conexion
            ruta="/datadis"
            titulo="Datadis"
            campoUsuario="usuario"
            etiquetaUsuario="Usuario (NIF/NIE)"
            ayuda="Portal oficial de las distribuidoras. Regístrate gratis en datadis.es con tu DNI."
          />
          <Conexion
            ruta="/octopus"
            titulo="Octopus Energy"
            campoUsuario="email"
            etiquetaUsuario="Email del área de cliente"
            ayuda="Los mismos datos con los que entras en la web o la app de Octopus."
          />
        </div>
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

function Conexion({ ruta, titulo, campoUsuario, etiquetaUsuario, ayuda }: {
  ruta: string; titulo: string; campoUsuario: "usuario" | "email"; etiquetaUsuario: string; ayuda: string;
}) {
  const { datos, recargar } = useDatos<Record<string, string | boolean | null>>(ruta);
  const [usuario, setUsuario] = useState<string | null>(null);
  const [clave, setClave] = useState("");
  const [msg, setMsg] = useState<{ tipo: "ok" | "error"; t: string } | null>(null);
  const valorUsuario = usuario ?? (datos?.[campoUsuario] as string | null) ?? "";

  const guardar = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api.put(ruta, { [campoUsuario]: valorUsuario, clave: clave || null });
      setClave("");
      setMsg({ tipo: "ok", t: "Guardado. Pruébalo desde un domicilio con el botón de importar." });
      recargar();
    } catch (err) {
      setMsg({ tipo: "error", t: (err as Error).message });
    }
  };
  const olvidar = async () => {
    if (!confirm(`¿Borrar los datos de acceso a ${titulo}?`)) return;
    await api.del(ruta);
    setUsuario(null);
    setMsg(null);
    recargar();
  };

  return (
    <form className="tarjeta" onSubmit={guardar}>
      <h3 className="flex items-center gap-2 font-semibold"><KeyRound size={16} className="text-acento-600" /> {titulo}</h3>
      <p className="mt-1 text-sm text-zinc-500">{ayuda}</p>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <Campo etiqueta={etiquetaUsuario}><input className="entrada" required value={valorUsuario} onChange={(e) => setUsuario(e.target.value)} autoComplete="off" /></Campo>
        <Campo etiqueta="Contraseña" ayuda={datos?.tiene_clave ? "Guardada. Déjala vacía para no cambiarla." : undefined}>
          <input className="entrada" type="password" value={clave} onChange={(e) => setClave(e.target.value)} required={!datos?.tiene_clave} autoComplete="new-password" />
        </Campo>
      </div>
      {msg && <div className="mt-3"><Aviso tipo={msg.tipo}>{msg.t}</Aviso></div>}
      <div className="mt-4 flex items-center gap-2">
        <button className="btn-primario">Guardar</button>
        {datos?.tiene_clave && <button type="button" className="btn-peligro" onClick={olvidar}>Olvidar</button>}
        <span className="ml-auto text-xs text-zinc-500">Se guarda solo en tu servidor.</span>
      </div>
    </form>
  );
}
