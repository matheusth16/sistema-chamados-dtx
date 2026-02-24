"""
Serviço centralizado de atualização de status de chamados.

Consolida a lógica que estava repetida em 3 locais:
- admin.py (POST form)
- api.py atualizar_status_ajax()
- api.py api_editar_chamado()
"""

import logging
from firebase_admin import firestore
from app.database import db
from app.models_historico import Historico
from app.models_usuario import Usuario
from app.services.notifications import notificar_solicitante_status
from app.firebase_retry import execute_with_retry

logger = logging.getLogger(__name__)


def atualizar_status_chamado(
    chamado_id: str,
    novo_status: str,
    usuario_id: str,
    usuario_nome: str,
    data_chamado: dict = None,
) -> dict:
    """Atualiza o status de um chamado, registra histórico e envia notificação.
    
    Args:
        chamado_id: ID do chamado no Firestore
        novo_status: Novo status ('Aberto', 'Em Atendimento', 'Concluído')
        usuario_id: ID do usuário que está fazendo a alteração
        usuario_nome: Nome do usuário que está fazendo a alteração
        data_chamado: Dict do chamado (opcional, busca se não informado)
    
    Returns:
        dict com:
            'sucesso': bool
            'mensagem': str
            'erro': str (se falhar)
    """
    try:
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
        
        # Envia notificação ao solicitante
        if novo_status in ('Em Atendimento', 'Concluído'):
            _notificar_solicitante(chamado_id, data_chamado, novo_status)
        
        return {
            'sucesso': True,
            'mensagem': f'Status alterado para {novo_status}',
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
