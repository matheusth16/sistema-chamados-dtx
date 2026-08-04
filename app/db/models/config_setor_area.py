"""Tabela config_setor_area — Fase 2, Marco 9.

Linha única (id sempre True, CHECK força isso) guardando o mapa setor→área
em JSONB — substitui o doc singleton config/setor_para_area do Firestore.
Tabela vazia (sem a linha) é um estado válido: app/utils_areas.py cai no
fallback estático nesse caso, igual ao doc inexistente no Firestore.
"""

from typing import Any

from sqlalchemy import Boolean, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConfigSetorAreaRow(Base):
    __tablename__ = "config_setor_area"
    __table_args__ = (CheckConstraint("id", name="ck_config_setor_area_singleton"),)

    id: Mapped[bool] = mapped_column(Boolean, primary_key=True, default=True)
    mapa: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
