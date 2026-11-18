"""Historial de potencias con el caso real: 3,5 kW hasta el 11/02/2026 y 4,5 kW desde el 12/02/2026."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.fuentes.datadis import interpretar_contratos
from app.fuentes.octopus import interpretar_potencias
from app.main import app


def _consumo_csv(desde: date, hasta: date) -> str:
    from datetime import timedelta

    lineas = ["fecha;hora;consumo"]
    d = desde
    while d <= hasta:
        lineas += [f"{d:%d/%m/%Y};{h};0,5" for h in range(1, 25)]
        d += timedelta(days=1)
    return "\n".join(lineas)


def test_facturas_desde_consumo_con_cambio_de_potencia():
    with TestClient(app) as c:
        dom = c.post("/api/domicilios", json={"nombre": "Cambio", "potencia_p1_kw": 3.45, "potencia_p2_kw": 3.45}).json()
        i = dom["id"]
        c.post(f"/api/domicilios/{i}/consumo/csv", json={"contenido": _consumo_csv(date(2026, 1, 1), date(2026, 3, 31))})
        assert c.post(f"/api/domicilios/{i}/potencias", json={"desde": "2025-12-12", "hasta": "2026-02-11", "kw_p1": 3.5, "kw_p2": 3.5}).status_code == 201
        assert c.post(f"/api/domicilios/{i}/potencias", json={"desde": "2026-02-12", "kw_p1": 4.5, "kw_p2": 4.5}).status_code == 201

        # La potencia actual del domicilio pasa a ser la del tramo vigente
        assert c.get(f"/api/domicilios/{i}").json()["potencia_p1_kw"] == 4.5

        c.post(f"/api/domicilios/{i}/consumo/generar-facturas")
        f = {x["fecha_inicio"][:7]: x for x in c.get(f"/api/domicilios/{i}/facturas").json()}
        assert f["2026-01"]["kw_p1"] == 3.5
        assert f["2026-03"]["kw_p1"] == 4.5
        # Febrero: 11 días a 3,5 y 17 a 4,5 → media ponderada (exacta para el término de potencia)
        assert f["2026-02"]["kw_p1"] == pytest.approx((11 * 3.5 + 17 * 4.5) / 28, abs=1e-4)

        # Corregir el historial recalcula las facturas creadas desde el consumo
        tramo = next(p for p in c.get(f"/api/domicilios/{i}/potencias").json() if p["kw_p1"] == 3.5)
        c.put(f"/api/potencias/{tramo['id']}", json={**tramo, "kw_p1": 3.3, "kw_p2": 3.3})
        f = {x["fecha_inicio"][:7]: x for x in c.get(f"/api/domicilios/{i}/facturas").json()}
        assert f["2026-01"]["kw_p1"] == 3.3

        # Fechas al revés: rechazado
        assert c.post(f"/api/domicilios/{i}/potencias", json={"desde": "2026-05-01", "hasta": "2026-04-01", "kw_p1": 3, "kw_p2": 3}).status_code == 422
        assert c.delete(f"/api/domicilios/{i}").status_code == 204


def test_las_facturas_manuales_conservan_su_potencia():
    with TestClient(app) as c:
        i = c.post("/api/domicilios", json={"nombre": "Manual"}).json()["id"]
        m = c.post("/api/facturas", json={"domicilio_id": i, "fecha_inicio": "2026-01-01", "fecha_fin": "2026-01-31", "kw_p1": 3.5, "kw_p2": 3.5}).json()
        c.post(f"/api/domicilios/{i}/potencias", json={"desde": "2025-01-01", "kw_p1": 9, "kw_p2": 9})
        assert c.get(f"/api/domicilios/{i}/facturas").json()[0]["kw_p1"] == 3.5 == m["kw_p1"]
        c.delete(f"/api/domicilios/{i}")


def test_interpretar_contratos_de_octopus():
    datos = {"account": {"properties": [{"id": "77", "electricitySupplyPoints": [{"cups": "ES1", "agreements": [
        {"validFrom": "2025-12-12T00:00:00+01:00", "validTo": "2026-02-12T00:00:00+01:00", "details": {"contractualMaxPower": "3.5"}},
        {"validFrom": "2026-02-12T00:00:00+01:00", "validTo": None, "details": {"contractualMaxPower": "4500"}},
        {"validFrom": "2026-03-01T00:00:00+01:00", "validTo": None, "details": {"contractualMaxPower": None}},
    ]}]}, {"id": "99", "electricitySupplyPoints": []}]}}  # fmt: skip
    t = interpretar_potencias(datos, "77")
    assert t == [
        {"desde": date(2025, 12, 12), "hasta": date(2026, 2, 11), "kw_p1": 3.5, "kw_p2": 3.5, "nota": "Contrato de Octopus"},
        {"desde": date(2026, 2, 12), "hasta": None, "kw_p1": 4.5, "kw_p2": 4.5, "nota": "Contrato de Octopus"},
    ]
    assert interpretar_potencias(datos, "99") == []


def test_interpretar_contratos_de_datadis():
    t = interpretar_contratos([
        {"cups": "ES1", "contractedPowerkW": [3.5, 3.5], "startDate": "2025/12/12", "endDate": "2026/02/11"},
        {"cups": "ES1", "contractedPowerkW": [4.5, 4.6], "startDate": "2026/02/12", "endDate": ""},
        {"cups": "ES1", "contractedPowerkW": [], "startDate": "2020/01/01"},
    ])
    assert [(x["desde"], x["hasta"], x["kw_p1"], x["kw_p2"]) for x in t] == [
        (date(2025, 12, 12), date(2026, 2, 11), 3.5, 3.5),
        (date(2026, 2, 12), None, 4.5, 4.6),
    ]
