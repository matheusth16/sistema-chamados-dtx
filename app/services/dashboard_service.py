"""
Serviço de carregamento do dashboard (admin).

Centraliza a construção do contexto da página admin: chamados com filtros,
paginação por cursor, listas de responsáveis e gates.
"""
from typing import Any, Dict, List

from app.database import db
from app.models import Chamado
from app.models_usuario import Usuario
from app.models_categorias import CategoriaGate
from app.services.filters import aplicar_filtros_dashboard_com_paginacao
from app.cache import get_static_cached
from app.services.permissions import usuario_pode_ver_chamado_otimizado
from app.services.analytics import obter_sla_para_exibicao
from app.utils import extrair_numero_chamado


def _filtrar_chamados_por_permissao(docs: List[Any], user: Any) -> List[Chamado]:
    """Filtra chamados que o usuário pode ver, com cache para evitar N+1 queries."""
    chamados = []
    if user.perfil == 'admin':
        for doc in docs:
            chamados.append(Chamado.from_dict(doc.to_dict(), doc.id))
        return chamados
    chamados_raw = []
    responsavel_ids = set()
    for doc in docs:
        c = Chamado.from_dict(doc.to_dict(), doc.id)
        chamados_raw.append(c)
        if c.responsavel_id:
            responsavel_ids.add(c.responsavel_id)
    cache_usuarios = {}
    for uid in responsavel_ids:
        u = Usuario.get_by_id(uid)
        if u:
            cache_usuarios[uid] = u
    for c in chamados_raw:
        if usuario_pode_ver_chamado_otimizado(user, c, cache_usuarios):
            chamados.append(c)
    return chamados


def obter_contexto_admin(user: Any, args: Dict[str, Any], itens_por_pagina: int = 25) -> Dict[str, Any]:
    """
    Monta o contexto para renderizar a página do dashboard (admin).

    Args:
        user: usuário logado (current_user)
        args: request.args (filtros, cursor, cursor_prev)
        itens_por_pagina: tamanho da página (padrão 25)

    Returns:
        Dict com chamados, lista_responsaveis, supervisores_detalhados, lista_gates,
        paginação (proximo_cursor, tem_proxima, cursor_anterior, tem_anterior), etc.
    """
    usuarios_gestao = get_static_cached("usuarios_all", Usuario.get_all, ttl_seconds=300)
    supervisores = [u for u in usuarios_gestao if u.perfil == 'supervisor' and u.nome]
    # Supervisor vê apenas responsáveis do(s) mesmo(s) setor(es); admin vê todos
    if user.perfil == 'supervisor' and getattr(user, 'areas', None):
        user_areas_set = set(user.areas)
        supervisores = [u for u in supervisores if user_areas_set & set(getattr(u, 'areas', []))]
    lista_responsaveis = sorted([u.nome for u in supervisores], key=lambda x: x.upper())
    supervisores_detalhados = sorted(
        [{'id': u.id, 'nome': u.nome, 'area': u.area} for u in supervisores],
        key=lambda x: x['nome'].upper(),
    )
    chamados_ref = db.collection('chamados')
    if user.perfil == 'supervisor' and getattr(user, 'areas', None):
        areas = user.areas[:10]
        if areas:
            chamados_ref = chamados_ref.where('area', 'in', areas)
    cursor = (args.get('cursor') or '').strip() or None
    cursor_prev = (args.get('cursor_prev') or '').strip() or None
    resultado = aplicar_filtros_dashboard_com_paginacao(
        chamados_ref, args, limite=itens_por_pagina, cursor=cursor, cursor_anterior=cursor_prev
    )
    docs = resultado['docs']
    chamados = _filtrar_chamados_por_permissao(docs, user)

    def _chave(c):
        concluido = c.status == 'Concluído'
        num_id = extrair_numero_chamado(c.numero_chamado)
        if concluido:
            return (True, 0, num_id)
        prioridade_cat = 0 if c.categoria == 'Projetos' else 1
        return (False, prioridade_cat, num_id)

    chamados_ordenados = sorted(chamados, key=_chave)
    for c in chamados_ordenados:
        c.sla_info = obter_sla_para_exibicao(c)
    gates = get_static_cached("categorias_gate", CategoriaGate.get_all, ttl_seconds=300)
    lista_gates = sorted([g.nome_pt for g in gates])
    total_chamados = len(chamados_ordenados)
    total_paginas = (
        1
        if not resultado.get('tem_proxima') and not resultado.get('tem_anterior')
        else None
    )
    return {
        'chamados': chamados_ordenados,
        'pagina_atual': 1,
        'total_paginas': total_paginas,
        'total_chamados': total_chamados,
        'itens_por_pagina': itens_por_pagina,
        'lista_responsaveis': lista_responsaveis,
        'supervisores_detalhados': supervisores_detalhados,
        'lista_gates': lista_gates,
        'max': max,
        'min': min,
        'proximo_cursor': resultado.get('proximo_cursor'),
        'tem_proxima': resultado.get('tem_proxima', False),
        'cursor_anterior': resultado.get('cursor_anterior'),
        'tem_anterior': resultado.get('tem_anterior', False),
    }
