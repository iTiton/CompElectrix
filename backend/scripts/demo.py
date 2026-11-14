"""Carga datos de ejemplo INVENTADOS para probar la aplicación.

Uso:  python -m scripts.demo   (desde backend/, con la base de datos vacía)
"""

from datetime import date, datetime, timedelta

from sqlmodel import Session, select

from app.db import engine, init_db
from app.models import Domicilio, Factura, Tarifa
from app.motor.periodos import a_local, limites_utc, periodo_utc
from app.servicios import guardar_consumo

TARIFAS = [
    # comercializadora, nombre, tipo, pot P1, pot P2, en P1, en P2, en P3, cuota
    ("Ejemplo Energía", "Fija 24h", "fija", 0.0899, 0.0459, 0.139, 0.139, 0.139, 0.0),
    ("Ejemplo Energía", "Tres periodos", "fija", 0.0899, 0.0459, 0.199, 0.129, 0.089, 0.0),
    ("Demo Luz", "Plana Ahorro", "fija", 0.1011, 0.0320, 0.125, 0.125, 0.125, 2.5),
    ("Demo Luz", "Noche", "fija", 0.0950, 0.0400, 0.215, 0.140, 0.075, 0.0),
]

# Forma de un día tipo (peso relativo de cada hora local 0-23): noche baja, picos de mañana y cena
DIA_TIPO = [4, 3, 3, 3, 3, 3, 4, 7, 8, 6, 5, 5, 6, 7, 6, 5, 5, 6, 8, 10, 11, 10, 8, 6]


def _curva_mes(ini: date, fin: date, kwh_mes: float) -> list[tuple[datetime, float]]:
    """Reparte el consumo del mes hora a hora con la forma del día tipo (más en fin de semana)."""
    a, b = limites_utc(ini, fin)
    horas, h = [], a
    while h < b:
        local = a_local(h)
        peso = DIA_TIPO[local.hour] * (1.2 if local.weekday() >= 5 else 1.0)
        horas.append((h, peso))
        h += timedelta(hours=1)
    total = sum(p for _, p in horas)
    return [(h, round(kwh_mes * p / total, 4)) for h, p in horas]


# Perfil mensual (kWh) de una vivienda tipo: más consumo en invierno y verano
PERFIL = [330, 300, 270, 230, 220, 260, 320, 330, 260, 230, 260, 320]


def main() -> None:
    init_db()
    with Session(engine) as s:
        if s.exec(select(Domicilio)).first():
            print("Ya hay datos; no se carga la demo.")
            return
        tarifas = [
            Tarifa(comercializadora=c, nombre=n, tipo=t, potencia_p1=p1, potencia_p2=p2,
                   energia_p1=e1, energia_p2=e2, energia_p3=e3, cuota_fija_mes=q)
            for c, n, t, p1, p2, e1, e2, e3, q in TARIFAS
        ]  # fmt: skip
        s.add_all(tarifas)
        s.commit()
        casa = Domicilio(nombre="Casa (demo)", direccion="Calle Inventada 1", potencia_p1_kw=4.6,
                         potencia_p2_kw=4.6, tarifa_actual_id=tarifas[0].id)  # fmt: skip
        playa = Domicilio(nombre="Apartamento (demo)", potencia_p1_kw=3.45, potencia_p2_kw=3.45,
                          tarifa_actual_id=tarifas[2].id)  # fmt: skip
        s.add_all([casa, playa])
        s.commit()
        for dom, factor in ((casa, 1.0), (playa, 0.45)):
            for m, kwh_mes in enumerate(PERFIL, start=1):
                ini = date(2025, m, 1)
                fin = (date(2025, m + 1, 1) if m < 12 else date(2026, 1, 1)) - timedelta(days=1)
                horas = _curva_mes(ini, fin, kwh_mes * factor)
                if dom is casa:  # solo la casa tiene consumo horario
                    guardar_consumo(s, dom.id, [(h, k, True) for h, k in horas], "demo")
                por_periodo = {"p1": 0.0, "p2": 0.0, "p3": 0.0}
                for h, k in horas:
                    por_periodo[periodo_utc(h)] += k
                total = kwh_mes * factor
                s.add(Factura(domicilio_id=dom.id, fecha_inicio=ini, fecha_fin=fin,
                              comercializadora="Ejemplo Energía", kwh_p1=round(por_periodo["p1"], 1),
                              kwh_p2=round(por_periodo["p2"], 1), kwh_p3=round(por_periodo["p3"], 1),
                              kw_p1=dom.potencia_p1_kw, kw_p2=dom.potencia_p2_kw,
                              importe_total=round(total * 0.21 + 14, 2)))  # fmt: skip
        s.commit()
        print("Datos de demostración cargados.")


if __name__ == "__main__":
    main()
