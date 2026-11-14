"""Lectura de curvas de consumo horario (CSV de Datadis, distribuidoras y comercializadoras).

Cada fuente usa su propio formato, así que el lector es tolerante:
  - separador ; , o tabulador, decimales con coma o punto
  - fechas dd/mm/aaaa, aaaa/mm/dd o aaaa-mm-dd
  - hora como "01:00", "1" o "24": numeración de 1 a 24 (hora que TERMINA), la habitual
    en España; si aparece la hora 0 se entiende que es la hora que EMPIEZA
  - días del cambio de hora con 23 o 25 registros
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from ..motor.periodos import hora_local_a_utc, limites_utc

FORMATOS_FECHA = ("%d/%m/%Y", "%Y/%m/%d", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y")


@dataclass
class Registro:
    fecha: date
    hora: int  # tal y como viene en el fichero (1-25 si es hora final, 0-23 si es inicial)
    kwh: float
    real: bool = True


@dataclass
class Resultado:
    horas: list[tuple[datetime, float, bool]] = field(default_factory=list)  # (inicio UTC, kWh, real)
    cups: set[str] = field(default_factory=set)
    avisos: list[str] = field(default_factory=list)
    descartadas: int = 0


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", t)


def numero(t: str) -> float:
    t = t.strip().replace(" ", "")
    if "," in t and "." in t:
        t = t.replace(".", "")
    return float(t.replace(",", "."))


def fecha(t: str) -> date:
    t = t.strip().split(" ")[0].split("T")[0]
    for f in FORMATOS_FECHA:
        try:
            return datetime.strptime(t, f).date()
        except ValueError:
            continue
    raise ValueError(f"fecha no reconocida: {t!r}")


def hora(t: str) -> int:
    t = t.strip()
    m = re.match(r"^(\d{1,2})(?::\d{2})?(?::\d{2})?$", t)
    if not m:
        raise ValueError(f"hora no reconocida: {t!r}")
    return int(m.group(1))


def _columna(cabecera: list[str], *, exacta=(), contiene=(), excluye=()) -> int | None:
    norm = [_norm(c) for c in cabecera]
    for i, c in enumerate(norm):
        if c in exacta:
            return i
    for i, c in enumerate(norm):
        if any(k in c for k in contiene) and not any(k in c for k in excluye):
            return i
    return None


def leer_csv(texto: str) -> tuple[list[Registro], set[str], list[str]]:
    texto = texto.lstrip("﻿")
    muestra = texto[:4096]
    try:
        dialecto = csv.Sniffer().sniff(muestra, delimiters=";,\t")
        sep = dialecto.delimiter
    except csv.Error:
        sep = ";"
    filas = list(csv.reader(io.StringIO(texto), delimiter=sep))

    idx_cab = next(
        (i for i, f in enumerate(filas[:20]) if any(_norm(c) in ("fecha", "date", "dia") for c in f)),
        None,
    )
    if idx_cab is None:
        raise ValueError("No encuentro la fila de cabecera (debe tener una columna 'Fecha').")
    cab = filas[idx_cab]
    c_fecha = _columna(cab, exacta=("fecha", "date", "dia"))
    c_hora = _columna(cab, exacta=("hora", "hour", "time", "periodo"), contiene=("hora",))
    c_kwh = _columna(
        cab,
        exacta=("consumo", "consumokwh", "aekwh", "aewh", "ae", "consumptionkwh", "kwh", "wh"),
        contiene=("consumo", "kwh", "wh"),
        excluye=("vertid", "excedent", "surplus", "generad", "autoconsum", "reactiv"),
    )
    c_metodo = _columna(cab, contiene=("metodo", "obtencion", "obtainmethod", "real", "estimad"))
    c_cups = _columna(cab, exacta=("cups",))
    if c_fecha is None or c_hora is None or c_kwh is None:
        raise ValueError(
            "Faltan columnas: necesito fecha, hora y consumo. Cabecera encontrada: " + " | ".join(cab)
        )
    en_wh = "wh" in _norm(cab[c_kwh]) and "kwh" not in _norm(cab[c_kwh])

    registros: list[Registro] = []
    cups: set[str] = set()
    errores = 0
    for f in filas[idx_cab + 1 :]:
        if not f or all(not c.strip() for c in f):
            continue
        try:
            kwh = numero(f[c_kwh])
            r = Registro(
                fecha=fecha(f[c_fecha]),
                hora=hora(f[c_hora]),
                kwh=kwh / 1000 if en_wh else kwh,
                real=not (c_metodo is not None and _norm(f[c_metodo]).startswith("estim")),
            )
            registros.append(r)
            if c_cups is not None and f[c_cups].strip():
                cups.add(f[c_cups].strip().upper())
        except (ValueError, IndexError):
            errores += 1
    avisos = [f"{errores} fila(s) no se han podido leer y se han ignorado."] if errores else []
    return registros, cups, avisos


def a_horas_utc(registros: list[Registro]) -> Resultado:
    """Convierte registros con fecha y hora local a horas UTC, resolviendo los cambios de hora."""
    res = Resultado()
    if not registros:
        return res
    hora_inicial = any(r.hora == 0 for r in registros) and not any(r.hora >= 24 for r in registros)

    por_dia: dict[date, list[Registro]] = defaultdict(list)
    for r in registros:
        por_dia[r.fecha].append(r)

    for dia, regs in por_dia.items():
        ini, fin = limites_utc(dia, dia)
        esperadas = int((fin - ini).total_seconds() // 3600)
        etiquetas = [r.hora if hora_inicial else r.hora - 1 for r in regs]
        secuencial = len(regs) == esperadas and sorted(etiquetas) == list(range(esperadas))
        if secuencial:
            # Día completo numerado 0..n-1 (o 1..n): la posición marca la hora real
            for r, k in zip(regs, etiquetas, strict=True):
                res.horas.append((ini + timedelta(hours=k), r.kwh, r.real))
            continue
        vistas: dict[int, int] = defaultdict(int)
        for r, h in zip(regs, etiquetas, strict=True):
            if not 0 <= h <= 23:
                res.descartadas += 1
                continue
            utc = hora_local_a_utc(dia, h, segunda_vez=vistas[h] > 0)
            vistas[h] += 1
            if utc is None:
                res.descartadas += 1
                continue
            res.horas.append((utc, r.kwh, r.real))

    # Duplicados: se queda el último
    unicas = {h: (h, k, real) for h, k, real in res.horas}
    if len(unicas) < len(res.horas):
        res.avisos.append(f"{len(res.horas) - len(unicas)} hora(s) repetidas; se ha usado el último valor.")
    res.horas = sorted(unicas.values())
    if res.descartadas:
        res.avisos.append(f"{res.descartadas} registro(s) con una hora que no existe se han descartado.")
    estimadas = sum(1 for *_, real in res.horas if not real)
    if estimadas:
        res.avisos.append(f"{estimadas} hora(s) son lecturas estimadas por la distribuidora, no reales.")
    return res


def importar_csv(texto: str) -> Resultado:
    registros, cups, avisos = leer_csv(texto)
    res = a_horas_utc(registros)
    res.cups = cups
    res.avisos = avisos + res.avisos
    if not res.horas:
        raise ValueError("El fichero no contiene consumos horarios reconocibles.")
    return res
