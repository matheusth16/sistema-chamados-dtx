"""chamados_previsao_extensao_automatica

Duas colunas novas em chamados pro self-service de extensão automática de
previsão de atendimento (ver app/services/previsao_atendimento_service.py):
previsao_extensoes_automaticas_usadas conta quantas das 3 extensões grátis
por chamado já foram usadas; previsao_extensao_travada é o ratchet de mão
única — vira True assim que o gestor decide (aprova ou rejeita) qualquer
pedido manual desse chamado, e nunca volta a False.

chamados tem dados reais em produção (Marco 11) — usa server_default no
add_column (evita falha de NOT NULL em tabela populada) e remove depois,
pra bater exatamente com o modelo ORM (só default Python-side).

Revision ID: 23a2c20d92b5
Revises: 36c2debc2c3a
Create Date: 2026-08-17 14:54:20.750207

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "23a2c20d92b5"
down_revision: str | Sequence[str] | None = "36c2debc2c3a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "chamados",
        sa.Column(
            "previsao_extensoes_automaticas_usadas",
            sa.SmallInteger(),
            nullable=False,
            server_default="0",
        ),
    )
    op.alter_column("chamados", "previsao_extensoes_automaticas_usadas", server_default=None)
    op.add_column(
        "chamados",
        sa.Column(
            "previsao_extensao_travada",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("chamados", "previsao_extensao_travada", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("chamados", "previsao_extensao_travada")
    op.drop_column("chamados", "previsao_extensoes_automaticas_usadas")
