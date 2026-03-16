"""
Serviço centralizado de atualização de status de chamados.

Consolida a lógica que estava repetida em 3 locais:
- admin.py (POST form)
- api.py atualizar_status_ajax()
- api.py api_editar_chamado()
"""

import logging
import threading

from firebase_admin import firestore
from flask import current_app, session

from app.database import db
from app.firebase_retry import execute_with_retry
from app.i18n import get_translated_status, get_translation
from app.models_historico import Historico
from app.models_usuario import Usuario
from app.services.gamification_service import GamificationService
from app.services.notifications import notificar_solicitante_status

logger = logging.getLogger(__name__)


STATUS_VALIDOS = ('Aberto', 'Em Atendimento', 'Concluído', 'Cancelado')


def atualizar_status_chamado(
    chamado_id: str,
    novo_status: str,
    usuario_id: str,
    usuario_nome: str,
    data_chamado: dict = None,
    motivo_cancelamento: str = None,
) -> dict:
    """Atualiza o status de um chamado, registra histórico e envia notificação.

    Para status 'Cancelado', motivo_cancelamento é obrigatório.

    Args:
        chamado_id: ID do chamado no Firestore
        novo_status: Novo status ('Aberto', 'Em Atendimento', 'Concluído', 'Cancelado')
        usuario_id: ID do usuário que está fazendo a alteração
        usuario_nome: Nome do usuário que está fazendo a alteração
        data_chamado: Dict do chamado (opcional, busca se não informado)
        motivo_cancelamento: Obrigatório quando novo_status == 'Cancelado'

    Returns:
        dict com:
            'sucesso': bool
            'mensagem': str
            'erro': str (se falhar)
    """
    try:
        if novo_status not in STATUS_VALIDOS:
            return {'sucesso': False, 'erro': f'Status inválido: {novo_status}'}

        if novo_status == 'Cancelado':
            motivo = (motivo_cancelamento or '').strip()
            if not motivo:
                return {'sucesso': False, 'erro': 'Motivo do cancelamento é obrigatório'}

        # Busca dados do chamado se não fornecidos
        if data_chamado is None:
            doc = db.collection('chamados').document(chamado_id).get()
            if not doc.exists:
                return {'sucesso': False, 'erro': 'Chamado não encontrado'}
            data_chamado = doc.to_dict()

        status_anterior = data_chamado.get('status')

        # Monta dados de atualização
        update_data = {'status': novo_status}
        if novo_status == 'Concluído':
            update_data['data_conclusao'] = firestore.SERVER_TIMESTAMP
        elif novo_status == 'Cancelado':
            update_data['motivo_cancelamento'] = (motivo_cancelamento or '').strip()
            update_data['data_cancelamento'] = firestore.SERVER_TIMESTAMP

        # Atualiza no Firestore com retry
        execute_with_retry(
            db.collection('chamados').document(chamado_id).update,
            update_data,
            max_retries=3
        )

        # Registra histórico se houve mudança
        if status_anterior != novo_status:
            Historico(
                chamado_id=chamado_id,
                usuario_id=usuario_id,
                usuario_nome=usuario_nome,
                acao='alteracao_status',
                campo_alterado='status',
                valor_anterior=status_anterior,
                valor_novo=novo_status
            ).save()
            if novo_status == 'Cancelado' and (motivo_cancelamento or '').strip():
                Historico(
                    chamado_id=chamado_id,
                    usuario_id=usuario_id,
                    usuario_nome=usuario_nome,
                    acao='alteracao_dados',
                    campo_alterado='motivo_cancelamento',
                    valor_anterior='-',
                    valor_novo=(motivo_cancelamento or '').strip()[:500]
                ).save()

        # Envia notificação ao solicitante em background (não para Cancelado)
        if novo_status in ('Em Atendimento', 'Concluído'):
            try:
                _app = current_app._get_current_object()
                _cid = chamado_id
                _data = data_chamado
                _status = novo_status

                def _notif():
                    with _app.app_context():
                        _notificar_solicitante(_cid, _data, _status)

                threading.Thread(target=_notif, daemon=True).start()
            except RuntimeError:
                # Fora de contexto Flask (testes) — notifica de forma síncrona
                _notificar_solicitante(chamado_id, data_chamado, novo_status)

        # Gamificação: apenas para Em Atendimento / Concluído (não para Cancelado)
        if status_anterior != novo_status:
            if novo_status == 'Concluído':
                GamificationService.avaliar_resolucao_chamado(usuario_id, data_chamado)
            elif novo_status == 'Em Atendimento':
                GamificationService.avaliar_atendimento_inicial(usuario_id)

        try:
            lang = session.get('language', 'en')
        except RuntimeError:
            lang = 'en'
        status_traduzido = get_translated_status(novo_status, lang)
        mensagem = get_translation('status_changed_to', lang, status=status_traduzido)
        return {
            'sucesso': True,
            'mensagem': mensagem,
            'novo_status': novo_status
        }

    except Exception as e:
        logger.exception("Erro ao atualizar status do chamado %s: %s", chamado_id, e)
        return {'sucesso': False, 'erro': str(e)}


def _notificar_solicitante(chamado_id: str, data_chamado: dict, novo_status: str):
    """Notifica o solicitante sobre a mudança de status."""
    try:
        sid = data_chamado.get('solicitante_id')
        solicitante = Usuario.get_by_id(sid) if sid else None
        notificar_solicitante_status(
            chamado_id=chamado_id,
            numero_chamado=data_chamado.get('numero_chamado') or 'N/A',
            novo_status=novo_status,
            categoria=data_chamado.get('categoria') or 'Chamado',
            solicitante_usuario=solicitante,
        )
    except Exception as e:
        logger.warning("Notificação ao solicitante não enviada: %s", e)
