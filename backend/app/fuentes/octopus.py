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

    def potencias(self, cuenta: str, propiedad_id: str) -> list[dict]:
        """Potencia contratada en cada contrato, con sus fechas (para el historial de potencias)."""
        return interpretar_potencias(self._consulta(CONSULTA_POTENCIAS, {"cuenta": cuenta}), propiedad_id)

    def facturas(self, cuenta: str) -> list[dict]:
        """Facturas de la cuenta, de la más antigua a la más reciente."""
        salida, despues = [], None
        for _ in range(40):  # límite de seguridad: 1.000 facturas
            d = self._consulta(CONSULTA_FACTURAS, {"cuenta": cuenta, "despues": despues})
            b = (d.get("account") or {}).get("bills") or {}
            for e in b.get("edges") or []:
                f = interpretar_factura(e.get("node") or {})
                if f:
                    salida.append(f)
            if not (b.get("pageInfo") or {}).get("hasNextPage"):
                break
            despues = b["pageInfo"]["endCursor"]
        return sorted(salida, key=lambda f: f["desde"])

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


CONSULTA_POTENCIAS = """
query($cuenta: String!) {
  account(accountNumber: $cuenta) {
    properties { id electricitySupplyPoints { cups agreements { validFrom validTo details { contractualMaxPower } } } }
  }
}"""


def _a_dia_local(texto: str | None, fin: bool = False):
    """Fecha local de un instante de Octopus. Para el fin de un contrato, el último día completo."""
    if not texto:
        return None
    from datetime import timedelta

    from ..motor.periodos import a_local

    local = a_local(datetime.fromisoformat(texto))
    if fin and local.hour == 0 and local.minute == 0:
        return (local - timedelta(days=1)).date()  # termina a las 0:00: ese día ya no cuenta
    return local.date()


def _potencias_kw(bruto) -> list[float]:
    """Normaliza la potencia de un contrato a una lista de kW por periodo.

    Octopus la devuelve como lista (una por periodo: P1, P2…), aunque el esquema dice número; se aceptan
    los dos formatos, como número o texto, en kW o en vatios.
    """
    valores = bruto if isinstance(bruto, (list, tuple)) else [bruto]
    salida = []
    for v in valores:
        if isinstance(v, dict):  # por si algún día viene como {"period": "P1", "value": 4.5}
            v = v.get("value") or v.get("power")
        try:
            kw = float(str(v).replace(",", "."))
        except (TypeError, ValueError):
            continue
        if kw > 100:  # en vatios
            kw /= 1000
        if 0 < kw <= 15:
            salida.append(round(kw, 3))
    return salida


def interpretar_potencias(datos: dict, propiedad_id: str) -> list[dict]:
    """Tramos de potencia de los contratos de una propiedad (P1 y P2; si solo hay una, para los dos)."""
    tramos = []
    for p in (datos.get("account") or {}).get("properties") or []:
        if str(p.get("id")) != str(propiedad_id):
            continue
        for sp in p.get("electricitySupplyPoints") or []:
            for a in sp.get("agreements") or []:
                bruto = (a.get("details") or {}).get("contractualMaxPower")
                desde = _a_dia_local(a.get("validFrom"))
                kws = _potencias_kw(bruto)
                if not kws or desde is None:
                    continue
                kw1, kw2 = kws[0], (kws[1] if len(kws) > 1 else kws[0])
                tramos.append({
                    "desde": desde, "hasta": _a_dia_local(a.get("validTo"), fin=True),
                    "kw_p1": kw1, "kw_p2": kw2, "nota": "Contrato de Octopus",
                })  # fmt: skip
    return sorted(tramos, key=lambda t: t["desde"])




CONSULTA_FACTURAS = """
query($cuenta: String!, $despues: String) {
  account(accountNumber: $cuenta) {
    bills(first: 25, after: $despues, includeBillsWithoutPDF: true) {
      pageInfo { hasNextPage endCursor }
      edges { node {
        id billType fromDate toDate issuedDate
        ... on StatementType {
          totalCharges { grossTotal }
          transactions(first: 100) { edges { node {
            __typename
            ... on Charge { consumption { startDate endDate quantity unit } }
          } } }
        }
        ... on InvoiceType {
          grossAmount totalCharges { grossTotal }
          transactions(first: 100) { edges { node {
            __typename
            ... on BillCharge { consumption { startDate endDate quantity unit } }
          } } }
        }
        ... on PeriodBasedDocumentType {
          totalCharges { grossTotal }
          transactions(first: 100) { edges { node {
            __typename
            ... on BillCharge { consumption { startDate endDate quantity unit } }
          } } }
        }
      } }
    }
  }
}"""


def interpretar_factura(nodo: dict) -> dict | None:
    """Datos útiles de una factura de Octopus: periodo, emisión, total (€) y kWh facturados (si vienen)."""
    if not nodo.get("fromDate") or not nodo.get("toDate"):
        return None
    if nodo.get("billType") in ("CREDIT_NOTE",):
        return None
    total = (nodo.get("totalCharges") or {}).get("grossTotal")
    if total is None:
        total = nodo.get("grossAmount")
    kwh = 0.0
    hay_kwh = False
    for e in ((nodo.get("transactions") or {}).get("edges")) or []:
        c = (e.get("node") or {}).get("consumption") or {}
        if c.get("quantity") is not None and str(c.get("unit", "")).upper().startswith("KWH"):
            try:
                kwh += float(c["quantity"])
                hay_kwh = True
            except (TypeError, ValueError):
                pass
    return {
        "id": str(nodo.get("id")),
        "desde": date.fromisoformat(nodo["fromDate"]),
        "hasta": date.fromisoformat(nodo["toDate"]),
        "emision": date.fromisoformat(nodo["issuedDate"]) if nodo.get("issuedDate") else None,
        "total": round(total / 100, 2) if total is not None else None,  # céntimos → €
        "kwh": round(kwh, 3) if hay_kwh else None,
    }
