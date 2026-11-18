"""Endpoints REST bajo /api."""

from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field, SecretStr, model_validator
from sqlalchemy import text
from sqlmodel import Session, SQLModel, delete, func, select

from . import copias, pvpc, servicios
from .version import VERSION
from .db import DATA_DIR, compactar, ficheros_bd, get_session
from .fuentes.datadis import ClienteDatadis, ErrorDatadis
from .fuentes.octopus import ClienteOctopus, ErrorOctopus
from .importadores.consumo import a_horas_utc, importar_csv
from .motor.periodos import a_local, limites_utc, periodo_local
from .models import (
    ConsumoHorario,
    Domicilio,
    DomicilioBase,
    Factura,
    FacturaBase,
    PotenciaBase,
    PotenciaContratada,
    PrecioHorario,
    Tarifa,
    TarifaBase,
    VigenciaBase,
    VigenciaRegulada,
)

log = logging.getLogger("compelectrix")
router = APIRouter(prefix="/api")
SessionDep = Annotated[Session, Depends(get_session)]


def _obtener(s: Session, modelo: type[SQLModel], id_: int):
    obj = s.get(modelo, id_)
    if not obj:
        raise HTTPException(404, f"{modelo.__name__} {id_} no encontrado")
    return obj


def _guardar(s: Session, obj):
    s.add(obj)
    s.commit()
    s.refresh(obj)
    return obj


def _actualizar(s: Session, obj, datos: SQLModel):
    for k, v in datos.model_dump().items():
        setattr(obj, k, v)
    return _guardar(s, obj)


# ---------------------------------------------------------------- Domicilios
class DomicilioLeido(DomicilioBase):
    id: int
    num_facturas: int = 0
    ultima_factura: date | None = None
    gasto_12m: float | None = None


@router.get("/domicilios", response_model=list[DomicilioLeido])
def listar_domicilios(s: SessionDep):
    salida = []
    for d in s.exec(select(Domicilio).order_by(Domicilio.nombre)):
        facturas = list(s.exec(select(Factura).where(Factura.domicilio_id == d.id)))
        ultima = max((f.fecha_fin for f in facturas), default=None)
        gasto = None
        if ultima:
            limite = date(ultima.year - 1, ultima.month, min(ultima.day, 28))
            gasto = round(
                sum(f.importe_total or 0 for f in facturas if f.fecha_fin > limite), 2
            )
        salida.append(
            DomicilioLeido(
                **d.model_dump(), num_facturas=len(facturas), ultima_factura=ultima, gasto_12m=gasto
            )
        )
    return salida


@router.post("/domicilios", response_model=Domicilio, status_code=201)
def crear_domicilio(datos: DomicilioBase, s: SessionDep):
    return _guardar(s, Domicilio.model_validate(datos))


@router.get("/domicilios/{id_}", response_model=Domicilio)
def leer_domicilio(id_: int, s: SessionDep):
    return _obtener(s, Domicilio, id_)


@router.put("/domicilios/{id_}", response_model=Domicilio)
def editar_domicilio(id_: int, datos: DomicilioBase, s: SessionDep):
    return _actualizar(s, _obtener(s, Domicilio, id_), datos)


@router.delete("/domicilios/{id_}", status_code=204)
def borrar_domicilio(id_: int, s: SessionDep):
    d = _obtener(s, Domicilio, id_)
    s.exec(delete(ConsumoHorario).where(ConsumoHorario.domicilio_id == id_))  # type: ignore[call-overload]
    s.exec(delete(PotenciaContratada).where(PotenciaContratada.domicilio_id == id_))  # type: ignore[call-overload]
    for f in s.exec(select(Factura).where(Factura.domicilio_id == id_)):
        s.delete(f)
    s.flush()  # las facturas primero: no hay relación ORM que fije el orden
    s.delete(d)
    s.commit()


# ------------------------------------------------------- Historial de potencias
@router.get("/domicilios/{id_}/potencias", response_model=list[PotenciaContratada])
def listar_potencias(id_: int, s: SessionDep):
    _obtener(s, Domicilio, id_)
    return servicios.tramos_potencia(s, id_)


def _tras_cambiar_potencias(s: Session, d: Domicilio) -> None:
    servicios.sincronizar_potencia_actual(s, d)
    servicios.recalcular_potencia_facturas(s, d)


class PotenciaEntrada(PotenciaBase):
    @model_validator(mode="after")
    def _fechas(self):
        if self.hasta and self.hasta < self.desde:
            raise ValueError("La fecha «hasta» no puede ser anterior a «desde»")
        return self


@router.post("/domicilios/{id_}/potencias", response_model=PotenciaContratada, status_code=201)
def crear_potencia(id_: int, datos: PotenciaEntrada, s: SessionDep):
    d = _obtener(s, Domicilio, id_)
    p = _guardar(s, PotenciaContratada(domicilio_id=id_, **datos.model_dump()))
    _tras_cambiar_potencias(s, d)
    return p


@router.put("/potencias/{id_}", response_model=PotenciaContratada)
def editar_potencia(id_: int, datos: PotenciaEntrada, s: SessionDep):
    p = _actualizar(s, _obtener(s, PotenciaContratada, id_), datos)
    _tras_cambiar_potencias(s, _obtener(s, Domicilio, p.domicilio_id))
    return p


@router.delete("/potencias/{id_}", status_code=204)
def borrar_potencia(id_: int, s: SessionDep):
    p = _obtener(s, PotenciaContratada, id_)
    d = _obtener(s, Domicilio, p.domicilio_id)
    s.delete(p)
    s.commit()
    _tras_cambiar_potencias(s, d)


# ------------------------------------------------------------------ Facturas
class FacturaEntrada(FacturaBase):
    @model_validator(mode="after")
    def _fechas(self):
        if self.fecha_fin < self.fecha_inicio:
            raise ValueError("La fecha de fin no puede ser anterior a la de inicio")
        return self


@router.get("/domicilios/{id_}/facturas", response_model=list[Factura])
def listar_facturas(id_: int, s: SessionDep):
    _obtener(s, Domicilio, id_)
    q = select(Factura).where(Factura.domicilio_id == id_).order_by(Factura.fecha_inicio.desc())  # type: ignore[attr-defined]
    return list(s.exec(q))


@router.get("/domicilios/{id_}/facturas/importes")
def importes_facturas(id_: int, s: SessionDep):
    """Importe calculado de cada factura con su tarifa o la actual del domicilio."""
    return servicios.importes_calculados(s, _obtener(s, Domicilio, id_))


@router.post("/facturas", response_model=Factura, status_code=201)
def crear_factura(datos: FacturaEntrada, s: SessionDep):
    _obtener(s, Domicilio, datos.domicilio_id)
    return _guardar(s, Factura.model_validate(datos))


@router.put("/facturas/{id_}", response_model=Factura)
def editar_factura(id_: int, datos: FacturaEntrada, s: SessionDep):
    return _actualizar(s, _obtener(s, Factura, id_), datos)


@router.delete("/facturas/{id_}", status_code=204)
def borrar_factura(id_: int, s: SessionDep):
    s.delete(_obtener(s, Factura, id_))
    s.commit()


@router.get("/facturas/{id_}/simular/{tarifa_id}")
def simular_factura(id_: int, tarifa_id: int, s: SessionDep):
    f = _obtener(s, Factura, id_)
    t = _obtener(s, Tarifa, tarifa_id)
    return servicios.simular(s, f, t).a_dict() | {"importe_real": f.importe_total}


# ------------------------------------------------------------------- Tarifas
@router.get("/tarifas", response_model=list[Tarifa])
def listar_tarifas(s: SessionDep, solo_activas: bool = False):
    q = select(Tarifa)
    if solo_activas:
        q = q.where(Tarifa.activa == True)  # noqa: E712
    return list(s.exec(q.order_by(Tarifa.comercializadora, Tarifa.nombre)))


@router.post("/tarifas", response_model=Tarifa, status_code=201)
def crear_tarifa(datos: TarifaBase, s: SessionDep):
    return _guardar(s, Tarifa.model_validate(datos))


@router.put("/tarifas/{id_}", response_model=Tarifa)
def editar_tarifa(id_: int, datos: TarifaBase, s: SessionDep):
    return _actualizar(s, _obtener(s, Tarifa, id_), datos)


@router.delete("/tarifas/{id_}", status_code=204)
def borrar_tarifa(id_: int, s: SessionDep):
    t = _obtener(s, Tarifa, id_)
    en_uso = s.exec(select(func.count()).select_from(Domicilio).where(Domicilio.tarifa_actual_id == id_)).one()
    if en_uso:
        raise HTTPException(409, "La tarifa es la actual de algún domicilio; cámbiala antes o desactívala.")
    for f in s.exec(select(Factura).where(Factura.tarifa_id == id_)):
        f.tarifa_id = None
        s.add(f)
    s.delete(t)
    s.commit()


# --------------------------------------------------------------- Comparativa
class PeticionComparativa(BaseModel):
    domicilio_id: int
    desde: date | None = None
    hasta: date | None = None
    tarifa_ids: list[int] | None = None


@router.post("/comparativa")
def comparativa(p: PeticionComparativa, s: SessionDep):
    d = _obtener(s, Domicilio, p.domicilio_id)
    return servicios.comparar(s, d, p.desde, p.hasta, p.tarifa_ids)


# ------------------------------------------------------ Parámetros regulados
@router.get("/vigencias", response_model=list[VigenciaRegulada])
def listar_vigencias(s: SessionDep):
    return list(s.exec(select(VigenciaRegulada).order_by(VigenciaRegulada.fecha_desde.desc())))  # type: ignore[attr-defined]


@router.post("/vigencias", response_model=VigenciaRegulada, status_code=201)
def crear_vigencia(datos: VigenciaBase, s: SessionDep):
    return _guardar(s, VigenciaRegulada.model_validate(datos))


@router.put("/vigencias/{id_}", response_model=VigenciaRegulada)
def editar_vigencia(id_: int, datos: VigenciaBase, s: SessionDep):
    return _actualizar(s, _obtener(s, VigenciaRegulada, id_), datos)


@router.delete("/vigencias/{id_}", status_code=204)
def borrar_vigencia(id_: int, s: SessionDep):
    total = s.exec(select(func.count()).select_from(VigenciaRegulada)).one()
    if total <= 1:
        raise HTTPException(409, "Debe quedar al menos una vigencia de parámetros regulados.")
    s.delete(_obtener(s, VigenciaRegulada, id_))
    s.commit()


@router.get("/salud")
def salud():
    return {"estado": "ok", "version": VERSION}


# ======================================================================= PVPC
@router.get("/pvpc/estado")
def estado_pvpc(s: SessionDep):
    mn, mx, n = pvpc.rango_precios(s)
    return {
        "horas": n,
        "desde": a_local(mn).date().isoformat() if mn else None,
        "hasta": a_local(mx).date().isoformat() if mx else None,
        "ultima_sync": pvpc.obtener_ajuste(s, "pvpc_ultima_sync"),
        "ultimo_error": pvpc.obtener_ajuste(s, "pvpc_ultimo_error"),
        **pvpc.estado,
    }


class PeticionSync(BaseModel):
    desde: date | None = None
    hasta: date | None = None


@router.post("/pvpc/sincronizar", status_code=202)
def sincronizar_pvpc(p: PeticionSync):
    try:
        pvpc.sincronizar_en_segundo_plano(p.desde, p.hasta)
    except RuntimeError as e:
        raise HTTPException(409, str(e)) from e
    return {"mensaje": "Actualización iniciada"}


@router.post("/pvpc/al-entrar")
def pvpc_al_entrar():
    """Lo llama la interfaz al abrirse: completa los huecos de precios si los hay."""
    return pvpc.al_entrar()


@router.get("/pvpc/dia")
def precios_dia(s: SessionDep, dia: date):
    ini, fin = limites_utc(dia, dia)
    filas = s.exec(
        select(PrecioHorario)
        .where(PrecioHorario.serie == "pvpc", PrecioHorario.inicio_utc >= ini, PrecioHorario.inicio_utc < fin)
        .order_by(PrecioHorario.inicio_utc)  # type: ignore[arg-type]
    ).all()
    horas = []
    for p in filas:
        local = a_local(p.inicio_utc)
        horas.append(
            {"hora": local.strftime("%H:%M"), "precio": round(p.precio_eur_kwh, 5), "periodo": periodo_local(local)}
        )
    precios = [h["precio"] for h in horas]
    return {
        "dia": dia.isoformat(),
        "horas": horas,
        "media": round(sum(precios) / len(precios), 5) if precios else None,
        "minimo": min(horas, key=lambda h: h["precio"]) if horas else None,
        "maximo": max(horas, key=lambda h: h["precio"]) if horas else None,
    }


# ============================================================ Consumo horario
class SubidaCsv(BaseModel):
    contenido: str
    nombre: str | None = None


@router.post("/domicilios/{id_}/consumo/csv")
def importar_consumo_csv(id_: int, p: SubidaCsv, s: SessionDep):
    d = _obtener(s, Domicilio, id_)
    try:
        res = importar_csv(p.contenido)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    avisos = list(res.avisos)
    if d.cups and res.cups and d.cups.upper() not in res.cups:
        avisos.append(f"El CUPS del fichero ({', '.join(sorted(res.cups))}) no coincide con el del domicilio.")
    if len(res.cups) > 1:
        avisos.append("El fichero contiene varios CUPS; se han sumado todos en este domicilio.")
    n = servicios.guardar_consumo(s, id_, res.horas, "csv")
    return {"horas": n, "avisos": avisos, "desde": _dia_local(res.horas[0][0]), "hasta": _dia_local(res.horas[-1][0])}


def _dia_local(utc: datetime) -> str:
    return a_local(utc).date().isoformat()


@router.get("/domicilios/{id_}/consumo")
def resumen_consumo(id_: int, s: SessionDep):
    _obtener(s, Domicilio, id_)
    return servicios.resumen_consumo(s, id_)


@router.delete("/domicilios/{id_}/consumo", status_code=204)
def borrar_consumo(id_: int, s: SessionDep):
    _obtener(s, Domicilio, id_)
    s.exec(delete(ConsumoHorario).where(ConsumoHorario.domicilio_id == id_))  # type: ignore[call-overload]
    s.commit()


@router.post("/domicilios/{id_}/consumo/generar-facturas")
def generar_facturas(id_: int, s: SessionDep):
    return servicios.generar_facturas_desde_consumo(s, _obtener(s, Domicilio, id_))


# ============================================== Datadis y Octopus (sin guardar credenciales)
# Las credenciales llegan en cada petición desde el navegador (donde las rellena el gestor de
# contraseñas), se usan para esa operación y se descartan: nunca se escriben en disco ni en logs.
class Credenciales(BaseModel):
    usuario: str = Field(min_length=1)
    clave: SecretStr

    def __repr__(self) -> str:  # por si alguna vez se registrara el objeto
        return "Credenciales(***)"


@router.post("/datadis/suministros")
def suministros_datadis(c: Credenciales):
    try:
        return ClienteDatadis(c.usuario.strip().upper(), c.clave.get_secret_value()).suministros()
    except ErrorDatadis as e:
        raise HTTPException(502, str(e)) from e


class PeticionDatadis(BaseModel):
    credenciales: Credenciales
    cups: str
    codigo_distribuidora: str
    tipo_punto: int | str = 5
    desde: date
    hasta: date


@router.post("/domicilios/{id_}/consumo/datadis")
def importar_datadis(id_: int, p: PeticionDatadis, s: SessionDep):
    _obtener(s, Domicilio, id_)
    cliente = ClienteDatadis(p.credenciales.usuario.strip().upper(), p.credenciales.clave.get_secret_value())
    try:
        registros = cliente.consumos(p.cups, p.codigo_distribuidora, p.tipo_punto, p.desde, p.hasta)
    except ErrorDatadis as e:
        raise HTTPException(502, str(e)) from e
    registros = [r for r in registros if p.desde <= r.fecha <= p.hasta]
    if not registros:
        raise HTTPException(404, "Datadis no ha devuelto consumos para ese periodo.")
    res = a_horas_utc(registros)
    n = servicios.guardar_consumo(s, id_, res.horas, "datadis")
    avisos = list(res.avisos)
    try:
        tramos = cliente.potencias(p.cups, p.codigo_distribuidora)
        if tramos:
            servicios.guardar_tramos_importados(s, _obtener(s, Domicilio, id_), tramos, "datadis")
            avisos.append(f"Historial de potencia actualizado con {len(tramos)} contrato(s) de la distribuidora.")
    except Exception as e:  # noqa: BLE001 - la potencia nunca debe impedir importar el consumo
        log.exception("Error leyendo la potencia de Datadis")
        avisos.append(f"Consumo importado, pero no se pudo leer la potencia contratada ({type(e).__name__}: {e}). Revísala en el domicilio.")
    return {"horas": n, "avisos": avisos}


@router.post("/octopus/suministros")
def suministros_octopus(c: Credenciales):
    try:
        return ClienteOctopus(c.usuario.strip(), c.clave.get_secret_value()).suministros()
    except ErrorOctopus as e:
        raise HTTPException(502, str(e)) from e


class PeticionOctopus(BaseModel):
    credenciales: Credenciales
    propiedad_id: str
    cuenta: str | None = None
    desde: date
    hasta: date


@router.post("/domicilios/{id_}/consumo/octopus")
def importar_octopus(id_: int, p: PeticionOctopus, s: SessionDep):
    _obtener(s, Domicilio, id_)
    cliente = ClienteOctopus(p.credenciales.usuario.strip(), p.credenciales.clave.get_secret_value())
    try:
        horas = cliente.consumos(p.propiedad_id, p.desde, p.hasta)
    except ErrorOctopus as e:
        raise HTTPException(502, str(e)) from e
    if not horas:
        raise HTTPException(404, "Octopus no ha devuelto consumos para ese periodo.")
    n = servicios.guardar_consumo(s, id_, horas, "octopus")
    avisos: list[str] = []
    if p.cuenta:
        try:
            tramos = cliente.potencias(p.cuenta, p.propiedad_id)
            if tramos:
                servicios.guardar_tramos_importados(s, _obtener(s, Domicilio, id_), tramos, "octopus")
                avisos.append(f"Historial de potencia actualizado con {len(tramos)} contrato(s) de Octopus. Revísalo en el domicilio.")
            else:
                avisos.append("Octopus no ha indicado la potencia contratada: revísala en el domicilio.")
        except Exception as e:  # noqa: BLE001 - la potencia nunca debe impedir importar el consumo
            log.exception("Error leyendo la potencia de Octopus")
            avisos.append(f"Consumo importado, pero no se pudo leer la potencia contratada ({type(e).__name__}: {e}). Revísala en el domicilio.")
    return {"horas": n, "avisos": avisos}


# ============================================================== Almacenamiento
@router.get("/almacenamiento")
def almacenamiento(s: SessionDep):
    def contar(modelo) -> int:
        return s.exec(select(func.count()).select_from(modelo)).one()

    ficheros = ficheros_bd()
    return {
        "bytes_total": sum(p.stat().st_size for p in ficheros),
        "bytes_libres": _bytes_libres(s),
        "filas": {
            "precios_horarios": contar(PrecioHorario),
            "consumos_horarios": contar(ConsumoHorario),
            "facturas": contar(Factura),
            "tarifas": contar(Tarifa),
            "domicilios": contar(Domicilio),
        },
    }


def _bytes_libres(s: Session) -> int:
    """Espacio dentro del fichero que se recuperaría compactando."""
    libres = s.exec(text("PRAGMA freelist_count")).one()[0]  # type: ignore[call-overload]
    tam = s.exec(text("PRAGMA page_size")).one()[0]  # type: ignore[call-overload]
    return libres * tam


@router.post("/almacenamiento/compactar")
def compactar_bd(s: SessionDep):
    antes = sum(p.stat().st_size for p in ficheros_bd())
    s.close()
    compactar()
    despues = sum(p.stat().st_size for p in ficheros_bd())
    return {"antes": antes, "despues": despues}


# ========================================================== Copias de seguridad
@router.get("/copia")
def descargar_copia():
    """Descarga un .zip con todos los datos: la base de datos (para restaurar) y tablas CSV legibles."""
    fd, nombre = tempfile.mkstemp(suffix=".zip", dir=DATA_DIR)
    os.close(fd)
    ruta = copias.crear_copia_zip(Path(nombre))
    return FileResponse(
        ruta,
        media_type="application/zip",
        filename=f"compelectrix-copia-{datetime.now():%Y-%m-%d-%H%M}.zip",
        background=BackgroundTask(ruta.unlink, missing_ok=True),
    )


@router.post("/copia/restaurar")
async def restaurar_copia(request: Request):
    """Restaura una copia subida tal cual en el cuerpo de la petición (sin formulario)."""
    fd, nombre = tempfile.mkstemp(suffix=".sqlite", dir=DATA_DIR)
    ruta = Path(nombre)
    try:
        tamano = 0
        with os.fdopen(fd, "wb") as f:
            async for trozo in request.stream():
                tamano += len(trozo)
                if tamano > copias.TAMANO_MAXIMO:
                    raise HTTPException(413, "El archivo es demasiado grande para ser una copia de CompElectrix.")
                f.write(trozo)
        if tamano == 0:
            raise HTTPException(422, "No se ha recibido ningún archivo.")
        try:
            return await run_in_threadpool(copias.restaurar, ruta)
        except copias.CopiaNoValida as e:
            raise HTTPException(422, str(e)) from e
    finally:
        ruta.unlink(missing_ok=True)


@router.get("/copia/automaticas")
def copias_automaticas():
    """Copias que se guardan solas antes de cada restauración (las últimas tres)."""
    if not copias.COPIAS_AUTOMATICAS.is_dir():
        return []
    return [
        {"nombre": p.name, "bytes": p.stat().st_size, "fecha": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")}
        for p in sorted(copias.COPIAS_AUTOMATICAS.glob("antes-de-restaurar-*.sqlite"), reverse=True)
    ]


@router.get("/copia/automaticas/{nombre}")
def descargar_copia_automatica(nombre: str):
    if not re.fullmatch(r"antes-de-restaurar-\d{8}-\d{6}\.sqlite", nombre):
        raise HTTPException(404, "Copia no encontrada")
    ruta = copias.COPIAS_AUTOMATICAS / nombre
    if not ruta.is_file():
        raise HTTPException(404, "Copia no encontrada")
    return FileResponse(ruta, media_type="application/vnd.sqlite3", filename=f"compelectrix-{nombre}")



class PeticionFacturasOctopus(BaseModel):
    credenciales: Credenciales
    cuenta: str


@router.post("/domicilios/{id_}/facturas/octopus")
def importar_facturas_octopus(id_: int, p: PeticionFacturasOctopus, s: SessionDep):
    """Trae las facturas de Octopus con sus periodos, fecha de emisión y total pagado."""
    d = _obtener(s, Domicilio, id_)
    cliente = ClienteOctopus(p.credenciales.usuario.strip(), p.credenciales.clave.get_secret_value())
    try:
        facturas = cliente.facturas(p.cuenta)
    except ErrorOctopus as e:
        raise HTTPException(502, str(e)) from e
    if not facturas:
        raise HTTPException(404, "Octopus no ha devuelto facturas para esa cuenta.")
    return servicios.importar_facturas_octopus(s, d, facturas) | {"total": len(facturas)}
