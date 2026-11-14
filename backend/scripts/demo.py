"""Carga datos de ejemplo INVENTADOS para probar la aplicación.

Uso:  python -m scripts.demo   (desde backend/, con la base de datos vacía)
"""

from datetime import date, timedelta

from sqlmodel import Session, select

from app.db import engine, init_db
from app.models import Domicilio, Factura, Tarifa

TARIFAS = [
    # comercializadora, nombre, tipo, pot P1, pot P2, en P1, en P2, en P3, cuota
    ("Ejemplo Energía", "Fija 24h", "fija", 0.0899, 0.0459, 0.139, 0.139, 0.139, 0.0),
    ("Ejemplo Energía", "Tres periodos", "fija", 0.0899, 0.0459, 0.199, 0.129, 0.089, 0.0),
    ("Demo Luz", "Plana Ahorro", "fija", 0.1011, 0.0320, 0.125, 0.125, 0.125, 2.5),
    ("Demo Luz", "Noche", "fija", 0.0950, 0.0400, 0.215, 0.140, 0.075, 0.0),
]

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
            for m, kwh in enumerate(PERFIL, start=1):
                ini = date(2025, m, 1)
                fin = (date(2025, m + 1, 1) if m < 12 else date(2026, 1, 1)) - timedelta(days=1)
                total = kwh * factor
                s.add(Factura(domicilio_id=dom.id, fecha_inicio=ini, fecha_fin=fin,
                              comercializadora="Ejemplo Energía", kwh_p1=round(total * 0.24, 1),
                              kwh_p2=round(total * 0.28, 1), kwh_p3=round(total * 0.48, 1),
                              kw_p1=dom.potencia_p1_kw, kw_p2=dom.potencia_p2_kw,
                              importe_total=round(total * 0.21 + 14, 2)))  # fmt: skip
        s.commit()
        print("Datos de demostración cargados.")


if __name__ == "__main__":
    main()
