import os
import tempfile

os.environ["COMPELECTRIX_DATA"] = tempfile.mkdtemp()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def _tarifa(c, nombre, e):
    r = c.post(
        "/api/tarifas",
        json={
            "comercializadora": "Prueba",
            "nombre": nombre,
            "potencia_p1": 0.1,
            "potencia_p2": 0.05,
            "energia_p1": e,
            "energia_p2": e,
            "energia_p3": e,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_flujo_completo():
    with TestClient(app) as c:
        assert c.get("/api/salud").json() == {"estado": "ok"}
        assert len(c.get("/api/vigencias").json()) == 2

        cara = _tarifa(c, "Cara", 0.20)
        barata = _tarifa(c, "Barata", 0.12)

        r = c.post("/api/domicilios", json={"nombre": "Casa", "tarifa_actual_id": cara})
        assert r.status_code == 201
        dom = r.json()["id"]

        for mes in range(1, 13):
            fin = 28 if mes == 2 else 30
            r = c.post(
                "/api/facturas",
                json={
                    "domicilio_id": dom,
                    "fecha_inicio": f"2025-{mes:02d}-01",
                    "fecha_fin": f"2025-{mes:02d}-{fin}",
                    "kwh_p1": 80, "kwh_p2": 70, "kwh_p3": 120,
                    "kw_p1": 4.6, "kw_p2": 4.6,
                    "importe_total": 70,
                },
            )  # fmt: skip
            assert r.status_code == 201, r.text

        # fecha invertida rechazada
        r = c.post("/api/facturas", json={"domicilio_id": dom, "fecha_inicio": "2025-02-02", "fecha_fin": "2025-02-01"})
        assert r.status_code == 422

        res = c.post("/api/comparativa", json={"domicilio_id": dom}).json()
        assert res["resumen"]["num_facturas"] == 12
        assert res["resumen"]["referencia"] == "tarifa_actual"
        primero, segundo = res["tarifas"]
        assert primero["nombre"] == "Barata" and primero["ahorro_anual"] > 0
        assert segundo["es_actual"] and segundo["ahorro_anual"] == 0
        assert "desviacion_pct" in res["facturas"][0]

        dom_listado = c.get("/api/domicilios").json()[0]
        assert dom_listado["num_facturas"] == 12 and dom_listado["gasto_12m"] > 0

        # no se puede borrar la tarifa actual
        assert c.delete(f"/api/tarifas/{cara}").status_code == 409
        assert c.delete(f"/api/domicilios/{dom}").status_code == 204
