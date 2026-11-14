"""Precios horarios del PVPC 2.0TD desde la API pública de REE (REData).

No necesita clave. La API está detrás de una protección antibots que devuelve
403 si se hacen peticiones muy seguidas, por eso se espacian y se reintenta.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone

URL = "https://apidatos.ree.es/es/datos/mercados/precios-mercados-tiempo-real"
CABECERAS = {"User-Agent": "Mozilla/5.0 (X11; Linux) home-energy-app", "Accept": "application/json"}
ESPERAS_REINTENTO = (15, 30, 60)  # segundos
PAUSA_ENTRE_PETICIONES = 5


class ErrorREE(Exception):
    pass


def _get(url: str, dormir: Callable[[float], None]) -> dict:
    ultimo: Exception | None = None
    for intento, espera in enumerate((0, *ESPERAS_REINTENTO)):
        if espera:
            dormir(espera)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=CABECERAS), timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            ultimo = e
            if e.code not in (403, 429, 500, 502, 503, 504):
                break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            ultimo = e
    raise ErrorREE(f"No se pudo consultar REE: {ultimo}")


def interpretar(respuesta: dict) -> list[tuple[datetime, float]]:
    """Extrae la serie PVPC como [(inicio de la hora en UTC sin zona, €/kWh)].

    Si algún día REE la publicara en cuartos de hora, se promedia por hora.
    """
    serie = next(
        (x for x in respuesta.get("included", []) if x.get("attributes", {}).get("title") == "PVPC"),
        None,
    )
    if serie is None:
        return []
    por_hora: dict[datetime, list[float]] = defaultdict(list)
    for v in serie["attributes"]["values"]:
        dt = datetime.fromisoformat(v["datetime"]).astimezone(timezone.utc).replace(tzinfo=None)
        por_hora[dt.replace(minute=0, second=0, microsecond=0)].append(float(v["value"]) / 1000)
    return sorted((h, sum(p) / len(p)) for h, p in por_hora.items())


def tramos_mensuales(desde: date, hasta: date) -> list[tuple[date, date]]:
    tramos = []
    ini = desde
    while ini <= hasta:
        sig_mes = (ini.replace(day=1) + timedelta(days=32)).replace(day=1)
        fin = min(sig_mes - timedelta(days=1), hasta)
        tramos.append((ini, fin))
        ini = fin + timedelta(days=1)
    return tramos


def descargar_pvpc(
    desde: date,
    hasta: date,
    dormir: Callable[[float], None] = time.sleep,
    progreso: Callable[[int, int], None] | None = None,
):
    """Genera, mes a mes, las listas de precios horarios entre dos fechas locales."""
    tramos = tramos_mensuales(desde, hasta)
    for i, (ini, fin) in enumerate(tramos):
        if i:
            dormir(PAUSA_ENTRE_PETICIONES)
        q = urllib.parse.urlencode(
            {"start_date": f"{ini}T00:00", "end_date": f"{fin}T23:59", "time_trunc": "hour"}
        )
        yield interpretar(_get(f"{URL}?{q}", dormir))
        if progreso:
            progreso(i + 1, len(tramos))
