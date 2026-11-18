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
