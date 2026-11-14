"""Tablas de la base de datos (SQLModel sobre SQLite)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def _ahora() -> datetime:
    return datetime.now()


# ---------------------------------------------------------------- Domicilios
class DomicilioBase(SQLModel):
    nombre: str = Field(min_length=1, max_length=80)
    direccion: str | None = None
    cups: str | None = Field(default=None, max_length=22)
    distribuidora: str | None = None
    potencia_p1_kw: float = Field(default=3.45, ge=0, le=15)
    potencia_p2_kw: float = Field(default=3.45, ge=0, le=15)
    tarifa_actual_id: int | None = Field(default=None, foreign_key="tarifa.id")
    color: str | None = None
    notas: str | None = None


class Domicilio(DomicilioBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    creado: datetime = Field(default_factory=_ahora)


# ------------------------------------------------------------------- Tarifas
class TarifaBase(SQLModel):
    comercializadora: str = Field(min_length=1)
    nombre: str = Field(min_length=1)
    tipo: str = Field(default="fija", description="fija | indexada | pvpc")
    potencia_p1: float = Field(ge=0, description="€/kW·día")
    potencia_p2: float = Field(ge=0, description="€/kW·día")
    energia_p1: float = Field(ge=0, description="€/kWh")
    energia_p2: float = Field(ge=0, description="€/kWh")
    energia_p3: float = Field(ge=0, description="€/kWh")
    cuota_fija_mes: float = Field(default=0, ge=0)
    descuento_energia_pct: float = Field(default=0, ge=0, le=100)
    incluye_bono_social: bool = False
    permanencia_meses: int = Field(default=0, ge=0)
    url: str | None = None
    notas: str | None = None
    vigente_desde: date | None = None
    origen: str = Field(default="manual", description="manual | cnmc | octopus | ...")
    activa: bool = True


class Tarifa(TarifaBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    actualizada: datetime = Field(default_factory=_ahora)


# ------------------------------------------------------------------ Facturas
class FacturaBase(SQLModel):
    domicilio_id: int = Field(foreign_key="domicilio.id", index=True)
    fecha_inicio: date
    fecha_fin: date
    comercializadora: str | None = None
    tarifa_id: int | None = Field(default=None, foreign_key="tarifa.id")
    numero: str | None = None
    kwh_p1: float = Field(default=0, ge=0)
    kwh_p2: float = Field(default=0, ge=0)
    kwh_p3: float = Field(default=0, ge=0)
    kw_p1: float = Field(default=0, ge=0)
    kw_p2: float = Field(default=0, ge=0)
    importe_total: float | None = Field(default=None, description="Total real de la factura con IVA")
    importe_potencia: float | None = None
    importe_energia: float | None = None
    importe_otros: float | None = None
    origen: str = Field(default="manual", description="manual | pdf | imagen | texto | datadis | api")
    notas: str | None = None


class Factura(FacturaBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    creada: datetime = Field(default_factory=_ahora)


# ------------------------------------------------------ Parámetros regulados
class VigenciaBase(SQLModel):
    fecha_desde: date
    fecha_hasta: date | None = None
    iee_pct: float = 5.11269632
    iee_minimo_eur_mwh: float = 1.0
    iva_pct: float = 21.0
    alquiler_contador_eur_dia: float = round(0.81 * 12 / 365, 6)
    bono_social_eur_anio: float = 0.0
    iee_incluye_bono_social: bool = True
    nota: str | None = None


class VigenciaRegulada(VigenciaBase, table=True):
    id: int | None = Field(default=None, primary_key=True)


# ------------------------------------------------------- Datos horarios
class PrecioHorario(SQLModel, table=True):
    """Precio horario de una serie (de momento solo el PVPC 2.0TD de REE)."""

    __table_args__ = (UniqueConstraint("serie", "inicio_utc"),)
    id: int | None = Field(default=None, primary_key=True)
    serie: str = Field(default="pvpc", index=True)
    inicio_utc: datetime = Field(index=True)
    precio_eur_kwh: float


class ConsumoHorario(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("domicilio_id", "inicio_utc"),)
    id: int | None = Field(default=None, primary_key=True)
    domicilio_id: int = Field(foreign_key="domicilio.id", index=True)
    inicio_utc: datetime = Field(index=True)
    kwh: float = Field(ge=0)
    real: bool = True  # False si la distribuidora lo marca como estimado
    origen: str = "csv"


class Ajuste(SQLModel, table=True):
    """Pares clave/valor de configuración local (credenciales, estado de sincronización…)."""

    clave: str = Field(primary_key=True)
    valor: str
