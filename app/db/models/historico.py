"""Tabela historico — Fase 2, Marco 8.

FK real em chamado_id (chamados já migrado desde o Marco 7) com ON DELETE
CASCADE — histórico não faz sentido órfão. valor_anterior/valor_novo viram
JSONB: no Firestore era tipo dinâmico (hoje sempre string na prática, mas
sem garantia pro dado legado real que a migração de produção vai importar).
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class HistoricoRow(Base):
    __tablename__ = "historico"
    __table_args__ = (Index("idx_historico_chamado_data", "chamado_id", "data_acao"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chamado_id: Mapped[int] = mapped_column(
        ForeignKey("chamados.id", ondelete="CASCADE"), nullable=False
    )
    usuario_id: Mapped[str] = mapped_column(Text, nullable=False)
    usuario_nome: Mapped[str | None] = mapped_column(Text)
    acao: Mapped[str] = mapped_column(Text, nullable=False)
    campo_alterado: Mapped[str | None] = mapped_column(Text)
    valor_anterior: Mapped[Any | None] = mapped_column(JSONB)
    valor_novo: Mapped[Any | None] = mapped_column(JSONB)
    detalhe: Mapped[str | None] = mapped_column(Text)
    data_acao: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
