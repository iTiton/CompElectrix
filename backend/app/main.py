"""Punto de entrada: API + interfaz estática compilada."""

from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
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

    INDEX = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")

    @app.get("/{ruta:path}", include_in_schema=False)
    def spa(ruta: str, request: Request):
        fichero = (FRONTEND_DIR / ruta).resolve()
        if ruta and fichero.is_file() and FRONTEND_DIR.resolve() in fichero.parents:
            return FileResponse(fichero)
        return HTMLResponse(INDEX.replace('<base href="/" />', f'<base href="{prefijo(request)}/" />', 1))


PREFIJO_VALIDO = re.compile(r"^(/[A-Za-z0-9._~-]+)+$")


def prefijo(request: Request) -> str:
    """Ruta bajo la que la publica un proxy (p. ej. el portal: /compelectrix). Vacía si se accede directo.

    El proxy recorta el prefijo antes de reenviar y lo indica en la cabecera estándar
    X-Forwarded-Prefix; la interfaz lo recibe como <base href> y construye todo en relativo.
    """
    p = request.headers.get("x-forwarded-prefix", "").rstrip("/")
    return p if PREFIJO_VALIDO.match(p) else ""
