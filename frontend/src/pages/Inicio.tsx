import { Building2, MapPin, Plus, Receipt } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { Domicilio, Tarifa } from "../api";
import { FormDomicilio } from "../components/formularios";
import { Aviso, Cabecera, eur, fecha, Modal, num, useDatos, Vacio } from "../components/ui";

export default function Inicio() {
  const { datos: domicilios, error } = useDatos<Domicilio[]>("/domicilios");
  const { datos: tarifas } = useDatos<Tarifa[]>("/tarifas");
  const [nuevo, setNuevo] = useState(false);
  const ir = useNavigate();
  const nombreTarifa = (id: number | null) => {
    const t = tarifas?.find((x) => x.id === id);
    return t ? `${t.comercializadora} · ${t.nombre}` : "Sin tarifa indicada";
  };

  return (
    <>
      <Cabecera titulo="Domicilios" sub="Cada domicilio se gestiona de forma independiente: facturas, tarifa y comparativas.">
        <button className="btn-primario" onClick={() => setNuevo(true)}><Plus size={16} /> Nuevo domicilio</button>
      </Cabecera>
      {error && <Aviso tipo="error">No se pudo conectar con el servidor: {error}</Aviso>}
      {domicilios?.length === 0 && (
        <Vacio icono={<Building2 />} titulo="Aún no hay domicilios">
          Crea tu primer domicilio para empezar a registrar facturas y comparar tarifas.
          <div className="mt-4"><button className="btn-primario" onClick={() => setNuevo(true)}><Plus size={16} /> Crear domicilio</button></div>
        </Vacio>
      )}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {domicilios?.map((d) => (
          <Link key={d.id} to={`/domicilios/${d.id}`} className="tarjeta group transition hover:border-acento-400 hover:shadow-md">
            <div className="flex items-start justify-between">
              <h3 className="font-semibold group-hover:text-acento-600">{d.nombre}</h3>
              <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                {num(d.potencia_p1_kw, 2)} kW
              </span>
            </div>
            {d.direccion && <p className="mt-1 flex items-center gap-1 text-sm text-zinc-500"><MapPin size={14} /> {d.direccion}</p>}
            <p className="mt-3 text-xs text-zinc-500">{nombreTarifa(d.tarifa_actual_id)}</p>
            <div className="mt-4 grid grid-cols-2 gap-3 border-t border-zinc-100 pt-4 dark:border-zinc-800">
              <div>
                <p className="text-xs text-zinc-500">Gasto últimos 12 meses</p>
                <p className="text-lg font-semibold tabular-nums">{eur(d.gasto_12m)}</p>
              </div>
              <div>
                <p className="flex items-center gap-1 text-xs text-zinc-500"><Receipt size={12} /> {d.num_facturas} facturas</p>
                <p className="text-sm">Última: {fecha(d.ultima_factura)}</p>
              </div>
            </div>
          </Link>
        ))}
      </div>
      <Modal titulo="Nuevo domicilio" abierto={nuevo} cerrar={() => setNuevo(false)}>
        <FormDomicilio tarifas={tarifas ?? []} cancelar={() => setNuevo(false)} hecho={(d) => ir(`/domicilios/${d.id}`)} />
      </Modal>
    </>
  );
}
