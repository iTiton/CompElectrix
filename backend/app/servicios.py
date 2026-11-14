"""Lógica de negocio que une la base de datos con el motor de cálculo."""

from __future__ import annotations

from datetime import date

from sqlmodel import Session, select

from .models import Domicilio, Factura, Tarifa, VigenciaRegulada
from .motor.calculo import DIAS_ANIO, Consumo, Desglose, PreciosTarifa, Vigencia, calcular


def a_consumo(f: Factura) -> Consumo:
    return Consumo(
        fecha_inicio=f.fecha_inicio,
        fecha_fin=f.fecha_fin,
        kwh_p1=f.kwh_p1,
        kwh_p2=f.kwh_p2,
        kwh_p3=f.kwh_p3,
        kw_p1=f.kw_p1,
        kw_p2=f.kw_p2,
    )


def a_precios(t: Tarifa) -> PreciosTarifa:
    return PreciosTarifa(
        potencia_p1=t.potencia_p1,
        potencia_p2=t.potencia_p2,
        energia_p1=t.energia_p1,
        energia_p2=t.energia_p2,
        energia_p3=t.energia_p3,
        cuota_fija_mes=t.cuota_fija_mes,
        descuento_energia_pct=t.descuento_energia_pct,
        incluye_bono_social=t.incluye_bono_social,
    )


def vigencias(s: Session) -> list[Vigencia]:
    return [
        Vigencia(**v.model_dump(exclude={"id", "nota"})) for v in s.exec(select(VigenciaRegulada))
    ]


def simular(s: Session, factura: Factura, tarifa: Tarifa) -> Desglose:
    return calcular(a_consumo(factura), a_precios(tarifa), vigencias(s))


def _r(x: float | None, n: int = 2) -> float | None:
    return None if x is None else round(x, n)


def comparar(
    s: Session,
    domicilio: Domicilio,
    desde: date | None = None,
    hasta: date | None = None,
    tarifa_ids: list[int] | None = None,
) -> dict:
    q = select(Factura).where(Factura.domicilio_id == domicilio.id)
    if desde:
        q = q.where(Factura.fecha_fin >= desde)
    if hasta:
        q = q.where(Factura.fecha_inicio <= hasta)
    facturas = list(s.exec(q.order_by(Factura.fecha_inicio)))

    qt = select(Tarifa)
    if tarifa_ids:
        qt = qt.where(Tarifa.id.in_(tarifa_ids))  # type: ignore[union-attr]
    else:
        qt = qt.where(Tarifa.activa == True)  # noqa: E712
    tarifas = list(s.exec(qt))
    actual = s.get(Tarifa, domicilio.tarifa_actual_id) if domicilio.tarifa_actual_id else None
    if actual and actual not in tarifas:
        tarifas.append(actual)

    base = {
        "domicilio": {"id": domicilio.id, "nombre": domicilio.nombre},
        "facturas": [],
        "tarifas": [],
        "resumen": None,
        "avisos": [],
    }
    if not facturas:
        base["avisos"].append("Este domicilio no tiene facturas en el periodo seleccionado.")
        return base
    if not tarifas:
        base["avisos"].append("No hay tarifas activas en el catálogo para comparar.")
        return base

    vig = vigencias(s)
    dias_totales = sum(a_consumo(f).dias for f in facturas)
    kwh_totales = sum(f.kwh_p1 + f.kwh_p2 + f.kwh_p3 for f in facturas)
    factor_anual = DIAS_ANIO / dias_totales
    reales = [f.importe_total for f in facturas if f.importe_total is not None]
    real_total = sum(reales) if len(reales) == len(facturas) else None

    resultados = []
    for t in tarifas:
        desgloses = [calcular(a_consumo(f), a_precios(t), vig) for f in facturas]
        total = sum(d.total for d in desgloses)
        avisos = sorted({a for d in desgloses for a in d.avisos})
        resultados.append(
            {
                "tarifa_id": t.id,
                "comercializadora": t.comercializadora,
                "nombre": t.nombre,
                "tipo": t.tipo,
                "es_actual": actual is not None and t.id == actual.id,
                "total_periodo": _r(total),
                "anual_estimado": _r(total * factor_anual),
                "mensual_medio": _r(total * factor_anual / 12),
                "precio_medio_kwh": _r(total / kwh_totales, 4) if kwh_totales else None,
                "por_factura": [_r(d.total) for d in desgloses],
                "desglose_total": _sumar_desgloses(desgloses),
                "avisos": avisos,
            }
        )
    resultados.sort(key=lambda r: r["total_periodo"])

    # Referencia del ahorro: tarifa actual simulada; si no hay, lo realmente pagado
    if actual:
        ref = next(r for r in resultados if r["es_actual"])
        ref_total, ref_origen = ref["total_periodo"], "tarifa_actual"
    elif real_total is not None:
        ref_total, ref_origen = real_total, "importe_real"
    else:
        ref_total, ref_origen = None, None
        base["avisos"].append(
            "Indica la tarifa actual del domicilio o el importe real de todas las facturas para calcular el ahorro."
        )

    for i, r in enumerate(resultados, start=1):
        r["posicion"] = i
        if ref_total is not None:
            ahorro = ref_total - r["total_periodo"]
            r["ahorro_periodo"] = _r(ahorro)
            r["ahorro_anual"] = _r(ahorro * factor_anual)
            r["ahorro_mensual"] = _r(ahorro * factor_anual / 12)
            r["ahorro_pct"] = _r(ahorro / ref_total * 100, 1) if ref_total else None

    filas = []
    for i, f in enumerate(facturas):
        fila = {
            "id": f.id,
            "fecha_inicio": f.fecha_inicio.isoformat(),
            "fecha_fin": f.fecha_fin.isoformat(),
            "dias": a_consumo(f).dias,
            "kwh_p1": f.kwh_p1,
            "kwh_p2": f.kwh_p2,
            "kwh_p3": f.kwh_p3,
            "importe_real": f.importe_total,
        }
        if actual:
            sim = next(r for r in resultados if r["es_actual"])["por_factura"][i]
            fila["importe_simulado_actual"] = sim
            if f.importe_total:
                fila["desviacion_pct"] = _r((sim - f.importe_total) / f.importe_total * 100, 1)
        filas.append(fila)

    base["facturas"] = filas
    base["tarifas"] = resultados
    base["resumen"] = {
        "num_facturas": len(facturas),
        "fecha_inicio": facturas[0].fecha_inicio.isoformat(),
        "fecha_fin": facturas[-1].fecha_fin.isoformat(),
        "dias": dias_totales,
        "kwh_total": _r(kwh_totales),
        "kwh_reparto_pct": {
            p: _r(sum(getattr(f, f"kwh_{p}") for f in facturas) / kwh_totales * 100, 1)
            if kwh_totales
            else 0
            for p in ("p1", "p2", "p3")
        },
        "importe_real_total": _r(real_total),
        "referencia": ref_origen,
        "referencia_total": _r(ref_total),
        "referencia_anual": _r(ref_total * factor_anual) if ref_total is not None else None,
        "mejor": resultados[0]["tarifa_id"],
        "cobertura_anual": dias_totales >= 360,
    }
    if dias_totales < 360:
        base["avisos"].append(
            f"Solo hay {dias_totales} días de datos: la estimación anual extrapola y no recoge la estacionalidad."
        )
    return base


def _sumar_desgloses(ds: list[Desglose]) -> dict:
    campos = [
        "potencia_p1", "potencia_p2", "energia_p1", "energia_p2", "energia_p3",
        "descuento_energia", "cuota_fija", "bono_social", "iee", "alquiler_contador", "iva", "total",
    ]  # fmt: skip
    return {c: round(sum(getattr(d, c) for d in ds), 2) for c in campos}
