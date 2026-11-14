"""Endpoints REST bajo /api."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator
from sqlmodel import Session, SQLModel, delete, func, select

from . import pvpc, servicios
from .db import get_session
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
    PrecioHorario,
    Tarifa,
    TarifaBase,
    VigenciaBase,
    VigenciaRegulada,
)

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
    for f in s.exec(select(Factura).where(Factura.domicilio_id == id_)):
        s.delete(f)
    s.flush()  # las facturas primero: no hay relación ORM que fije el orden
    s.delete(d)
    s.commit()


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
    return {"estado": "ok"}


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


# ==================================================================== Datadis
class CredencialesDatadis(BaseModel):
    usuario: str
    clave: str | None = None  # vacía = conservar la guardada


def _cliente_datadis(s: Session) -> ClienteDatadis:
    u = pvpc.obtener_ajuste(s, "datadis_usuario")
    c = pvpc.obtener_ajuste(s, "datadis_clave")
    if not u or not c:
        raise HTTPException(400, "Configura primero tu usuario y contraseña de Datadis en Ajustes.")
    return ClienteDatadis(u, c)


@router.get("/datadis")
def ver_datadis(s: SessionDep):
    return {
        "usuario": pvpc.obtener_ajuste(s, "datadis_usuario"),
        "tiene_clave": bool(pvpc.obtener_ajuste(s, "datadis_clave")),
    }


@router.put("/datadis")
def guardar_datadis(p: CredencialesDatadis, s: SessionDep):
    pvpc.guardar_ajuste(s, "datadis_usuario", p.usuario.strip().upper())
    if p.clave:
        pvpc.guardar_ajuste(s, "datadis_clave", p.clave)
    return ver_datadis(s)


@router.delete("/datadis", status_code=204)
def borrar_datadis(s: SessionDep):
    pvpc.guardar_ajuste(s, "datadis_usuario", None)
    pvpc.guardar_ajuste(s, "datadis_clave", None)


@router.get("/datadis/suministros")
def suministros_datadis(s: SessionDep):
    try:
        return _cliente_datadis(s).suministros()
    except ErrorDatadis as e:
        raise HTTPException(502, str(e)) from e


class PeticionDatadis(BaseModel):
    cups: str
    codigo_distribuidora: str
    tipo_punto: int | str = 5
    desde: date
    hasta: date


@router.post("/domicilios/{id_}/consumo/datadis")
def importar_datadis(id_: int, p: PeticionDatadis, s: SessionDep):
    _obtener(s, Domicilio, id_)
    try:
        registros = _cliente_datadis(s).consumos(p.cups, p.codigo_distribuidora, p.tipo_punto, p.desde, p.hasta)
    except ErrorDatadis as e:
        raise HTTPException(502, str(e)) from e
    registros = [r for r in registros if p.desde <= r.fecha <= p.hasta]
    if not registros:
        raise HTTPException(404, "Datadis no ha devuelto consumos para ese periodo.")
    res = a_horas_utc(registros)
    n = servicios.guardar_consumo(s, id_, res.horas, "datadis")
    return {"horas": n, "avisos": res.avisos}


# ==================================================================== Octopus
class CredencialesOctopus(BaseModel):
    email: str
    clave: str | None = None


def _cliente_octopus(s: Session) -> ClienteOctopus:
    e = pvpc.obtener_ajuste(s, "octopus_email")
    c = pvpc.obtener_ajuste(s, "octopus_clave")
    if not e or not c:
        raise HTTPException(400, "Configura primero tu email y contraseña de Octopus en Ajustes.")
    return ClienteOctopus(e, c)


@router.get("/octopus")
def ver_octopus(s: SessionDep):
    return {
        "email": pvpc.obtener_ajuste(s, "octopus_email"),
        "tiene_clave": bool(pvpc.obtener_ajuste(s, "octopus_clave")),
    }


@router.put("/octopus")
def guardar_octopus(p: CredencialesOctopus, s: SessionDep):
    pvpc.guardar_ajuste(s, "octopus_email", p.email.strip())
    if p.clave:
        pvpc.guardar_ajuste(s, "octopus_clave", p.clave)
    return ver_octopus(s)


@router.delete("/octopus", status_code=204)
def borrar_octopus(s: SessionDep):
    pvpc.guardar_ajuste(s, "octopus_email", None)
    pvpc.guardar_ajuste(s, "octopus_clave", None)


@router.get("/octopus/suministros")
def suministros_octopus(s: SessionDep):
    try:
        return _cliente_octopus(s).suministros()
    except ErrorOctopus as e:
        raise HTTPException(502, str(e)) from e


class PeticionOctopus(BaseModel):
    propiedad_id: str
    desde: date
    hasta: date


@router.post("/domicilios/{id_}/consumo/octopus")
def importar_octopus(id_: int, p: PeticionOctopus, s: SessionDep):
    _obtener(s, Domicilio, id_)
    try:
        horas = _cliente_octopus(s).consumos(p.propiedad_id, p.desde, p.hasta)
    except ErrorOctopus as e:
        raise HTTPException(502, str(e)) from e
    if not horas:
        raise HTTPException(404, "Octopus no ha devuelto consumos para ese periodo.")
    return {"horas": servicios.guardar_consumo(s, id_, horas, "octopus"), "avisos": []}
