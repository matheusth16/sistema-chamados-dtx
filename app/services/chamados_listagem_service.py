"""
Serviço de listagem de chamados.

Centraliza a lógica de listagem para "Meus chamados" (solicitante) com
paginação por cursor, contagens por status e fallback quando o índice Firestore não existe.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List

from firebase_admin import firestore

from app.database import db
from app.models import Chamado
from app.services.pagination import obter_total_por_contagem

logger = logging.getLogger(__name__)


def _eh_erro_indice_firestore(exc: Exception) -> bool:
    """Verifica se a exceção é de índice do Firestore (FAILED_PRECONDITION / index)."""
    msg = (getattr(exc, 'message', '') or str(exc) or '').lower()
    return 'failed_precondition' in msg or 'index' in msg or 'requires an index' in msg


def listar_meus_chamados_fallback(
    user_id: str,
    status_filtro: str,
    itens_por_pagina: int,
    pagina_atual: int,
    rl_codigo: str = "",
) -> Dict[str, Any]:
    """
    Fallback quando a query com order_by falha por falta de índice:
    busca só por solicitante_id (não exige índice composto), ordena em memória e pagina.
    """
    q = db.collection('chamados').where('solicitante_id', '==', user_id).limit(500)
    docs = list(q.stream())
    if status_filtro:
        docs = [d for d in docs if (d.to_dict() or {}).get('status') == status_filtro]
    rl_codigo = (rl_codigo or '').strip()
    if rl_codigo:
        docs = [d for d in docs if (d.to_dict() or {}).get('rl_codigo') == rl_codigo]

    def _data_key(d):
        data = (d.to_dict() or {}).get('data_abertura')
        if data is None or data == firestore.SERVER_TIMESTAMP:
            return None
        if hasattr(data, 'to_pydatetime'):
            return data.to_pydatetime()
        return data

    # Ordena por prioridade (0=Projetos primeiro) e depois por data
    def _sort_key(d):
        data_dict = d.to_dict() or {}
        prioridade = data_dict.get('prioridade', 1)
        data = _data_key(d)
        return (prioridade, data is None, -(data.timestamp() if data else 0))
    
    docs.sort(key=_sort_key)
    status_counts = {'Aberto': 0, 'Em Atendimento': 0, 'Concluído': 0, 'Cancelado': 0}
    for d in docs:
        st = (d.to_dict() or {}).get('status', 'Aberto')
        if st in status_counts:
            status_counts[st] += 1
    total_chamados = len(docs)
    total_paginas = max(1, (total_chamados + itens_por_pagina - 1) // itens_por_pagina)
    pagina_atual = max(1, min(pagina_atual, total_paginas))
    inicio = (pagina_atual - 1) * itens_por_pagina
    fim = inicio + itens_por_pagina
    docs_pagina = docs[inicio:fim]
    chamados: List[Chamado] = []
    for doc in docs_pagina:
        try:
            data = doc.to_dict()
            if not data:
                continue
            chamados.append(Chamado.from_dict(data, doc.id))
        except Exception as doc_err:
            logger.warning("Chamado %s ignorado (dados inválidos): %s", doc.id, doc_err)
    cursor_next = (
        docs_pagina[-1].id
        if len(docs_pagina) == itens_por_pagina and fim < total_chamados
        else None
    )
    cursor_prev = docs_pagina[0].id if inicio > 0 else None

    # Calcula grupo_key para ordenar grupos Projetos antes dos demais no Jinja groupby
    from collections import defaultdict
    _grupo_prio: dict = defaultdict(lambda: 1)
    for c in chamados:
        rl = c.rl_codigo or ''
        if getattr(c, 'prioridade', 1) == 0:
            _grupo_prio[rl] = 0
    for c in chamados:
        rl = c.rl_codigo or ''
        c.grupo_key = f"{_grupo_prio[rl]}|{rl}"

    return {
        'chamados': chamados,
        'pagina_atual': pagina_atual,
        'total_paginas': total_paginas,
        'total_chamados': total_chamados,
        'status_counts': status_counts,
        'cursor_next': cursor_next,
        'cursor_prev': cursor_prev,
    }


def listar_meus_chamados(
    user_id: str,
    status_filtro: str = "",
    rl_codigo: str = "",
    cursor: str = "",
    cursor_prev: str = "",
    pagina_atual: int = 1,
    itens_por_pagina: int = 10,
) -> Dict[str, Any]:
    """
    Lista chamados do solicitante com paginação por cursor.

    Returns:
        Dict com: chamados, pagina_atual, total_paginas, total_chamados,
        status_counts, cursor_next, cursor_prev.
    """
    rl_codigo = (rl_codigo or '').strip()
    q = db.collection('chamados').where('solicitante_id', '==', user_id)
    if status_filtro:
        q = q.where('status', '==', status_filtro)
    if rl_codigo:
        q = q.where('rl_codigo', '==', rl_codigo)
    # Ordena por prioridade (Projetos=0 primeiro) e depois por data_abertura
    q = q.order_by('prioridade').order_by('data_abertura', direction=firestore.Query.DESCENDING)

    total_chamados = obter_total_por_contagem(q) or 0
    status_counts = {'Aberto': 0, 'Em Atendimento': 0, 'Concluído': 0, 'Cancelado': 0}
    try:
        base_ref = db.collection('chamados').where('solicitante_id', '==', user_id)
        if rl_codigo:
            base_ref = base_ref.where('rl_codigo', '==', rl_codigo)
        for st in ('Aberto', 'Em Atendimento', 'Concluído', 'Cancelado'):
            c = obter_total_por_contagem(base_ref.where('status', '==', st))
            status_counts[st] = c if c is not None else 0
    except Exception as e:
        logger.debug("Contagem por status em meus_chamados: %s", e)

    total_paginas = max(1, (total_chamados + itens_por_pagina - 1) // itens_por_pagina)
    pagina_atual = max(1, min(pagina_atual, total_paginas))

    if cursor:
        try:
            cursor_doc = db.collection('chamados').document(cursor).get()
            if cursor_doc.exists:
                q_page = q.start_after(cursor_doc).limit(itens_por_pagina + 1)
            else:
                q_page = q.limit(itens_por_pagina + 1)
        except Exception as e:
            logger.debug("Cursor inválido em meus_chamados: %s", e)
            q_page = q.limit(itens_por_pagina + 1)
    else:
        q_page = q.limit(itens_por_pagina + 1)

    docs = list(q_page.stream())
    tem_proxima = len(docs) > itens_por_pagina
    if tem_proxima:
        docs = docs[:itens_por_pagina]
    cursor_next = docs[-1].id if docs and tem_proxima else None

    chamados = []
    for doc in docs:
        try:
            data = doc.to_dict()
            if not data:
                continue
            chamados.append(Chamado.from_dict(data, doc.id))
        except Exception as doc_err:
            logger.warning("Chamado %s ignorado (dados inválidos): %s", doc.id, doc_err)

    # Calcula grupo_key para ordenar grupos Projetos antes dos demais no Jinja groupby
    from collections import defaultdict
    _grupo_prio: dict = defaultdict(lambda: 1)
    for c in chamados:
        rl = c.rl_codigo or ''
        if getattr(c, 'prioridade', 1) == 0:
            _grupo_prio[rl] = 0
    for c in chamados:
        rl = c.rl_codigo or ''
        c.grupo_key = f"{_grupo_prio[rl]}|{rl}"

    return {
        'chamados': chamados,
        'pagina_atual': pagina_atual,
        'total_paginas': total_paginas,
        'total_chamados': total_chamados,
        'status_counts': status_counts,
        'cursor_next': cursor_next,
        'cursor_prev': cursor_prev,
    }
