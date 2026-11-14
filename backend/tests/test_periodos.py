from datetime import date, datetime

from app.motor.periodos import hora_local_a_utc, horas_esperadas, periodo_local, MADRID


def L(*a):
    return datetime(*a, tzinfo=MADRID)


def test_laborable():
    # martes 4 de noviembre de 2025
    assert periodo_local(L(2025, 11, 4, 0)) == "p3"
    assert periodo_local(L(2025, 11, 4, 7)) == "p3"
    assert periodo_local(L(2025, 11, 4, 8)) == "p2"
    assert periodo_local(L(2025, 11, 4, 10)) == "p1"
    assert periodo_local(L(2025, 11, 4, 14)) == "p2"
    assert periodo_local(L(2025, 11, 4, 18)) == "p1"
    assert periodo_local(L(2025, 11, 4, 21)) == "p1"
    assert periodo_local(L(2025, 11, 4, 22)) == "p2"
    assert periodo_local(L(2025, 11, 4, 23)) == "p2"


def test_fin_de_semana_y_festivo_nacional():
    assert periodo_local(L(2025, 11, 8, 12)) == "p3"  # sábado
    assert periodo_local(L(2025, 12, 8, 12)) == "p3"  # Inmaculada, lunes
    # El Viernes Santo no tiene fecha fija: es laborable a efectos del peaje
    assert periodo_local(L(2025, 4, 18, 12)) == "p1"


def test_cambios_de_hora():
    assert horas_esperadas(date(2026, 3, 29), date(2026, 3, 29)) == 23
    assert horas_esperadas(date(2026, 10, 25), date(2026, 10, 25)) == 25
    assert horas_esperadas(date(2026, 1, 1), date(2026, 1, 31)) == 744
    assert hora_local_a_utc(date(2026, 3, 29), 2) is None  # las 2:00 no existen
    a = hora_local_a_utc(date(2026, 10, 25), 2)
    b = hora_local_a_utc(date(2026, 10, 25), 2, segunda_vez=True)
    assert (b - a).total_seconds() == 3600
