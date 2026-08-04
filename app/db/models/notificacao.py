"""Tabela notificacoes — Fase 2, Marco 8.

Notificações in-app (sino). FK real em chamado_id (CASCADE — notificação sem
chamado não faz sentido). categoria/solicitante_nome ficam nullable: são
metadados opcionais usados só pra tradução dinâmica na leitura (ver
app/services/notifications_inapp.py::localizar_notificacao).
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NotificacaoRow(Base):
    __tablename__ = "notificacoes"
    __table_args__ = (
        Index("idx_notificacoes_usuario_data", "usuario_id", "data_criacao"),
        Index("idx_notificacoes_usuario_lida", "usuario_id", "lida"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[str] = mapped_column(Text, nullable=False)
    chamado_id: Mapped[int] = mapped_column(
        ForeignKey("chamados.id", ondelete="CASCADE"), nullable=False
    )
    numero_chamado: Mapped[str | None] = mapped_column(Text)
    titulo: Mapped[str] = mapped_column(Text, nullable=False)
    mensagem: Mapped[str] = mapped_column(Text, nullable=False)
    tipo: Mapped[str] = mapped_column(Text, nullable=False, default="novo_chamado")
    categoria: Mapped[str | None] = mapped_column(Text)
    solicitante_nome: Mapped[str | None] = mapped_column(Text)
    lida: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    data_criacao: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
