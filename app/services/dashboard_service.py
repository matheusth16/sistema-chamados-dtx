"""
Serviço de carregamento do dashboard (admin).

Centraliza a construção do contexto da página admin: chamados com filtros,
paginação por cursor, listas de responsáveis e gates.
"""

import logging
from typing import Any

from app.cache import get_static_cached
from app.database import db
from app.models import Chamado
from app.models_categorias import CategoriaGate
from app.models_usuario import Usuario
from app.services.analytics import obter_sla_para_exibicao
from app.services.filters import aplicar_filtros_dashboard_com_paginacao
from app.services.permission_validation import filtrar_supervisores_por_area
from app.services.permissions import usuario_pode_ver_chamado_otimizado
from app.utils import extrair_numero_chamado

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers de relatórios: ordenação e paginação de métricas
# ---------------------------------------------------------------------------

_CAMPOS_SUP = {
    "total": lambda x: x.get("total_chamados", 0),
    "carga": lambda x: x.get("carga_atual", 0),
    "taxa": lambda x: x.get("taxa_resolucao_percentual", 0),
    "tempo": lambda x: x.get("tempo_medio_resolucao_horas", 0),
    "nome": lambda x: (x.get("supervisor_nome") or "").lower(),
    "area": lambda x: (x.get("area") or "").lower(),
}

_CAMPOS_AREA = {
    "total": lambda x: x.get("total_chamados", 0),
    "abertos": lambda x: x.get("abertos", 0),
    "taxa": lambda x: x.get("taxa_resolucao_percentual", 0),
    "tempo": lambda x: x.get("tempo_medio_resolucao_horas", 0),
    "area": lambda x: (x.get("area") or "").lower(),
}


def ordenar_metricas_supervisores(lista: list[dict], campo: str, asc: bool) -> list[dict]:
    """Ordena métricas de supervisores por campo.

    Campos aceitos: total, carga, taxa, tempo, nome, area, sla.
    """
    reverse = not asc
    if campo == "sla":

        def _sla_key(x):
            v = x.get("percentual_dentro_sla")
            return (v is None, -(v or 0))

        return sorted(lista, key=_sla_key, reverse=reverse)
    key_fn = _CAMPOS_SUP.get(campo)
    if key_fn:
        return sorted(lista, key=key_fn, reverse=reverse)
    return lista


def ordenar_metricas_areas(lista: list[dict], campo: str, asc: bool) -> list[dict]:
    """Ordena métricas de áreas por campo.

    Campos aceitos: total, abertos, taxa, tempo, area.
    """
    key_fn = _CAMPOS_AREA.get(campo)
    if key_fn:
        return sorted(lista, key=key_fn, reverse=not asc)
    return lista


def preparar_metricas_paginadas(
    items_full: list[dict],
    campo_ordenacao: str,
    ordem_asc: bool,
    pagina: int,
    itens_por_pagina: int,
    ordenar_fn,
) -> dict:
    """Aplica ordenação e paginação a uma lista de métricas.

    Returns:
        dict com items, items_full (ordenado, para gráficos), total,
        total_paginas e pagina (clampeada).
    """
    ordered = ordenar_fn(items_full, campo_ordenacao, ordem_asc)
    total = len(ordered)
    total_paginas = max(1, (total + itens_por_pagina - 1) // itens_por_pagina)
    pagina = max(1, min(pagina, total_paginas))
    inicio = (pagina - 1) * itens_por_pagina
    return {
        "items": ordered[inicio : inicio + itens_por_pagina],
        "items_full": ordered,
        "total": total,
        "total_paginas": total_paginas,
        "pagina": pagina,
    }


def _filtrar_chamados_por_permissao(docs: list[Any], user: Any) -> list[Chamado]:
    """Filtra chamados que o usuário pode ver, com cache para evitar N+1 queries."""
    chamados = []
    if user.perfil == "admin":
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
    cache_usuarios = Usuario.get_by_ids(list(responsavel_ids))
    for c in chamados_raw:
        if usuario_pode_ver_chamado_otimizado(user, c, cache_usuarios):
            chamados.append(c)
    return chamados


def obter_contexto_admin(
    user: Any, args: dict[str, Any], itens_por_pagina: int = 25
) -> dict[str, Any]:
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
    supervisores = [u for u in usuarios_gestao if u.perfil == "supervisor" and u.nome]
    # Supervisor vê apenas responsáveis do(s) mesmo(s) setor(es); admin vê todos
    supervisores = filtrar_supervisores_por_area(user, supervisores)
    lista_responsaveis = sorted([u.nome for u in supervisores], key=lambda x: x.upper())
    supervisores_detalhados = sorted(
        [{"id": u.id, "nome": u.nome, "area": u.area} for u in supervisores],
        key=lambda x: x["nome"].upper(),
    )
    chamados_ref = db.collection("chamados")
    if user.perfil == "supervisor" and getattr(user, "areas", None):
        areas = user.areas[:10]
        if areas:
            chamados_ref = chamados_ref.where("area", "in", areas)
    cursor = (args.get("cursor") or "").strip() or None
    cursor_prev = (args.get("cursor_prev") or "").strip() or None
    pagina_atual = int(args.get("pagina") or 1)
    if pagina_atual < 1:
        pagina_atual = 1
    resultado = aplicar_filtros_dashboard_com_paginacao(
        chamados_ref, args, limite=itens_por_pagina, cursor=cursor, cursor_anterior=cursor_prev
    )
    docs = resultado["docs"]
    chamados = _filtrar_chamados_por_permissao(docs, user)

    def _chave(c):
        concluido = c.status in ("Concluído", "Cancelado")
        num_id = extrair_numero_chamado(c.numero_chamado)
        if concluido:
            return (True, 0, num_id)
        # Projetos Aberto/Em Atendimento sempre no topo
        # Verifica categoria diretamente (não depende do campo prioridade, que pode não existir em chamados antigos)
        eh_projetos = c.categoria == "Projetos" or getattr(c, "prioridade", 1) == 0
        prioridade_cat = 0 if eh_projetos else 1
        return (False, prioridade_cat, num_id)

    chamados_ordenados = sorted(chamados, key=_chave)

    # Calcula grupo_key para ordenar grupos Projetos antes dos demais no Jinja groupby
    from collections import defaultdict

    _grupo_prio: dict = defaultdict(lambda: 1)
    for c in chamados_ordenados:
        rl = c.rl_codigo or ""
        if c.categoria == "Projetos" or getattr(c, "prioridade", 1) == 0:
            _grupo_prio[rl] = 0
    for c in chamados_ordenados:
        rl = c.rl_codigo or ""
        c.grupo_key = f"{_grupo_prio[rl]}|{rl}"

    for c in chamados_ordenados:
        c.sla_info = obter_sla_para_exibicao(c)
    gates = get_static_cached("categorias_gate", CategoriaGate.get_all, ttl_seconds=300)
    lista_gates = sorted([g.nome_pt for g in gates])
    total_chamados = len(chamados_ordenados)
    total_paginas = (
        1 if not resultado.get("tem_proxima") and not resultado.get("tem_anterior") else None
    )
    return {
        "chamados": chamados_ordenados,
        "pagina_atual": pagina_atual,
        "total_paginas": total_paginas,
        "total_chamados": total_chamados,
        "itens_por_pagina": itens_por_pagina,
        "lista_responsaveis": lista_responsaveis,
        "supervisores_detalhados": supervisores_detalhados,
        "lista_gates": lista_gates,
        "max": max,
        "min": min,
        "proximo_cursor": resultado.get("proximo_cursor"),
        "tem_proxima": resultado.get("tem_proxima", False),
        "cursor_anterior": resultado.get("cursor_anterior"),
        "tem_anterior": resultado.get("tem_anterior", False),
    }
