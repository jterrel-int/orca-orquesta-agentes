"""Entidad Item: modelo ORM y esquemas de entrada/salida."""

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)


class ItemCrear(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ItemActualizar(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ItemLeer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    creado_en: datetime
