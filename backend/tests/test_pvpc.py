from datetime import date, timedelta

from fastapi.testclient import TestClient

from app import pvpc
from app.db import engine
from app.main import app
from app.motor.periodos import a_local, limites_utc
from sqlmodel import Session


def _precios_enero():
    ini, fin = limites_utc(date(2025, 1, 1), date(2025, 1, 31))
    filas, h = [], ini
    while h < fin:
        filas.append((h, 0.10 + 0.01 * a_local(h).hour))  # más caro según avanza el día
        h += timedelta(hours=1)
    with Session(engine) as s:
        pvpc.guardar_precios(s, filas)
        return pvpc.asegurar_tarifa_pvpc(s).id


def _csv_enero(nocturno: bool) -> str:
    lineas = ["fecha;hora;consumo"]
    d = date(2025, 1, 1)
    while d.month == 1:
        for h in range(1, 25):
            kwh = 1.0 if (h <= 8) == nocturno else 0.1
            lineas.append(f"{d:%d/%m/%Y};{h};{kwh}".replace(".", ","))
        d += timedelta(days=1)
    return "\n".join(lineas)


def test_pvpc_estimado_y_horario():
    with TestClient(app) as c:
        id_pvpc = _precios_enero()
        dom = c.post("/api/domicilios", json={"nombre": "PVPC"}).json()["id"]
        r = c.post(
            "/api/facturas",
            json={"domicilio_id": dom, "fecha_inicio": "2025-01-01", "fecha_fin": "2025-01-31",
                  "kwh_p1": 50, "kwh_p2": 60, "kwh_p3": 190, "kw_p1": 3.45, "kw_p2": 3.45},
        )  # fmt: skip
        assert r.status_code == 201

        cmp = lambda: c.post("/api/comparativa", json={"domicilio_id": dom, "tarifa_ids": [id_pvpc]}).json()  # noqa: E731
        est = cmp()["tarifas"][0]
        assert est["precision"] == "estimado" and est["avisos"]

        # Consumo concentrado de noche (horas baratas) -> más barato que la estimación
        r = c.post(f"/api/domicilios/{dom}/consumo/csv", json={"contenido": _csv_enero(nocturno=True)})
        assert r.status_code == 200 and r.json()["horas"] == 744
        exacto = cmp()["tarifas"][0]
        assert exacto["precision"] == "horario"
        assert exacto["total_periodo"] < est["total_periodo"]

        res = c.get(f"/api/domicilios/{dom}/consumo").json()
        assert res["horas"] == 744 and res["meses"][0]["completo"]

        # El mes ya tiene factura: no se duplica
        g = c.post(f"/api/domicilios/{dom}/consumo/generar-facturas").json()
        assert g["creadas"] == [] and g["con_factura"] == ["01/2025"]

        dia = c.get("/api/pvpc/dia", params={"dia": "2025-01-15"}).json()
        assert len(dia["horas"]) == 24 and dia["minimo"]["hora"] == "00:00"

        assert c.delete(f"/api/domicilios/{dom}").status_code == 204


def test_generar_facturas_y_sin_precios():
    with TestClient(app) as c:
        dom = c.post("/api/domicilios", json={"nombre": "Solo horario", "potencia_p1_kw": 4.6}).json()["id"]
        texto = _csv_enero(nocturno=False).replace("/01/2025", "/01/2024")
        c.post(f"/api/domicilios/{dom}/consumo/csv", json={"contenido": texto})
        g = c.post(f"/api/domicilios/{dom}/consumo/generar-facturas").json()
        assert g["creadas"] == ["01/2024"]
        f = c.get(f"/api/domicilios/{dom}/facturas").json()[0]
        assert f["origen"] == "horario" and f["kw_p1"] == 4.6
        assert abs(f["kwh_p1"] + f["kwh_p2"] + f["kwh_p3"] - (31 * (16 * 1.0 + 8 * 0.1))) < 0.01

        # Sin precios PVPC de 2024: se excluye con aviso, no rompe
        with Session(engine) as s:
            id_pvpc = pvpc.asegurar_tarifa_pvpc(s).id
        r = c.post("/api/comparativa", json={"domicilio_id": dom, "tarifa_ids": [id_pvpc]}).json()
        assert r["tarifas"] == [] and any("faltan precios" in a for a in r["avisos"])
