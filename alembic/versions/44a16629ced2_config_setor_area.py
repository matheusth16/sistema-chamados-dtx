"""config_setor_area

Fase 2, Marco 9 — último singleton Firestore (config/setor_para_area) vira
tabela config_setor_area (linha única, mapa JSONB). Aproveita a migration
pra também criar chamados_numero_seq, substituindo a transação Firestore
em _sistema/contador_chamados (app/utils.py::gerar_numero_chamado) por uma
sequência nativa — atômica por construção, sem transação explícita.

Revision ID: 44a16629ced2
Revises: fd6113edb603
Create Date: 2026-08-04 08:52:20.409018

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "44a16629ced2"
down_revision: str | Sequence[str] | None = "fd6113edb603"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "config_setor_area",
        sa.Column("id", sa.Boolean(), nullable=False),
        sa.Column("mapa", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint("id", name="ck_config_setor_area_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("CREATE SEQUENCE chamados_numero_seq START WITH 1 INCREMENT BY 1")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP SEQUENCE chamados_numero_seq")
    op.drop_table("config_setor_area")
