"""Copias de seguridad: descargar todos los datos en un archivo y restaurarlos.

La copia es la propia base de datos SQLite, hecha con su mecanismo de copia en
caliente: es coherente aunque la aplicación se esté usando y se puede abrir con
cualquier programa de SQLite.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from .db import DATA_DIR, engine, init_db

TABLAS_OBLIGATORIAS = {"domicilio", "factura", "tarifa", "vigenciaregulada"}
CABECERA_SQLITE = b"SQLite format 3\x00"
TAMANO_MAXIMO = 500 * 1024 * 1024  # 500 MB, muy por encima de lo que ocupa
COPIAS_AUTOMATICAS = DATA_DIR / "copias"
CONSERVAR_AUTOMATICAS = 3


class CopiaNoValida(ValueError):
    pass


def _conexion_viva():
    """Conexión sqlite3 de bajo nivel a la base de datos de la aplicación."""
    return engine.raw_connection()


def crear_copia(destino: Path) -> Path:
    """Escribe una copia coherente de la base de datos en `destino`."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    viva = _conexion_viva()
    try:
        with sqlite3.connect(destino) as copia:
            viva.driver_connection.backup(copia)
        with sqlite3.connect(destino) as copia:
            # Un solo archivo autosuficiente (sin diario WAL aparte)
            copia.execute("PRAGMA journal_mode=DELETE")
    finally:
        viva.close()
    return destino


def validar(ruta: Path) -> dict:
    """Comprueba que el archivo es una copia de CompElectrix sana. Devuelve un resumen."""
    if ruta.stat().st_size > TAMANO_MAXIMO:
        raise CopiaNoValida("El archivo es demasiado grande para ser una copia de CompElectrix.")
    with open(ruta, "rb") as f:
        if f.read(16) != CABECERA_SQLITE:
            raise CopiaNoValida("El archivo no es una copia de seguridad de CompElectrix.")
    try:
        con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
        try:
            tablas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            faltan = TABLAS_OBLIGATORIAS - tablas
            if faltan:
                raise CopiaNoValida("El archivo es una base de datos, pero no de CompElectrix.")
            if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise CopiaNoValida("La copia está dañada y no se puede restaurar.")
            return {
                t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]  # noqa: S608 - nombres fijos
                for t in ("domicilio", "factura", "tarifa")
            }
        finally:
            con.close()
    except sqlite3.DatabaseError as e:
        raise CopiaNoValida(f"No se puede leer la copia: {e}") from e


def _copia_automatica() -> Path:
    """Guarda cómo estaban los datos antes de restaurar y conserva solo las últimas."""
    ruta = crear_copia(COPIAS_AUTOMATICAS / f"antes-de-restaurar-{datetime.now():%Y%m%d-%H%M%S}.sqlite")
    viejas = sorted(COPIAS_AUTOMATICAS.glob("antes-de-restaurar-*.sqlite"))[:-CONSERVAR_AUTOMATICAS]
    for v in viejas:
        v.unlink(missing_ok=True)
    return ruta


def restaurar(subido: Path) -> dict:
    """Sustituye todos los datos por los de la copia (.zip o .sqlite), tras validarla y guardar los actuales."""
    origen = extraer_sqlite(subido)
    try:
        return _restaurar_sqlite(origen)
    finally:
        if origen != subido:
            origen.unlink(missing_ok=True)


def _restaurar_sqlite(origen: Path) -> dict:
    resumen = validar(origen)
    previa = _copia_automatica()
    engine.dispose()  # cierra las conexiones abiertas antes de sobrescribir
    viva = _conexion_viva()
    try:
        with sqlite3.connect(f"file:{origen}?mode=ro", uri=True) as fuente:
            fuente.backup(viva.driver_connection)
    finally:
        viva.close()
    engine.dispose()
    init_db()  # completa tablas nuevas si la copia es de una versión anterior
    return {"contenido": resumen, "copia_previa": previa.name}


# ------------------------------------------------------- copia legible (ZIP)
# Tablas que se exportan también en CSV, con un nombre comprensible
TABLAS_CSV = {
    "domicilio": "domicilios",
    "tarifa": "tarifas",
    "factura": "facturas",
    "consumohorario": "consumo_horario",
    "vigenciaregulada": "impuestos_y_cargos",
}
LEEME = """COPIA DE SEGURIDAD DE COMPELECTRIX
Creada el {fecha}.

datos.sqlite
    Todos los datos. Es lo que usa la aplicación para restaurar:
    Ajustes → Copia de seguridad → Restaurar, y elige este .zip (o este archivo).

tablas/*.csv
    Los mismos datos para consultarlos con Excel, Numbers o LibreOffice.
    Separador «;», decimales con coma, texto en UTF-8. Las horas del consumo horario
    están en hora peninsular española. Modificar estos CSV no cambia la copia.

No contiene contraseñas: CompElectrix no las guarda.
"""


def _formato(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "sí" if v else "no"
    if isinstance(v, float):
        return f"{v:.6f}".rstrip("0").rstrip(".").replace(".", ",")
    return str(v)


def _csv_de_tabla(con: sqlite3.Connection, tabla: str) -> str:
    import csv
    import io

    from .motor.periodos import a_local

    cur = con.execute(f"SELECT * FROM {tabla}")  # noqa: S608 - nombres fijos
    columnas = [d[0] for d in cur.description]
    salida = io.StringIO()
    w = csv.writer(salida, delimiter=";", lineterminator="\r\n")
    hora_local = tabla == "consumohorario" and "inicio_utc" in columnas
    w.writerow(["hora_local" if (hora_local and c == "inicio_utc") else c for c in columnas])
    for fila in cur:
        valores = list(fila)
        if hora_local:
            i = columnas.index("inicio_utc")
            valores[i] = a_local(datetime.fromisoformat(valores[i])).strftime("%Y-%m-%d %H:%M")
        w.writerow([_formato(v) for v in valores])
    return "﻿" + salida.getvalue()  # BOM: Excel detecta UTF-8


def crear_copia_zip(destino: Path) -> Path:
    import zipfile

    sqlite_tmp = destino.with_suffix(".tmp.sqlite")
    try:
        crear_copia(sqlite_tmp)
        with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(sqlite_tmp, "datos.sqlite")
            z.writestr("LEEME.txt", LEEME.format(fecha=f"{datetime.now():%d/%m/%Y a las %H:%M}"))
            with sqlite3.connect(f"file:{sqlite_tmp}?mode=ro", uri=True) as con:
                existentes = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                for tabla, nombre in TABLAS_CSV.items():
                    if tabla in existentes:
                        z.writestr(f"tablas/{nombre}.csv", _csv_de_tabla(con, tabla))
    finally:
        sqlite_tmp.unlink(missing_ok=True)
    return destino


def extraer_sqlite(subido: Path) -> Path:
    """Si lo subido es el ZIP de una copia, extrae su datos.sqlite junto a él. Si no, lo devuelve tal cual."""
    import zipfile

    with open(subido, "rb") as f:
        es_zip = f.read(4) == b"PK\x03\x04"
    if not es_zip:
        return subido
    try:
        with zipfile.ZipFile(subido) as z:
            try:
                info = z.getinfo("datos.sqlite")
            except KeyError as e:
                raise CopiaNoValida("El .zip no contiene una copia de CompElectrix (falta datos.sqlite).") from e
            if info.file_size > TAMANO_MAXIMO:
                raise CopiaNoValida("La copia es demasiado grande.")
            destino = subido.with_suffix(".extraida.sqlite")
            with z.open(info) as origen, open(destino, "wb") as f:
                f.write(origen.read(TAMANO_MAXIMO + 1))
            return destino
    except zipfile.BadZipFile as e:
        raise CopiaNoValida("El .zip está dañado.") from e
