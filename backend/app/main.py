"""Punto de entrada: API + interfaz estática compilada."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import router
from .db import init_db

__version__ = "0.2.0"

FRONTEND_DIR = Path(
    os.environ.get("COMPELECTRIX_FRONTEND", Path(__file__).resolve().parents[2] / "frontend" / "dist")
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Sin tareas periódicas: los precios del PVPC se completan al abrir la interfaz
    # (POST /api/pvpc/al-entrar), así en reposo no se consume CPU ni red.
    init_db()
    yield


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
