"""Periodos horarios del peaje 2.0TD (Circular CNMC 3/2020) y utilidades de hora.

Energía (hora peninsular):
  P1 punta : lunes a viernes 10-14 h y 18-22 h
  P2 llano : lunes a viernes 8-10 h, 14-18 h y 22-24 h
  P3 valle : lunes a viernes 0-8 h, y las 24 h de sábados, domingos y festivos

Festivos: los nacionales de fecha fija y no sustituibles (no cuentan los
autonómicos, los locales ni el Viernes Santo).

Internamente las horas se guardan en UTC para evitar ambigüedades en los
cambios de hora; el periodo se calcula siempre en hora local de Madrid.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

MADRID = ZoneInfo("Europe/Madrid")

# (mes, día)
FESTIVOS_NACIONALES = {(1, 1), (1, 6), (5, 1), (8, 15), (10, 12), (11, 1), (12, 6), (12, 8), (12, 25)}

PUNTA = {10, 11, 12, 13, 18, 19, 20, 21}
LLANO = {8, 9, 14, 15, 16, 17, 22, 23}


def es_festivo(d: date) -> bool:
    return (d.month, d.day) in FESTIVOS_NACIONALES


def periodo_local(local: datetime) -> str:
    """Periodo de energía ('p1', 'p2', 'p3') de una hora local que empieza en `local`."""
    if local.weekday() >= 5 or es_festivo(local.date()):
        return "p3"
    if local.hour in PUNTA:
        return "p1"
    if local.hour in LLANO:
        return "p2"
    return "p3"


def periodo_utc(inicio_utc: datetime) -> str:
    return periodo_local(a_local(inicio_utc))


def a_local(utc: datetime) -> datetime:
    if utc.tzinfo is None:
        utc = utc.replace(tzinfo=timezone.utc)
    return utc.astimezone(MADRID)


def a_utc_naive(dt: datetime) -> datetime:
    """UTC sin zona (lo que se guarda en SQLite)."""
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def limites_utc(desde: date, hasta: date) -> tuple[datetime, datetime]:
    """[inicio, fin) en UTC naive para los días locales desde..hasta (ambos incluidos)."""
    ini = datetime.combine(desde, datetime.min.time(), MADRID)
    fin = datetime.combine(hasta + timedelta(days=1), datetime.min.time(), MADRID)
    return a_utc_naive(ini), a_utc_naive(fin)


def horas_esperadas(desde: date, hasta: date) -> int:
    """Número real de horas (23, 24 o 25 por día según el cambio de hora)."""
    ini, fin = limites_utc(desde, hasta)
    return int((fin - ini).total_seconds() // 3600)


def hora_local_a_utc(dia: date, hora: int, segunda_vez: bool = False) -> datetime | None:
    """Hora local de inicio (0-23) a UTC naive. None si esa hora no existe (adelanto de marzo).

    `segunda_vez` elige la segunda aparición de la hora repetida en el retraso de octubre.
    """
    local = datetime(dia.year, dia.month, dia.day, hora, tzinfo=MADRID).replace(fold=int(segunda_vez))
    utc = local.astimezone(timezone.utc)
    # Si al volver a local no coincide, la hora no existe
    if utc.astimezone(MADRID).replace(tzinfo=None) != local.replace(tzinfo=None):
        return None
    return utc.replace(tzinfo=None)
