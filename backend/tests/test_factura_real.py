"""Factura real de Octopus Energy (datos personales omitidos) usada como referencia del cálculo.

Periodo 21/09/2026 – 20/10/2026, que Octopus cuenta como 29 días. 4,5 kW. Precio único de energía.

    Potencia punta   4,50 kW × 29 días × 0,097 €/kW·día   12,66 €
    Potencia valle   4,50 kW × 29 días × 0,029 €/kW·día    3,79 €
    Energía          47 + 50 + 175 kWh × 0,129 €/kWh      35,19 €
    Bono social      29 días × 0,025 €/día                 0,72 €
    Alquiler equipos 29 días × 0,027 €/día                 0,77 €
    Impuesto eléctrico 5,11 % s/ 51,64 €                   2,64 €   ← base sin bono social
    IVA 21 % s/ 55,77 €                                   11,71 €
    Total                                                 67,48 €
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

# Precios deducidos de los importes de la factura (la factura muestra 3 decimales)
TARIFA = {
    "comercializadora": "Octopus Energy",
    "nombre": "Tarifa de la factura de referencia",
    "potencia_p1": 12.66 / (4.5 * 29),
    "potencia_p2": 3.79 / (4.5 * 29),
    "energia_p1": 35.19 / 272,
    "energia_p2": 35.19 / 272,
    "energia_p3": 35.19 / 272,
}


def test_reproduce_la_factura_real_de_octopus():
    with TestClient(app) as c:
        t = c.post("/api/tarifas", json=TARIFA).json()["id"]
        dom = c.post("/api/domicilios", json={"nombre": "Referencia", "potencia_p1_kw": 4.5, "potencia_p2_kw": 4.5}).json()["id"]
        f = c.post(
            "/api/facturas",
            json={"domicilio_id": dom, "fecha_inicio": "2026-09-21", "fecha_fin": "2026-10-20", "dias": 29,
                  "kwh_p1": 47, "kwh_p2": 50, "kwh_p3": 175, "kw_p1": 4.5, "kw_p2": 4.5, "importe_total": 67.48},
        ).json()  # fmt: skip
        d = c.get(f"/api/facturas/{f['id']}/simular/{t}").json()
        assert d["dias"] == 29
        assert d["termino_potencia"] == pytest.approx(16.45, abs=0.01)
        assert d["termino_energia"] == pytest.approx(35.19, abs=0.01)
        assert d["bono_social"] == pytest.approx(0.72, abs=0.01)
        assert d["alquiler_contador"] == pytest.approx(0.77, abs=0.01)
        assert d["base_iee"] == pytest.approx(51.64, abs=0.01)
        assert d["iee"] == pytest.approx(2.64, abs=0.01)
        assert d["base_iva"] == pytest.approx(55.77, abs=0.02)
        assert d["iva"] == pytest.approx(11.71, abs=0.01)
        assert d["total"] == pytest.approx(67.48, abs=0.01)
        c.delete(f"/api/domicilios/{dom}")
        c.delete(f"/api/tarifas/{t}")


def test_migracion_desde_una_base_de_datos_anterior(tmp_path, monkeypatch):
    """Una base de datos de la 1.02 (sin la columna «dias» y con el IEE sobre el bono) se pone al día."""
    import sqlite3

    from sqlmodel import Session, select

    from app import db
    from app.models import VigenciaRegulada

    with Session(db.engine) as s:
        s.exec(db.text("UPDATE vigenciaregulada SET iee_incluye_bono_social = 1"))
        s.exec(db.text("DELETE FROM ajuste WHERE clave = 'migracion_iee_sin_bono'"))
        s.commit()
    db.init_db()
    with Session(db.engine) as s:
        assert all(not v.iee_incluye_bono_social for v in s.exec(select(VigenciaRegulada)))
    # La columna nueva existe y una segunda ejecución no falla
    db.init_db()
    ruta = db.engine.url.database
    assert "dias" in {r[1] for r in sqlite3.connect(ruta).execute("PRAGMA table_info(factura)")}


def test_importe_calculado_en_la_lista_de_facturas():
    with TestClient(app) as c:
        t = c.post("/api/tarifas", json=TARIFA).json()["id"]
        i = c.post("/api/domicilios", json={"nombre": "Importes", "potencia_p1_kw": 4.5, "potencia_p2_kw": 4.5}).json()["id"]
        f = c.post("/api/facturas", json={"domicilio_id": i, "fecha_inicio": "2026-09-21", "fecha_fin": "2026-10-20", "dias": 29,
                                          "kwh_p1": 47, "kwh_p2": 50, "kwh_p3": 175, "kw_p1": 4.5, "kw_p2": 4.5}).json()  # fmt: skip
        # Sin tarifa: no hay importe calculado
        r = c.get(f"/api/domicilios/{i}/facturas/importes").json()
        assert r == {"importes": {}, "tarifa_actual": None}
        # Con tarifa actual en el domicilio: se calcula con ella
        dom = c.get(f"/api/domicilios/{i}").json()
        c.put(f"/api/domicilios/{i}", json={**dom, "tarifa_actual_id": t})
        r = c.get(f"/api/domicilios/{i}/facturas/importes").json()
        assert r["tarifa_actual"] == TARIFA["nombre"]
        assert r["importes"][str(f["id"])]["total"] == pytest.approx(67.48, abs=0.01)
        c.delete(f"/api/domicilios/{i}")
        c.delete(f"/api/tarifas/{t}")


def test_factura_con_la_rebaja_de_impuestos_de_2026():
    """Última factura «REDUCIDO» de Octopus: 20/04–20/05/2026. IVA 10 % e IEE al mínimo de 1 €/MWh."""
    with TestClient(app) as c:
        vig = c.get("/api/vigencias").json()
        rebaja = [v for v in vig if v["iva_pct"] == 10]
        assert len(rebaja) == 1 and rebaja[0]["fecha_desde"] == "2026-03-22" and rebaja[0]["fecha_hasta"] == "2026-05-31"

        t = c.post("/api/tarifas", json=TARIFA).json()["id"]
        i = c.post("/api/domicilios", json={"nombre": "Rebaja"}).json()["id"]
        f = c.post("/api/facturas", json={"domicilio_id": i, "fecha_inicio": "2026-04-20", "fecha_fin": "2026-05-20", "dias": 30,
                                          "kwh_p1": 50, "kwh_p2": 50, "kwh_p3": 150, "kw_p1": 4.5, "kw_p2": 4.5}).json()  # fmt: skip
        d = c.get(f"/api/facturas/{f['id']}/simular/{t}").json()
        # 0,5 % de la base (~0,23 €) es menos que 250 kWh × 1 €/MWh = 0,25 €: se aplica el mínimo, como en la factura
        assert d["iee"] == pytest.approx(0.25, abs=0.001)
        assert d["iva"] == pytest.approx(d["base_iva"] * 0.10, abs=0.01)
        c.delete(f"/api/domicilios/{i}")
        c.delete(f"/api/tarifas/{t}")


def test_los_impuestos_se_aplican_segun_la_fecha_de_emision():
    """Factura real 20/05–19/06/2026, emitida el 22/06: empieza dentro de la rebaja (hasta el 31/05) pero
    Octopus aplica toda ella IEE 5,11 % e IVA 21 %, porque el impuesto se devenga al facturar."""
    with TestClient(app) as c:
        t = c.post("/api/tarifas", json=TARIFA).json()["id"]
        i = c.post("/api/domicilios", json={"nombre": "Devengo"}).json()["id"]
        base = {"domicilio_id": i, "fecha_inicio": "2026-05-20", "fecha_fin": "2026-06-19", "dias": 30,
                "kwh_p1": 60, "kwh_p2": 70, "kwh_p3": 200, "kw_p1": 4.5, "kw_p2": 4.5}  # fmt: skip
        con = c.post("/api/facturas", json={**base, "fecha_emision": "2026-06-22"}).json()
        sin = c.post("/api/facturas", json=base).json()
        d = c.get(f"/api/facturas/{con['id']}/simular/{t}").json()
        assert d["iee"] == pytest.approx(d["base_iee"] * 0.0511269632, abs=0.001)
        assert d["iva"] == pytest.approx(d["base_iva"] * 0.21, abs=0.01)
        assert d["bono_social"] == pytest.approx(0.019 * 30, abs=0.01)  # el bono sigue por días: 0,57 € como en la factura
        # Sin fecha de emisión se prorratea: 12 días rebajados, sale más barata
        d2 = c.get(f"/api/facturas/{sin['id']}/simular/{t}").json()
        assert d2["total"] < d["total"] - 2

        # Y la última reducida (20/04–20/05, emitida el 22/05) va entera con la rebaja
        r = c.post("/api/facturas", json={**base, "fecha_inicio": "2026-04-20", "fecha_fin": "2026-05-20", "fecha_emision": "2026-05-22"}).json()
        d3 = c.get(f"/api/facturas/{r['id']}/simular/{t}").json()
        assert d3["iva"] == pytest.approx(d3["base_iva"] * 0.10, abs=0.01)
        c.delete(f"/api/domicilios/{i}")
        c.delete(f"/api/tarifas/{t}")
