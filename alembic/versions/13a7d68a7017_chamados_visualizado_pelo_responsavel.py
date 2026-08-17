"""chamados_visualizado_pelo_responsavel

Confirmação de leitura do chamado (versão simples): coluna nullable que
grava só a primeira vez que o responsável ATUAL do chamado abre a tela de
detalhe — ver app/services/visualizacao_chamado_service.py. NULL = ainda
não visto; não precisa de server_default porque o default desejado (não
visualizado) já É o NULL do Postgres.

Revision ID: 13a7d68a7017
Revises: 23a2c20d92b5
Create Date: 2026-08-17 15:38:03.839641

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "13a7d68a7017"
down_revision: str | Sequence[str] | None = "23a2c20d92b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "chamados",
        sa.Column("visualizado_pelo_responsavel_em", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("chamados", "visualizado_pelo_responsavel_em")
