"""apoio_push_historico_lgpd_contadores

Fase 2, Marco 5 — push_subscriptions, historico_usuarios, solicitacoes_lgpd,
contadores_uso (sem FK entre si).

Nota: removidos manualmente os "removed index" de lower(nome_pt) detectados
(falso positivo do autogenerate, mesmo caso do Marco 4) — continuam existindo.

Revision ID: 9ef3ef37804a
Revises: a3c148870905
Create Date: 2026-08-03 10:18:13.463781

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9ef3ef37804a"
down_revision: str | Sequence[str] | None = "a3c148870905"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "contadores_uso",
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("relatorio_geracoes", sa.Integer(), nullable=False),
        sa.Column("export_excel_geracoes", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "data"),
    )
    op.create_index("idx_contadores_uso_data", "contadores_uso", ["data"])

    op.create_table(
        "historico_usuarios",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("usuario_alvo_id", sa.Text(), nullable=False),
        sa.Column("usuario_alvo_nome", sa.Text(), nullable=True),
        sa.Column("admin_id", sa.Text(), nullable=True),
        sa.Column("admin_nome", sa.Text(), nullable=True),
        sa.Column("acao", sa.Text(), nullable=False),
        sa.Column("detalhe", sa.Text(), nullable=True),
        sa.Column(
            "data_acao",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_historico_usuarios_alvo_data", "historico_usuarios", ["usuario_alvo_id", "data_acao"]
    )

    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("usuario_id", sa.Text(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.Text(), nullable=True),
        sa.Column("auth", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("usuario_id", "endpoint", name="uq_push_usuario_endpoint"),
    )

    op.create_table(
        "solicitacoes_lgpd",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("usuario_id", sa.Text(), nullable=False),
        sa.Column("usuario_nome", sa.Text(), nullable=True),
        sa.Column("usuario_email", sa.Text(), nullable=True),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "data_solicitacao",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("data_resolucao", sa.DateTime(timezone=True), nullable=True),
        sa.Column("admin_id", sa.Text(), nullable=True),
        sa.Column("admin_nome", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_solicitacoes_lgpd_usuario", "solicitacoes_lgpd", ["usuario_id"])
    op.create_index("idx_solicitacoes_lgpd_status", "solicitacoes_lgpd", ["status"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("solicitacoes_lgpd")
    op.drop_table("push_subscriptions")
    op.drop_table("historico_usuarios")
    op.drop_table("contadores_uso")
