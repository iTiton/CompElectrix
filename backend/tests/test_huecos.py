from datetime import date, datetime, timedelta

from sqlmodel import Session, delete

from app import pvpc
from app.db import engine, init_db
from app.models import Ajuste, Factura, PrecioHorario
from app.motor.periodos import limites_utc


def _limpiar(s):
    s.exec(delete(PrecioHorario))
    s.exec(delete(Ajuste))
    s.exec(delete(Factura))
    s.commit()


def _guardar_dias(s, desde, hasta):
    a, b = limites_utc(desde, hasta)
    filas, h = [], a
    while h < b:
        filas.append((h, 0.1))
        h += timedelta(hours=1)
    pvpc.guardar_precios(s, filas)


def test_huecos_desde_el_ultimo_uso():
    init_db()
    with Session(engine) as s:
        _limpiar(s)
        _guardar_dias(s, date(2026, 10, 1), date(2026, 10, 20))
        _guardar_dias(s, date(2026, 10, 23), date(2026, 11, 5))  # faltan 21 y 22
        # 25 de octubre (25 h) incompleto: quitamos una hora
        a, _ = limites_utc(date(2026, 10, 25), date(2026, 10, 25))
        s.exec(delete(PrecioHorario).where(PrecioHorario.inicio_utc == a))
        s.commit()

        manana = datetime(2026, 11, 14, 10, 0)
        assert pvpc.huecos(s, manana) == [
            (date(2026, 10, 21), date(2026, 10, 22)),
            (date(2026, 10, 25), date(2026, 10, 25)),
            (date(2026, 11, 6), date(2026, 11, 14)),  # hasta hoy: mañana aún no está publicado
        ]
        noche = datetime(2026, 11, 14, 21, 0)
        assert pvpc.huecos(s, noche)[-1] == (date(2026, 11, 6), date(2026, 11, 15))


def test_huecos_incluye_facturas_antiguas():
    init_db()
    with Session(engine) as s:
        _limpiar(s)
        _guardar_dias(s, date(2026, 1, 1), date(2026, 1, 31))
        s.add(Factura(domicilio_id=0, fecha_inicio=date(2025, 12, 1), fecha_fin=date(2025, 12, 31)))
        s.exec(__import__("sqlalchemy").text("PRAGMA foreign_keys=OFF"))
        s.commit()
        h = pvpc.huecos(s, datetime(2026, 1, 31, 12))
        assert h == [(date(2025, 12, 1), date(2025, 12, 31))]


def test_al_entrar_no_insiste(monkeypatch):
    init_db()
    lanzados = []
    monkeypatch.setattr(pvpc, "_lanzar", lambda **kw: lanzados.append(kw))
    with Session(engine) as s:
        _limpiar(s)
        _guardar_dias(s, date(2026, 11, 1), date(2026, 11, 10))
    t = datetime(2026, 11, 14, 10, 0)
    r = pvpc.al_entrar(t)
    assert r == {"actualizando": True, "dias": 4} and lanzados[0]["rangos"] == [(date(2026, 11, 11), date(2026, 11, 14))]
    assert pvpc.al_entrar(t + timedelta(minutes=5)) == {"actualizando": False, "dias": 0}
    assert len(lanzados) == 1
    pvpc.al_entrar(t + timedelta(minutes=11))
    assert len(lanzados) == 2
