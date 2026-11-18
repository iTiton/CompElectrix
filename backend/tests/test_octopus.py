import io
import json
from datetime import date, datetime

import pytest

from app.fuentes import octopus


def _resp(data=None, errors=None):
    return io.BytesIO(json.dumps({"data": data, "errors": errors} if errors else {"data": data}).encode())


def test_cliente_octopus(monkeypatch):
    peticiones = []

    def falso(req, timeout):
        cuerpo = json.loads(req.data)
        peticiones.append((req, cuerpo))
        q = cuerpo["query"]
        if "obtainKrakenToken" in q:
            return _resp({"obtainKrakenToken": {"token": "jwt"}})
        if "viewer" in q:
            return _resp({"viewer": {"accounts": [{"number": "A-1"}]}})
        if "properties" in q:
            return _resp({"account": {"properties": [
                {"id": "77", "address": "C/ Falsa 1", "electricitySupplyPoints": [{"cups": "ESX"}], "gasSupplyPoints": []}
            ]}})  # fmt: skip
        pagina = cuerpo["variables"]["despues"]
        nodos = [{"node": {"value": "0.5", "unit": "kWh", "startAt": "2026-01-01T00:00:00+01:00"}}]
        if pagina:
            nodos = [{"node": {"value": "0.25", "unit": "kWh", "startAt": "2026-01-01T01:00:00+01:00"}}]
        return _resp({"property": {"measurements": {
            "pageInfo": {"hasNextPage": not pagina, "endCursor": "c1"}, "edges": nodos}}})  # fmt: skip

    monkeypatch.setattr(octopus.urllib.request, "urlopen", falso)
    c = octopus.ClienteOctopus("a@b.c", "x")
    assert c.suministros() == [
        {"cuenta": "A-1", "propiedad_id": "77", "direccion": "C/ Falsa 1", "cups_luz": ["ESX"], "cups_gas": []}
    ]
    assert peticiones[1][0].headers["Authorization"] == "jwt"
    horas = c.consumos("77", date(2026, 1, 1), date(2026, 1, 1))
    assert horas == [(datetime(2025, 12, 31, 23), 0.5, True), (datetime(2026, 1, 1, 0), 0.25, True)]


def test_credenciales_octopus(monkeypatch):
    err = [{"message": "Invalid data.", "extensions": {"errorCode": "KT-CT-1138"}}]
    monkeypatch.setattr(octopus.urllib.request, "urlopen", lambda req, timeout: _resp(None, err))
    with pytest.raises(octopus.ErrorOctopus, match="incorrectos"):
        octopus.ClienteOctopus("a", "b").suministros()


def test_un_fallo_en_la_potencia_no_impide_importar_el_consumo(monkeypatch):
    from datetime import datetime

    from fastapi.testclient import TestClient

    from app import api as modulo
    from app.main import app

    class Falso:
        def __init__(self, *_):
            pass

        def consumos(self, *_):
            return [(datetime(2026, 1, 1, 0), 0.5, True)]

        def potencias(self, *_):
            raise ValueError("formato inesperado")

    monkeypatch.setattr(modulo, "ClienteOctopus", Falso)
    with TestClient(app, raise_server_exceptions=False) as c:
        i = c.post("/api/domicilios", json={"nombre": "Fallo potencia"}).json()["id"]
        r = c.post(f"/api/domicilios/{i}/consumo/octopus", json={
            "credenciales": {"usuario": "a@b.c", "clave": "x"}, "propiedad_id": "1", "cuenta": "A-1",
            "desde": "2026-01-01", "hasta": "2026-01-01"})  # fmt: skip
        assert r.status_code == 200, r.text
        assert r.json()["horas"] == 1 and "formato inesperado" in r.json()["avisos"][0]
        c.delete(f"/api/domicilios/{i}")
