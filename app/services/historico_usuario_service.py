"""Histórico persistente de ações administrativas sobre contas de usuário
(criação, edição, desativação, ativação, exclusão) — auditoria LGPD/CWI.

Fase 2: armazenamento migrado de Firestore para PostgreSQL.
"""

import logging

from sqlalchemy import select

from app import db as db_module
from app.db.models.apoio import HistoricoUsuarioRow

logger = logging.getLogger(__name__)


def registrar_historico_usuario(
    usuario_alvo_id: str,
    usuario_alvo_nome: str,
    admin_id: str,
    admin_nome: str,
    acao: str,
    detalhe: str | None = None,
) -> bool:
    """Grava um registro de auditoria para ação administrativa sobre um usuário.

    acao: 'criacao', 'edicao', 'desativacao', 'ativacao', 'exclusao', 'anonimizacao'
    """
    try:
        with db_module.SessionLocal() as session, session.begin():
            row = HistoricoUsuarioRow(
                usuario_alvo_id=usuario_alvo_id,
                usuario_alvo_nome=usuario_alvo_nome,
                admin_id=admin_id,
                admin_nome=admin_nome,
                acao=acao,
                detalhe=detalhe,
            )
            session.add(row)
        return True
    except Exception:
        logger.exception(
            "Erro ao registrar histórico de usuário: usuario_alvo_id=%s acao=%s",
            usuario_alvo_id,
            acao,
        )
        return False


def obter_historico_usuario(usuario_alvo_id: str) -> list[dict]:
    """Retorna o histórico administrativo de um usuário, mais recente primeiro."""
    try:
        with db_module.SessionLocal() as session:
            rows = (
                session.execute(
                    select(HistoricoUsuarioRow)
                    .where(HistoricoUsuarioRow.usuario_alvo_id == usuario_alvo_id)
                    .order_by(HistoricoUsuarioRow.data_acao.desc(), HistoricoUsuarioRow.id.desc())
                )
                .scalars()
                .all()
            )
            return [
                {
                    "usuario_alvo_id": row.usuario_alvo_id,
                    "usuario_alvo_nome": row.usuario_alvo_nome,
                    "admin_id": row.admin_id,
                    "admin_nome": row.admin_nome,
                    "acao": row.acao,
                    "detalhe": row.detalhe,
                    "data_acao": row.data_acao,
                }
                for row in rows
            ]
    except Exception:
        logger.exception("Erro ao buscar histórico do usuário: usuario_alvo_id=%s", usuario_alvo_id)
        return []
