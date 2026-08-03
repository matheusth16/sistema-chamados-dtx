"""categorias

Fase 2, Marco 3 — categorias_setores/gates/impactos. Índices funcionais em
lower(nome_pt) aceleram CategoriaX.nome_existe() (busca case-insensitive);
não são UNIQUE — a checagem de duplicidade continua sendo responsabilidade
da aplicação (nome_existe), preservando o comportamento atual do Firestore
(sem constraint de unicidade no banco).

Revision ID: 80d73e83fb89
Revises:
Create Date: 2026-08-03 09:35:35.526481

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "80d73e83fb89"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "categorias_gates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("nome_pt", sa.Text(), nullable=False),
        sa.Column("nome_en", sa.Text(), nullable=True),
        sa.Column("nome_es", sa.Text(), nullable=True),
        sa.Column("descricao_pt", sa.Text(), nullable=True),
        sa.Column("descricao_en", sa.Text(), nullable=True),
        sa.Column("descricao_es", sa.Text(), nullable=True),
        sa.Column("gate_pai", sa.Text(), nullable=True),
        sa.Column("etapa", sa.Text(), nullable=True),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False),
        sa.Column(
            "data_criacao",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_gates_nome_pt_lower", "categorias_gates", [sa.text("lower(nome_pt)")])

    op.create_table(
        "categorias_impactos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("nome_pt", sa.Text(), nullable=False),
        sa.Column("nome_en", sa.Text(), nullable=True),
        sa.Column("nome_es", sa.Text(), nullable=True),
        sa.Column("descricao_pt", sa.Text(), nullable=True),
        sa.Column("descricao_en", sa.Text(), nullable=True),
        sa.Column("descricao_es", sa.Text(), nullable=True),
        sa.Column("nivel", sa.Integer(), nullable=False),
        sa.Column("cor", sa.String(length=32), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False),
        sa.Column(
            "data_criacao",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_impactos_nome_pt_lower", "categorias_impactos", [sa.text("lower(nome_pt)")]
    )

    op.create_table(
        "categorias_setores",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("nome_pt", sa.Text(), nullable=False),
        sa.Column("nome_en", sa.Text(), nullable=True),
        sa.Column("nome_es", sa.Text(), nullable=True),
        sa.Column("descricao_pt", sa.Text(), nullable=True),
        sa.Column("descricao_en", sa.Text(), nullable=True),
        sa.Column("descricao_es", sa.Text(), nullable=True),
        sa.Column("ativo", sa.Boolean(), nullable=False),
        sa.Column(
            "data_criacao",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_setores_nome_pt_lower", "categorias_setores", [sa.text("lower(nome_pt)")])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("categorias_setores")
    op.drop_table("categorias_impactos")
    op.drop_table("categorias_gates")
