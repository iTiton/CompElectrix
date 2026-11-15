from datetime import date, datetime, timedelta

import pytest

from app.fuentes import ree
from app.importadores.consumo import importar_csv
from app.motor.periodos import limites_utc


def _datadis(dia: date, n: int, cups="ES0000000000000000AA0F") -> str:
    lineas = ["cups;fecha;hora;consumo;metodoObtencion;energiaVertida"]
    for h in range(1, n + 1):
        lineas.append(f"{cups};{dia:%Y/%m/%d};{h:02d}:00;0,{h:03d};Real;0")
    return "\n".join(lineas)


def test_csv_datadis_dia_normal():
    r = importar_csv(_datadis(date(2026, 1, 15), 24))
    assert len(r.horas) == 24 and r.cups == {"ES0000000000000000AA0F"}
    ini, _ = limites_utc(date(2026, 1, 15), date(2026, 1, 15))
    assert r.horas[0][0] == ini  # la "01:00" es la hora 0-1
    assert r.horas[0][1] == pytest.approx(0.001)


@pytest.mark.parametrize("dia,n", [(date(2026, 3, 29), 23), (date(2026, 10, 25), 25)])
def test_csv_dias_de_cambio_de_hora(dia, n):
    r = importar_csv(_datadis(dia, n))
    assert len(r.horas) == n
    horas = [h for h, *_ in r.horas]
    assert all(b - a == timedelta(hours=1) for a, b in zip(horas, horas[1:]))


def test_csv_distribuidora_formato_espanol_y_wh():
    texto = "Informe de consumo\n\nCUPS,Fecha,Hora,AE_Wh,Estimado\n"
    texto += "\n".join(f"ES1,15-01-2026,{h},{h * 100},R" for h in range(1, 25))
    r = importar_csv(texto)
    assert len(r.horas) == 24 and r.horas[-1][1] == pytest.approx(2.4)


def test_csv_hora_inicial_0_23():
    texto = "Fecha;Hora;Consumo kWh\n" + "\n".join(f"2026-01-15;{h};1,5" for h in range(24))
    r = importar_csv(texto)
    ini, _ = limites_utc(date(2026, 1, 15), date(2026, 1, 15))
    assert r.horas[0][0] == ini and len(r.horas) == 24


def test_csv_estimadas_y_errores():
    texto = "fecha;hora;consumo;metodo\n2026/01/15;01:00;0,5;Estimada\n2026/01/15;xx;1;Real\n"
    r = importar_csv(texto)
    assert len(r.horas) == 1 and r.horas[0][2] is False
    assert any("no se han podido leer" in a for a in r.avisos)
    assert any("estimadas" in a for a in r.avisos)


def test_csv_sin_cabecera():
    with pytest.raises(ValueError):
        importar_csv("a;b;c\n1;2;3")


def test_ree_interpretar_y_cuartos_de_hora():
    resp = {
        "included": [
            {"attributes": {"title": "Precio mercado spot", "values": []}},
            {
                "attributes": {
                    "title": "PVPC",
                    "values": [
                        {"value": 100.0, "datetime": "2026-11-10T00:00:00.000+01:00"},
                        {"value": 200.0, "datetime": "2026-11-10T01:00:00.000+01:00"},
                        {"value": 300.0, "datetime": "2026-11-10T01:30:00.000+01:00"},
                    ],
                }
            },
        ]
    }
    filas = ree.interpretar(resp)
    assert filas == [(datetime(2026, 11, 9, 23), 0.1), (datetime(2026, 11, 10, 0), 0.25)]


def test_ree_tramos_mensuales():
    t = ree.tramos_mensuales(date(2026, 1, 20), date(2026, 3, 5))
    assert t == [
        (date(2026, 1, 20), date(2026, 1, 31)),
        (date(2026, 2, 1), date(2026, 2, 28)),
        (date(2026, 3, 1), date(2026, 3, 5)),
    ]


def test_ree_reintenta_tras_403(monkeypatch):
    import io
    import json
    import urllib.error

    llamadas = []

    def falso(req, timeout):
        llamadas.append(req.full_url)
        if len(llamadas) == 1:
            raise urllib.error.HTTPError(req.full_url, 403, "bloqueado", {}, io.BytesIO())
        return io.BytesIO(json.dumps({"included": []}).encode())

    monkeypatch.setattr(ree.urllib.request, "urlopen", falso)
    esperas = []
    assert list(ree.descargar_pvpc(date(2026, 1, 1), date(2026, 1, 2), dormir=esperas.append)) == [[]]
    assert len(llamadas) == 2 and esperas == [15]
