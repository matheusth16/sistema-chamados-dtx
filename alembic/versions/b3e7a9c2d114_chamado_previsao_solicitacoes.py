"""chamado_previsao_solicitacoes

Unifica "Prazo do chamado (dias)" e "Adiar avisos de escalonamento" numa
única solicitação de previsão de atendimento, que só passa a valer
(chamados.previsao_atendimento) depois de aprovada pelo gestor do setor da
área do chamado. Tabela de audit trail — guarda todo pedido, não só o
ativo — com índice único parcial garantindo no máximo 1 pedido pendente
por chamado.

Revision ID: b3e7a9c2d114
Revises: fa06279766ba
Create Date: 2026-08-12 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3e7a9c2d114"
down_revision: str | Sequence[str] | None = "fa06279766ba"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "chamado_previsao_solicitacoes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "chamado_id",
            sa.Integer(),
            sa.ForeignKey("chamados.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("solicitante_id", sa.Text(), nullable=False),
        sa.Column("solicitante_nome", sa.Text(), nullable=False),
        sa.Column("previsao_solicitada", sa.DateTime(timezone=True), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pendente"),
        sa.Column("gestor_id", sa.Text(), nullable=True),
        sa.Column("gestor_nome", sa.Text(), nullable=True),
        sa.Column("motivo_rejeicao", sa.Text(), nullable=True),
        sa.Column("decidido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "idx_previsao_solicitacoes_chamado",
        "chamado_previsao_solicitacoes",
        ["chamado_id"],
    )
    op.create_index(
        "uq_previsao_solicitacoes_pendente_por_chamado",
        "chamado_previsao_solicitacoes",
        ["chamado_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pendente'"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "uq_previsao_solicitacoes_pendente_por_chamado",
        table_name="chamado_previsao_solicitacoes",
    )
    op.drop_index(
        "idx_previsao_solicitacoes_chamado",
        table_name="chamado_previsao_solicitacoes",
    )
    op.drop_table("chamado_previsao_solicitacoes")
