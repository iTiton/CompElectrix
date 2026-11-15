"""Cliente de la API privada de Datadis (consumos de las distribuidoras).

Necesita el usuario (NIF) y la contraseña de datadis.es. Datadis limita el
número de consultas diarias, así que se piden los meses de uno en uno y con
pausa entre ellos.

EXPERIMENTAL: el formato de respuesta se ha implementado según la
documentación pública de Datadis, pero aún no se ha probado con una cuenta
real. Por eso se aceptan tanto listas como objetos con la lista dentro.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import date

from ..importadores.consumo import Registro, fecha, hora
from .ree import tramos_mensuales

BASE = "https://datadis.es"
CABECERAS = {"User-Agent": "Mozilla/5.0 (X11; Linux) home-energy-app"}


class ErrorDatadis(Exception):
    pass


def _peticion(req: urllib.request.Request) -> bytes:
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode(errors="ignore")[:300]
        if e.code in (401, 403) or "credentials" in cuerpo.lower():
            raise ErrorDatadis("Usuario o contraseña de Datadis incorrectos.") from e
        if e.code == 429:
            raise ErrorDatadis("Datadis ha limitado las consultas por hoy. Prueba mañana.") from e
        raise ErrorDatadis(f"Datadis respondió {e.code}: {cuerpo}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise ErrorDatadis(f"No se pudo conectar con Datadis: {e}") from e


def _lista(datos, *claves: str) -> list:
    if isinstance(datos, list):
        return datos
    if isinstance(datos, dict):
        for c in claves:
            if isinstance(datos.get(c), list):
                return datos[c]
    return []


class ClienteDatadis:
    def __init__(self, usuario: str, clave: str, dormir: Callable[[float], None] = time.sleep):
        self.usuario, self.clave, self.dormir = usuario, clave, dormir
        self.token: str | None = None

    def entrar(self) -> None:
        cuerpo = urllib.parse.urlencode({"username": self.usuario, "password": self.clave}).encode()
        req = urllib.request.Request(
            f"{BASE}/nikola-auth/tokens/login",
            data=cuerpo,
            headers={**CABECERAS, "Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        token = _peticion(req).decode().strip()
        if not token or token.startswith("{"):
            raise ErrorDatadis("Datadis no ha devuelto un token válido.")
        self.token = token

    def _get(self, ruta: str, params: dict) -> object:
        if not self.token:
            self.entrar()
        url = f"{BASE}/api-private/api/{ruta}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={**CABECERAS, "Authorization": f"Bearer {self.token}"})
        bruto = _peticion(req)
        try:
            return json.loads(bruto)
        except json.JSONDecodeError as e:
            raise ErrorDatadis("Respuesta de Datadis no válida.") from e

    def suministros(self) -> list[dict]:
        datos = _lista(self._get("get-supplies", {}), "supplies", "response")
        return [
            {
                "cups": s.get("cups"),
                "direccion": ", ".join(
                    x for x in (s.get("address"), s.get("municipality"), s.get("province")) if x
                ),
                "distribuidora": s.get("distributor"),
                "codigo_distribuidora": str(s.get("distributorCode", "")),
                "tipo_punto": s.get("pointType"),
                "desde": s.get("validDateFrom"),
                "hasta": s.get("validDateTo"),
            }
            for s in datos
        ]

    def consumos(
        self, cups: str, codigo_distribuidora: str, tipo_punto: int | str, desde: date, hasta: date
    ) -> list[Registro]:
        registros: list[Registro] = []
        for i, (ini, fin) in enumerate(tramos_mensuales(desde, hasta)):
            if i:
                self.dormir(2)
            datos = self._get(
                "get-consumption-data",
                {
                    "cups": cups,
                    "distributorCode": codigo_distribuidora,
                    "startDate": f"{ini:%Y/%m}",
                    "endDate": f"{fin:%Y/%m}",
                    "measurementType": 0,  # horario
                    "pointType": tipo_punto,
                },
            )
            for c in _lista(datos, "timeCurve", "response"):
                try:
                    registros.append(
                        Registro(
                            fecha=fecha(c["date"]),
                            hora=hora(c["time"]),
                            kwh=float(c.get("consumptionKWh") or 0),
                            real=str(c.get("obtainMethod", "Real")).lower().startswith("real"),
                        )
                    )
                except (KeyError, ValueError, TypeError):
                    continue
        return registros
