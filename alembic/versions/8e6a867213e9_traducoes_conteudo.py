"""traducoes_conteudo

Cache de tradução automática de conteúdo dinâmico dos chamados (descrição,
histórico, conversa) via LibreTranslate self-hosted — ver
app/services/traducao_conteudo_service.py. Chave por hash do texto original +
idioma destino (não por chamado_id/historico_id): funciona igual pra
Histórico (imutável) e pra Chamado.descricao/motivo_* (mutáveis) — editar o
texto muda o hash e gera uma linha nova; a linha antiga vira órfã inofensiva
(tradução de um texto fixo nunca muda, sem TTL/limpeza nesta v1).

Revision ID: 8e6a867213e9
Revises: 13a7d68a7017
Create Date: 2026-08-20 14:05:42.863895

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8e6a867213e9"
down_revision: str | Sequence[str] | None = "13a7d68a7017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "traducoes_conteudo",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("texto_original_hash", sa.Text(), nullable=False),
        sa.Column("idioma_destino", sa.Text(), nullable=False),
        sa.Column("idioma_origem_detectado", sa.Text(), nullable=True),
        sa.Column("texto_traduzido", sa.Text(), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "texto_original_hash", "idioma_destino", name="uq_traducao_hash_idioma"
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("traducoes_conteudo")
