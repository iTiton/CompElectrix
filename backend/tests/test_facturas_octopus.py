"""Importación de facturas de Octopus (periodo, emisión, total) sobre el consumo horario."""

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import api as modulo
from app.fuentes.octopus import interpretar_factura
from app.main import app
from app.servicios import juntar_tramos


def _csv(desde: date, hasta: date, kwh_hora: float = 0.5) -> str:
    lineas, d = ["fecha;hora;consumo"], desde
    while d <= hasta:
        n = 23 if d == date(2026, 3, 29) else 25 if d == date(2025, 10, 26) else 24
        lineas += [f"{d:%d/%m/%Y};{h};{str(kwh_hora).replace('.', ',')}" for h in range(1, n + 1)]
        d += timedelta(days=1)
    return "\n".join(lineas)


def test_interpretar_factura():
    nodo = {"id": "123", "billType": "STATEMENT", "fromDate": "2026-09-21", "toDate": "2026-10-20", "issuedDate": "2026-10-23",
            "totalCharges": {"grossTotal": 6748},
            "transactions": {"edges": [
                {"node": {"__typename": "Charge", "consumption": {"quantity": "272.0", "unit": "kWh"}}},
                {"node": {"__typename": "Payment"}},
            ]}}  # fmt: skip
    f = interpretar_factura(nodo)
    assert f == {"id": "123", "desde": date(2026, 9, 21), "hasta": date(2026, 10, 20), "emision": date(2026, 10, 23),
                 "total": 67.48, "kwh": 272.0}  # fmt: skip
    assert interpretar_factura({**nodo, "billType": "CREDIT_NOTE"}) is None


def test_juntar_tramos():
    t = juntar_tramos([
        {"desde": date(2025, 12, 12), "hasta": date(2026, 1, 1), "kw_p1": 3.5, "kw_p2": 3.5},
        {"desde": date(2026, 1, 1), "hasta": date(2026, 2, 11), "kw_p1": 3.5, "kw_p2": 3.5},
        {"desde": date(2026, 2, 12), "hasta": date(2026, 6, 30), "kw_p1": 4.5, "kw_p2": 4.5},
        {"desde": date(2026, 7, 1), "hasta": None, "kw_p1": 4.5, "kw_p2": 4.5},
    ])
    assert [(x["desde"], x["hasta"], x["kw_p1"]) for x in t] == [
        (date(2025, 12, 12), date(2026, 2, 11), 3.5),
        (date(2026, 2, 12), None, 4.5),
    ]


def test_importar_facturas_de_octopus(monkeypatch):
    # Consumo: 0,5 kWh cada hora de enero a marzo de 2026
    facturas = [
        # Periodo «21 al 20» sin incluir el último día: 31 días × 24 h × 0,5 = 372 kWh
        {"id": "F1", "desde": date(2026, 1, 1), "hasta": date(2026, 2, 1), "emision": date(2026, 2, 3), "total": 80.0, "kwh": 372.0},
        # Sin kWh en la factura: se aplica la regla (no incluye el último día)
        {"id": "F2", "desde": date(2026, 2, 1), "hasta": date(2026, 2, 21), "emision": date(2026, 2, 23), "total": 50.0, "kwh": None},
        # Más allá del consumo disponible: se omite
        {"id": "F3", "desde": date(2026, 3, 20), "hasta": date(2026, 4, 20), "emision": date(2026, 4, 22), "total": 70.0, "kwh": None},
    ]

    class Falso:
        def __init__(self, *_):
            pass

        def facturas(self, cuenta):
            assert cuenta == "A-1"
            return facturas

    monkeypatch.setattr(modulo, "ClienteOctopus", Falso)
    with TestClient(app) as c:
        i = c.post("/api/domicilios", json={"nombre": "Octopus", "potencia_p1_kw": 4.5, "potencia_p2_kw": 4.5}).json()["id"]
        c.post(f"/api/domicilios/{i}/consumo/csv", json={"contenido": _csv(date(2026, 1, 1), date(2026, 3, 31))})
        c.post(f"/api/domicilios/{i}/consumo/generar-facturas")  # enero, febrero, marzo por meses naturales
        cuerpo = {"credenciales": {"usuario": "a@b.c", "clave": "x"}, "cuenta": "A-1"}
        r = c.post(f"/api/domicilios/{i}/facturas/octopus", json=cuerpo).json()
        assert r["creadas"] == 2 and r["total"] == 3
        assert r["sustituidas"] == 2  # las mensuales de enero y febrero
        assert len(r["omitidas"]) == 1 and "incompleto" in r["omitidas"][0]

        lista = {f["numero"] or f["origen"]: f for f in c.get(f"/api/domicilios/{i}/facturas").json()}
        f1 = lista["F1"]
        assert f1["dias"] == 31 and f1["importe_total"] == 80.0 and f1["fecha_emision"] == "2026-02-03"
        assert f1["kwh_p1"] + f1["kwh_p2"] + f1["kwh_p3"] == pytest.approx(372.0)
        assert lista["F2"]["dias"] == 20
        assert lista["horario"]["fecha_inicio"] == "2026-03-01"  # marzo no se solapa con ninguna: se queda

        # Repetir no duplica: actualiza
        r = c.post(f"/api/domicilios/{i}/facturas/octopus", json=cuerpo).json()
        assert r["creadas"] == 0 and r["actualizadas"] == 2
        assert len(c.get(f"/api/domicilios/{i}/facturas").json()) == 3
        c.delete(f"/api/domicilios/{i}")
