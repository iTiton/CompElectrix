export interface Domicilio {
  id: number;
  nombre: string;
  direccion: string | null;
  cups: string | null;
  distribuidora: string | null;
  potencia_p1_kw: number;
  potencia_p2_kw: number;
  tarifa_actual_id: number | null;
  color: string | null;
  notas: string | null;
  num_facturas?: number;
  ultima_factura?: string | null;
  gasto_12m?: number | null;
}

export interface Tarifa {
  id: number;
  comercializadora: string;
  nombre: string;
  tipo: string;
  potencia_p1: number;
  potencia_p2: number;
  energia_p1: number;
  energia_p2: number;
  energia_p3: number;
  cuota_fija_mes: number;
  descuento_energia_pct: number;
  incluye_bono_social: boolean;
  permanencia_meses: number;
  url: string | null;
  notas: string | null;
  vigente_desde: string | null;
  origen: string;
  activa: boolean;
}

export interface Factura {
  id: number;
  domicilio_id: number;
  fecha_inicio: string;
  fecha_fin: string;
  comercializadora: string | null;
  tarifa_id: number | null;
  numero: string | null;
  kwh_p1: number;
  kwh_p2: number;
  kwh_p3: number;
  kw_p1: number;
  kw_p2: number;
  importe_total: number | null;
  importe_potencia: number | null;
  importe_energia: number | null;
  importe_otros: number | null;
  origen: string;
  notas: string | null;
}

export interface Vigencia {
  id: number;
  fecha_desde: string;
  fecha_hasta: string | null;
  iee_pct: number;
  iee_minimo_eur_mwh: number;
  iva_pct: number;
  alquiler_contador_eur_dia: number;
  bono_social_eur_anio: number;
  iee_incluye_bono_social: boolean;
  nota: string | null;
}

export interface Desglose {
  potencia_p1: number;
  potencia_p2: number;
  energia_p1: number;
  energia_p2: number;
  energia_p3: number;
  descuento_energia: number;
  cuota_fija: number;
  bono_social: number;
  iee: number;
  alquiler_contador: number;
  iva: number;
  total: number;
}

export interface ResultadoTarifa {
  tarifa_id: number;
  comercializadora: string;
  nombre: string;
  tipo: string;
  es_actual: boolean;
  precision: "horario" | "estimado" | null;
  posicion: number;
  total_periodo: number;
  anual_estimado: number;
  mensual_medio: number;
  precio_medio_kwh: number | null;
  por_factura: number[];
  desglose_total: Desglose;
  ahorro_periodo?: number;
  ahorro_anual?: number;
  ahorro_mensual?: number;
  ahorro_pct?: number | null;
  avisos: string[];
}

export interface Comparativa {
  domicilio: { id: number; nombre: string };
  facturas: {
    id: number;
    fecha_inicio: string;
    fecha_fin: string;
    dias: number;
    kwh_p1: number;
    kwh_p2: number;
    kwh_p3: number;
    importe_real: number | null;
    importe_simulado_actual?: number;
    desviacion_pct?: number | null;
  }[];
  tarifas: ResultadoTarifa[];
  resumen: null | {
    num_facturas: number;
    fecha_inicio: string;
    fecha_fin: string;
    dias: number;
    kwh_total: number;
    kwh_reparto_pct: { p1: number; p2: number; p3: number };
    importe_real_total: number | null;
    referencia: "tarifa_actual" | "importe_real" | null;
    referencia_total: number | null;
    referencia_anual: number | null;
    mejor: number;
    cobertura_anual: boolean;
  };
  avisos: string[];
}

async function peticion<T>(metodo: string, ruta: string, cuerpo?: unknown): Promise<T> {
  const r = await fetch(`/api${ruta}`, {
    method: metodo,
    headers: cuerpo ? { "Content-Type": "application/json" } : undefined,
    body: cuerpo ? JSON.stringify(cuerpo) : undefined,
  });
  if (!r.ok) {
    let msg = `Error ${r.status}`;
    try {
      const j = await r.json();
      if (typeof j.detail === "string") msg = j.detail;
      else if (Array.isArray(j.detail))
        msg = j.detail.map((d: { loc?: string[]; msg: string }) => `${d.loc?.slice(-1)[0] ?? ""}: ${d.msg}`).join(" · ");
    } catch {
      /* respuesta sin JSON */
    }
    throw new Error(msg);
  }
  return (r.status === 204 ? undefined : await r.json()) as T;
}

export const api = {
  get: <T>(ruta: string) => peticion<T>("GET", ruta),
  post: <T>(ruta: string, cuerpo: unknown) => peticion<T>("POST", ruta, cuerpo),
  put: <T>(ruta: string, cuerpo: unknown) => peticion<T>("PUT", ruta, cuerpo),
  del: (ruta: string) => peticion<void>("DELETE", ruta),
};

export interface EstadoPvpc {
  horas: number;
  desde: string | null;
  hasta: string | null;
  ultima_sync: string | null;
  ultimo_error: string | null;
  en_curso: boolean;
  progreso: string | null;
  mensaje: string | null;
}

export interface HoraPvpc {
  hora: string;
  precio: number;
  periodo: "p1" | "p2" | "p3";
}

export interface DiaPvpc {
  dia: string;
  horas: HoraPvpc[];
  media: number | null;
  minimo: HoraPvpc | null;
  maximo: HoraPvpc | null;
}

export interface ResumenConsumo {
  horas: number;
  desde: string | null;
  hasta: string | null;
  meses: {
    mes: string;
    kwh_p1: number;
    kwh_p2: number;
    kwh_p3: number;
    kwh_total: number;
    horas: number;
    horas_esperadas: number;
    completo: boolean;
    estimadas: number;
  }[];
}

export interface SuministroDatadis {
  cups: string;
  direccion: string;
  distribuidora: string;
  codigo_distribuidora: string;
  tipo_punto: number | string;
  desde: string | null;
  hasta: string | null;
}

export interface SuministroOctopus {
  cuenta: string;
  propiedad_id: string;
  direccion: string | null;
  cups_luz: string[];
  cups_gas: string[];
}

export interface ResultadoImportacion {
  horas: number;
  avisos: string[];
  desde?: string;
  hasta?: string;
}
