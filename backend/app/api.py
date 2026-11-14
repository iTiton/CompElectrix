"""Endpoints REST bajo /api."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator
from sqlmodel import Session, SQLModel, func, select

from . import servicios
from .db import get_session
from .models import (
    Domicilio,
    DomicilioBase,
    Factura,
    FacturaBase,
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
