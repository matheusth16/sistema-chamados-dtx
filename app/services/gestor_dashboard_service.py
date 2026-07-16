"""Serviço do Dashboard Gerencial (Fase 5).

Fornece contexto read-only para /gestor/dashboard: contadores e listas de
chamados classificados por filtro (atrasados, aberto_sem_resposta, multi_setor_travado).

Regras de classificação v1 (critérios mínimos):
- atrasados: campo `sla_dias` preenchido e minutos úteis desde abertura excedem o limite
             OU campo is_atrasado=True (se disponível no documento)
- aberto_sem_resposta: status == "Aberto" e chamado aberto há mais de 60 min úteis (1h Escada A)
- multi_setor_travado: len(participantes) > 0 E algum participante status != "concluido"
                       E chamado não está "Concluído"
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app.database import db
from app.models import Chamado
from app.services.business_time import minutos_uteis_entre
from config import Config

logger = logging.getLogger(__name__)

# Limiar Escada A: 60 minutos úteis sem atendimento
_LIMIAR_ABERTO_MINUTOS = 60

# Statuses que indicam chamado finalizado
_STATUS_FINALIZADOS = {"Concluído", "Cancelado"}

# Quantos chamados exibir por raia no modo visão geral (painel de triagem)
_LIMITE_POR_RAIA = 6


def _is_atrasado(chamado: Chamado) -> bool:
    """Classifica chamado como atrasado.

    Usa campo is_atrasado do documento se disponível; caso contrário,
    verifica sla_dias e tempo desde abertura como proxy.
    """
    if getattr(chamado, "is_atrasado", None) is True:
        return True
    status = getattr(chamado, "status", "")
    if status in _STATUS_FINALIZADOS:
        return False
    sla_dias = getattr(chamado, "sla_dias", None)
    if sla_dias is None:
        return False
    data_abertura = getattr(chamado, "data_abertura", None)
    if data_abertura is None:
        return False
    agora = datetime.now(ZoneInfo(Config.SLA_TIMEZONE))
    minutos = minutos_uteis_entre(data_abertura, agora)
    return minutos > sla_dias * 24 * 60


def _is_aberto_sem_resposta(chamado: Chamado, agora: datetime | None = None) -> bool:
    """Classifica chamado como Aberto sem resposta (≥ 60 minutos úteis sem atendimento)."""
    if getattr(chamado, "status", "") != "Aberto":
        return False
    data_abertura = getattr(chamado, "data_abertura", None)
    if data_abertura is None:
        return False
    _agora = agora or datetime.now(ZoneInfo(Config.SLA_TIMEZONE))
    return minutos_uteis_entre(data_abertura, _agora) >= _LIMIAR_ABERTO_MINUTOS


def _is_multi_setor_travado(chamado: Chamado) -> bool:
    """Classifica chamado como multi-setor travado."""
    if getattr(chamado, "status", "") in _STATUS_FINALIZADOS:
        return False
    participantes = getattr(chamado, "participantes", None) or []
    if not participantes:
        return False
    for p in participantes:
        status_p = p.get("status") if isinstance(p, dict) else getattr(p, "status", None)
        if status_p != "concluido":
            return True
    return False


def _marcar_riscos(chamado: Chamado, ids_atrasados: set, ids_sem_resp: set, ids_multi: set) -> None:
    """Anota chamado.riscos com as categorias de risco que ele atende (para exibição em card)."""
    riscos = []
    if id(chamado) in ids_atrasados:
        riscos.append("atrasado")
    if id(chamado) in ids_sem_resp:
        riscos.append("sem_resposta")
    if id(chamado) in ids_multi:
        riscos.append("multi_setor")
    chamado.riscos = riscos


def _calcular_insights(
    todos: list[Chamado],
    atrasados: list[Chamado],
    abertos_sem_resp: list[Chamado],
    multi_travados: list[Chamado],
    agora: datetime,
) -> dict:
    """Calcula indicadores de triagem a partir dos chamados já carregados (sem queries extras).

    Returns:
        dict com area_critica (área com mais atrasados), tempo_medio_sem_resposta_min
        (média de minutos úteis em aberto sem resposta) e saude_percentual (% do total
        fora de qualquer bucket de risco).
    """
    area_critica = None
    if atrasados:
        contagem_por_area: dict[str, int] = {}
        for c in atrasados:
            area = getattr(c, "area", None) or "Sem área"
            contagem_por_area[area] = contagem_por_area.get(area, 0) + 1
        nome_area = max(contagem_por_area, key=contagem_por_area.get)
        area_critica = {"nome": nome_area, "qtd": contagem_por_area[nome_area]}

    tempo_medio_sem_resposta_min = None
    if abertos_sem_resp:
        total_min = 0
        contados = 0
        for c in abertos_sem_resp:
            data_abertura = getattr(c, "data_abertura", None)
            if data_abertura is None:
                continue
            total_min += minutos_uteis_entre(data_abertura, agora)
            contados += 1
        if contados:
            tempo_medio_sem_resposta_min = round(total_min / contados)

    ids_em_risco = (
        {id(c) for c in atrasados}
        | {id(c) for c in abertos_sem_resp}
        | {id(c) for c in multi_travados}
    )
    saude_percentual = 100 if not todos else round(100 * (1 - len(ids_em_risco) / len(todos)))

    return {
        "area_critica": area_critica,
        "tempo_medio_sem_resposta_min": tempo_medio_sem_resposta_min,
        "saude_percentual": saude_percentual,
    }


def _carregar_todos_chamados() -> list[Chamado]:
    """Carrega chamados ativos do Firestore sem filtro de área."""
    try:
        docs = (
            db.collection("chamados")
            .order_by("data_abertura", direction="DESCENDING")
            .limit(500)
            .stream()
        )
        return [Chamado.from_dict(doc.to_dict(), doc.id) for doc in docs]
    except Exception:
        logger.exception("Erro ao carregar chamados para dashboard gestor")
        return []


def obter_contexto_gestor_dashboard(
    filtro: str | None = None, agora: datetime | None = None, usuario=None
) -> dict:
    """Constrói o contexto para o template gestor_dashboard.html.

    Args:
        filtro: "atrasados" | "aberto_sem_resposta" | "multi_setor" | "todos" | None
        agora: Instante de referência para cálculo de minutos úteis. None = now().
        usuario: current_user. Quando nivel_gestao == "gestor_setor", restringe os
            chamados à(s) área(s) do usuário (Nível 3). Outros níveis de gestão e
            usuario=None mantêm a visão ampliada (todas as áreas).

    Returns:
        dict com contadores, insights de triagem, lista de chamados (filtrada pelo
        filtro ativo) e grupos (raias por categoria de risco, usadas na visão geral).
    """
    _agora = agora or datetime.now(ZoneInfo(Config.SLA_TIMEZONE))
    todos = _carregar_todos_chamados()

    if usuario is not None and getattr(usuario, "nivel_gestao", None) == "gestor_setor":
        areas_gestor = set(getattr(usuario, "areas", None) or [])
        todos = [c for c in todos if getattr(c, "area", None) in areas_gestor]

    atrasados = [c for c in todos if _is_atrasado(c)]
    abertos_sem_resp = [c for c in todos if _is_aberto_sem_resposta(c, _agora)]
    multi_travados = [c for c in todos if _is_multi_setor_travado(c)]

    ids_atrasados = {id(c) for c in atrasados}
    ids_sem_resp = {id(c) for c in abertos_sem_resp}
    ids_multi = {id(c) for c in multi_travados}
    for c in todos:
        _marcar_riscos(c, ids_atrasados, ids_sem_resp, ids_multi)

    contadores = {
        "total": len(todos),
        "atrasados": len(atrasados),
        "aberto_sem_resposta": len(abertos_sem_resp),
        "multi_setor_travado": len(multi_travados),
    }

    filtro_norm = (filtro or "").strip().lower()
    if filtro_norm == "atrasados":
        lista = atrasados
    elif filtro_norm in ("aberto_sem_resposta", "aberto"):
        lista = abertos_sem_resp
    elif filtro_norm in ("multi_setor", "multi_setor_travado"):
        lista = multi_travados
    else:
        lista = todos

    insights = _calcular_insights(todos, atrasados, abertos_sem_resp, multi_travados, _agora)

    grupos = [
        {
            "chave": "atrasados",
            "titulo": "gestor_counter_atrasados",
            "cor": "danger",
            "total": len(atrasados),
            "chamados": atrasados[:_LIMITE_POR_RAIA],
        },
        {
            "chave": "aberto_sem_resposta",
            "titulo": "gestor_counter_sem_resposta",
            "cor": "warn",
            "total": len(abertos_sem_resp),
            "chamados": abertos_sem_resp[:_LIMITE_POR_RAIA],
        },
        {
            "chave": "multi_setor",
            "titulo": "gestor_lane_multi_setor_travado",
            "cor": "purple",
            "total": len(multi_travados),
            "chamados": multi_travados[:_LIMITE_POR_RAIA],
        },
    ]

    return {
        "contadores": contadores,
        "insights": insights,
        "chamados": lista,
        "grupos": grupos,
        "filtro_ativo": filtro_norm or "todos",
    }
