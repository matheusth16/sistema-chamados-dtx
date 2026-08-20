"""Tabela traducoes_conteudo — cache de tradução automática de conteúdo dinâmico
(descrição do chamado, histórico, conversa) via LibreTranslate self-hosted.

Chave por hash do texto original + idioma destino (não por chamado_id/historico_id):
funciona igual pra Histórico (imutável) e pra Chamado.descricao/motivo_* (mutáveis)
— editar o texto muda o hash e gera uma linha nova; a linha antiga vira órfã
inofensiva (tradução de um texto fixo nunca muda, sem necessidade de TTL/limpeza).
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TraducaoConteudoRow(Base):
    __tablename__ = "traducoes_conteudo"
    __table_args__ = (
        UniqueConstraint("texto_original_hash", "idioma_destino", name="uq_traducao_hash_idioma"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    texto_original_hash: Mapped[str] = mapped_column(Text, nullable=False)
    idioma_destino: Mapped[str] = mapped_column(Text, nullable=False)
    idioma_origem_detectado: Mapped[str | None] = mapped_column(Text)
    texto_traduzido: Mapped[str] = mapped_column(Text, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
