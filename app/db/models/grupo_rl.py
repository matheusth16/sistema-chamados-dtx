"""Tabela grupos_rl — Fase 2, Marco 4.

rl_codigo é UNIQUE: a própria constraint corrige a race condition do antigo
GrupoRL.get_or_create() do Firestore (check-then-act não atômico) — o upsert
via INSERT ... ON CONFLICT DO NOTHING é atômico por construção do banco.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GrupoRLRow(Base):
    __tablename__ = "grupos_rl"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rl_codigo: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    criado_por_id: Mapped[str | None] = mapped_column(Text)
    area: Mapped[str | None] = mapped_column(Text)
