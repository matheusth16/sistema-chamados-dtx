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
    filtro: str | None = None, agora: datetime | None = None
) -> dict:
    """Constrói o contexto para o template gestor_dashboard.html.

    Args:
        filtro: "atrasados" | "aberto_sem_resposta" | "multi_setor" | "todos" | None
        agora: Instante de referência para cálculo de minutos úteis. None = now().

    Returns:
        dict com contadores e lista paginada de chamados.
    """
    _agora = agora or datetime.now(ZoneInfo(Config.SLA_TIMEZONE))
    todos = _carregar_todos_chamados()

    atrasados = [c for c in todos if _is_atrasado(c)]
    abertos_sem_resp = [c for c in todos if _is_aberto_sem_resposta(c, _agora)]
    multi_travados = [c for c in todos if _is_multi_setor_travado(c)]

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

    return {
        "contadores": contadores,
        "chamados": lista,
        "filtro_ativo": filtro_norm or "todos",
    }
