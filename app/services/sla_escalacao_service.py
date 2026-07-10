"""Serviço de Escalada Gerencial — Escada A (Fase 6).

A Escada A notifica gestores quando chamados Abertos excedem thresholds cumulativos
de minutos úteis sem entrar em atendimento. O job APScheduler chama
processar_escada_a() a cada 10 minutos.

Decisão de design (sem e-mail configurado):
  Se a chave do nível não estiver em GESTOR_EMAILS, o nível é incrementado mesmo
  assim, sem envio de e-mail. Isso evita que chamados fiquem presos tentando
  re-notificar um destinatário não configurado a cada execução do job. O
  comportamento é registrado em log warning para diagnóstico operacional.

Índice Firestore necessário (composite):
  Collection: chamados
  Fields: status ASC, escalacao_resposta_nivel ASC
  Ver: docs/INDICES_FIRESTORE.md
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.cloud.firestore_v1.base_query import FieldFilter

from app.database import db
from app.services.business_time import (
    adicionar_dias_uteis,
    minutos_corridos_entre,
    minutos_uteis_entre,
    percentual_prazo_resolucao,
    pode_enviar_notificacao_agora,
)
from app.services.notifications import (
    notificar_aviso_resolucao_supervisor,
    notificar_escalada_resolucao_gerencial,
    notificar_escalada_resposta_gerencial,
)
from config import Config

logger = logging.getLogger(__name__)

NIVEL_PARA_CHAVE_GESTOR: dict[int, str] = {
    1: "gestor_setor",
    2: "gerente_producao",
    3: "assistente_gm",
    4: "gm",
}


def _construir_mapa_gestor_setor() -> dict[str, str]:
    """Monta {nome_setor: email} uma vez por execução do job (evita N leituras).

    O gestor de cada setor é sempre um usuário real do sistema: marcado com
    nivel_gestao == 'gestor_setor' e com as áreas que gerencia em .areas
    (mesmos campos já usados pelo cadastro de usuário / Gestor Dashboard).
    Usuários inativos ou sem nivel_gestao='gestor_setor' são ignorados. Se
    duas pessoas cobrirem a mesma área (config inconsistente), mantém a
    primeira encontrada e loga warning — não é motivo para travar o job.
    Setores sem gestor mapeado caem no fallback flat em
    _processar_chamado_escada_a/_b.
    """
    from app.models_usuario import Usuario

    try:
        mapa: dict[str, str] = {}
        for usuario in Usuario.get_all():
            if getattr(usuario, "nivel_gestao", None) != "gestor_setor":
                continue
            if not getattr(usuario, "ativo", True) or not getattr(usuario, "email", None):
                continue
            for area in usuario.areas or []:
                if area in mapa:
                    logger.warning(
                        "Escada: mais de um gestor_setor para a área '%s' — mantendo %s, "
                        "ignorando %s.",
                        area,
                        mapa[area],
                        usuario.email,
                    )
                    continue
                mapa[area] = usuario.email
        return mapa
    except Exception as exc:
        logger.warning("Falha ao montar mapa gestor_setor: %s. Usando fallback flat.", exc)
        return {}


# Thresholds em minutos úteis derivados de SLA_ESCALADA_A_HORAS_UTEIS = [1, 2, 3, 4]
_MINUTOS_THRESHOLDS: list[int] = [h * 60 for h in Config.SLA_ESCALADA_A_HORAS_UTEIS]

# Thresholds Escada B: [0, 240, 480, 720] minutos úteis APÓS o deadline de resolução
_MINUTOS_THRESHOLDS_B: list[int] = [h * 60 for h in Config.SLA_ESCALADA_B_HORAS_UTEIS]


def calcular_nivel_esperado_escada_a(minutos_uteis: int) -> int:
    """Retorna 0–4 conforme thresholds cumulativos de minutos úteis.

    Exemplo: 59 min → 0, 60 → 1, 120 → 2, 180 → 3, 240 → 4.
    """
    nivel = 0
    for threshold in _MINUTOS_THRESHOLDS:
        if minutos_uteis >= threshold:
            nivel += 1
        else:
            break
    return nivel


def processar_escada_a(agora: datetime | None = None) -> dict:
    """Processa todos os chamados elegíveis para Escada A.

    Consulta chamados com status == 'Aberto' e escalacao_resposta_nivel < 4.
    Para cada chamado elegível, calcula minutos úteis desde a abertura e
    incrementa um nível por vez, enviando e-mail ao gestor correspondente.

    O incremento só ocorre dentro da janela de expediente DTX (seg–sex,
    07:00–11:30, 13:00–16:30). Fora da janela, o chamado é contado em
    pulados_fora_janela e processado no próximo job dentro do horário.

    Args:
        agora: Instante de referência (naive → tratado como BRT). None = now().

    Returns:
        dict com contadores: processados, escalados, emails, erros, pulados_fora_janela
    """
    if agora is None:
        agora = datetime.now(ZoneInfo(Config.SLA_TIMEZONE))

    stats: dict = {
        "processados": 0,
        "escalados": 0,
        "emails": 0,
        "erros": 0,
        "pulados_fora_janela": 0,
    }

    mapa_gestor_setor = _construir_mapa_gestor_setor()

    try:
        docs = (
            db.collection("chamados")
            .where(filter=FieldFilter("status", "==", "Aberto"))
            .where(filter=FieldFilter("escalacao_resposta_nivel", "<", 4))
            .limit(500)
            .stream()
        )
    except Exception as exc:
        logger.exception("Escada A: erro ao consultar Firestore: %s", exc)
        stats["erros"] += 1
        return stats

    for doc in docs:
        stats["processados"] += 1
        try:
            _processar_chamado_escada_a(doc, agora, stats, mapa_gestor_setor)
        except Exception as exc:
            logger.exception("Escada A: erro ao processar chamado %s: %s", doc.id, exc)
            stats["erros"] += 1

    return stats


def _processar_chamado_escada_a(
    doc, agora: datetime, stats: dict, mapa_gestor_setor: dict[str, str]
) -> None:
    """Avalia e (se aplicável) escala um único chamado na Escada A."""
    data = doc.to_dict()

    # Guard: só processa Abertos (a query filtra, mas defensivo contra dados inconsistentes)
    if data.get("status") != "Aberto":
        return

    nivel_atual = int(data.get("escalacao_resposta_nivel") or 0)

    data_abertura = data.get("data_abertura")
    if data_abertura is None:
        logger.warning("Escada A: chamado %s sem data_abertura; ignorado.", doc.id)
        return

    minutos = minutos_uteis_entre(data_abertura, agora)
    nivel_esperado = calcular_nivel_esperado_escada_a(minutos)

    if nivel_esperado <= nivel_atual:
        return  # threshold não atingido ou chamado já no nível correto

    # Threshold atingido: verificar janela de notificação
    if not pode_enviar_notificacao_agora(agora):
        # Não incrementar — aguardar próximo job dentro da janela (e-mail adiado, não perdido)
        stats["pulados_fora_janela"] += 1
        return

    novo_nivel = nivel_atual + 1
    chave_gestor = NIVEL_PARA_CHAVE_GESTOR.get(novo_nivel)
    if chave_gestor == "gestor_setor":
        categoria = data.get("categoria") or ""
        email_dest = mapa_gestor_setor.get(categoria) or Config.get_gestor_email("gestor_setor")
    elif chave_gestor:
        email_dest = Config.get_gestor_email(chave_gestor)
    else:
        email_dest = None

    if email_dest:
        try:
            notificar_escalada_resposta_gerencial(
                chamado_data=data,
                chamado_id=doc.id,
                nivel=novo_nivel,
                email_dest=email_dest,
            )
            stats["emails"] += 1
        except Exception as exc:
            logger.warning(
                "Escada A: falha ao enviar e-mail nível %d para %s (chamado %s): %s",
                novo_nivel,
                email_dest,
                doc.id,
                exc,
            )
    else:
        # E-mail não configurado: incrementa nível mesmo assim para evitar loop
        logger.warning(
            "Escada A: chamado %s → nível %d: chave '%s' não configurada em GESTOR_EMAILS. "
            "Incrementando nível sem e-mail.",
            doc.id,
            novo_nivel,
            chave_gestor,
        )

    db.collection("chamados").document(doc.id).update({"escalacao_resposta_nivel": novo_nivel})
    stats["escalados"] += 1

    logger.info(
        "Escada A: chamado %s escalado %d→%d (min_uteis=%d, chave=%s, email_ok=%s)",
        doc.id,
        nivel_atual,
        novo_nivel,
        minutos,
        chave_gestor,
        bool(email_dest),
    )


# ---------------------------------------------------------------------------
# Fase 7 — Escada B (resolução) + Avisos 50%/80%
# ---------------------------------------------------------------------------


def calcular_deadline_resolucao(data_em_atendimento: datetime, categoria: str) -> datetime:
    """Calcula o deadline de resolução.

    AOG      → SLA_AOG_MINUTOS_RESOLUCAO_DEADLINE minutos corridos (calendário, 24/7).
    Projetos → SLA_DIAS_RESOLUCAO_PROJETOS dias úteis.
    Demais   → SLA_DIAS_RESOLUCAO_PADRAO dias úteis.
    """
    if categoria == "AOG":
        return data_em_atendimento + timedelta(minutes=Config.SLA_AOG_MINUTOS_RESOLUCAO_DEADLINE)
    dias = (
        Config.SLA_DIAS_RESOLUCAO_PROJETOS
        if categoria == "Projetos"
        else Config.SLA_DIAS_RESOLUCAO_PADRAO
    )
    return adicionar_dias_uteis(data_em_atendimento, dias)


def calcular_nivel_esperado_escada_b(
    minutos_apos_deadline: int, thresholds: list[int] | None = None
) -> int:
    """Retorna 1–4 conforme minutos decorridos APÓS o deadline de resolução.

    Thresholds padrão (SLA_ESCALADA_B_HORAS_UTEIS = [0, 4, 8, 12], minutos úteis):
      0 min  → nível 1 (deadline ultrapassado)
      240 min → nível 2 (4h úteis após deadline)
      480 min → nível 3 (8h úteis após deadline)
      720 min → nível 4 (12h úteis após deadline)

    `thresholds` customizado (ex: Config.SLA_AOG_MINUTOS_RESOLUCAO_ESCALADA) permite
    reusar a mesma função para a escada AOG, em minutos corridos.
    """
    limites = thresholds if thresholds is not None else _MINUTOS_THRESHOLDS_B
    nivel = 0
    for threshold in limites:
        if minutos_apos_deadline >= threshold:
            nivel += 1
        else:
            break
    return nivel


def processar_avisos_resolucao(agora: datetime | None = None) -> dict:
    """Envia avisos de 50% e 80% do prazo de resolução para chamados Em Atendimento.

    Consulta chamados com status == 'Em Atendimento' e verifica o percentual do SLA
    de resolução consumido. Se atingiu 50% e ainda não foi notificado, envia aviso.
    Idem para 80%. Cada aviso é enviado no máximo uma vez por chamado.

    O envio só ocorre dentro da janela de expediente DTX (seg–sex, 07:00–11:30,
    13:00–16:30). Fora da janela, o chamado é contado em pulados_fora_janela e
    reprocessado na próxima execução dentro do horário.

    Canais: in-app + e-mail + Web Push. E-mail omitido se responsável sem email.

    Args:
        agora: Instante de referência (naive → BRT). None = now().

    Returns:
        dict com contadores: processados, notificados_50, notificados_80, erros,
        pulados_fora_janela
    """
    if agora is None:
        agora = datetime.now(ZoneInfo(Config.SLA_TIMEZONE))

    stats: dict = {
        "processados": 0,
        "notificados_50": 0,
        "notificados_80": 0,
        "erros": 0,
        "pulados_fora_janela": 0,
    }

    try:
        docs = (
            db.collection("chamados")
            .where(filter=FieldFilter("status", "==", "Em Atendimento"))
            .limit(500)
            .stream()
        )
    except Exception as exc:
        logger.exception("Avisos resolução: erro ao consultar Firestore: %s", exc)
        stats["erros"] += 1
        return stats

    for doc in docs:
        stats["processados"] += 1
        try:
            _processar_aviso_resolucao(doc, agora, stats)
        except Exception as exc:
            logger.exception("Avisos resolução: erro ao processar chamado %s: %s", doc.id, exc)
            stats["erros"] += 1

    return stats


def _processar_aviso_resolucao(doc, agora: datetime, stats: dict) -> None:
    """Avalia e (se aplicável) envia aviso de SLA de resolução para um único chamado."""
    data = doc.to_dict()

    responsavel_id = data.get("responsavel_id")
    if not responsavel_id:
        return

    data_em_atendimento = data.get("data_em_atendimento")
    if data_em_atendimento is None:
        logger.warning("Avisos resolução: chamado %s sem data_em_atendimento; ignorado.", doc.id)
        return

    alerta_50 = bool(data.get("alerta_supervisor_50_enviado"))
    alerta_80 = bool(data.get("alerta_supervisor_80_enviado"))

    precisa_50 = not alerta_50
    precisa_80 = not alerta_80

    if not (precisa_50 or precisa_80):
        return  # Ambos os alertas já foram enviados

    categoria = data.get("categoria") or ""
    pct = percentual_prazo_resolucao(data_em_atendimento, categoria, agora)

    # Verifica se algum threshold foi atingido
    threshold_50 = precisa_50 and pct >= 0.5
    threshold_80 = precisa_80 and pct >= 0.8
    if not (threshold_50 or threshold_80):
        return

    # Threshold atingido: verificar janela de notificação (mesmo padrão Escada A/B)
    if not pode_enviar_notificacao_agora(agora):
        stats["pulados_fora_janela"] += 1
        return

    email_resp: str | None = _obter_email_responsavel(responsavel_id)
    updates: dict = {}

    # Aviso 50%
    if threshold_50:
        notificar_aviso_resolucao_supervisor(
            chamado_data=data,
            chamado_id=doc.id,
            marco=50,
            responsavel_id=responsavel_id,
            email_dest=email_resp,
        )
        stats["notificados_50"] += 1
        updates["alerta_supervisor_50_enviado"] = True

    # Aviso 80%
    if threshold_80:
        notificar_aviso_resolucao_supervisor(
            chamado_data=data,
            chamado_id=doc.id,
            marco=80,
            responsavel_id=responsavel_id,
            email_dest=email_resp,
        )
        stats["notificados_80"] += 1
        updates["alerta_supervisor_80_enviado"] = True

    if updates:
        db.collection("chamados").document(doc.id).update(updates)
        logger.info(
            "Avisos resolução: chamado %s atualizado (pct=%.0f%%), flags=%s",
            doc.id,
            pct * 100,
            list(updates.keys()),
        )


def _obter_email_responsavel(responsavel_id: str) -> str | None:
    """Busca e-mail do responsável pelo ID (inline import para evitar circular import)."""
    try:
        from app.models_usuario import Usuario

        u = Usuario.get_by_id(responsavel_id)
        if u and getattr(u, "email", None):
            return u.email.strip() or None
    except Exception as exc:
        logger.warning(
            "Avisos resolução: falha ao buscar e-mail do responsável %s: %s", responsavel_id, exc
        )
    return None


def processar_escada_b(agora: datetime | None = None) -> dict:
    """Processa chamados Em Atendimento que excederam o prazo de resolução (Escada B).

    Consulta chamados com status == 'Em Atendimento' e escalacao_resolucao_nivel < 4.
    Para cada chamado elegível, calcula minutos úteis após o deadline e incrementa
    um nível por vez, notificando o gestor correspondente.

    O incremento só ocorre dentro da janela de expediente DTX.

    Args:
        agora: Instante de referência (naive → BRT). None = now().

    Returns:
        dict com contadores: processados, escalados, emails, erros, pulados_fora_janela
    """
    if agora is None:
        agora = datetime.now(ZoneInfo(Config.SLA_TIMEZONE))

    stats: dict = {
        "processados": 0,
        "escalados": 0,
        "emails": 0,
        "erros": 0,
        "pulados_fora_janela": 0,
    }

    mapa_gestor_setor = _construir_mapa_gestor_setor()

    try:
        docs = (
            db.collection("chamados")
            .where(filter=FieldFilter("status", "==", "Em Atendimento"))
            .where(filter=FieldFilter("escalacao_resolucao_nivel", "<", 4))
            .limit(500)
            .stream()
        )
    except Exception as exc:
        logger.exception("Escada B: erro ao consultar Firestore: %s", exc)
        stats["erros"] += 1
        return stats

    for doc in docs:
        stats["processados"] += 1
        try:
            _processar_chamado_escada_b(doc, agora, stats, mapa_gestor_setor)
        except Exception as exc:
            logger.exception("Escada B: erro ao processar chamado %s: %s", doc.id, exc)
            stats["erros"] += 1

    return stats


def _processar_chamado_escada_b(
    doc, agora: datetime, stats: dict, mapa_gestor_setor: dict[str, str]
) -> None:
    """Avalia e (se aplicável) escala um único chamado na Escada B."""
    data = doc.to_dict()

    nivel_atual = int(data.get("escalacao_resolucao_nivel") or 0)

    data_em_atendimento = data.get("data_em_atendimento")
    if data_em_atendimento is None:
        logger.warning("Escada B: chamado %s sem data_em_atendimento; ignorado.", doc.id)
        return

    categoria = data.get("categoria") or ""
    is_aog = categoria == "AOG"
    deadline = calcular_deadline_resolucao(data_em_atendimento, categoria)

    # Normaliza para naive a fim de comparar de forma segura (datetimes BRT naive em testes)
    agora_naive = agora.replace(tzinfo=None)
    deadline_naive = deadline.replace(tzinfo=None)

    if agora_naive <= deadline_naive:
        return  # Prazo ainda não vencido

    if is_aog:
        minutos_apos = minutos_corridos_entre(deadline, agora)
        nivel_esperado = calcular_nivel_esperado_escada_b(
            minutos_apos, thresholds=Config.SLA_AOG_MINUTOS_RESOLUCAO_ESCALADA
        )
    else:
        minutos_apos = minutos_uteis_entre(deadline, agora)
        nivel_esperado = calcular_nivel_esperado_escada_b(minutos_apos)

    if nivel_esperado <= nivel_atual:
        return  # Já no nível correto

    # Threshold atingido: verificar janela de notificação (AOG é 24/7, não espera expediente)
    if not is_aog and not pode_enviar_notificacao_agora(agora):
        stats["pulados_fora_janela"] += 1
        return

    novo_nivel = nivel_atual + 1
    chave_gestor = NIVEL_PARA_CHAVE_GESTOR.get(novo_nivel)
    if chave_gestor == "gestor_setor":
        categoria = data.get("categoria") or ""
        email_dest = mapa_gestor_setor.get(categoria) or Config.get_gestor_email("gestor_setor")
    elif chave_gestor:
        email_dest = Config.get_gestor_email(chave_gestor)
    else:
        email_dest = None

    if email_dest:
        try:
            notificar_escalada_resolucao_gerencial(
                chamado_data=data,
                chamado_id=doc.id,
                nivel=novo_nivel,
                email_dest=email_dest,
            )
            stats["emails"] += 1
        except Exception as exc:
            logger.warning(
                "Escada B: falha ao enviar e-mail nível %d para %s (chamado %s): %s",
                novo_nivel,
                email_dest,
                doc.id,
                exc,
            )
    else:
        logger.warning(
            "Escada B: chamado %s → nível %d: chave '%s' não configurada em GESTOR_EMAILS. "
            "Incrementando nível sem e-mail.",
            doc.id,
            novo_nivel,
            chave_gestor,
        )

    db.collection("chamados").document(doc.id).update({"escalacao_resolucao_nivel": novo_nivel})
    stats["escalados"] += 1

    logger.info(
        "Escada B: chamado %s escalado %d→%d (min_apos_deadline=%d, chave=%s, email_ok=%s)",
        doc.id,
        nivel_atual,
        novo_nivel,
        minutos_apos,
        chave_gestor,
        bool(email_dest),
    )
