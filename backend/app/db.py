"""Conexión a SQLite y datos iniciales."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import date
from pathlib import Path

from sqlalchemy import event, text
from sqlmodel import Session, SQLModel, create_engine, select

from .models import Ajuste, VigenciaRegulada

DATA_DIR = Path(os.environ.get("COMPELECTRIX_DATA", Path(__file__).resolve().parents[2] / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_URL = os.environ.get("COMPELECTRIX_DB", f"sqlite:///{DATA_DIR / 'compelectrix.db'}")

engine = create_engine(DB_URL, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _pragmas(dbapi_conn, _):  # pragma: no cover - configuración de SQLite
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    # WAL + synchronous NORMAL: menos escrituras en la tarjeta SD de la Raspberry
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.close()


VIGENCIAS_INICIALES = [
    VigenciaRegulada(
        fecha_desde=date(2021, 6, 1),
        fecha_hasta=date(2026, 6, 25),
        bono_social_eur_anio=6.979247,
        nota="Tipos ordinarios (IEE 5,11269632 %, IVA 21 %).",
    ),
    REBAJA_2026 := VigenciaRegulada(
        fecha_desde=date(2026, 3, 22),
        fecha_hasta=date(2026, 5, 31),
        iee_pct=0.5,
        iee_minimo_eur_mwh=1.0,
        iva_pct=10.0,
        bono_social_eur_anio=6.979247,
        nota=(
            "Rebaja temporal del RDL 7/2026: IVA 10 % e impuesto eléctrico 0,5 % (mínimo 1 €/MWh). "
            "Desde el 22/03/2026 (AEAT); hasta el 31/05/2026, comprobado con facturas reales de Octopus."
        ),
    ),
    VigenciaRegulada(
        fecha_desde=date(2026, 6, 26),
        bono_social_eur_anio=9.011295,
        nota="Financiación del bono social según Orden TED/634/2026. Verifica la fecha de aplicación.",
    ),
]


INDICES_OBSOLETOS = (  # redundantes con las restricciones únicas (versión 0.2.0)
    "ix_preciohorario_serie",
    "ix_preciohorario_inicio_utc",
    "ix_consumohorario_domicilio_id",
    "ix_consumohorario_inicio_utc",
)


def _columnas(s: Session, tabla: str) -> set[str]:
    return {r[1] for r in s.exec(text(f"PRAGMA table_info({tabla})"))}  # type: ignore[call-overload]


def _migrar(s: Session) -> None:
    """Cambios de estructura entre versiones (SQLite no añade columnas solo)."""
    if "dias" not in _columnas(s, "factura"):  # 1.03
        s.exec(text("ALTER TABLE factura ADD COLUMN dias INTEGER"))  # type: ignore[call-overload]
    # 1.03: comprobado con una factura real de Octopus que la base del impuesto eléctrico
    # es potencia + energía, sin el bono social. Se corrige una sola vez.
    if not s.get(Ajuste, "migracion_iee_sin_bono"):
        s.exec(text("UPDATE vigenciaregulada SET iee_incluye_bono_social = 0"))  # type: ignore[call-overload]
        s.add(Ajuste(clave="migracion_iee_sin_bono", valor="hecha"))
    # 1.04: rebaja de impuestos de 2026, ya con fechas confirmadas
    if not s.get(Ajuste, "migracion_rebaja_2026"):
        ya = s.exec(select(VigenciaRegulada).where(VigenciaRegulada.iva_pct == 10.0)).first()
        if not ya and s.exec(select(VigenciaRegulada)).first():
            s.add(VigenciaRegulada.model_validate(REBAJA_2026))
        s.add(Ajuste(clave="migracion_rebaja_2026", valor="hecha"))
    s.commit()


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        _migrar(s)
        for i in INDICES_OBSOLETOS:
            s.exec(text(f"DROP INDEX IF EXISTS {i}"))  # type: ignore[call-overload]
        if not s.exec(select(VigenciaRegulada)).first():
            s.add_all(VigenciaRegulada.model_validate(v) for v in VIGENCIAS_INICIALES)
            s.commit()
        # La versión 0.2.0 guardaba credenciales; ya no se guardan: se borran si quedan
        for clave in ("datadis_usuario", "datadis_clave", "octopus_email", "octopus_clave"):
            if a := s.get(Ajuste, clave):
                s.delete(a)
        s.commit()


def get_session() -> Iterator[Session]:
    with Session(engine) as s:
        yield s


def ficheros_bd() -> list[Path]:
    base = Path(engine.url.database or "")
    return [p for p in (base, base.with_name(base.name + "-wal"), base.with_name(base.name + "-shm")) if p.exists()]


def compactar() -> None:
    """Reescribe la base de datos sin huecos y vacía el diario WAL."""
    with engine.connect() as c:
        c.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
        c.exec_driver_sql("VACUUM")
        c.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
