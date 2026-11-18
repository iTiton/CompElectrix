from datetime import date

import pytest

from app.motor.calculo import Consumo, PreciosTarifa, Vigencia, calcular, repartir_dias

VIG = Vigencia(fecha_desde=date(2021, 6, 1), fecha_hasta=None, bono_social_eur_anio=0.0)
TARIFA = PreciosTarifa(0.1, 0.1, 0.15, 0.15, 0.15)
JUNIO = Consumo(date(2025, 6, 1), date(2025, 6, 30), 100, 100, 100, 3.45, 3.45)


def test_dias_inclusivos():
    assert JUNIO.dias == 30


def test_factura_calculada_a_mano():
    d = calcular(JUNIO, TARIFA, [VIG])
    assert d.termino_potencia == pytest.approx(20.70)
    assert d.termino_energia == pytest.approx(45.00)
    assert d.iee == pytest.approx(65.70 * 0.0511269632)
    assert d.alquiler_contador == pytest.approx(0.81 * 12 / 365 * 30)
    base_iva = 65.70 + 65.70 * 0.0511269632 + 0.81 * 12 / 365 * 30
    assert d.iva == pytest.approx(base_iva * 0.21)
    assert d.total == pytest.approx(base_iva * 1.21)
    assert round(d.total, 2) == 84.53


def test_descuento_cuota_y_bono():
    t = PreciosTarifa(0.1, 0.1, 0.15, 0.15, 0.15, cuota_fija_mes=3.0, descuento_energia_pct=10)
    v = Vigencia(date(2021, 6, 1), None, bono_social_eur_anio=7.3, iee_incluye_bono_social=True)
    d = calcular(JUNIO, t, [v])
    assert d.descuento_energia == pytest.approx(4.5)
    assert d.cuota_fija == pytest.approx(3.0 * 12 / 365 * 30)
    assert d.bono_social == pytest.approx(0.6)
    # con la opción activada, el bono social entra en la base del IEE
    assert d.base_iee == pytest.approx(20.70 + 40.50 + 0.6)


def test_tarifa_que_incluye_bono_social_no_lo_suma():
    t = PreciosTarifa(0.1, 0.1, 0.15, 0.15, 0.15, incluye_bono_social=True)
    v = Vigencia(date(2021, 6, 1), None, bono_social_eur_anio=7.3)
    assert calcular(JUNIO, t, [v]).bono_social == 0


def test_minimo_iee_por_mwh():
    v = Vigencia(date(2021, 6, 1), None, iee_pct=0.5, iee_minimo_eur_mwh=1.0)
    grande = Consumo(date(2025, 6, 1), date(2025, 6, 30), 3000, 3000, 3000, 3.45, 3.45)
    d = calcular(grande, PreciosTarifa(0.0, 0.0, 0.01, 0.01, 0.01), [v])
    # 0,5 % de 90 € = 0,45 € < 9 MWh · 1 €/MWh = 9 €
    assert d.iee == pytest.approx(9.0)


def test_prorrateo_entre_vigencias():
    a = Vigencia(date(2021, 6, 1), date(2025, 6, 15), iva_pct=21)
    b = Vigencia(date(2025, 6, 16), None, iva_pct=10)
    tramos, sin = repartir_dias(JUNIO.fecha_inicio, JUNIO.fecha_fin, [a, b])
    assert sin == 0 and sorted(n for _, n in tramos) == [15, 15]
    d = calcular(JUNIO, TARIFA, [a, b])
    mitad = d.base_iva / 2
    assert d.iva == pytest.approx(mitad * 0.21 + mitad * 0.10)


def test_dias_sin_vigencia_generan_aviso():
    v = Vigencia(date(2025, 6, 10), None)
    d = calcular(JUNIO, TARIFA, [v])
    assert d.avisos and "9 día" in d.avisos[0]


def test_fechas_invertidas():
    with pytest.raises(ValueError):
        calcular(Consumo(date(2025, 6, 2), date(2025, 6, 1)), TARIFA, [VIG])


def test_por_defecto_el_iee_no_incluye_el_bono_social():
    v = Vigencia(date(2021, 6, 1), None, bono_social_eur_anio=7.3)
    d = calcular(JUNIO, TARIFA, [v])
    assert d.base_iee == pytest.approx(d.termino_potencia + d.termino_energia)
