"""Motor de cálculo de facturas eléctricas en baja tensión (peaje 2.0TD).

Funciones puras, sin acceso a base de datos, para que se puedan probar
de forma aislada. Todos los importes en euros, energía en kWh y potencia en kW.

Estructura del cálculo (orden de una factura española):
  1. Término de potencia  = Σ kW contratados(Pi) · precio(Pi) €/kW·día · días
  2. Término de energía   = Σ kWh(Pi) · precio(Pi) €/kWh  (− descuento sobre energía)
  3. Cuota fija / servicios de la comercializadora (prorrateada por días)
  4. Financiación del bono social (si la tarifa no la incluye ya en precio)
  5. Impuesto especial sobre la electricidad (IEE) = máx(% · base, mínimo €/MWh · MWh)
  6. Alquiler del contador
  7. IVA sobre todo lo anterior

Los parámetros regulados (IEE, IVA, alquiler, bono social) cambian con el
tiempo, por eso se reciben como una lista de vigencias y el periodo de la
factura se prorratea por días entre ellas.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

DIAS_ANIO = 365


@dataclass(frozen=True)
class Consumo:
    fecha_inicio: date
    fecha_fin: date  # inclusive, como en las facturas ("del 1 al 31: 31 días")
    kwh_p1: float = 0.0
    kwh_p2: float = 0.0
    kwh_p3: float = 0.0
    kw_p1: float = 0.0
    kw_p2: float = 0.0

    @property
    def dias(self) -> int:
        return (self.fecha_fin - self.fecha_inicio).days + 1

    @property
    def kwh_total(self) -> float:
        return self.kwh_p1 + self.kwh_p2 + self.kwh_p3


@dataclass(frozen=True)
class PreciosTarifa:
    potencia_p1: float  # €/kW·día
    potencia_p2: float  # €/kW·día
    energia_p1: float  # €/kWh
    energia_p2: float
    energia_p3: float
    cuota_fija_mes: float = 0.0  # € al mes (servicios, cuota de gestión...)
    descuento_energia_pct: float = 0.0  # % sobre el término de energía
    incluye_bono_social: bool = False  # True si el precio ya lo lleva dentro


@dataclass(frozen=True)
class Vigencia:
    fecha_desde: date
    fecha_hasta: date | None  # None = vigente sin fecha de fin
    iee_pct: float = 5.11269632
    iee_minimo_eur_mwh: float = 1.0
    iva_pct: float = 21.0
    alquiler_contador_eur_dia: float = 0.81 * 12 / DIAS_ANIO
    bono_social_eur_anio: float = 0.0
    iee_incluye_bono_social: bool = False

    def cubre(self, dia: date) -> bool:
        return self.fecha_desde <= dia and (self.fecha_hasta is None or dia <= self.fecha_hasta)


@dataclass
class Desglose:
    dias: int
    kwh_total: float
    potencia_p1: float = 0.0
    potencia_p2: float = 0.0
    energia_p1: float = 0.0
    energia_p2: float = 0.0
    energia_p3: float = 0.0
    descuento_energia: float = 0.0
    cuota_fija: float = 0.0
    bono_social: float = 0.0
    base_iee: float = 0.0
    iee: float = 0.0
    alquiler_contador: float = 0.0
    base_iva: float = 0.0
    iva: float = 0.0
    total: float = 0.0
    avisos: list[str] = field(default_factory=list)

    @property
    def termino_potencia(self) -> float:
        return self.potencia_p1 + self.potencia_p2

    @property
    def termino_energia(self) -> float:
        return self.energia_p1 + self.energia_p2 + self.energia_p3 - self.descuento_energia

    def a_dict(self) -> dict:
        d = asdict(self)
        d["termino_potencia"] = self.termino_potencia
        d["termino_energia"] = self.termino_energia
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()}


def repartir_dias(
    inicio: date, fin: date, vigencias: list[Vigencia]
) -> tuple[list[tuple[Vigencia, int]], int]:
    """Agrupa los días del periodo por la vigencia que aplica a cada uno.

    Si hay solapes gana la vigencia que empieza más tarde (la más reciente).
    Los días sin vigencia se asignan a la más cercana; se devuelve cuántos son
    para poder avisar.
    """
    if not vigencias:
        raise ValueError("No hay parámetros regulados configurados")
    ordenadas = sorted(vigencias, key=lambda v: v.fecha_desde, reverse=True)
    conteo: dict[int, int] = {}
    sin_vigencia = 0
    dia = inicio
    while dia <= fin:
        idx = next((i for i, v in enumerate(ordenadas) if v.cubre(dia)), None)
        if idx is None:
            sin_vigencia += 1
            # anterior a todas -> la más antigua; en otro caso, la más reciente que ya empezó
            idx = next(
                (i for i, v in enumerate(ordenadas) if v.fecha_desde <= dia), len(ordenadas) - 1
            )
        conteo[idx] = conteo.get(idx, 0) + 1
        dia += timedelta(days=1)
    return [(ordenadas[i], n) for i, n in sorted(conteo.items())], sin_vigencia


def vigencia_en(vigencias: list[Vigencia], dia: date) -> Vigencia:
    """Vigencia aplicable un día (la que empezó más tarde si se solapan; la más cercana si no hay)."""
    ordenadas = sorted(vigencias, key=lambda v: v.fecha_desde, reverse=True)
    return next((v for v in ordenadas if v.cubre(dia)), None) or next(
        (v for v in ordenadas if v.fecha_desde <= dia), ordenadas[-1]
    )


def calcular(
    consumo: Consumo, tarifa: PreciosTarifa, vigencias: list[Vigencia], fecha_devengo: date | None = None
) -> Desglose:
    """Calcula una factura.

    `fecha_devengo` (la fecha de emisión de la factura): si se indica, el impuesto eléctrico y el IVA se aplican a
    toda la factura con los tipos de ese día, que es como lo hacen las comercializadoras (el impuesto se devenga al
    facturar). El bono social y el alquiler siguen contando por días. Sin ella, todo se prorratea por días.
    """
    dias = consumo.dias
    if dias <= 0:
        raise ValueError("La fecha de fin debe ser igual o posterior a la de inicio")

    d = Desglose(dias=dias, kwh_total=consumo.kwh_total)

    # 1. Potencia
    d.potencia_p1 = consumo.kw_p1 * tarifa.potencia_p1 * dias
    d.potencia_p2 = consumo.kw_p2 * tarifa.potencia_p2 * dias

    # 2. Energía
    d.energia_p1 = consumo.kwh_p1 * tarifa.energia_p1
    d.energia_p2 = consumo.kwh_p2 * tarifa.energia_p2
    d.energia_p3 = consumo.kwh_p3 * tarifa.energia_p3
    bruto_energia = d.energia_p1 + d.energia_p2 + d.energia_p3
    d.descuento_energia = bruto_energia * tarifa.descuento_energia_pct / 100

    # 3. Cuota fija prorrateada
    d.cuota_fija = tarifa.cuota_fija_mes * 12 / DIAS_ANIO * dias

    base_suministro = d.termino_potencia + d.termino_energia

    # 4-7. Conceptos regulados, prorrateados por vigencia
    tramos, dias_sin = repartir_dias(consumo.fecha_inicio, consumo.fecha_fin, vigencias)
    if dias_sin:
        d.avisos.append(
            f"{dias_sin} día(s) sin parámetros regulados configurados; se han usado los más cercanos"
        )

    devengo = vigencia_en(vigencias, fecha_devengo) if fecha_devengo else None
    for vig, n in tramos:
        f = n / dias
        imp = devengo or vig  # tipos de los impuestos: los de la fecha de la factura o los de cada día
        bono = 0.0 if tarifa.incluye_bono_social else vig.bono_social_eur_anio / DIAS_ANIO * n
        base_iee = base_suministro * f + (bono if imp.iee_incluye_bono_social else 0.0)
        alquiler = vig.alquiler_contador_eur_dia * n
        d.bono_social += bono
        d.base_iee += base_iee
        d.alquiler_contador += alquiler
        if devengo is None:
            iee = max(base_iee * vig.iee_pct / 100, consumo.kwh_total * f / 1000 * vig.iee_minimo_eur_mwh)
            base_iva = base_suministro * f + bono + iee + alquiler + d.cuota_fija * f
            d.iee += iee
            d.base_iva += base_iva
            d.iva += base_iva * vig.iva_pct / 100

    if devengo is not None:
        d.iee = max(d.base_iee * devengo.iee_pct / 100, consumo.kwh_total / 1000 * devengo.iee_minimo_eur_mwh)
        d.base_iva = base_suministro + d.bono_social + d.iee + d.alquiler_contador + d.cuota_fija
        d.iva = d.base_iva * devengo.iva_pct / 100

    d.total = d.base_iva + d.iva
    return d
