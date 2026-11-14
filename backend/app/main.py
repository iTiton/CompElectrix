"""Punto de entrada: API + interfaz estática compilada."""

from __future__ import annotations

import os
import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import router
from . import pvpc
from .db import init_db

__version__ = "0.2.0"

log = logging.getLogger("compelectrix")
INTERVALO_PVPC_H = 6

FRONTEND_DIR = Path(
    os.environ.get("COMPELECTRIX_FRONTEND", Path(__file__).resolve().parents[2] / "frontend" / "dist")
)


async def _actualizar_pvpc_periodicamente() -> None:
    """Descarga el PVPC al arrancar y cada pocas horas. Ligero: una petición al mes que falte."""
    await asyncio.sleep(30)
    while True:
        try:
            await asyncio.to_thread(pvpc.sincronizar)
        except Exception as e:  # noqa: BLE001 - sin conexión, REE caído…: se reintenta luego
            log.info("PVPC no actualizado: %s", e)
        await asyncio.sleep(INTERVALO_PVPC_H * 3600)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    tarea = None
    if not os.environ.get("COMPELECTRIX_SIN_TAREAS"):
        tarea = asyncio.create_task(_actualizar_pvpc_periodicamente())
    yield
    if tarea:
        tarea.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await tarea


app = FastAPI(title="CompElectrix", version=__version__, lifespan=lifespan)
app.include_router(router)

if FRONTEND_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")

    @app.get("/{ruta:path}", include_in_schema=False)
    def spa(ruta: str):
        fichero = (FRONTEND_DIR / ruta).resolve()
        if ruta and fichero.is_file() and FRONTEND_DIR.resolve() in fichero.parents:
            return FileResponse(fichero)
        return FileResponse(FRONTEND_DIR / "index.html")
