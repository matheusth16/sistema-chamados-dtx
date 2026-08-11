"""chamados_escalonamento_unificado_digest

Colapsa escalacao_resposta_nivel + escalacao_resolucao_nivel (duas escadas
independentes) em uma única escalacao_nivel — o motor de escalonamento
passa a usar um único prazo (TAT) por categoria, contado de data_abertura,
com cadência que muda conforme o status atual do chamado. Ver
app/services/sla_escalacao_service.py.

Backfill: chamados 'Aberto' zeram o nível (thresholds antigos de 1-4h não
são comparáveis ao TAT novo, em dias); chamados 'Em Atendimento' carregam o
escalacao_resolucao_nivel antigo — o throttle de "+1 nível por execução do
job" (preservado no motor novo) absorve a diferença suavemente.

Também cria digest_diario_usuarios (rastreio por pessoa do último envio do
resumo diário de chamados abertos).

Revision ID: 671588c434ba
Revises: 44a16629ced2
Create Date: 2026-08-11 09:03:30.884181

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "671588c434ba"
down_revision: str | Sequence[str] | None = "44a16629ced2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("chamados", sa.Column("escalacao_nivel", sa.SmallInteger(), nullable=True))
    op.add_column(
        "chamados",
        sa.Column("escalacao_proximo_tick_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "chamados",
        sa.Column("escalacao_pre_aviso_nivel_enviado", sa.SmallInteger(), nullable=True),
    )

    conn = op.get_bind()
    # Aberto: thresholds antigos (1-4h úteis) não são comparáveis ao TAT novo
    # (dias úteis / 24h AOG) — reinicia limpo. Cobre também o sentinel
    # escalacao_resposta_nivel=4 gravado na criação de chamados AOG (não pode
    # sobreviver, ou bloquearia pra sempre a nova escalada de reivindicação).
    conn.execute(sa.text("UPDATE chamados SET escalacao_nivel = 0 WHERE status = 'Aberto'"))
    # Em Atendimento: carrega o nível antigo de resolução como aproximação —
    # o throttle de "+1 nível por execução do job" absorve a diferença.
    conn.execute(
        sa.text(
            "UPDATE chamados SET escalacao_nivel = LEAST(COALESCE(escalacao_resolucao_nivel, 0), 4) "
            "WHERE status = 'Em Atendimento'"
        )
    )
    conn.execute(sa.text("UPDATE chamados SET escalacao_nivel = 0 WHERE escalacao_nivel IS NULL"))

    op.alter_column("chamados", "escalacao_nivel", nullable=False, server_default="0")
    op.drop_column("chamados", "escalacao_resposta_nivel")
    op.drop_column("chamados", "escalacao_resolucao_nivel")

    op.create_table(
        "digest_diario_usuarios",
        sa.Column("usuario_id", sa.Text(), nullable=False),
        sa.Column("ultimo_envio_em", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("usuario_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("digest_diario_usuarios")

    op.add_column(
        "chamados",
        sa.Column(
            "escalacao_resposta_nivel", sa.SmallInteger(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "chamados",
        sa.Column(
            "escalacao_resolucao_nivel", sa.SmallInteger(), nullable=False, server_default="0"
        ),
    )
    op.drop_column("chamados", "escalacao_pre_aviso_nivel_enviado")
    op.drop_column("chamados", "escalacao_proximo_tick_em")
    op.drop_column("chamados", "escalacao_nivel")
