"""Serviço de Escalonamento Gerencial — motor unificado por TAT.

Cada chamado tem um único prazo (TAT) por categoria, contado sempre de
data_abertura (nunca de data_em_atendimento): 3 dias úteis (Não Aplicável),
2 dias úteis (Projetos), 24h corridas (AOG). AOG tem, além disso, um limiar
mais cedo e separado — 1h corrida — só pra "ainda não foi assumido", que
dispara escalonamento antes mesmo do TAT vencer.

Quando o prazo relevante vence, o sistema olha o status do chamado NAQUELE
MOMENTO: se ainda 'Aberto' (não assumido), escala a cada
SLA_CADENCIA_NAO_ASSUMIDO_MINUTOS (2h); se 'Em Atendimento' (assumido, não
resolvido), escala a cada SLA_CADENCIA_ASSUMIDO_MINUTOS (1h). AOG usa sempre
a cadência "assumido" nas duas fases. Se um chamado que está escalando na
cadência "não assumido" é assumido no meio do caminho, a cadência muda pra
"assumido" a partir dali, mas o nível não é resetado (continua de onde
estava) — ver status_service.py.

30 minutos antes de cada tick (incluindo o primeiro), o responsável recebe
um aviso prévio (ver notifications_escalonamento.notificar_pre_aviso_
escalonamento) — dedup por nível-alvo em escalacao_pre_aviso_nivel_enviado.

Decisão de design (sem gestor cadastrado):
  Se não houver usuário ativo com o nivel_gestao daquele nível (ver
  gestor_escalonamento_service), o nível é incrementado mesmo assim, sem envio
  de e-mail. Isso evita que chamados fiquem presos tentando re-notificar um
  destinatário inexistente a cada execução do job. O comportamento é
  registrado em log warning para diagnóstico operacional.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app import db as db_module
from app.db.models.chamado import ChamadoRow
from app.models import Chamado
from app.models_historico import Historico
from app.services.business_time import (
    adicionar_dias_uteis,
    adicionar_horas_corridas,
    percentual_prazo_resolucao,
    pode_enviar_notificacao_agora,
)
from app.services.gestor_escalonamento_service import (
    NIVEL_PARA_CHAVE_GESTOR,
)
from app.services.gestor_escalonamento_service import (
    construir_mapa_gestor_setor as _construir_mapa_gestor_setor,
)
from app.services.gestor_escalonamento_service import (
    construir_mapa_niveis_superiores as _construir_mapa_niveis_superiores,
)
from app.services.gestor_escalonamento_service import (
    resolver_email_gestor as _resolver_email_gestor,
)
from app.services.notifications import (
    notificar_aviso_resolucao_supervisor,
    notificar_escalada_gerencial,
    notificar_pre_aviso_escalonamento,
)
from config import Config

logger = logging.getLogger(__name__)

_NIVEL_MAXIMO = 4

# Ator de Histórico para ações disparadas pelo job de escalonamento (sem
# usuário humano envolvido) — ver app/models_historico.py (usuario_id sem
# FK, mesmo padrão de responsavel_id/solicitante_id em Chamado).
USUARIO_ID_SISTEMA = "sistema"
USUARIO_NOME_SISTEMA_SLA = "Sistema (Motor de Escalonamento SLA)"


def calcular_deadline_inicial(categoria: str, status: str, data_abertura: datetime) -> datetime:
    """Deadline do 1º tick (nivel 0 -> 1), sempre contado de data_abertura.

    Recalculada a cada passagem do job enquanto escalacao_nivel==0 (o alvo
    pode mudar pro AOG, cujo limiar depende do status atual: se já foi
    assumido antes do limiar de reivindicação, o alvo salta direto pro TAT).

    AOG    Aberto         -> data_abertura + SLA_AOG_CLAIM_HORAS (1h corrida)
    AOG    Em Atendimento -> data_abertura + SLA_AOG_TAT_HORAS (24h corridas)
    Demais (Não Aplicável/Projetos) -> data_abertura + TAT em dias úteis
    """
    if categoria == "AOG":
        if status == "Aberto":
            return adicionar_horas_corridas(data_abertura, Config.SLA_AOG_CLAIM_HORAS)
        return adicionar_horas_corridas(data_abertura, Config.SLA_AOG_TAT_HORAS)
    dias = (
        Config.SLA_DIAS_RESOLUCAO_PROJETOS
        if categoria == "Projetos"
        else Config.SLA_DIAS_RESOLUCAO_PADRAO
    )
    return adicionar_dias_uteis(data_abertura, dias)


def calcular_cadencia_minutos(categoria: str, status: str) -> int:
    """Cadência (minutos) do próximo tick, escolhida pelo status atual do
    chamado. AOG usa sempre a cadência "assumido" (mais agressiva) nas duas
    fases — não faz sentido escalar mais devagar só porque ainda não foi
    reivindicado quando a categoria já é prioridade máxima."""
    if categoria == "AOG":
        return Config.SLA_CADENCIA_ASSUMIDO_MINUTOS
    return (
        Config.SLA_CADENCIA_ASSUMIDO_MINUTOS
        if status == "Em Atendimento"
        else Config.SLA_CADENCIA_NAO_ASSUMIDO_MINUTOS
    )


def processar_escalonamento(agora: datetime | None = None) -> dict:
    """Processa todos os chamados elegíveis para o motor de escalonamento
    unificado (substitui as antigas Escada A + Escada B).

    Consulta chamados com status IN ('Aberto', 'Em Atendimento') e
    escalacao_nivel < 4. Para cada chamado elegível: dispara aviso prévio
    quando o próximo tick cai dentro da janela de SLA_PRE_AVISO_MINUTOS (uma
    vez por nível-alvo); dispara o tick de escalonamento em si quando o
    prazo vence, incrementando um nível por vez.

    O tick só ocorre dentro da janela de expediente DTX pra Não Aplicável/
    Projetos (adiado, não perdido, se fora da janela); AOG ignora a janela e
    dispara 24/7.

    Args:
        agora: Instante de referência (naive → tratado como BRT). None = now().

    Returns:
        dict com contadores: processados, escalados, emails, pre_avisos, erros,
        pulados_fora_janela, adiados
    """
    if agora is None:
        agora = datetime.now(ZoneInfo(Config.SLA_TIMEZONE))

    stats: dict = {
        "processados": 0,
        "escalados": 0,
        "emails": 0,
        "pre_avisos": 0,
        "erros": 0,
        "pulados_fora_janela": 0,
        "adiados": 0,
    }

    mapa_gestor_setor = _construir_mapa_gestor_setor()
    mapa_niveis_superiores = _construir_mapa_niveis_superiores()

    try:
        with db_module.SessionLocal() as session:
            stmt = (
                select(ChamadoRow)
                .where(
                    ChamadoRow.status.in_(("Aberto", "Em Atendimento")),
                    ChamadoRow.escalacao_nivel < _NIVEL_MAXIMO,
                )
                .limit(500)
            )
            rows = session.execute(stmt).scalars().all()
    except Exception as exc:
        logger.exception("Escalonamento: erro ao consultar chamados: %s", exc)
        stats["erros"] += 1
        return stats

    for row in rows:
        stats["processados"] += 1
        try:
            _processar_chamado_escalonamento(
                row, agora, stats, mapa_gestor_setor, mapa_niveis_superiores
            )
        except Exception as exc:
            logger.exception("Escalonamento: erro ao processar chamado %s: %s", row.id, exc)
            stats["erros"] += 1

    return stats


def _obter_alvo_tick(chamado: Chamado, data: dict, nivel_atual: int) -> datetime | None:
    """Retorna o datetime do próximo tick agendado (alvo).

    Enquanto nivel_atual==0, recalcula a cada passagem a partir de
    categoria+status+data_abertura (o alvo do AOG pode mudar se o chamado
    for assumido antes do limiar de reivindicação). A partir do nível 1,
    usa o valor persistido em escalacao_proximo_tick_em.
    """
    if nivel_atual > 0:
        return data.get("escalacao_proximo_tick_em")

    data_abertura = data.get("data_abertura")
    if data_abertura is None:
        return None
    return calcular_deadline_inicial(data["categoria"], data["status"], data_abertura)


def _processar_chamado_escalonamento(
    row: ChamadoRow,
    agora: datetime,
    stats: dict,
    mapa_gestor_setor: dict[str, str],
    mapa_niveis_superiores: dict[str, str],
) -> None:
    """Avalia e (se aplicável) escala ou avisa previamente um único chamado."""
    chamado = Chamado._from_row(row)
    data = chamado.to_dict()
    chamado_id = chamado.id
    categoria = data.get("categoria") or ""
    status = data.get("status")
    is_aog = categoria == "AOG"

    # Previsão de atendimento: supervisor/admin combinou mais tempo com o gestor —
    # silencia a escalada inteira (nível não muda) até a data passar. AOG nunca
    # deveria ter esse campo preenchido (bloqueado em definir_previsao_atendimento),
    # mas o gate fica aqui também por defesa em profundidade.
    previsao = data.get("previsao_atendimento")
    if previsao is not None and agora.replace(tzinfo=None) < previsao.replace(tzinfo=None):
        stats["adiados"] += 1
        return

    nivel_atual = int(data.get("escalacao_nivel") or 0)
    alvo_tick = _obter_alvo_tick(chamado, data, nivel_atual)
    if alvo_tick is None:
        logger.warning("Escalonamento: chamado %s sem data_abertura; ignorado.", chamado_id)
        return

    agora_naive = agora.replace(tzinfo=None)
    alvo_naive = alvo_tick.replace(tzinfo=None)
    pode_notificar_agora = is_aog or pode_enviar_notificacao_agora(agora)

    # Aviso prévio: dispara uma vez por nível-alvo quando o tick cai dentro
    # da janela de antecedência configurada, mesmo que o tick em si ainda
    # não tenha vencido. Mesmo gate de expediente do tick em si (não faz
    # sentido avisar de madrugada sobre algo que só vai realmente escalar
    # na próxima janela útil).
    nivel_alvo = nivel_atual + 1
    ja_avisado = data.get("escalacao_pre_aviso_nivel_enviado")
    dentro_janela_aviso = (
        agora_naive < alvo_naive <= agora_naive + timedelta(minutes=Config.SLA_PRE_AVISO_MINUTOS)
    )
    if dentro_janela_aviso and ja_avisado != nivel_alvo and pode_notificar_agora:
        _enviar_pre_aviso(chamado, data, nivel_alvo, alvo_naive, agora_naive)
        chamado.atualizar_campos(escalacao_pre_aviso_nivel_enviado=nivel_alvo)
        stats["pre_avisos"] += 1

    if agora_naive < alvo_naive:
        return  # tick ainda não venceu

    if not pode_notificar_agora:
        stats["pulados_fora_janela"] += 1
        return

    novo_nivel = nivel_atual + 1
    chave_gestor = NIVEL_PARA_CHAVE_GESTOR.get(novo_nivel)
    email_dest = _resolver_email_gestor(
        chave_gestor, categoria, mapa_gestor_setor, mapa_niveis_superiores
    )
    assumido = status == "Em Atendimento"

    if email_dest:
        try:
            notificar_escalada_gerencial(
                chamado_data=data,
                chamado_id=chamado_id,
                nivel=novo_nivel,
                email_dest=email_dest,
                assumido=assumido,
            )
            stats["emails"] += 1
        except Exception as exc:
            logger.warning(
                "Escalonamento: falha ao enviar e-mail nível %d para %s (chamado %s): %s",
                novo_nivel,
                email_dest,
                chamado_id,
                exc,
            )
    else:
        logger.warning(
            "Escalonamento: chamado %s → nível %d: nenhum usuário ativo com nivel_gestao='%s' "
            "cadastrado. Incrementando nível sem e-mail.",
            chamado_id,
            novo_nivel,
            chave_gestor,
        )

    cadencia = calcular_cadencia_minutos(categoria, status)
    chamado.atualizar_campos(
        escalacao_nivel=novo_nivel,
        escalacao_proximo_tick_em=agora.replace(tzinfo=None) + timedelta(minutes=cadencia),
    )
    stats["escalados"] += 1

    Historico(
        chamado_id=chamado_id,
        usuario_id=USUARIO_ID_SISTEMA,
        usuario_nome=USUARIO_NOME_SISTEMA_SLA,
        acao="escalonamento_automatico",
        campo_alterado="escalacao_nivel",
        valor_anterior=str(nivel_atual),
        valor_novo=str(novo_nivel),
        detalhe=f"Nível {nivel_atual}→{novo_nivel}"
        + (
            f" — e-mail para {email_dest}" if email_dest else " — sem gestor cadastrado, sem e-mail"
        ),
    ).save()

    logger.info(
        "Escalonamento: chamado %s escalado %d→%d (status=%s, chave=%s, email_ok=%s)",
        chamado_id,
        nivel_atual,
        novo_nivel,
        status,
        chave_gestor,
        bool(email_dest),
    )


def _enviar_pre_aviso(
    chamado: Chamado,
    data: dict,
    nivel_alvo: int,
    alvo_naive: datetime,
    agora_naive: datetime,
) -> None:
    minutos_restantes = max(1, int((alvo_naive - agora_naive).total_seconds() // 60))
    responsavel_id = data.get("responsavel_id")
    email_dest = _obter_email_responsavel(responsavel_id) if responsavel_id else None
    try:
        notificar_pre_aviso_escalonamento(
            chamado_data=data,
            chamado_id=chamado.id,
            nivel_alvo=nivel_alvo,
            minutos_restantes=minutos_restantes,
            responsavel_id=responsavel_id,
            email_dest=email_dest,
        )
    except Exception as exc:
        logger.warning(
            "Escalonamento: falha ao enviar aviso prévio (chamado %s, nível-alvo %d): %s",
            chamado.id,
            nivel_alvo,
            exc,
        )

    Historico(
        chamado_id=chamado.id,
        usuario_id=USUARIO_ID_SISTEMA,
        usuario_nome=USUARIO_NOME_SISTEMA_SLA,
        acao="aviso_previo_escalonamento",
        campo_alterado="escalacao_nivel",
        valor_anterior=None,
        valor_novo=str(nivel_alvo),
        detalhe=f"Faltam ~{minutos_restantes}min pro nível {nivel_alvo}",
    ).save()


# ---------------------------------------------------------------------------
# Avisos 50%/80% do prazo de resolução — não faz parte do motor de
# escalonamento gerencial acima, segue com sua própria lógica inalterada.
# ---------------------------------------------------------------------------


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
        with db_module.SessionLocal() as session:
            stmt = select(ChamadoRow).where(ChamadoRow.status == "Em Atendimento").limit(500)
            rows = session.execute(stmt).scalars().all()
    except Exception as exc:
        logger.exception("Avisos resolução: erro ao consultar chamados: %s", exc)
        stats["erros"] += 1
        return stats

    for row in rows:
        stats["processados"] += 1
        try:
            _processar_aviso_resolucao(row, agora, stats)
        except Exception as exc:
            logger.exception("Avisos resolução: erro ao processar chamado %s: %s", row.id, exc)
            stats["erros"] += 1

    return stats


def _processar_aviso_resolucao(row: ChamadoRow, agora: datetime, stats: dict) -> None:
    """Avalia e (se aplicável) envia aviso de SLA de resolução para um único chamado."""
    chamado = Chamado._from_row(row)
    data = chamado.to_dict()
    chamado_id = chamado.id

    responsavel_id = data.get("responsavel_id")
    if not responsavel_id:
        return

    data_em_atendimento = data.get("data_em_atendimento")
    if data_em_atendimento is None:
        logger.warning(
            "Avisos resolução: chamado %s sem data_em_atendimento; ignorado.", chamado_id
        )
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

    # Threshold atingido: verificar janela de notificação (mesmo padrão do motor de escalonamento)
    if not pode_enviar_notificacao_agora(agora):
        stats["pulados_fora_janela"] += 1
        return

    email_resp: str | None = _obter_email_responsavel(responsavel_id)
    updates: dict = {}

    # Aviso 50%
    if threshold_50:
        notificar_aviso_resolucao_supervisor(
            chamado_data=data,
            chamado_id=chamado_id,
            marco=50,
            responsavel_id=responsavel_id,
            email_dest=email_resp,
        )
        stats["notificados_50"] += 1
        updates["alerta_supervisor_50_enviado"] = True
        Historico(
            chamado_id=chamado_id,
            usuario_id=USUARIO_ID_SISTEMA,
            usuario_nome=USUARIO_NOME_SISTEMA_SLA,
            acao="aviso_resolucao_prazo",
            campo_alterado="alerta_supervisor_50_enviado",
            valor_anterior=None,
            valor_novo="50%",
        ).save()

    # Aviso 80%
    if threshold_80:
        notificar_aviso_resolucao_supervisor(
            chamado_data=data,
            chamado_id=chamado_id,
            marco=80,
            responsavel_id=responsavel_id,
            email_dest=email_resp,
        )
        stats["notificados_80"] += 1
        updates["alerta_supervisor_80_enviado"] = True
        Historico(
            chamado_id=chamado_id,
            usuario_id=USUARIO_ID_SISTEMA,
            usuario_nome=USUARIO_NOME_SISTEMA_SLA,
            acao="aviso_resolucao_prazo",
            campo_alterado="alerta_supervisor_80_enviado",
            valor_anterior=None,
            valor_novo="80%",
        ).save()

    if updates:
        chamado.atualizar_campos(**updates)
        logger.info(
            "Avisos resolução: chamado %s atualizado (pct=%.0f%%), flags=%s",
            chamado_id,
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
