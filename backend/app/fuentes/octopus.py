"""Cliente de la API GraphQL de Octopus Energy España (plataforma Kraken).

Usa el email y la contraseña del área de cliente. Permite listar los
suministros de la cuenta y descargar el consumo horario de cada uno.

Las consultas están validadas contra el esquema público de la API, pero la
descarga de datos reales aún no se ha probado con una cuenta.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import date, datetime, timezone

URL = "https://api.oees-kraken.energy/v1/graphql/"
CABECERAS = {"User-Agent": "Mozilla/5.0 (X11; Linux) home-energy-app", "Content-Type": "application/json"}

MUTACION_TOKEN = """
mutation($email: String!, $password: String!) {
  obtainKrakenToken(input: {email: $email, password: $password}) { token }
}"""

CONSULTA_CUENTAS = """
query { viewer { accounts { number } } }"""

CONSULTA_PROPIEDADES = """
query($cuenta: String!) {
  account(accountNumber: $cuenta) {
    properties { id address electricitySupplyPoints { cups } gasSupplyPoints { cups } }
  }
}"""

CONSULTA_CONSUMO = """
query($id: ID!, $desde: Date, $hasta: Date, $despues: String) {
  property(id: $id) {
    measurements(
      startOn: $desde, endOn: $hasta, timezone: "Europe/Madrid", first: 500, after: $despues,
      utilityFilters: [{electricityFilters: {readingFrequencyType: HOUR_INTERVAL, readingDirection: CONSUMPTION}}]
    ) {
      pageInfo { hasNextPage endCursor }
      edges { node { value unit ... on IntervalMeasurementType { startAt endAt } } }
    }
  }
}"""


class ErrorOctopus(Exception):
    pass


class ClienteOctopus:
    def __init__(self, email: str, clave: str):
        self.email, self.clave = email, clave
        self.token: str | None = None

    def _consulta(self, consulta: str, variables: dict | None = None, autenticar: bool = True) -> dict:
        if autenticar and not self.token:
            self.entrar()
        cab = dict(CABECERAS)
        if autenticar and self.token:
            cab["Authorization"] = self.token
        req = urllib.request.Request(
            URL, data=json.dumps({"query": consulta, "variables": variables or {}}).encode(), headers=cab
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                datos = json.load(r)
        except urllib.error.HTTPError as e:
            try:
                datos = json.load(e)
            except json.JSONDecodeError:
                raise ErrorOctopus(f"Octopus respondió {e.code}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            raise ErrorOctopus(f"No se pudo conectar con Octopus: {e}") from e
        if datos.get("errors"):
            err = datos["errors"][0]
            ext = err.get("extensions", {})
            if ext.get("errorCode") == "KT-CT-1138" or "credentials" in str(ext.get("errorDescription", "")):
                raise ErrorOctopus("Email o contraseña de Octopus incorrectos.")
            raise ErrorOctopus(ext.get("errorDescription") or err.get("message", "Error de Octopus"))
        return datos["data"]

    def entrar(self) -> None:
        d = self._consulta(MUTACION_TOKEN, {"email": self.email, "password": self.clave}, autenticar=False)
        self.token = d["obtainKrakenToken"]["token"]

    def suministros(self) -> list[dict]:
        salida = []
        for cuenta in self._consulta(CONSULTA_CUENTAS)["viewer"]["accounts"]:
            num = cuenta["number"]
            for p in self._consulta(CONSULTA_PROPIEDADES, {"cuenta": num})["account"]["properties"]:
                salida.append(
                    {
                        "cuenta": num,
                        "propiedad_id": p["id"],
                        "direccion": p.get("address"),
                        "cups_luz": [x["cups"] for x in p.get("electricitySupplyPoints") or []],
                        "cups_gas": [x["cups"] for x in p.get("gasSupplyPoints") or []],
                    }
                )
        return salida

    def consumos(self, propiedad_id: str, desde: date, hasta: date) -> list[tuple[datetime, float, bool]]:
        """Horas de consumo como (inicio UTC sin zona, kWh, real)."""
        horas: list[tuple[datetime, float, bool]] = []
        despues = None
        for _ in range(500):  # límite de seguridad: ~10 años de horas
            d = self._consulta(
                CONSULTA_CONSUMO,
                {"id": propiedad_id, "desde": desde.isoformat(), "hasta": hasta.isoformat(), "despues": despues},
            )
            m = d["property"]["measurements"]
            for e in m["edges"]:
                n = e["node"]
                if not n.get("startAt") or n.get("value") is None:
                    continue
                kwh = float(n["value"])
                if (n.get("unit") or "kwh").lower() == "wh":
                    kwh /= 1000
                inicio = datetime.fromisoformat(n["startAt"]).astimezone(timezone.utc).replace(tzinfo=None)
                horas.append((inicio, kwh, True))
            if not m["pageInfo"]["hasNextPage"]:
                break
            despues = m["pageInfo"]["endCursor"]
        return sorted(horas)
