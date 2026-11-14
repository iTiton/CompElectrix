import { Copy, ExternalLink, Pencil, Plus, Tags, Trash2 } from "lucide-react";
import { useState } from "react";
import { api, type Tarifa } from "../api";
import { FormTarifa } from "../components/formularios";
import { Aviso, Cabecera, Modal, num, useDatos, Vacio } from "../components/ui";

export default function Tarifas() {
  const { datos, recargar } = useDatos<Tarifa[]>("/tarifas");
  const [editar, setEditar] = useState<Tarifa | "nueva" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const borrar = async (t: Tarifa) => {
    if (!confirm(`¿Borrar la tarifa "${t.nombre}"?`)) return;
    try {
      await api.del(`/tarifas/${t.id}`);
      setError(null);
      recargar();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const duplicar = async (t: Tarifa) => {
    const { id: _id, ...resto } = t;
    void _id;
    await api.post("/tarifas", { ...resto, nombre: `${t.nombre} (copia)`, origen: "manual" });
    recargar();
  };
  const p = (v: number) => num(v, 6);

  return (
    <>
      <Cabecera titulo="Tarifas" sub="Catálogo de ofertas con el que se compara. Precios sin impuestos, tal como los publican las comercializadoras.">
        <button className="btn-primario" onClick={() => setEditar("nueva")}><Plus size={16} /> Nueva tarifa</button>
      </Cabecera>
      {error && <div className="mb-4"><Aviso tipo="error">{error}</Aviso></div>}
      {datos?.length === 0 ? (
        <Vacio icono={<Tags />} titulo="Catálogo vacío">
          Añade tu tarifa actual y las ofertas que quieras comparar. El PVPC aparece solo en cuanto se descargan sus precios. En una próxima versión se podrán importar las ofertas del comparador de la CNMC.
        </Vacio>
      ) : (
        <div className="tarjeta overflow-x-auto p-0">
          <table className="tabla">
            <thead>
              <tr>
                <th>Tarifa</th>
                <th className="num">Pot. P1<br />€/kW·día</th><th className="num">Pot. P2</th>
                <th className="num">Energía P1<br />€/kWh</th><th className="num">P2</th><th className="num">P3</th>
                <th className="num">Cuota<br />€/mes</th><th />
              </tr>
            </thead>
            <tbody>
              {datos?.map((t) => (
                <tr key={t.id} className={`hover:bg-zinc-50 dark:hover:bg-zinc-800/40 ${t.activa ? "" : "opacity-50"}`}>
                  <td>
                    <span className="font-medium">{t.nombre}</span>
                    <span className="block text-xs text-zinc-500">
                      {t.comercializadora} · {t.tipo}
                      {t.permanencia_meses > 0 && ` · ${t.permanencia_meses} m permanencia`}
                      {t.descuento_energia_pct > 0 && ` · −${t.descuento_energia_pct}% energía`}
                    </span>
                  </td>
                  <td className="num">{p(t.potencia_p1)}</td>
                  <td className="num">{p(t.potencia_p2)}</td>
                  {t.tipo === "pvpc" ? (
                    <td className="text-center text-xs text-zinc-500" colSpan={3}>Precio horario oficial (REE)</td>
                  ) : (
                    <>
                      <td className="num">{p(t.energia_p1)}</td>
                      <td className="num">{p(t.energia_p2)}</td>
                      <td className="num">{p(t.energia_p3)}</td>
                    </>
                  )}
                  <td className="num">{num(t.cuota_fija_mes, 2)}</td>
                  <td className="whitespace-nowrap text-right">
                    {t.url && <a className="btn p-1.5" href={t.url} target="_blank" rel="noreferrer" aria-label="Ver oferta"><ExternalLink size={15} /></a>}
                    <button className="btn p-1.5" onClick={() => duplicar(t)} aria-label="Duplicar"><Copy size={15} /></button>
                    <button className="btn p-1.5" onClick={() => setEditar(t)} aria-label="Editar"><Pencil size={15} /></button>
                    <button className="btn-peligro p-1.5" onClick={() => borrar(t)} aria-label="Borrar"><Trash2 size={15} /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Modal titulo={editar === "nueva" ? "Nueva tarifa" : "Editar tarifa"} abierto={editar !== null} cerrar={() => setEditar(null)}>
        {editar !== null && (
          <FormTarifa inicial={editar === "nueva" ? undefined : editar} cancelar={() => setEditar(null)} hecho={() => (setEditar(null), recargar())} />
        )}
      </Modal>
    </>
  );
}
