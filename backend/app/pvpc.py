"""Sincronización del PVPC y estado de la tarea en segundo plano."""

from __future__ import annotations

import logging
import threading
from datetime import date, datetime, timedelta

from sqlalchemy.dialects.sqlite import insert
from sqlmodel import Session, func, select

from .db import engine
from .fuentes import ree
from .models import Ajuste, Factura, PrecioHorario, Tarifa
from .motor.periodos import a_local

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


def rango_por_defecto(s: Session, hoy: date) -> tuple[date, date]:
    hasta = hoy + timedelta(days=1)  # mañana se publica sobre las 20:30
    _, mx, n = rango_precios(s)
    if n:
        desde = a_local(mx).date()  # vuelve a pedir el último día por si estaba incompleto
    else:
        primera = s.exec(select(func.min(Factura.fecha_inicio))).one()
        desde = min(primera or hoy, hoy - timedelta(days=DIAS_HISTORICO))
    return max(desde, INICIO_2_0TD), hasta


def sincronizar(desde: date | None = None, hasta: date | None = None, **kw) -> int:
    """Descarga y guarda precios. Devuelve cuántas horas se han guardado.

    Solo puede haber una sincronización a la vez.
    """
    if not _cerrojo.acquire(blocking=False):
        raise RuntimeError("Ya hay una actualización del PVPC en curso")
    total = 0
    try:
        estado.update(en_curso=True, progreso=None, mensaje=None)
        with Session(engine) as s:
            asegurar_tarifa_pvpc(s)
            d0, d1 = rango_por_defecto(s, date.today())
            desde, hasta = desde or d0, hasta or d1

            def prog(i: int, n: int) -> None:
                estado["progreso"] = f"{i}/{n} meses"

            for filas in ree.descargar_pvpc(desde, hasta, progreso=prog, **kw):
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


def sincronizar_en_segundo_plano(desde: date | None = None, hasta: date | None = None) -> None:
    if estado["en_curso"]:
        raise RuntimeError("Ya hay una actualización del PVPC en curso")

    def tarea() -> None:
        try:
            sincronizar(desde, hasta)
        except Exception:  # noqa: BLE001 - ya registrado
            pass

    threading.Thread(target=tarea, daemon=True, name="pvpc").start()
