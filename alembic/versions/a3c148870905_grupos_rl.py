"""grupos_rl

Fase 2, Marco 4 — grupos_rl. rl_codigo é UNIQUE: corrige a race condition do
antigo GrupoRL.get_or_create() do Firestore (check-then-act não atômico).

Nota: o autogenerate detectou (falso positivo) os índices funcionais
lower(nome_pt) do Marco 3 como "removidos" — SQLAlchemy não reflete
expression indexes definidos só via op.create_index nas migrations, sem
Index() correspondente nos models Python. Removidos manualmente desta
migration; eles continuam existindo, criados pela migration anterior.

Revision ID: a3c148870905
Revises: 80d73e83fb89
Create Date: 2026-08-03 10:10:54.390893

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3c148870905"
down_revision: str | Sequence[str] | None = "80d73e83fb89"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "grupos_rl",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("rl_codigo", sa.Text(), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("criado_por_id", sa.Text(), nullable=True),
        sa.Column("area", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rl_codigo"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("grupos_rl")
