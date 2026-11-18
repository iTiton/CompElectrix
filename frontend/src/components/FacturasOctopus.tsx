import { useState } from "react";
import { api, type Domicilio, type SuministroOctopus } from "../api";
import { Acceso, type Cred } from "./ConsumoHorario";
import { Aviso } from "./ui";

interface Resultado {
  total: number;
  creadas: number;
  actualizadas: number;
  sustituidas: number;
  omitidas: string[];
}

/** Trae las facturas de Octopus: periodo exacto, fecha de emisión y total pagado. */
export default function FacturasOctopus({ domicilio, cerrar, hecho }: { domicilio: Domicilio; cerrar: () => void; hecho: () => void }) {
  const [cred, setCred] = useState<Cred | null>(null);
  const [cuentas, setCuentas] = useState<string[]>([]);
  const [cuenta, setCuenta] = useState<string | null>(null);
  const [res, setRes] = useState<Resultado | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const traer = async (c: Cred, num: string) => {
    setOcupado(true);
    setError(null);
    try {
      setRes(await api.post<Resultado>(`/domicilios/${domicilio.id}/facturas/octopus`, { credenciales: c, cuenta: num }));
      hecho();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setOcupado(false);
    }
  };

  if (!cred)
    return (
      <Acceso
        servicio="Octopus" nombre="octopus" etiquetaUsuario="Email" tipoUsuario="email"
        ayuda="Se traen tus facturas con su periodo exacto, la fecha de emisión y lo que pagaste. Los kWh de cada periodo salen del consumo horario que ya has importado."
        enviar={async (c) => {
          const l = await api.post<SuministroOctopus[]>("/octopus/suministros", c);
          const unicas = [...new Set(l.map((x) => x.cuenta))];
          setCred(c);
          setCuentas(unicas);
          if (unicas.length === 1) {
            setCuenta(unicas[0]);
            traer(c, unicas[0]);
          }
        }}
      />
    );

  return (
    <div className="space-y-4">
      {cuentas.length > 1 && !res && (
        <div className="space-y-2">
          <p className="text-sm">Tienes varias cuentas en Octopus. ¿De cuál traigo las facturas?</p>
          {cuentas.map((n) => (
            <label key={n} className="flex items-center gap-2 text-sm">
              <input type="radio" name="cuenta" checked={cuenta === n} onChange={() => setCuenta(n)} /> Cuenta {n}
            </label>
          ))}
          <button className="btn-primario" disabled={!cuenta || ocupado} onClick={() => traer(cred, cuenta!)}>Traer facturas</button>
        </div>
      )}
      {ocupado && <Aviso>Descargando tus facturas de Octopus…</Aviso>}
      {error && <Aviso tipo="error">{error}</Aviso>}
      {res && (
        <Aviso tipo="ok">
          {res.total} facturas en Octopus: {res.creadas} nuevas y {res.actualizadas} actualizadas.
          {res.sustituidas > 0 && ` Sustituyen a ${res.sustituidas} facturas mensuales creadas desde el consumo.`}
          {res.omitidas.length > 0 && (
            <span className="mt-2 block text-xs">
              No se han traído {res.omitidas.length}:
              {res.omitidas.map((o) => <span key={o} className="block">· {o}</span>)}
            </span>
          )}
        </Aviso>
      )}
      <div className="flex justify-end">
        <button className="btn-secundario" onClick={cerrar}>{res ? "Cerrar" : "Cancelar"}</button>
      </div>
    </div>
  );
}
