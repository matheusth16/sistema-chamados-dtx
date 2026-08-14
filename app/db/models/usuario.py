"""Tabela usuarios — Fase 2, Marco 6.

id fica TEXT (não BIGSERIAL): mantém compatibilidade com os IDs de string já
referenciados por coleções ainda não migradas (chamados.solicitante_id,
historico_usuarios.admin_id, contadores_uso.user_id, etc.) — evita ter que
tocar todas elas antes da hora. PII (email/nome/mfa_secret) continua
guardada como ciphertext Fernet, exatamente como no Firestore — a troca de
banco não toca pii_encryption.py.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UsuarioRow(Base):
    __tablename__ = "usuarios"
    __table_args__ = (
        # Único apenas quando preenchido (encryption ligada) — mesma semântica
        # do índice condicional que o Firestore não tinha, mas o app já exigia
        # via checagem em email_existe()/get_by_email().
        Index(
            "idx_usuarios_email_lookup_hash",
            "email_lookup_hash",
            unique=True,
            postgresql_where=text("email_lookup_hash IS NOT NULL"),
        ),
        Index("idx_usuarios_areas", "areas", postgresql_using="gin"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    email_lookup_hash: Mapped[str | None] = mapped_column(Text)
    nome: Mapped[str] = mapped_column(Text, nullable=False)
    perfil: Mapped[str] = mapped_column(Text, nullable=False, default="solicitante")
    areas: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    senha_hash: Mapped[str | None] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exp_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    exp_semanal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    conquistas: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    onboarding_perfis_vistos: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list
    )
    onboarding_passo: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    nivel_gestao: Mapped[str | None] = mapped_column(Text)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mfa_secret: Mapped[str | None] = mapped_column(Text)
    mfa_backup_codes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    auth_provider: Mapped[str] = mapped_column(Text, nullable=False, default="local")
    criado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mfa_lembrete_enviado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
