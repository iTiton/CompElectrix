"""Lógica de negocio que une la base de datos con el motor de cálculo."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Session, func, select

from .models import ConsumoHorario, Domicilio, Factura, PotenciaContratada, PrecioHorario, Tarifa, VigenciaRegulada
from .motor.calculo import DIAS_ANIO, Consumo, Desglose, PreciosTarifa, Vigencia, calcular
from .motor.periodos import a_local, horas_esperadas, limites_utc, periodo_local, periodo_utc


def fin_efectivo(f: Factura) -> date:
    """Último día que cubre la factura. Si indica sus días (p. ej. Octopus cuenta del 21 al 20 como 29),
    el periodo termina el día anterior a la fecha de fin; si no, la fecha de fin está incluida."""
    return f.fecha_inicio + timedelta(days=f.dias - 1) if f.dias else f.fecha_fin


def a_consumo(f: Factura) -> Consumo:
    return Consumo(
        fecha_inicio=f.fecha_inicio,
        fecha_fin=fin_efectivo(f),
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
    return calcular(a_consumo(factura), a_precios(tarifa), vigencias(s), factura.fecha_emision)


def _r(x: float | None, n: int = 2) -> float | None:
    return None if x is None else round(x, n)


def comparar(
    s: Session,
    domicilio: Domicilio,
    desde: date | None = None,
    hasta: date | None = None,
    tarifa_ids: list[int] | None = None,
    modo: str = "hoy",
) -> dict:
    """Compara las tarifas sobre las facturas del domicilio.

    modo «hoy»: referencia = la tarifa actual con sus precios de hoy (para decidir de cara al futuro).
    modo «pagado»: solo facturas con importe real; referencia = lo que se pagó de verdad, frente a cada tarifa
    (el PVPC, con sus precios reales de esas fechas): pasado contra pasado.
    """
    q = select(Factura).where(Factura.domicilio_id == domicilio.id)
    if desde:
        q = q.where(Factura.fecha_fin >= desde)
    if hasta:
        q = q.where(Factura.fecha_inicio <= hasta)
    facturas = list(s.exec(q.order_by(Factura.fecha_inicio)))
    if modo == "pagado":
        facturas = [f for f in facturas if f.importe_total is not None]
        if not facturas:
            return {
                "domicilio": {"id": domicilio.id, "nombre": domicilio.nombre}, "facturas": [], "tarifas": [],
                "resumen": None,
                "avisos": ["No hay facturas con importe real en ese periodo. Tráelas de Octopus o anota lo que pagaste en cada factura."],
            }  # fmt: skip

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

    horarios = None
    if any(t.tipo == "pvpc" for t in tarifas):
        horarios = DatosHorarios(s, domicilio.id, facturas[0].fecha_inicio, max(f.fecha_fin for f in facturas))

    resultados = []
    for t in tarifas:
        base_precios = a_precios(t)
        desgloses, modos = [], []
        for f in facturas:
            precios = base_precios
            if t.tipo == "pvpc" and horarios is not None:
                r = horarios.precios_energia_pvpc(f)
                if r is None:
                    break
                e, modo_pvpc = r
                precios = replace(base_precios, energia_p1=e["p1"], energia_p2=e["p2"], energia_p3=e["p3"])
                modos.append(modo_pvpc)
            desgloses.append(calcular(a_consumo(f), precios, vig, f.fecha_emision))
        if len(desgloses) < len(facturas):
            base["avisos"].append(
                f"«{t.nombre}» no se ha incluido: faltan precios del PVPC para algunas fechas. "
                "Actualízalos en Ajustes."
            )
            continue
        total = sum(d.total for d in desgloses)
        avisos = sorted({a for d in desgloses for a in d.avisos})
        precision = None
        if modos:
            precision = "horario" if all(m == "horario" for m in modos) else "estimado"
            if precision == "estimado":
                avisos.append(
                    "PVPC estimado con el precio medio de cada periodo: importa tu consumo horario "
                    "para calcularlo hora a hora."
                )
        resultados.append(
            {
                "tarifa_id": t.id,
                "comercializadora": t.comercializadora,
                "nombre": t.nombre,
                "tipo": t.tipo,
                "es_actual": actual is not None and t.id == actual.id,
                "es_real": False,
                "precision": precision,
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
    if not resultados:
        return base

    # Referencia del ahorro: tarifa actual simulada; si no hay (o en modo «pagado»), lo realmente pagado
    ref_actual = next((r for r in resultados if r["es_actual"]), None)
    if modo == "pagado" and real_total is not None:
        total_real = round(real_total, 2)
        resultados.append({
            "tarifa_id": 0, "comercializadora": "Tus facturas", "nombre": "Lo que pagaste", "tipo": "real",
            "es_actual": False, "es_real": True, "precision": None,
            "total_periodo": total_real, "anual_estimado": _r(total_real * factor_anual),
            "mensual_medio": _r(total_real * factor_anual / 12),
            "precio_medio_kwh": _r(total_real / kwh_totales, 4) if kwh_totales else None,
            "por_factura": [f.importe_total for f in facturas], "desglose_total": None, "avisos": [],
        })  # fmt: skip
        resultados.sort(key=lambda r: r["total_periodo"])
        ref_total, ref_origen = total_real, "importe_real"
    elif ref_actual:
        ref = ref_actual
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
        if ref_actual:
            sim = ref_actual["por_factura"][i]
            fila["importe_simulado_actual"] = sim
            if f.importe_total:
                fila["desviacion_pct"] = _r((sim - f.importe_total) / f.importe_total * 100, 1)
        filas.append(fila)

    # El PVPC depende del mercado: si gana, se indica en qué facturas habría salido más caro
    mejor = resultados[0]
    ref_por_factura = (
        [f.importe_total for f in facturas] if ref_origen == "importe_real" and real_total is not None
        else (ref_actual["por_factura"] if ref_actual else None)
    )
    if mejor["tipo"] == "pvpc" and ref_por_factura:
        peores = [
            f"{f.fecha_inicio:%m/%Y}" for f, pv, ref in zip(facturas, mejor["por_factura"], ref_por_factura, strict=False)
            if ref is not None and pv > ref
        ]  # fmt: skip
        texto = (
            "El PVPC sale más barato con los precios de mercado de este periodo, pero cambia cada hora y nadie "
            "garantiza que el futuro se parezca al pasado."
        )
        if peores:
            texto += f" Habría salido más caro en {len(peores)} de {len(facturas)} facturas: {', '.join(peores)}."
        base["avisos"].append(texto)

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
        "modo": modo,
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


# ============================================================ Consumo horario
def guardar_consumo(s: Session, domicilio_id: int, horas: list[tuple[datetime, float, bool]], origen: str) -> int:
    """Inserta o sustituye horas de consumo. Devuelve cuántas se han guardado."""
    filas = [
        {"domicilio_id": domicilio_id, "inicio_utc": h, "kwh": k, "real": real, "origen": origen}
        for h, k, real in horas
    ]
    for i in range(0, len(filas), 500):
        stmt = sqlite_insert(ConsumoHorario).values(filas[i : i + 500])
        stmt = stmt.on_conflict_do_update(
            index_elements=["domicilio_id", "inicio_utc"],
            set_={"kwh": stmt.excluded.kwh, "real": stmt.excluded.real, "origen": stmt.excluded.origen},
        )
        s.exec(stmt)  # type: ignore[call-overload]
    s.commit()
    return len(filas)


def _consumo_por_mes(s: Session, domicilio_id: int) -> dict[tuple[int, int], dict]:
    meses: dict[tuple[int, int], dict] = {}
    q = select(ConsumoHorario).where(ConsumoHorario.domicilio_id == domicilio_id)
    for c in s.exec(q):
        local = a_local(c.inicio_utc)
        m = meses.setdefault(
            (local.year, local.month), {"p1": 0.0, "p2": 0.0, "p3": 0.0, "horas": 0, "estimadas": 0}
        )
        m[periodo_local(local)] += c.kwh
        m["horas"] += 1
        m["estimadas"] += 0 if c.real else 1
    return meses


def _ultimo_dia(anio: int, mes: int) -> date:
    return (date(anio, mes, 28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def resumen_consumo(s: Session, domicilio_id: int) -> dict:
    meses = _consumo_por_mes(s, domicilio_id)
    lista = []
    for (a, m), v in sorted(meses.items()):
        esperadas = horas_esperadas(date(a, m, 1), _ultimo_dia(a, m))
        lista.append(
            {
                "mes": f"{a}-{m:02d}",
                "kwh_p1": round(v["p1"], 3),
                "kwh_p2": round(v["p2"], 3),
                "kwh_p3": round(v["p3"], 3),
                "kwh_total": round(v["p1"] + v["p2"] + v["p3"], 3),
                "horas": v["horas"],
                "horas_esperadas": esperadas,
                "completo": v["horas"] >= esperadas,
                "estimadas": v["estimadas"],
            }
        )
    mn, mx, n = s.exec(
        select(func.min(ConsumoHorario.inicio_utc), func.max(ConsumoHorario.inicio_utc), func.count())
        .where(ConsumoHorario.domicilio_id == domicilio_id)
    ).one()
    return {
        "horas": n,
        "desde": a_local(mn).date().isoformat() if mn else None,
        "hasta": a_local(mx).date().isoformat() if mx else None,
        "meses": lista,
    }


def generar_facturas_desde_consumo(s: Session, dom: Domicilio) -> dict:
    """Crea una 'factura' por cada mes completo de consumo horario que no tenga ya factura."""
    existentes = list(s.exec(select(Factura).where(Factura.domicilio_id == dom.id)))
    tramos = tramos_potencia(s, dom.id)
    creadas, con_factura, incompletos = [], [], []
    for (a, m), v in sorted(_consumo_por_mes(s, dom.id).items()):
        ini, fin = date(a, m, 1), _ultimo_dia(a, m)
        etiqueta = f"{m:02d}/{a}"
        if v["horas"] < horas_esperadas(ini, fin):
            incompletos.append(etiqueta)
            continue
        if any(f.fecha_inicio <= fin and f.fecha_fin >= ini for f in existentes):
            con_factura.append(etiqueta)
            continue
        kw1, kw2 = potencia_media(tramos, ini, fin, (dom.potencia_p1_kw, dom.potencia_p2_kw))
        f = Factura(
            domicilio_id=dom.id, fecha_inicio=ini, fecha_fin=fin,
            kwh_p1=round(v["p1"], 3), kwh_p2=round(v["p2"], 3), kwh_p3=round(v["p3"], 3),
            kw_p1=kw1, kw_p2=kw2, origen="horario",
            notas="Generada a partir del consumo horario (sin importe real).",
        )  # fmt: skip
        s.add(f)
        creadas.append(etiqueta)
    s.commit()
    return {"creadas": creadas, "con_factura": con_factura, "incompletos": incompletos}


# ======================================================================= PVPC
class DatosHorarios:
    """Precios PVPC y consumo horario de un rango, cargados una vez para toda la comparativa."""

    def __init__(self, s: Session, domicilio_id: int, desde: date, hasta: date):
        ini, fin = limites_utc(desde, hasta)
        self.precios = {
            p.inicio_utc: p.precio_eur_kwh
            for p in s.exec(
                select(PrecioHorario).where(
                    PrecioHorario.serie == "pvpc", PrecioHorario.inicio_utc >= ini, PrecioHorario.inicio_utc < fin
                )
            )
        }
        self.consumo = {
            c.inicio_utc: c.kwh
            for c in s.exec(
                select(ConsumoHorario).where(
                    ConsumoHorario.domicilio_id == domicilio_id,
                    ConsumoHorario.inicio_utc >= ini,
                    ConsumoHorario.inicio_utc < fin,
                )
            )
        }

    def precios_energia_pvpc(self, f: Factura) -> tuple[dict[str, float], str] | None:
        """Precio efectivo €/kWh por periodo para una factura y cómo se ha obtenido.

        - 'horario': hay consumo y precio para todas las horas → coste exacto hora a hora,
          expresado como precio medio ponderado de cada periodo.
        - 'estimado': hay precios pero no consumo horario completo → media simple del PVPC
          de cada periodo en esas fechas (supone consumo repartido por igual).
        None si faltan precios.
        """
        ini, fin = limites_utc(f.fecha_inicio, fin_efectivo(f))
        horas = [ini + timedelta(hours=i) for i in range(int((fin - ini).total_seconds() // 3600))]
        if not horas or any(h not in self.precios for h in horas):
            return None
        coste = {"p1": 0.0, "p2": 0.0, "p3": 0.0}
        kwh = {"p1": 0.0, "p2": 0.0, "p3": 0.0}
        suma = {"p1": 0.0, "p2": 0.0, "p3": 0.0}
        n = {"p1": 0, "p2": 0, "p3": 0}
        completo = all(h in self.consumo for h in horas)
        for h in horas:
            p = periodo_utc(h)
            suma[p] += self.precios[h]
            n[p] += 1
            if completo:
                coste[p] += self.precios[h] * self.consumo[h]
                kwh[p] += self.consumo[h]
        media = {p: (suma[p] / n[p] if n[p] else 0.0) for p in suma}
        if completo:
            return {p: (coste[p] / kwh[p] if kwh[p] else media[p]) for p in coste}, "horario"
        return media, "estimado"


# ================================================== Historial de potencias
def tramos_potencia(s: Session, domicilio_id: int) -> list[PotenciaContratada]:
    q = select(PotenciaContratada).where(PotenciaContratada.domicilio_id == domicilio_id)
    return sorted(s.exec(q), key=lambda p: p.desde)


def potencia_en(tramos: list[PotenciaContratada], dia: date) -> tuple[float, float] | None:
    """Potencia vigente un día. Si dos tramos se solapan, manda el que empezó más tarde."""
    for p in reversed(tramos):
        if p.desde <= dia and (p.hasta is None or dia <= p.hasta):
            return p.kw_p1, p.kw_p2
    return None


def potencia_media(tramos: list[PotenciaContratada], desde: date, hasta: date, defecto: tuple[float, float]) -> tuple[float, float]:
    """Potencia media de un periodo ponderada por días.

    Como la potencia se paga por kW y día, la media ponderada da exactamente el mismo importe
    que facturar cada tramo por separado. Los días sin tramo usan la potencia del domicilio.
    """
    dias = (hasta - desde).days + 1
    suma1 = suma2 = 0.0
    d = desde
    while d <= hasta:
        kw1, kw2 = potencia_en(tramos, d) or defecto
        suma1 += kw1
        suma2 += kw2
        d += timedelta(days=1)
    return round(suma1 / dias, 4), round(suma2 / dias, 4)


def recalcular_potencia_facturas(s: Session, dom: Domicilio) -> int:
    """Aplica el historial a las facturas creadas desde el consumo horario (no a las introducidas a mano)."""
    tramos = tramos_potencia(s, dom.id)
    n = 0
    for f in s.exec(select(Factura).where(Factura.domicilio_id == dom.id, Factura.origen == "horario")):
        kw = potencia_media(tramos, f.fecha_inicio, fin_efectivo(f), (dom.potencia_p1_kw, dom.potencia_p2_kw))
        if (f.kw_p1, f.kw_p2) != kw:
            f.kw_p1, f.kw_p2 = kw
            s.add(f)
            n += 1
    s.commit()
    return n


def sincronizar_potencia_actual(s: Session, dom: Domicilio) -> None:
    """La potencia «actual» del domicilio es la del tramo vigente hoy, si lo hay."""
    actual = potencia_en(tramos_potencia(s, dom.id), date.today())
    if actual and (dom.potencia_p1_kw, dom.potencia_p2_kw) != actual:
        dom.potencia_p1_kw, dom.potencia_p2_kw = actual
        s.add(dom)
        s.commit()


def guardar_tramos_importados(s: Session, dom: Domicilio, tramos: list[dict], origen: str) -> int:
    """Sustituye los tramos de un origen (octopus, datadis) por los recién importados. Los manuales no se tocan.
    Los tramos seguidos con la misma potencia se juntan en uno (Octopus crea un contrato por cada cambio de precios)."""
    tramos = juntar_tramos(tramos)
    for p in s.exec(select(PotenciaContratada).where(
        PotenciaContratada.domicilio_id == dom.id, PotenciaContratada.origen == origen
    )):  # fmt: skip
        s.delete(p)
    for t in tramos:
        s.add(PotenciaContratada(domicilio_id=dom.id, origen=origen, **t))
    s.commit()
    sincronizar_potencia_actual(s, dom)
    recalcular_potencia_facturas(s, dom)
    return len(tramos)


# ============================================ Importes calculados por factura
def importes_calculados(s: Session, dom: Domicilio) -> dict:
    """Importe de cada factura según su tarifa (o la actual del domicilio), para las que no tienen importe real."""
    facturas = list(s.exec(select(Factura).where(Factura.domicilio_id == dom.id)))
    if not facturas:
        return {"importes": {}, "tarifa_actual": None}
    actual = s.get(Tarifa, dom.tarifa_actual_id) if dom.tarifa_actual_id else None
    vig = vigencias(s)
    horarios = None
    tarifas: dict[int, Tarifa | None] = {}
    importes = {}
    for f in facturas:
        tid = f.tarifa_id or (actual.id if actual else None)
        if tid is None:
            continue
        if tid not in tarifas:
            tarifas[tid] = s.get(Tarifa, tid)
        t = tarifas[tid]
        if t is None:
            continue
        precios, precision = a_precios(t), None
        if t.tipo == "pvpc":
            if horarios is None:
                horarios = DatosHorarios(
                    s, dom.id, min(x.fecha_inicio for x in facturas), max(fin_efectivo(x) for x in facturas)
                )
            r = horarios.precios_energia_pvpc(f)
            if r is None:
                continue  # faltan precios del PVPC para esas fechas
            e, precision = r
            precios = replace(precios, energia_p1=e["p1"], energia_p2=e["p2"], energia_p3=e["p3"])
        d = calcular(a_consumo(f), precios, vig, f.fecha_emision)
        importes[f.id] = {"total": round(d.total, 2), "tarifa": t.nombre, "precision": precision}
    return {"importes": importes, "tarifa_actual": actual.nombre if actual else None}


# ======================================== Facturas reales traídas de Octopus
def _kwh_por_periodo(s: Session, domicilio_id: int, desde: date, hasta: date) -> tuple[dict[str, float], int, int]:
    """kWh por periodo del consumo horario entre dos días (incluidos), horas con dato y horas esperadas."""
    ini, fin = limites_utc(desde, hasta)
    kwh = {"p1": 0.0, "p2": 0.0, "p3": 0.0}
    n = 0
    q = select(ConsumoHorario).where(
        ConsumoHorario.domicilio_id == domicilio_id, ConsumoHorario.inicio_utc >= ini, ConsumoHorario.inicio_utc < fin
    )
    for c in s.exec(q):
        kwh[periodo_utc(c.inicio_utc)] += c.kwh
        n += 1
    return kwh, n, horas_esperadas(desde, hasta)


def elegir_fin(s: Session, domicilio_id: int, f: dict) -> tuple[date, str]:
    """Octopus no siempre incluye el último día del periodo. Se decide comparando los kWh facturados con el
    consumo horario contando y sin contar ese día; sin kWh, se usa lo visto en sus facturas (lo incluye
    solo cuando el periodo termina el 31 de diciembre)."""
    con = f["hasta"]
    sin = f["hasta"] - timedelta(days=1) if f["hasta"] > f["desde"] else f["hasta"]
    if f.get("kwh"):
        k_con = sum(_kwh_por_periodo(s, domicilio_id, f["desde"], con)[0].values())
        k_sin = sum(_kwh_por_periodo(s, domicilio_id, f["desde"], sin)[0].values())
        if k_con or k_sin:
            return (con, "kwh") if abs(k_con - f["kwh"]) < abs(k_sin - f["kwh"]) else (sin, "kwh")
    return (con if (f["hasta"].month, f["hasta"].day) == (12, 31) else sin), "regla"


def importar_facturas_octopus(s: Session, dom: Domicilio, facturas: list[dict]) -> dict:
    """Crea (o actualiza) una factura por cada factura de Octopus, con su periodo, emisión y total reales.

    Los kWh por periodo salen del consumo horario de esas fechas. Sustituye a las facturas mensuales creadas desde
    el consumo que se solapen; las introducidas a mano no se tocan.
    """
    existentes = list(s.exec(select(Factura).where(Factura.domicilio_id == dom.id)))
    por_numero = {f.numero: f for f in existentes if f.origen == "octopus" and f.numero}
    tramos = tramos_potencia(s, dom.id)
    creadas = actualizadas = sustituidas = 0
    omitidas: list[str] = []
    for fo in facturas:
        etiqueta = f"{fo['desde']:%d/%m/%Y}–{fo['hasta']:%d/%m/%Y}"
        fin, _metodo = elegir_fin(s, dom.id, fo)
        kwh, horas, esperadas = _kwh_por_periodo(s, dom.id, fo["desde"], fin)
        if horas < esperadas:
            omitidas.append(f"{etiqueta} (consumo horario incompleto: {horas}/{esperadas} h)")
            continue
        manual = next(
            (f for f in existentes if f.origen not in ("horario", "octopus") and f.fecha_inicio <= fin and fin_efectivo(f) >= fo["desde"]),
            None,
        )
        if manual:
            omitidas.append(f"{etiqueta} (ya hay una factura introducida a mano en esas fechas)")
            continue
        solapadas = [
            f for f in existentes if f.origen == "horario" and f.fecha_inicio <= fin and fin_efectivo(f) >= fo["desde"]
        ]
        for f in solapadas:
            s.delete(f)
            sustituidas += 1
        existentes = [f for f in existentes if f not in solapadas]
        kw1, kw2 = potencia_media(tramos, fo["desde"], fin, (dom.potencia_p1_kw, dom.potencia_p2_kw))
        datos = {
            "fecha_inicio": fo["desde"], "fecha_fin": fo["hasta"], "dias": (fin - fo["desde"]).days + 1,
            "fecha_emision": fo["emision"], "kwh_p1": round(kwh["p1"], 3), "kwh_p2": round(kwh["p2"], 3),
            "kwh_p3": round(kwh["p3"], 3), "kw_p1": kw1, "kw_p2": kw2, "importe_total": fo["total"],
            "comercializadora": "Octopus Energy",
        }  # fmt: skip
        nota = f"Factura de Octopus. kWh facturados: {fo['kwh']}" if fo.get("kwh") is not None else "Factura de Octopus."
        if fo["id"] in por_numero:
            f = por_numero[fo["id"]]
            for k, v in datos.items():
                setattr(f, k, v)
            f.notas = nota
            actualizadas += 1
        else:
            f = Factura(domicilio_id=dom.id, numero=fo["id"], origen="octopus", notas=nota, **datos)
            creadas += 1
        s.add(f)
    s.commit()
    return {"creadas": creadas, "actualizadas": actualizadas, "sustituidas": sustituidas, "omitidas": omitidas}


def juntar_tramos(tramos: list[dict]) -> list[dict]:
    """Une tramos seguidos (o solapados) con la misma potencia en uno solo."""
    salida: list[dict] = []
    for t in sorted(tramos, key=lambda x: x["desde"]):
        if salida:
            prev = salida[-1]
            misma = (prev["kw_p1"], prev["kw_p2"]) == (t["kw_p1"], t["kw_p2"])
            pegado = prev["hasta"] is None or t["desde"] <= prev["hasta"] + timedelta(days=1)
            if misma and pegado:
                if prev["hasta"] is not None:
                    prev["hasta"] = None if t["hasta"] is None else max(prev["hasta"], t["hasta"])
                continue
        salida.append(dict(t))
    return salida
