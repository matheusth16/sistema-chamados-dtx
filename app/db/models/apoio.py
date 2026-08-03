"""Tabelas de apoio sem FK entre si — Fase 2, Marco 5.

push_subscriptions, historico_usuarios, solicitacoes_lgpd, contadores_uso.
"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Index, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PushSubscriptionRow(Base):
    __tablename__ = "push_subscriptions"
    __table_args__ = (UniqueConstraint("usuario_id", "endpoint", name="uq_push_usuario_endpoint"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[str] = mapped_column(Text, nullable=False)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    p256dh: Mapped[str | None] = mapped_column(Text)
    auth: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class HistoricoUsuarioRow(Base):
    __tablename__ = "historico_usuarios"
    __table_args__ = (Index("idx_historico_usuarios_alvo_data", "usuario_alvo_id", "data_acao"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_alvo_id: Mapped[str] = mapped_column(Text, nullable=False)
    usuario_alvo_nome: Mapped[str | None] = mapped_column(Text)
    admin_id: Mapped[str | None] = mapped_column(Text)
    admin_nome: Mapped[str | None] = mapped_column(Text)
    acao: Mapped[str] = mapped_column(Text, nullable=False)
    detalhe: Mapped[str | None] = mapped_column(Text)
    data_acao: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SolicitacaoLgpdRow(Base):
    __tablename__ = "solicitacoes_lgpd"
    __table_args__ = (
        Index("idx_solicitacoes_lgpd_usuario", "usuario_id"),
        Index("idx_solicitacoes_lgpd_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[str] = mapped_column(Text, nullable=False)
    usuario_nome: Mapped[str | None] = mapped_column(Text)
    usuario_email: Mapped[str | None] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pendente")
    data_solicitacao: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    data_resolucao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    admin_id: Mapped[str | None] = mapped_column(Text)
    admin_nome: Mapped[str | None] = mapped_column(Text)


class ContadorUsoRow(Base):
    __tablename__ = "contadores_uso"
    __table_args__ = (Index("idx_contadores_uso_data", "data"),)

    user_id: Mapped[str] = mapped_column(Text, primary_key=True)
    data: Mapped[date] = mapped_column(Date, primary_key=True)
    relatorio_geracoes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    export_excel_geracoes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
