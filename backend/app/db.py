"""Conexión a SQLite y datos iniciales."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import date
from pathlib import Path

from sqlalchemy import event
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
        nota=(
            "Tipos ordinarios (IEE 5,11269632 %, IVA 21 %). Entre marzo y mayo de 2026 hubo una "
            "rebaja temporal (RDL 7/2026: IEE 0,5 %, IVA 10 %): añádela con las fechas exactas "
            "que figuren en tus facturas."
        ),
    ),
    VigenciaRegulada(
        fecha_desde=date(2026, 6, 26),
        bono_social_eur_anio=9.011295,
        nota="Financiación del bono social según Orden TED/634/2026. Verifica la fecha de aplicación.",
    ),
]


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
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
