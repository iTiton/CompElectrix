import { Gauge, Pencil, Plus, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { api, type Domicilio, type TramoPotencia } from "../api";
import { Aviso, Campo, fecha, Modal, num, useDatos } from "./ui";

const ORIGEN: Record<string, string> = { manual: "a mano", octopus: "Octopus", datadis: "Datadis" };

/** Tramos de potencia contratada con sus fechas. Las facturas creadas desde el consumo usan la vigente en cada día. */
export default function HistorialPotencia({ domicilio, alCambiar }: { domicilio: Domicilio; alCambiar: () => void }) {
  const { datos, recargar } = useDatos<TramoPotencia[]>(`/domicilios/${domicilio.id}/potencias`);
  const [editar, setEditar] = useState<TramoPotencia | "nuevo" | null>(null);

  const cambiado = () => {
    setEditar(null);
    recargar();
    alCambiar();
  };
  const borrar = async (t: TramoPotencia) => {
    if (!confirm(`¿Borrar el tramo de ${num(t.kw_p1, 2)} kW desde el ${fecha(t.desde)}?`)) return;
    await api.del(`/potencias/${t.id}`);
    cambiado();
  };
  const tramos = [...(datos ?? [])].reverse();

  return (
    <section className="tarjeta mt-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 font-semibold"><Gauge size={18} className="text-acento-600" /> Potencia contratada</h2>
          <p className="mt-1 max-w-xl text-sm text-zinc-500">
            Si has cambiado de potencia, indica desde cuándo. Las facturas creadas desde el consumo usan la que estaba vigente
            cada día. Se rellena sola al importar de Octopus o Datadis.
          </p>
        </div>
        <button className="btn-secundario" onClick={() => setEditar("nuevo")}><Plus size={16} /> Añadir cambio</button>
      </div>
      {tramos.length === 0 ? (
        <p className="mt-4 text-sm text-zinc-500">
          Sin historial: se usa la del domicilio ({num(domicilio.potencia_p1_kw, 2)} / {num(domicilio.potencia_p2_kw, 2)} kW) para todas las fechas.
        </p>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <table className="tabla [&_td]:px-2 [&_th]:px-2 sm:[&_td]:px-3 sm:[&_th]:px-3">
            <thead><tr><th>Desde</th><th>Hasta</th><th className="num">P1 <span className="normal-case">kW</span></th><th className="num">P2 <span className="normal-case">kW</span></th><th className="hidden sm:table-cell">Origen</th><th /></tr></thead>
            <tbody>
              {tramos.map((t) => (
                <tr key={t.id}>
                  <td className="whitespace-nowrap">{fecha(t.desde)}</td>
                  <td className="whitespace-nowrap">{t.hasta ? fecha(t.hasta) : <span className="text-acento-600">actual</span>}</td>
                  <td className="num whitespace-nowrap">{num(t.kw_p1, 2)}</td>
                  <td className="num whitespace-nowrap">{num(t.kw_p2, 2)}</td>
                  <td className="hidden text-xs text-zinc-500 sm:table-cell">{ORIGEN[t.origen] ?? t.origen}</td>
                  <td className="whitespace-nowrap text-right">
                    <button className="btn p-1.5" onClick={() => setEditar(t)} aria-label="Editar"><Pencil size={15} /></button>
                    <button className="btn-peligro hidden p-1.5 sm:inline-flex" onClick={() => borrar(t)} aria-label="Borrar"><Trash2 size={15} /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Modal titulo={editar === "nuevo" ? "Cambio de potencia" : "Editar tramo de potencia"} abierto={editar !== null} cerrar={() => setEditar(null)} ancho="max-w-lg">
        {editar !== null && (
          <FormTramo
            domicilio={domicilio}
            inicial={editar === "nuevo" ? undefined : editar}
            cancelar={() => setEditar(null)}
            hecho={cambiado}
            borrar={editar === "nuevo" ? undefined : () => borrar(editar)}
          />
        )}
      </Modal>
    </section>
  );
}

function FormTramo({ domicilio, inicial, cancelar, hecho, borrar }: {
  domicilio: Domicilio; inicial?: TramoPotencia; cancelar: () => void; hecho: () => void; borrar?: () => void;
}) {
  const [v, setV] = useState({
    desde: inicial?.desde ?? "",
    hasta: inicial?.hasta ?? "",
    kw_p1: String(inicial?.kw_p1 ?? domicilio.potencia_p1_kw),
    kw_p2: String(inicial?.kw_p2 ?? domicilio.potencia_p2_kw),
  });
  const [error, setError] = useState<string | null>(null);
  const c = (k: keyof typeof v) => ({ value: v[k], onChange: (e: React.ChangeEvent<HTMLInputElement>) => setV({ ...v, [k]: e.target.value }) });
  const n = (x: string) => Number(x.replace(",", "."));

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const cuerpo = { desde: v.desde, hasta: v.hasta || null, kw_p1: n(v.kw_p1), kw_p2: n(v.kw_p2), origen: inicial?.origen ?? "manual", nota: inicial?.nota ?? null };
    try {
      if (inicial) await api.put(`/potencias/${inicial.id}`, cuerpo);
      else await api.post(`/domicilios/${domicilio.id}/potencias`, cuerpo);
      hecho();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <form onSubmit={enviar} className="grid gap-4 sm:grid-cols-2">
      <Campo etiqueta="Desde *"><input className="entrada" type="date" required {...c("desde")} /></Campo>
      <Campo etiqueta="Hasta" ayuda="Vacío = sigue vigente"><input className="entrada" type="date" {...c("hasta")} /></Campo>
      <Campo etiqueta="Potencia P1 punta (kW)"><input className="entrada num" type="number" step="0.001" min="0.1" max="15" required {...c("kw_p1")} /></Campo>
      <Campo etiqueta="Potencia P2 valle (kW)"><input className="entrada num" type="number" step="0.001" min="0.1" max="15" required {...c("kw_p2")} /></Campo>
      <p className="text-xs text-zinc-500 sm:col-span-2">
        Si dos tramos se solapan, manda el que empieza más tarde: para registrar un cambio basta con añadir el nuevo tramo «desde» la fecha del cambio.
      </p>
      <div className="space-y-3 sm:col-span-2">
        {error && <Aviso tipo="error">{error}</Aviso>}
        <div className="flex justify-end gap-2">
          {borrar && <button type="button" className="btn-peligro mr-auto" onClick={borrar}><Trash2 size={16} /> Borrar</button>}
          <button type="button" className="btn-secundario" onClick={cancelar}>Cancelar</button>
          <button className="btn-primario">Guardar</button>
        </div>
      </div>
    </form>
  );
}
