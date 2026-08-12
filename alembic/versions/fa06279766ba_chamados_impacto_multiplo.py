"""chamados_impacto_multiplo

O campo "Impacto Principal" na abertura de chamado passa de seleção única
(radio) pra múltipla (checkbox) — coluna impacto sai de Text pra
ARRAY(Text), mesmo padrão já usado em anexos/setores_adicionais.

Backfill: valor de texto existente vira array de um elemento; NULL/vazio
vira array vazio.

Revision ID: fa06279766ba
Revises: 671588c434ba
Create Date: 2026-08-12 09:11:28.903447

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fa06279766ba"
down_revision: str | Sequence[str] | None = "671588c434ba"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "chamados",
        "impacto",
        type_=postgresql.ARRAY(sa.Text()),
        nullable=False,
        server_default="{}",
        postgresql_using=(
            "CASE WHEN impacto IS NULL OR impacto = '' THEN ARRAY[]::text[] ELSE ARRAY[impacto] END"
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "chamados",
        "impacto",
        type_=sa.Text(),
        nullable=True,
        server_default=None,
        postgresql_using="array_to_string(impacto, ', ')",
    )
