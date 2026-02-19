"""
Notificações in-app (sino): criar, listar e marcar como lida.
Armazenamento no Firestore, collection 'notificacoes'.
"""

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from firebase_admin import firestore
from app.database import db

logger = logging.getLogger(__name__)


def criar_notificacao(usuario_id: str, chamado_id: str, numero_chamado: str,
                      titulo: str, mensagem: str, tipo: str = 'novo_chamado') -> Optional[str]:
    """
    Cria uma notificação in-app para o usuário (ex.: aprovador quando recebe novo chamado).
    Retorna o id do documento criado ou None em caso de erro.
    """
    if not usuario_id or not chamado_id:
        return None
    try:
        ref = db.collection('notificacoes').add({
            'usuario_id': usuario_id,
            'chamado_id': chamado_id,
            'numero_chamado': numero_chamado,
            'titulo': titulo,
            'mensagem': mensagem,
            'tipo': tipo,
            'lida': False,
            'data_criacao': firestore.SERVER_TIMESTAMP,
        })
        logger.debug(f"Notificação in-app criada: usuario={usuario_id}, chamado={numero_chamado}")
        return ref[1].id
    except Exception as e:
        logger.exception(f"Erro ao criar notificação in-app: {e}")
        return None


def listar_para_usuario(usuario_id: str, limite: int = 30, apenas_nao_lidas: bool = False) -> List[Dict[str, Any]]:
    """
    Lista notificações do usuário, mais recentes primeiro.
    Retorna lista de dicts com id, chamado_id, numero_chamado, titulo, mensagem, lida, data_criacao.
    """
    if not usuario_id:
        return []
    try:
        q = db.collection('notificacoes').where('usuario_id', '==', usuario_id)
        if apenas_nao_lidas:
            q = q.where('lida', '==', False)
        docs = q.limit(limite * 2).stream()  # busca extra para ordenar em memória (evita índice composto)
        out = []
        for doc in docs:
            d = doc.to_dict()
            d['id'] = doc.id
            # Serializar data para JSON
            ts = d.get('data_criacao')
            if hasattr(ts, 'to_pydatetime'):
                d['data_criacao'] = ts.to_pydatetime().isoformat()
            elif isinstance(ts, datetime):
                d['data_criacao'] = ts.isoformat()
            else:
                d['data_criacao'] = str(ts) if ts else None
            out.append(d)
        out.sort(key=lambda x: (x.get('data_criacao') or ''), reverse=True)
        return out[:limite]
    except Exception as e:
        logger.exception(f"Erro ao listar notificações: {e}")
        return []


def contar_nao_lidas(usuario_id: str) -> int:
    """Retorna a quantidade de notificações não lidas do usuário."""
    if not usuario_id:
        return 0
    try:
        docs = db.collection('notificacoes')\
            .where('usuario_id', '==', usuario_id)\
            .where('lida', '==', False)\
            .stream()
        return sum(1 for _ in docs)
    except Exception as e:
        logger.exception(f"Erro ao contar notificações: {e}")
        return 0


def marcar_como_lida(notificacao_id: str, usuario_id: str) -> bool:
    """Marca a notificação como lida. Retorna True se encontrou e pertence ao usuário."""
    if not notificacao_id or not usuario_id:
        return False
    try:
        ref = db.collection('notificacoes').document(notificacao_id)
        doc = ref.get()
        if not doc.exists or doc.to_dict().get('usuario_id') != usuario_id:
            return False
        ref.update({'lida': True})
        return True
    except Exception as e:
        logger.exception(f"Erro ao marcar notificação como lida: {e}")
        return False
