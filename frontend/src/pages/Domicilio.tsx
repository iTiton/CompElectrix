import { ArrowLeft, BarChart3, FilePlus2, Pencil, Plus, Receipt, Trash2 } from "lucide-react";
import { lazy, Suspense, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type Domicilio, type Factura, type ResumenConsumo, type Tarifa } from "../api";
import { FormDomicilio, FormFactura } from "../components/formularios";
import { Aviso, Cabecera, eur, fecha, Modal, num, useDatos, Vacio } from "../components/ui";

const ConsumoHorario = lazy(() => import("../components/ConsumoHorario"));

export default function DomicilioPage() {
  const { id } = useParams();
  const ir = useNavigate();
  const dom = useDatos<Domicilio>(`/domicilios/${id}`);
  const facs = useDatos<Factura[]>(`/domicilios/${id}/facturas`);
  const consumo = useDatos<ResumenConsumo>(`/domicilios/${id}/consumo`);
  const [generando, setGenerando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const { datos: tarifas } = useDatos<Tarifa[]>("/tarifas");
  const [editando, setEditando] = useState(false);
  const [factura, setFactura] = useState<Factura | "nueva" | null>(null);

  if (dom.error) return <Aviso tipo="error">{dom.error}</Aviso>;
  const d = dom.datos;
  if (!d) return null;
  const tarifa = tarifas?.find((t) => t.id === d.tarifa_actual_id);
  const lista = facs.datos ?? [];
  const totalKwh = lista.reduce((a, f) => a + f.kwh_p1 + f.kwh_p2 + f.kwh_p3, 0);
  const totalEur = lista.reduce((a, f) => a + (f.importe_total ?? 0), 0);

  const mesesCompletos = consumo.datos?.meses.filter((m) => m.completo).length ?? 0;
  const crearDesdeConsumo = async () => {
    setGenerando(true);
    try {
      const r = await api.post<{ creadas: string[]; incompletos: string[] }>(`/domicilios/${d.id}/consumo/generar-facturas`, {});
      setAviso(
        `Creadas ${r.creadas.length} facturas mensuales a partir del consumo horario.` +
          (r.incompletos.length ? ` Meses incompletos sin crear: ${r.incompletos.join(", ")}.` : ""),
      );
      facs.recargar();
    } finally {
      setGenerando(false);
    }
  };

  const borrarDomicilio = async () => {
    if (!confirm(`¿Borrar "${d.nombre}" y sus ${lista.length} facturas? No se puede deshacer.`)) return;
    await api.del(`/domicilios/${d.id}`);
    ir("/");
  };
  const borrarFactura = async (f: Factura) => {
    if (!confirm(`¿Borrar la factura del ${fecha(f.fecha_inicio)} al ${fecha(f.fecha_fin)}?`)) return;
    await api.del(`/facturas/${f.id}`);
    facs.recargar();
  };

  return (
    <>
      <Link to="/" className="mb-4 inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-acento-600"><ArrowLeft size={14} /> Domicilios</Link>
      <Cabecera titulo={d.nombre} sub={[d.direccion, d.cups].filter(Boolean).join(" · ") || undefined}>
        <button className="btn-secundario" onClick={() => setEditando(true)}><Pencil size={16} /> Editar</button>
        <Link className="btn-secundario" to={`/comparativa?domicilio=${d.id}`}><BarChart3 size={16} /> Comparar</Link>
        <button className="btn-primario" onClick={() => setFactura("nueva")}><Plus size={16} /> Añadir factura</button>
      </Cabecera>

      <div className="mb-6 grid gap-4 sm:grid-cols-4">
        <Dato t="Tarifa actual" v={tarifa ? tarifa.nombre : "—"} s={tarifa?.comercializadora} />
        <Dato t="Potencia contratada" v={`${num(d.potencia_p1_kw, 2)} / ${num(d.potencia_p2_kw, 2)} kW`} s="P1 punta / P2 valle" />
        <Dato t="Consumo registrado" v={`${num(totalKwh)} kWh`} s={`${lista.length} facturas`} />
        <Dato t="Importe registrado" v={eur(totalEur)} s={d.distribuidora ?? undefined} />
      </div>

      {aviso && <div className="mb-4"><Aviso tipo="ok">{aviso}</Aviso></div>}
      {lista.length === 0 ? (
        <Vacio icono={<Receipt />} titulo="Sin facturas">
          {mesesCompletos > 0 ? (
            <>
              Ya tienes consumo horario de {mesesCompletos} mes{mesesCompletos === 1 ? "" : "es"} completo{mesesCompletos === 1 ? "" : "s"}.
              Crea con él una factura por mes para poder comparar tarifas; después puedes editarlas para añadir lo que pagaste.
              <div className="mt-4">
                <button className="btn-primario" onClick={crearDesdeConsumo} disabled={generando}>
                  <FilePlus2 size={16} /> {generando ? "Creando…" : `Crear ${mesesCompletos} facturas desde el consumo`}
                </button>
              </div>
            </>
          ) : (
            "Añade tus facturas para poder comparar, o importa tu consumo horario más abajo y crea las facturas a partir de él. Con 12 meses la estimación anual recoge la estacionalidad."
          )}
        </Vacio>
      ) : (
        <div className="tarjeta overflow-x-auto p-0">
          <table className="tabla">
            <thead>
              <tr>
                <th>Periodo</th><th className="num">Días</th><th className="num">P1</th><th className="num">P2</th>
                <th className="num">P3</th><th className="num">Total kWh</th><th className="num">Importe</th><th />
              </tr>
            </thead>
            <tbody>
              {lista.map((f) => {
                const dias = Math.round((+new Date(f.fecha_fin) - +new Date(f.fecha_inicio)) / 864e5) + 1;
                return (
                  <tr key={f.id} className="hover:bg-zinc-50 dark:hover:bg-zinc-800/40">
                    <td>{fecha(f.fecha_inicio)} – {fecha(f.fecha_fin)}<span className="block text-xs text-zinc-500">{f.origen === "horario" ? "Desde consumo horario" : f.comercializadora}</span></td>
                    <td className="num">{dias}</td>
                    <td className="num">{num(f.kwh_p1)}</td>
                    <td className="num">{num(f.kwh_p2)}</td>
                    <td className="num">{num(f.kwh_p3)}</td>
                    <td className="num font-medium">{num(f.kwh_p1 + f.kwh_p2 + f.kwh_p3)}</td>
                    <td className="num font-medium">{eur(f.importe_total)}</td>
                    <td className="whitespace-nowrap text-right">
                      <button className="btn p-1.5" onClick={() => setFactura(f)} aria-label="Editar"><Pencil size={15} /></button>
                      <button className="btn-peligro p-1.5" onClick={() => borrarFactura(f)} aria-label="Borrar"><Trash2 size={15} /></button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <Suspense fallback={null}>
        <ConsumoHorario domicilio={d} alCambiar={() => (facs.recargar(), consumo.recargar())} />
      </Suspense>

      <div className="mt-8 text-right">
        <button className="btn-peligro" onClick={borrarDomicilio}><Trash2 size={16} /> Borrar domicilio</button>
      </div>

      <Modal titulo="Editar domicilio" abierto={editando} cerrar={() => setEditando(false)}>
        <FormDomicilio inicial={d} tarifas={tarifas ?? []} cancelar={() => setEditando(false)} hecho={() => (setEditando(false), dom.recargar())} />
      </Modal>
      <Modal titulo={factura === "nueva" ? "Nueva factura" : "Editar factura"} abierto={factura !== null} cerrar={() => setFactura(null)}>
        {factura !== null && (
          <FormFactura
            domicilio={d}
            inicial={factura === "nueva" ? undefined : factura}
            tarifas={tarifas ?? []}
            cancelar={() => setFactura(null)}
            hecho={() => (setFactura(null), facs.recargar())}
          />
        )}
      </Modal>
    </>
  );
}

function Dato({ t, v, s }: { t: string; v: string; s?: string }) {
  return (
    <div className="tarjeta">
      <p className="text-xs text-zinc-500">{t}</p>
      <p className="mt-1 truncate text-lg font-semibold tabular-nums">{v}</p>
      {s && <p className="truncate text-xs text-zinc-500">{s}</p>}
    </div>
  );
}
