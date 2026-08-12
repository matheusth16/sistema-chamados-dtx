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
    text,
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
    impacto: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
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
    # Motor de escalonamento unificado (TAT único por categoria, contado de
    # data_abertura) — ver app/services/sla_escalacao_service.py.
    escalacao_nivel: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    # Próximo tick agendado; NULL enquanto escalacao_nivel==0 (o alvo é
    # recalculado a cada passagem do job a partir de categoria+status+
    # data_abertura, porque pro AOG o alvo muda se o chamado for assumido
    # antes do limiar de reivindicação).
    escalacao_proximo_tick_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Nível-alvo (não boolean) pro qual o aviso prévio de 30min já foi
    # enviado — dedup natural, já que o próximo tick sempre mira um nível
    # maior que o anterior.
    escalacao_pre_aviso_nivel_enviado: Mapped[int | None] = mapped_column(SmallInteger)
    alerta_supervisor_50_enviado: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    alerta_supervisor_80_enviado: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    lembrete_confirmacao_1_enviado: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    lembrete_confirmacao_2_enviado: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    alerta_prazo_24h_enviado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reaberturas_solicitante_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0
    )


class ChamadoParticipanteRow(Base):
    """status só assume 'pendente' (na inclusão) ou 'concluido' (após
    concluir_minha_parte) — ver app/services/escalonamento_service.py."""

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
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pendente")
    concluido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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


class ChamadoPrevisaoSolicitacaoRow(Base):
    """Pedido de previsão de atendimento — une o antigo "Prazo do chamado
    (dias)" (sla_dias) e "Adiar avisos de escalonamento" (previsao_atendimento)
    numa única solicitação, que só passa a valer em chamados.previsao_atendimento
    depois de aprovada pelo gestor_setor da área do chamado (ver
    app/services/previsao_atendimento_service.py). Tabela é audit trail
    completo — guarda todo pedido, aprovado/rejeitado/pendente, nunca
    atualizado além da própria decisão."""

    __tablename__ = "chamado_previsao_solicitacoes"
    __table_args__ = (
        Index("idx_previsao_solicitacoes_chamado", "chamado_id"),
        Index(
            "uq_previsao_solicitacoes_pendente_por_chamado",
            "chamado_id",
            unique=True,
            postgresql_where=text("status = 'pendente'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chamado_id: Mapped[int] = mapped_column(
        ForeignKey("chamados.id", ondelete="CASCADE"), nullable=False
    )
    solicitante_id: Mapped[str] = mapped_column(Text, nullable=False)
    solicitante_nome: Mapped[str] = mapped_column(Text, nullable=False)
    previsao_solicitada: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    motivo: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pendente")
    gestor_id: Mapped[str | None] = mapped_column(Text)
    gestor_nome: Mapped[str | None] = mapped_column(Text)
    motivo_rejeicao: Mapped[str | None] = mapped_column(Text)
    decidido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
