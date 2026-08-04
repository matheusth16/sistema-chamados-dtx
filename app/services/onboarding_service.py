"""Serviço de onboarding: persiste progresso e conclusão do tour guiado."""

import logging

from app import db as db_module
from app.db.models.usuario import UsuarioRow

logger = logging.getLogger(__name__)


def avancar_passo(user_id: str, passo: int) -> bool:
    """Salva o passo atual do onboarding no Postgres."""
    try:
        with db_module.SessionLocal() as session, session.begin():
            row = session.get(UsuarioRow, user_id)
            if row is None:
                return False
            row.onboarding_passo = passo
        return True
    except Exception as e:
        logger.exception("Erro ao avançar passo de onboarding para usuário %s: %s", user_id, e)
        return False


def concluir_onboarding(user_id: str, perfil: str) -> bool:
    """Marca o tour do perfil atual como visto (concluído ou pulado) para o usuário.

    Adiciona `perfil` a onboarding_perfis_vistos de forma idempotente — não
    duplica se o usuário já tinha visto esse perfil antes (equivalente ao
    antigo ArrayUnion do Firestore).
    """
    try:
        with db_module.SessionLocal() as session, session.begin():
            row = session.get(UsuarioRow, user_id)
            if row is None:
                return False
            vistos = list(row.onboarding_perfis_vistos or [])
            if perfil not in vistos:
                vistos.append(perfil)
            row.onboarding_perfis_vistos = vistos
            row.onboarding_passo = 0
        return True
    except Exception as e:
        logger.exception("Erro ao concluir onboarding para usuário %s: %s", user_id, e)
        return False
