"""Confirmação de leitura do chamado: registra a primeira vez que o
responsável atual abre a tela de detalhe, pra o solicitante saber se o
chamado dele já foi visto ou não (ver `Chamado.visualizado_pelo_responsavel_em`).

Versão simples — só grava um timestamp único do responsável ATUAL. Se
reatribuído, o novo responsável precisa visualizar de novo (não herda a
marcação do responsável anterior). Uma versão com histórico completo de
todo mundo que visualizou (não só o responsável) fica planejada, não
implementada — ver memória de projeto se for retomar isso.
"""

import logging
from datetime import datetime

import pytz

logger = logging.getLogger(__name__)


def marcar_visualizado_pelo_responsavel(chamado, usuario_id: str | None) -> bool:
    """Grava visualizado_pelo_responsavel_em na primeira vez que o responsável
    atual do chamado abre a tela de detalhe. Idempotente — chamadas
    subsequentes (ou de qualquer outro usuário) não fazem nada.

    Retorna True só quando efetivamente gravou.
    """
    if chamado is None or not usuario_id:
        return False
    if chamado.visualizado_pelo_responsavel_em is not None:
        return False
    if not chamado.responsavel_id or chamado.responsavel_id != usuario_id:
        return False

    try:
        return chamado.atualizar_campos(visualizado_pelo_responsavel_em=datetime.now(pytz.utc))
    except Exception:
        logger.exception("Erro ao marcar chamado %s como visualizado pelo responsável", chamado.id)
        return False
