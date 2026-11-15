"""Sincronización del PVPC y estado de la tarea en segundo plano."""

from __future__ import annotations

import ctypes
import gc
import logging
import threading
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy.dialects.sqlite import insert
from sqlmodel import Session, func, select

from .db import engine
from .fuentes import ree
from .models import Ajuste, Factura, PrecioHorario, Tarifa
from .motor.periodos import a_local, horas_esperadas

log = logging.getLogger("compelectrix.pvpc")

INICIO_2_0TD = date(2021, 6, 1)  # antes no existía el peaje 2.0TD
DIAS_HISTORICO = 400  # primera descarga: algo más de un año

# Término de potencia del PVPC 2026 (peajes + cargos; P1 incluye el margen de
# comercialización fijo de 3,113 €/kW·año). Editable desde Tarifas.
POTENCIA_PVPC = {"p1": round(0.0738 + 3.113 / 365, 6), "p2": 0.0019}

_cerrojo = threading.Lock()
estado: dict = {"en_curso": False, "progreso": None, "mensaje": None}


def obtener_ajuste(s: Session, clave: str) -> str | None:
    a = s.get(Ajuste, clave)
    return a.valor if a else None


def guardar_ajuste(s: Session, clave: str, valor: str | None) -> None:
    a = s.get(Ajuste, clave)
    if valor is None:
        if a:
            s.delete(a)
    elif a:
        a.valor = valor
        s.add(a)
    else:
        s.add(Ajuste(clave=clave, valor=valor))
    s.commit()


def asegurar_tarifa_pvpc(s: Session) -> Tarifa:
    t = s.exec(select(Tarifa).where(Tarifa.tipo == "pvpc", Tarifa.origen == "ree")).first()
    if not t:
        t = Tarifa(
            comercializadora="Comercializadora de referencia",
            nombre="PVPC (precio regulado)",
            tipo="pvpc",
            potencia_p1=POTENCIA_PVPC["p1"],
            potencia_p2=POTENCIA_PVPC["p2"],
            energia_p1=0,
            energia_p2=0,
            energia_p3=0,
            incluye_bono_social=False,
            origen="ree",
            notas=(
                "Energía: precio horario oficial publicado por REE. Potencia 2026: peajes y cargos "
                "más el margen de comercialización; revísala si cambia la normativa."
            ),
        )
        s.add(t)
        s.commit()
        s.refresh(t)
    return t


def rango_precios(s: Session) -> tuple[datetime | None, datetime | None, int]:
    mn, mx, n = s.exec(
        select(func.min(PrecioHorario.inicio_utc), func.max(PrecioHorario.inicio_utc), func.count())
        .where(PrecioHorario.serie == "pvpc")
    ).one()
    return mn, mx, n


def guardar_precios(s: Session, filas: list[tuple[datetime, float]]) -> int:
    if not filas:
        return 0
    stmt = insert(PrecioHorario).values(
        [{"serie": "pvpc", "inicio_utc": h, "precio_eur_kwh": p} for h, p in filas]
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["serie", "inicio_utc"], set_={"precio_eur_kwh": stmt.excluded.precio_eur_kwh}
    )
    s.exec(stmt)  # type: ignore[call-overload]
    s.commit()
    return len(filas)


HORA_PUBLICACION_MANANA = time(20, 45)  # REE publica los precios del día siguiente hacia las 20:15
MINUTOS_ENTRE_COMPROBACIONES = 10


def huecos(s: Session, ahora: datetime) -> list[tuple[date, date]]:
    """Rangos de días (locales) a los que les faltan precios.

    Abarca desde el primer precio guardado (o la factura más antigua, si es anterior)
    hasta hoy, o mañana si ya se ha publicado. Si no hay nada guardado, algo más de un año.
    """
    hoy = ahora.date()
    fin = hoy + timedelta(days=1) if ahora.time() >= HORA_PUBLICACION_MANANA else hoy
    mn, _, n = rango_precios(s)
    primera_factura = s.exec(select(func.min(Factura.fecha_inicio))).one()
    if n:
        inicio = a_local(mn).date()
        if primera_factura and primera_factura < inicio:
            inicio = primera_factura
    else:
        inicio = min(primera_factura or hoy, hoy - timedelta(days=DIAS_HISTORICO))
    inicio = max(inicio, INICIO_2_0TD)

    horas_por_dia: dict[date, int] = defaultdict(int)
    for h in s.exec(select(PrecioHorario.inicio_utc).where(PrecioHorario.serie == "pvpc")):
        horas_por_dia[a_local(h).date()] += 1

    rangos: list[tuple[date, date]] = []
    d = inicio
    while d <= fin:
        if horas_por_dia.get(d, 0) < horas_esperadas(d, d):
            if rangos and rangos[-1][1] == d - timedelta(days=1):
                rangos[-1] = (rangos[-1][0], d)
            else:
                rangos.append((d, d))
        d += timedelta(days=1)
    return rangos


def sincronizar(desde: date | None = None, hasta: date | None = None, *, rangos=None, **kw) -> int:
    """Descarga y guarda precios. Devuelve cuántas horas se han guardado.

    Sin argumentos rellena los huecos. Solo puede haber una sincronización a la vez.
    """
    if not _cerrojo.acquire(blocking=False):
        raise RuntimeError("Ya hay una actualización del PVPC en curso")
    total = 0
    try:
        estado.update(en_curso=True, progreso=None, mensaje=None)
        with Session(engine) as s:
            asegurar_tarifa_pvpc(s)
            if rangos is None:
                rangos = [(desde, hasta or date.today() + timedelta(days=1))] if desde else huecos(s, datetime.now())
            pedidos = [t for a, b in rangos for t in ree.tramos_mensuales(a, b)]
            hechos = 0

            def prog(_i: int, _n: int) -> None:
                nonlocal hechos
                hechos += 1
                estado["progreso"] = f"{hechos}/{len(pedidos)}"

            for a, b in rangos:
                for filas in ree.descargar_pvpc(a, b, progreso=prog, **kw):
                    total += guardar_precios(s, filas)
            guardar_ajuste(s, "pvpc_ultima_sync", datetime.now().isoformat(timespec="seconds"))
            guardar_ajuste(s, "pvpc_ultimo_error", None)
        estado["mensaje"] = f"{total} horas actualizadas"
        return total
    except Exception as e:  # noqa: BLE001 - se informa en la interfaz
        log.warning("Error actualizando PVPC: %s", e)
        estado["mensaje"] = str(e)
        with Session(engine) as s:
            guardar_ajuste(s, "pvpc_ultimo_error", f"{datetime.now():%d/%m/%Y %H:%M} · {e}")
        raise
    finally:
        estado.update(en_curso=False, progreso=None)
        _cerrojo.release()
        liberar_memoria()


def liberar_memoria() -> None:
    """Devuelve al sistema la memoria usada durante una descarga grande (solo Linux/glibc)."""
    gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        pass


def _lanzar(**kw) -> None:
    if estado["en_curso"]:
        raise RuntimeError("Ya hay una actualización del PVPC en curso")

    def tarea() -> None:
        try:
            sincronizar(**kw)
        except Exception:  # noqa: BLE001 - ya registrado
            pass

    estado["en_curso"] = True  # para que la interfaz lo vea desde la primera consulta
    threading.Thread(target=tarea, daemon=True, name="pvpc").start()


def sincronizar_en_segundo_plano(desde: date | None = None, hasta: date | None = None) -> None:
    _lanzar(desde=desde, hasta=hasta)


def al_entrar(ahora: datetime | None = None) -> dict:
    """Al abrir la aplicación: si faltan precios, los descarga en segundo plano.

    No vuelve a preguntar a REE si ya se comprobó hace menos de unos minutos.
    """
    ahora = ahora or datetime.now()
    if estado["en_curso"]:
        return {"actualizando": True, "dias": None}
    with Session(engine) as s:
        ultimo = obtener_ajuste(s, "pvpc_ultima_comprobacion")
        if ultimo and ahora - datetime.fromisoformat(ultimo) < timedelta(minutes=MINUTOS_ENTRE_COMPROBACIONES):
            return {"actualizando": False, "dias": 0}
        rangos = huecos(s, ahora)
        guardar_ajuste(s, "pvpc_ultima_comprobacion", ahora.isoformat(timespec="seconds"))
    dias = sum((b - a).days + 1 for a, b in rangos)
    if rangos:
        _lanzar(rangos=rangos)
    return {"actualizando": bool(rangos), "dias": dias}
