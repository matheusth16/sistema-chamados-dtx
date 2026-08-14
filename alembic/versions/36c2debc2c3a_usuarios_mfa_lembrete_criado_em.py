"""usuarios_mfa_lembrete_criado_em

Adiciona duas colunas em usuarios pro lembrete de MFA pendente:
criado_em (a tabela não tinha data de criação — precisa pra grace period
de 24h antes do primeiro lembrete) e mfa_lembrete_enviado_em (timestamp
do último lembrete enviado — elegibilidade de reenvio + claim atômico).

Revision ID: 36c2debc2c3a
Revises: b3e7a9c2d114
Create Date: 2026-08-14 11:49:19.198035

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "36c2debc2c3a"
down_revision: str | Sequence[str] | None = "b3e7a9c2d114"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    criado_em: usuarios não tinha data de criação (ao contrário de chamados).
    server_default=now() só na migração — contas idle existentes recebem a
    data do deploy (evita disparar lembrete de MFA pra todo mundo no
    instante em que isso for ligado); dali pra frente quem popula é
    Usuario.save() (só na criação, nunca sobrescreve em update).

    mfa_lembrete_enviado_em: timestamp do último lembrete de MFA pendente
    enviado — usado tanto pra elegibilidade (intervalo de reenvio) quanto
    como claim atômico contra envio duplicado.
    """
    op.add_column(
        "usuarios",
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
    )
    op.alter_column("usuarios", "criado_em", server_default=None)
    op.add_column(
        "usuarios",
        sa.Column("mfa_lembrete_enviado_em", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("usuarios", "mfa_lembrete_enviado_em")
    op.drop_column("usuarios", "criado_em")
