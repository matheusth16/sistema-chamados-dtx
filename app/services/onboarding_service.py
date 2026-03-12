"""Serviço de onboarding: persiste progresso e conclusão do tour guiado."""
import logging
from app.database import db

logger = logging.getLogger(__name__)


def avancar_passo(user_id: str, passo: int) -> bool:
    """Salva o passo atual do onboarding no Firestore."""
    try:
        db.collection('usuarios').document(user_id).update({'onboarding_passo': passo})
        return True
    except Exception as e:
        logger.exception("Erro ao avançar passo de onboarding para usuário %s: %s", user_id, e)
        return False


def concluir_onboarding(user_id: str) -> bool:
    """Marca o onboarding como concluído para o usuário."""
    try:
        db.collection('usuarios').document(user_id).update({
            'onboarding_completo': True,
            'onboarding_passo': 0,
        })
        return True
    except Exception as e:
        logger.exception("Erro ao concluir onboarding para usuário %s: %s", user_id, e)
        return False
