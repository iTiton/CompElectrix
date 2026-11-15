import io
import json
from datetime import date

import pytest

from app.fuentes import datadis


class Falso:
    def __init__(self):
        self.peticiones = []

    def __call__(self, req, timeout):
        self.peticiones.append(req)
        url = req.full_url
        if "login" in url:
            return io.BytesIO(b"token-de-prueba")
        if "get-supplies" in url:
            return io.BytesIO(json.dumps([
                {"address": "C/ Falsa 1", "cups": "ES0000000000000000AA0F", "postalCode": "28000",
                 "province": "Madrid", "municipality": "Madrid", "distributor": "Ejemplo",
                 "validDateFrom": "2020/01/01", "validDateTo": "", "pointType": 5, "distributorCode": "2"}
            ]).encode())  # fmt: skip
        if "get-consumption-data" in url:
            return io.BytesIO(json.dumps({"timeCurve": [
                {"cups": "X", "date": "2026/01/01", "time": "01:00", "consumptionKWh": 0.5, "obtainMethod": "Real"},
                {"cups": "X", "date": "2026/01/01", "time": "02:00", "consumptionKWh": 0.4, "obtainMethod": "Estimada"},
            ]}).encode())  # fmt: skip
        raise AssertionError(url)


def test_cliente_datadis(monkeypatch):
    falso = Falso()
    monkeypatch.setattr(datadis.urllib.request, "urlopen", falso)
    c = datadis.ClienteDatadis("00000000T", "secreto", dormir=lambda _: None)
    sum_ = c.suministros()
    assert sum_[0]["cups"] == "ES0000000000000000AA0F" and sum_[0]["codigo_distribuidora"] == "2"
    regs = c.consumos("ES0000000000000000AA0F", "2", 5, date(2026, 1, 1), date(2026, 2, 10))
    assert len(regs) == 4  # 2 meses x 2 registros falsos
    assert regs[0].kwh == 0.5 and regs[1].real is False
    assert falso.peticiones[1].headers["Authorization"] == "Bearer token-de-prueba"
    assert "startDate=2026%2F02" in falso.peticiones[-1].full_url


def test_credenciales_incorrectas(monkeypatch):
    import urllib.error

    def falla(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, "no", {}, io.BytesIO(b"Bad credentials"))

    monkeypatch.setattr(datadis.urllib.request, "urlopen", falla)
    with pytest.raises(datadis.ErrorDatadis, match="incorrectos"):
        datadis.ClienteDatadis("a", "b").suministros()
