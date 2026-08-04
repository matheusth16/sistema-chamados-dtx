"""historico_notificacoes

Fase 2, Marco 8 — historico e notificacoes (in-app), ambas com FK real em
chamado_id (CASCADE): nenhuma das duas faz sentido órfã de um chamado.
valor_anterior/valor_novo de historico viram JSONB (tipo dinâmico no
Firestore, mesmo sempre string na prática atual — preserva dado legado real
na migração de produção, Marco 11).

Revision ID: fd6113edb603
Revises: 542481d03082
Create Date: 2026-08-04 08:18:22.670106

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fd6113edb603"
down_revision: str | Sequence[str] | None = "542481d03082"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "historico",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chamado_id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Text(), nullable=False),
        sa.Column("usuario_nome", sa.Text(), nullable=True),
        sa.Column("acao", sa.Text(), nullable=False),
        sa.Column("campo_alterado", sa.Text(), nullable=True),
        sa.Column("valor_anterior", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("valor_novo", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("detalhe", sa.Text(), nullable=True),
        sa.Column(
            "data_acao",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["chamado_id"], ["chamados.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_historico_chamado_data", "historico", ["chamado_id", "data_acao"])

    op.create_table(
        "notificacoes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("usuario_id", sa.Text(), nullable=False),
        sa.Column("chamado_id", sa.Integer(), nullable=False),
        sa.Column("numero_chamado", sa.Text(), nullable=True),
        sa.Column("titulo", sa.Text(), nullable=False),
        sa.Column("mensagem", sa.Text(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("categoria", sa.Text(), nullable=True),
        sa.Column("solicitante_nome", sa.Text(), nullable=True),
        sa.Column("lida", sa.Boolean(), nullable=False),
        sa.Column(
            "data_criacao",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["chamado_id"], ["chamados.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_notificacoes_usuario_data", "notificacoes", ["usuario_id", "data_criacao"])
    op.create_index("idx_notificacoes_usuario_lida", "notificacoes", ["usuario_id", "lida"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_notificacoes_usuario_lida", table_name="notificacoes")
    op.drop_index("idx_notificacoes_usuario_data", table_name="notificacoes")
    op.drop_table("notificacoes")
    op.drop_index("idx_historico_chamado_data", table_name="historico")
    op.drop_table("historico")
