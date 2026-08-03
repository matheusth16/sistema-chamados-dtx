"""Tabela chamados + tabelas-junção — Fase 2, Marco 7.

participantes/observadores viram tabela-junção de verdade (não ARRAY/JSONB):
têm múltiplos campos por item. observadores não tem FK forçada em usuario_id
— é retrato congelado (nome/email no momento da inclusão), não referência
viva; o usuário pode ter sido removido/renomeado depois.

grupo_rl_id ganha FK real (grupos_rl já migrado, estável). solicitante_id/
responsavel_id ficam TEXT sem FK — Firestore nunca teve essa garantia, e
usuarios pode ter registros órfãos legados; reduz risco na migração de dado
real (Marco 11).
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChamadoRow(Base):
    __tablename__ = "chamados"
    __table_args__ = (
        Index("idx_chamados_categoria_status_data", "categoria", "status", "data_abertura"),
        Index("idx_chamados_status_data", "status", "data_abertura"),
        Index("idx_chamados_categoria_prio_data", "categoria", "prioridade", "data_abertura"),
        Index("idx_chamados_gate_status_data", "gate", "status", "data_abertura"),
        Index("idx_chamados_solicitante", "solicitante_id", "prioridade", "data_abertura"),
        Index("idx_chamados_rl_codigo", "rl_codigo"),
        Index("idx_chamados_responsavel", "responsavel_id"),
        Index(
            "idx_chamados_supervisor_acesso", "supervisor_ids_com_acesso", postgresql_using="gin"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    numero_chamado: Mapped[str | None] = mapped_column(Text, unique=True)
    categoria: Mapped[str] = mapped_column(Text, nullable=False)
    tipo_solicitacao: Mapped[str] = mapped_column(Text, nullable=False)
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    responsavel: Mapped[str | None] = mapped_column(Text)
    responsavel_id: Mapped[str | None] = mapped_column(Text)
    motivo_atribuicao: Mapped[str | None] = mapped_column(Text)
    solicitante_id: Mapped[str | None] = mapped_column(Text)
    solicitante_nome: Mapped[str | None] = mapped_column(Text)
    area: Mapped[str | None] = mapped_column(Text)
    rl_codigo: Mapped[str | None] = mapped_column(Text)
    grupo_rl_id: Mapped[int | None] = mapped_column(ForeignKey("grupos_rl.id"))
    gate: Mapped[str | None] = mapped_column(Text)
    impacto: Mapped[str | None] = mapped_column(Text)
    anexo: Mapped[str | None] = mapped_column(Text)
    anexos: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    setores_adicionais: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    supervisor_ids_com_acesso: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list
    )
    prioridade: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="Aberto")
    data_abertura: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    data_conclusao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    data_cancelamento: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    data_em_atendimento: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    previsao_atendimento: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_previsao_atendimento: Mapped[str | None] = mapped_column(Text)
    motivo_cancelamento: Mapped[str | None] = mapped_column(Text)
    motivo_ultima_escalacao: Mapped[str | None] = mapped_column(Text)
    sla_dias: Mapped[int | None] = mapped_column(Integer)
    confirmacao_solicitante: Mapped[str | None] = mapped_column(Text)
    escalacao_resposta_nivel: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    escalacao_resolucao_nivel: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    alerta_supervisor_50_enviado: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    alerta_supervisor_80_enviado: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )


class ChamadoParticipanteRow(Base):
    __tablename__ = "chamados_participantes"
    __table_args__ = (
        UniqueConstraint("chamado_id", "supervisor_id", name="uq_participante_chamado_supervisor"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chamado_id: Mapped[int] = mapped_column(
        ForeignKey("chamados.id", ondelete="CASCADE"), nullable=False
    )
    supervisor_id: Mapped[str] = mapped_column(Text, nullable=False)
    area: Mapped[str | None] = mapped_column(Text)


class ChamadoObservadorRow(Base):
    __tablename__ = "chamados_observadores"
    __table_args__ = (
        UniqueConstraint("chamado_id", "usuario_id", name="uq_observador_chamado_usuario"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chamado_id: Mapped[int] = mapped_column(
        ForeignKey("chamados.id", ondelete="CASCADE"), nullable=False
    )
    # Sem FK forçada em usuario_id: retrato congelado no momento da inclusão,
    # não referência viva (usuário pode ter sido removido/renomeado depois).
    usuario_id: Mapped[str] = mapped_column(Text, nullable=False)
    nome: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
