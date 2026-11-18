import { useState, type FormEvent, type ReactNode } from "react";
import { api, type Domicilio, type Factura, type Tarifa } from "../api";
import { Aviso, Campo } from "./ui";

type Valores = Record<string, string | number | boolean | null>;

/** Estado de formulario sencillo: todo como texto, se convierte al enviar. */
function useFormulario<T extends Valores>(inicial: T) {
  const [v, setV] = useState<T>(inicial);
  const campo = (k: keyof T) => ({
    value: (v[k] ?? "") as string | number,
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
      setV((x) => ({ ...x, [k]: e.target.value })),
  });
  const marca = (k: keyof T) => ({
    checked: Boolean(v[k]),
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => setV((x) => ({ ...x, [k]: e.target.checked })),
  });
  return { v, setV, campo, marca };
}

const aNum = (x: unknown, defecto: number | null = 0) => {
  if (x === "" || x == null) return defecto;
  const n = Number(String(x).replace(",", "."));
  return Number.isFinite(n) ? n : defecto;
};
const aTexto = (x: unknown) => (x === "" || x == null ? null : String(x));

function Pie({ enviando, error, cancelar, texto = "Guardar" }: { enviando: boolean; error: string | null; cancelar: () => void; texto?: string }) {
  return (
    <div className="mt-6 space-y-3">
      {error && <Aviso tipo="error">{error}</Aviso>}
      <div className="flex justify-end gap-2">
        <button type="button" className="btn-secundario" onClick={cancelar}>Cancelar</button>
        <button className="btn-primario" disabled={enviando}>{enviando ? "Guardando…" : texto}</button>
      </div>
    </div>
  );
}

function useEnvio(fn: () => Promise<unknown>, ok: () => void) {
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    setEnviando(true);
    setError(null);
    try {
      await fn();
      ok();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setEnviando(false);
    }
  };
  return { enviar, enviando, error };
}

const Rejilla = ({ children, cols = 2 }: { children: ReactNode; cols?: 2 | 3 }) => (
  <div className={`grid gap-4 ${cols === 3 ? "sm:grid-cols-3" : "sm:grid-cols-2"}`}>{children}</div>
);

const Seccion = ({ titulo, children }: { titulo: string; children: ReactNode }) => (
  <fieldset className="mt-5">
    <legend className="mb-3 text-sm font-semibold text-zinc-700 dark:text-zinc-300">{titulo}</legend>
    {children}
  </fieldset>
);

// ------------------------------------------------------------- Domicilio
export function FormDomicilio({ inicial, tarifas, hecho, cancelar }: {
  inicial?: Domicilio; tarifas: Tarifa[]; hecho: (d: Domicilio) => void; cancelar: () => void;
}) {
  const { v, campo } = useFormulario({
    nombre: inicial?.nombre ?? "",
    direccion: inicial?.direccion ?? "",
    cups: inicial?.cups ?? "",
    distribuidora: inicial?.distribuidora ?? "",
    potencia_p1_kw: inicial?.potencia_p1_kw ?? 3.45,
    potencia_p2_kw: inicial?.potencia_p2_kw ?? 3.45,
    tarifa_actual_id: inicial?.tarifa_actual_id ?? "",
    notas: inicial?.notas ?? "",
  });
  let guardado: Domicilio;
  const { enviar, enviando, error } = useEnvio(async () => {
    const cuerpo = {
      ...v,
      direccion: aTexto(v.direccion),
      cups: aTexto(v.cups)?.toUpperCase().replace(/\s/g, "") ?? null,
      distribuidora: aTexto(v.distribuidora),
      notas: aTexto(v.notas),
      potencia_p1_kw: aNum(v.potencia_p1_kw),
      potencia_p2_kw: aNum(v.potencia_p2_kw),
      tarifa_actual_id: aNum(v.tarifa_actual_id, null),
    };
    guardado = inicial ? await api.put(`/domicilios/${inicial.id}`, cuerpo) : await api.post("/domicilios", cuerpo);
  }, () => hecho(guardado));

  return (
    <form onSubmit={enviar}>
      <Rejilla>
        <Campo etiqueta="Nombre *"><input className="entrada" required {...campo("nombre")} placeholder="Casa, apartamento playa…" /></Campo>
        <Campo etiqueta="CUPS" ayuda="Código de 20-22 caracteres que empieza por ES"><input className="entrada font-mono" {...campo("cups")} /></Campo>
        <Campo etiqueta="Dirección" className="sm:col-span-2"><input className="entrada" {...campo("direccion")} /></Campo>
        <Campo etiqueta="Distribuidora"><input className="entrada" {...campo("distribuidora")} placeholder="i-DE, e-distribución, UFD…" /></Campo>
        <Campo etiqueta="Tarifa actual" ayuda="Se usa como referencia para calcular el ahorro">
          <select className="entrada" {...campo("tarifa_actual_id")}>
            <option value="">— Sin indicar —</option>
            {tarifas.map((t) => <option key={t.id} value={t.id}>{t.comercializadora} · {t.nombre}</option>)}
          </select>
        </Campo>
        <Campo etiqueta="Potencia P1 punta (kW)"><input className="entrada" type="number" step="0.001" min="0" {...campo("potencia_p1_kw")} /></Campo>
        <Campo etiqueta="Potencia P2 valle (kW)"><input className="entrada" type="number" step="0.001" min="0" {...campo("potencia_p2_kw")} /></Campo>
        <Campo etiqueta="Notas" className="sm:col-span-2"><textarea className="entrada" rows={2} {...campo("notas")} /></Campo>
      </Rejilla>
      <Pie enviando={enviando} error={error} cancelar={cancelar} />
    </form>
  );
}

// --------------------------------------------------------------- Factura
export function FormFactura({ domicilio, inicial, tarifas, hecho, cancelar }: {
  domicilio: Domicilio; inicial?: Factura; tarifas: Tarifa[]; hecho: () => void; cancelar: () => void;
}) {
  const { v, campo } = useFormulario({
    fecha_inicio: inicial?.fecha_inicio ?? "",
    fecha_fin: inicial?.fecha_fin ?? "",
    dias: inicial?.dias ?? "",
    comercializadora: inicial?.comercializadora ?? "",
    tarifa_id: inicial?.tarifa_id ?? domicilio.tarifa_actual_id ?? "",
    numero: inicial?.numero ?? "",
    kwh_p1: inicial?.kwh_p1 ?? "",
    kwh_p2: inicial?.kwh_p2 ?? "",
    kwh_p3: inicial?.kwh_p3 ?? "",
    kw_p1: inicial?.kw_p1 ?? domicilio.potencia_p1_kw,
    kw_p2: inicial?.kw_p2 ?? domicilio.potencia_p2_kw,
    importe_total: inicial?.importe_total ?? "",
    importe_potencia: inicial?.importe_potencia ?? "",
    importe_energia: inicial?.importe_energia ?? "",
    importe_otros: inicial?.importe_otros ?? "",
    notas: inicial?.notas ?? "",
  });
  const { enviar, enviando, error } = useEnvio(async () => {
    const cuerpo = {
      domicilio_id: domicilio.id,
      fecha_inicio: v.fecha_inicio,
      fecha_fin: v.fecha_fin,
      dias: aNum(v.dias, null),
      comercializadora: aTexto(v.comercializadora),
      tarifa_id: aNum(v.tarifa_id, null),
      numero: aTexto(v.numero),
      kwh_p1: aNum(v.kwh_p1), kwh_p2: aNum(v.kwh_p2), kwh_p3: aNum(v.kwh_p3),
      kw_p1: aNum(v.kw_p1), kw_p2: aNum(v.kw_p2),
      importe_total: aNum(v.importe_total, null),
      importe_potencia: aNum(v.importe_potencia, null),
      importe_energia: aNum(v.importe_energia, null),
      importe_otros: aNum(v.importe_otros, null),
      notas: aTexto(v.notas),
      origen: inicial?.origen ?? "manual",
    };
    if (inicial) await api.put(`/facturas/${inicial.id}`, cuerpo);
    else await api.post("/facturas", cuerpo);
  }, hecho);

  const n = (k: Parameters<typeof campo>[0], paso = "0.01") => (
    <input className="entrada num" type="number" step={paso} min="0" {...campo(k)} />
  );
  const diasCalculados =
    v.fecha_inicio && v.fecha_fin
      ? Math.round((+new Date(String(v.fecha_fin)) - +new Date(String(v.fecha_inicio))) / 864e5) + 1
      : null;

  return (
    <form onSubmit={enviar}>
      <Rejilla cols={3}>
        <Campo etiqueta="Desde *"><input className="entrada" type="date" required {...campo("fecha_inicio")} /></Campo>
        <Campo etiqueta="Hasta *"><input className="entrada" type="date" required {...campo("fecha_fin")} /></Campo>
        <Campo etiqueta="Días facturados" ayuda={`Opcional: los que indique la factura. Vacío = ${diasCalculados ?? "del primer al último día, ambos incluidos"}`}>
          <input className="entrada num" type="number" min="1" max="400" step="1" {...campo("dias")} placeholder={diasCalculados ? String(diasCalculados) : ""} />
        </Campo>
        <Campo etiqueta="Nº factura"><input className="entrada" {...campo("numero")} /></Campo>
        <Campo etiqueta="Comercializadora"><input className="entrada" {...campo("comercializadora")} /></Campo>
        <Campo etiqueta="Tarifa aplicada" className="sm:col-span-2">
          <select className="entrada" {...campo("tarifa_id")}>
            <option value="">— Sin indicar —</option>
            {tarifas.map((t) => <option key={t.id} value={t.id}>{t.comercializadora} · {t.nombre}</option>)}
          </select>
        </Campo>
      </Rejilla>
      <Seccion titulo="Consumo (kWh)">
        <Rejilla cols={3}>
          <Campo etiqueta="P1 punta" ayuda="L-V 10-14 y 18-22 h">{n("kwh_p1")}</Campo>
          <Campo etiqueta="P2 llano" ayuda="L-V 8-10, 14-18 y 22-24 h">{n("kwh_p2")}</Campo>
          <Campo etiqueta="P3 valle" ayuda="L-V 0-8 h, fines de semana y festivos">{n("kwh_p3")}</Campo>
        </Rejilla>
      </Seccion>
      <Seccion titulo="Potencia facturada (kW)">
        <Rejilla>
          <Campo etiqueta="P1 punta">{n("kw_p1", "0.001")}</Campo>
          <Campo etiqueta="P2 valle">{n("kw_p2", "0.001")}</Campo>
        </Rejilla>
      </Seccion>
      <Seccion titulo="Importes de la factura (€)">
        <Rejilla cols={2}>
          <Campo etiqueta="Total con IVA" ayuda="Sirve para validar el cálculo y como referencia de ahorro">{n("importe_total")}</Campo>
          <Campo etiqueta="Término de potencia">{n("importe_potencia")}</Campo>
          <Campo etiqueta="Término de energía">{n("importe_energia")}</Campo>
          <Campo etiqueta="Otros (servicios, ajustes…)">{n("importe_otros")}</Campo>
        </Rejilla>
      </Seccion>
      <Campo etiqueta="Notas" className="mt-5"><textarea className="entrada" rows={2} {...campo("notas")} /></Campo>
      <Pie enviando={enviando} error={error} cancelar={cancelar} />
    </form>
  );
}

// ---------------------------------------------------------------- Tarifa
export function FormTarifa({ inicial, hecho, cancelar }: { inicial?: Tarifa; hecho: () => void; cancelar: () => void }) {
  const unico = inicial ? inicial.energia_p1 === inicial.energia_p2 && inicial.energia_p2 === inicial.energia_p3 : false;
  const { v, campo, marca, setV } = useFormulario({
    comercializadora: inicial?.comercializadora ?? "",
    nombre: inicial?.nombre ?? "",
    tipo: inicial?.tipo ?? "fija",
    precio_unico: unico,
    potencia_p1: inicial?.potencia_p1 ?? "",
    potencia_p2: inicial?.potencia_p2 ?? "",
    energia_p1: inicial?.energia_p1 ?? "",
    energia_p2: inicial?.energia_p2 ?? "",
    energia_p3: inicial?.energia_p3 ?? "",
    cuota_fija_mes: inicial?.cuota_fija_mes ?? 0,
    descuento_energia_pct: inicial?.descuento_energia_pct ?? 0,
    incluye_bono_social: inicial?.incluye_bono_social ?? false,
    permanencia_meses: inicial?.permanencia_meses ?? 0,
    vigente_desde: inicial?.vigente_desde ?? "",
    url: inicial?.url ?? "",
    notas: inicial?.notas ?? "",
    activa: inicial?.activa ?? true,
  });
  const { enviar, enviando, error } = useEnvio(async () => {
    const e1 = aNum(v.energia_p1);
    const cuerpo = {
      comercializadora: v.comercializadora,
      nombre: v.nombre,
      tipo: v.tipo,
      potencia_p1: aNum(v.potencia_p1),
      potencia_p2: aNum(v.potencia_p2),
      energia_p1: e1,
      energia_p2: v.precio_unico ? e1 : aNum(v.energia_p2),
      energia_p3: v.precio_unico ? e1 : aNum(v.energia_p3),
      cuota_fija_mes: aNum(v.cuota_fija_mes),
      descuento_energia_pct: aNum(v.descuento_energia_pct),
      incluye_bono_social: v.incluye_bono_social,
      permanencia_meses: aNum(v.permanencia_meses),
      vigente_desde: aTexto(v.vigente_desde),
      url: aTexto(v.url),
      notas: aTexto(v.notas),
      activa: v.activa,
      origen: inicial?.origen ?? "manual",
    };
    if (inicial) await api.put(`/tarifas/${inicial.id}`, cuerpo);
    else await api.post("/tarifas", cuerpo);
  }, hecho);

  const n = (k: Parameters<typeof campo>[0], paso = "0.000001") => (
    <input className="entrada num" type="number" step={paso} min="0" required {...campo(k)} />
  );

  return (
    <form onSubmit={enviar}>
      <Rejilla cols={3}>
        <Campo etiqueta="Comercializadora *"><input className="entrada" required {...campo("comercializadora")} /></Campo>
        <Campo etiqueta="Nombre de la tarifa *"><input className="entrada" required {...campo("nombre")} /></Campo>
        <Campo etiqueta="Tipo">
          <select className="entrada" {...campo("tipo")}>
            <option value="fija">Precio fijo</option>
            <option value="indexada">Indexada</option>
            <option value="pvpc">PVPC (regulada)</option>
          </select>
        </Campo>
      </Rejilla>
      <Seccion titulo="Término de potencia (€/kW·día)">
        <Rejilla>
          <Campo etiqueta="P1 punta" ayuda="Si te lo dan en €/kW·año, divide entre 365">{n("potencia_p1")}</Campo>
          <Campo etiqueta="P2 valle">{n("potencia_p2")}</Campo>
        </Rejilla>
      </Seccion>
      {v.tipo === "pvpc" ? (
        <Seccion titulo="Término de energía">
          <Aviso>La energía del PVPC se calcula con el precio oficial de cada hora que publica Red Eléctrica. No hace falta introducirlo.</Aviso>
        </Seccion>
      ) : (
      <Seccion titulo="Término de energía (€/kWh)">
        <label className="mb-3 flex items-center gap-2 text-sm">
          <input type="checkbox" {...marca("precio_unico")} onChange={(e) => setV((x) => ({ ...x, precio_unico: e.target.checked }))} />
          Mismo precio a todas horas
        </label>
        <Rejilla cols={3}>
          <Campo etiqueta={v.precio_unico ? "Precio único" : "P1 punta"}>{n("energia_p1")}</Campo>
          {!v.precio_unico && <Campo etiqueta="P2 llano">{n("energia_p2")}</Campo>}
          {!v.precio_unico && <Campo etiqueta="P3 valle">{n("energia_p3")}</Campo>}
        </Rejilla>
      </Seccion>
      )}
      <Seccion titulo="Condiciones">
        <Rejilla cols={3}>
          <Campo etiqueta="Cuota fija (€/mes)" ayuda="Servicios o cuota de gestión">{n("cuota_fija_mes", "0.01")}</Campo>
          <Campo etiqueta="Descuento energía (%)">{n("descuento_energia_pct", "0.1")}</Campo>
          <Campo etiqueta="Permanencia (meses)">{n("permanencia_meses", "1")}</Campo>
          <Campo etiqueta="Precios vigentes desde"><input className="entrada" type="date" {...campo("vigente_desde")} /></Campo>
          <Campo etiqueta="Enlace a la oferta" className="sm:col-span-2"><input className="entrada" type="url" {...campo("url")} /></Campo>
        </Rejilla>
        <div className="mt-4 flex flex-wrap gap-6 text-sm">
          <label className="flex items-center gap-2"><input type="checkbox" {...marca("incluye_bono_social")} /> El precio ya incluye la financiación del bono social</label>
          <label className="flex items-center gap-2"><input type="checkbox" {...marca("activa")} /> Incluir en comparativas</label>
        </div>
      </Seccion>
      <Campo etiqueta="Notas" className="mt-5"><textarea className="entrada" rows={2} {...campo("notas")} /></Campo>
      <Pie enviando={enviando} error={error} cancelar={cancelar} />
    </form>
  );
}
