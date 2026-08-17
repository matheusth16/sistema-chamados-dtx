"""Previsão de atendimento — unifica o antigo "Prazo do chamado (dias)"
(sla_dias) e "Adiar avisos de escalonamento" (previsao_atendimento) numa
única solicitação de data, que só passa a valer (chamados.previsao_atendimento
+ motivo_previsao_atendimento) depois de aprovada pelo gestor_setor da área
do chamado — com fallback em cascata pro próximo nível de gestão se não
houver gestor_setor cadastrado pra área (mesmo espírito de
resolver_email_gestor_com_cascata em gestor_escalonamento_service.py).

Enquanto pendente, o chamado continua se comportando como se nada tivesse
sido pedido: o gate de escalonamento (sla_escalacao_service.py) só lê
chamados.previsao_atendimento, que só é escrito na aprovação. Isso fecha a
brecha de pedir uma data só pra silenciar avisos e nunca decidir.

Aprovação por e-mail usa link assinado de uso único (itsdangerous, mesmo
padrão de app/routes/auth.py pra "dispositivo confiável"): GET mostra uma
página de confirmação somente leitura (sem efeito colateral — evita bot/
prefetch de e-mail disparando a decisão), POST efetiva a decisão.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import db as db_module
from app.db.models.chamado import ChamadoPrevisaoSolicitacaoRow, ChamadoRow
from app.i18n import get_translation_session
from app.models import Chamado
from app.models_historico import Historico
from app.services.analytics import _prazo_efetivo, _sla_dias_por_categoria
from app.services.business_time import adicionar_dias_uteis
from config import Config

logger = logging.getLogger(__name__)

_SALT_TOKEN_DECISAO = "previsao-atendimento-decisao"  # nosec B105 - salt público do itsdangerous, não segredo (ver _serializer)
_TOKEN_MAX_AGE_SEGUNDOS = 30 * 24 * 60 * 60  # 30 dias
ACOES_VALIDAS = ("aprovar", "rejeitar")
# Extensões automáticas (self-service) grátis por chamado antes de exigir
# aprovação do gestor — ver solicitar_extensao_automatica.
LIMITE_EXTENSOES_AUTOMATICAS = 3


def _t(key, **kwargs):
    return get_translation_session(key, **kwargs)


def _permite_solicitar_previsao(usuario, chamado) -> bool:
    """Owner-ou-admin E perfil supervisor+ — reusado por solicitar_previsao_atendimento
    e solicitar_extensao_automatica (mesma regra de quem pode mexer no prazo)."""
    eh_supervisor_ou_acima = getattr(usuario, "perfil", None) in (
        "supervisor",
        "admin",
        "admin_global",
    )
    eh_owner_ou_admin = chamado.responsavel_id == usuario.id or usuario.is_admin_or_above
    return eh_supervisor_ou_acima and eh_owner_ou_admin


# ── Token de aprovação por e-mail ────────────────────────────────────────────


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.secret_key, salt=_SALT_TOKEN_DECISAO)


def gerar_token_decisao(solicitacao_id: int, acao: str) -> str:
    """Token assinado de uso único (validade + status 'pendente' garantem
    isso — reaproveitar um token já decidido é um no-op, ver decidir_previsao_atendimento)."""
    return _serializer().dumps({"solicitacao_id": solicitacao_id, "acao": acao})


def validar_token_decisao(token: str) -> dict | None:
    """Retorna {"solicitacao_id": int, "acao": str} ou None se inválido/expirado/adulterado."""
    try:
        payload = _serializer().loads(token, max_age=_TOKEN_MAX_AGE_SEGUNDOS)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("acao") not in ACOES_VALIDAS:
        return None
    if not isinstance(payload.get("solicitacao_id"), int):
        return None
    return payload


# ── Resolução do gestor decisor ──────────────────────────────────────────────


def _localizar_gestor_setor(areas: str | list[str]):
    """Primeiro gestor_setor ativo cujo .areas bate com QUALQUER área da
    lista informada. Aceita uma única área (string, comportamento original,
    usado por resolver_gestor_decisor) ou uma lista (usado por
    resolver_gestor_do_solicitante — quem abriu o chamado pode ter mais de
    uma área cadastrada)."""
    lista_areas = [areas] if isinstance(areas, str) else list(areas or [])
    lista_areas = [a for a in lista_areas if a]
    if not lista_areas:
        return None

    from app.models_usuario import Usuario

    for usuario in Usuario.get_all():
        if (
            getattr(usuario, "nivel_gestao", None) == "gestor_setor"
            and getattr(usuario, "ativo", True)
            and any(a in (getattr(usuario, "areas", None) or []) for a in lista_areas)
        ):
            return usuario
    return None


def _localizar_fallback_superior():
    """Cai pro próximo nível de gestão (company-wide) se ninguém com
    nivel_gestao='gestor_setor' estiver cadastrado pra área — evita pedido
    travado pra sempre por lacuna de cadastro."""
    from app.models_usuario import Usuario
    from app.services.gestor_escalonamento_service import NIVEIS_GESTAO_SUPERIORES

    usuarios = list(Usuario.get_all())
    for nivel in NIVEIS_GESTAO_SUPERIORES:
        candidatos = sorted(
            (
                u
                for u in usuarios
                if getattr(u, "nivel_gestao", None) == nivel
                and getattr(u, "ativo", True)
                and getattr(u, "email", None)
            ),
            key=lambda u: u.email,
        )
        if candidatos:
            return candidatos[0]
    return None


def resolver_gestor_decisor(area: str):
    """Usuario que deve decidir o pedido: gestor_setor da área do chamado
    (chamado.area, não a área de quem solicitou), com fallback em cascata.
    Retorna None se não houver ninguém cadastrado em nível nenhum."""
    return _localizar_gestor_setor(area or "") or _localizar_fallback_superior()


def resolver_gestor_do_solicitante(usuario_solicitante):
    """Usuario que deve ser avisado em nome de quem ABRIU o chamado: o
    gestor_setor cujo .areas bate com o departamento do próprio solicitante
    (usuario_solicitante.areas), não com a área que está atendendo o
    chamado — usado só nas notificações de extensão automática. Mesmo
    fallback em cascata de resolver_gestor_decisor."""
    areas_solicitante = getattr(usuario_solicitante, "areas", None) or []
    return _localizar_gestor_setor(areas_solicitante) or _localizar_fallback_superior()


def usuario_pode_decidir_previsao_atendimento(usuario, chamado_area: str) -> bool:
    """Admin sempre pode. gestor_setor só se a área do chamado estiver entre
    as áreas que ele gerencia — independente de quem foi registrado como
    gestor_id no pedido (se o gestor mudou depois do pedido, quem qualifica
    hoje decide).

    Conta ativo=False sempre nega, admin incluso: a decisão por link de
    e-mail (app/routes/aprovacao_previsao.py) é uma rota pública sem
    login/sessão, então desativar a conta não bloqueia por si só o fluxo —
    quem desativou um gestor_setor pode não saber que um link de e-mail
    ainda válido (token dura até 30 dias) continua permitindo decidir (bug
    real, auditoria 2026-08-13)."""
    if not getattr(usuario, "ativo", True):
        return False
    if getattr(usuario, "is_admin_or_above", False):
        return True
    return getattr(usuario, "nivel_gestao", None) == "gestor_setor" and chamado_area in (
        getattr(usuario, "areas", None) or []
    )


# ── Leitura ───────────────────────────────────────────────────────────────


def _row_to_dict(row: ChamadoPrevisaoSolicitacaoRow) -> dict:
    return {
        "id": row.id,
        "chamado_id": row.chamado_id,
        "solicitante_id": row.solicitante_id,
        "solicitante_nome": row.solicitante_nome,
        "previsao_solicitada": row.previsao_solicitada,
        "motivo": row.motivo,
        "status": row.status,
        "gestor_id": row.gestor_id,
        "gestor_nome": row.gestor_nome,
        "motivo_rejeicao": row.motivo_rejeicao,
        "decidido_em": row.decidido_em,
        "criado_em": row.criado_em,
    }


def obter_solicitacao_pendente(chamado_id) -> dict | None:
    """Pedido pendente do chamado, se houver (no máximo 1 por construção do índice único)."""
    try:
        cid = int(chamado_id)
    except (TypeError, ValueError):
        return None
    with db_module.SessionLocal() as session:
        row = session.execute(
            select(ChamadoPrevisaoSolicitacaoRow).where(
                ChamadoPrevisaoSolicitacaoRow.chamado_id == cid,
                ChamadoPrevisaoSolicitacaoRow.status == "pendente",
            )
        ).scalar_one_or_none()
        return _row_to_dict(row) if row else None


def obter_solicitacao_por_id(solicitacao_id: int) -> dict | None:
    with db_module.SessionLocal() as session:
        row = session.get(ChamadoPrevisaoSolicitacaoRow, solicitacao_id)
        return _row_to_dict(row) if row else None


# ── Escrita ───────────────────────────────────────────────────────────────


def solicitar_previsao_atendimento(chamado_id: str, previsao, motivo: str, usuario) -> dict:
    """Cria um pedido de previsão de atendimento (status 'pendente'). Não
    mexe em chamados.previsao_atendimento — isso só acontece na aprovação
    (ver decidir_previsao_atendimento).

    Args:
        chamado_id: ID do chamado.
        previsao: datetime solicitado — obrigatório, futuro.
        motivo: obrigatório e não vazio.
        usuario: quem pede — precisa ser owner-ou-admin, E supervisor+.

    Returns:
        {"sucesso": True, "dados": {...}} ou {"sucesso": False, "erro": "..."}.

    Raises:
        ValueError: campos obrigatórios nulos/vazios (previsao, motivo).
    """
    if previsao is None:
        raise ValueError("previsao_atendimento obrigatória")

    motivo = (motivo or "").strip()
    if not motivo:
        raise ValueError("motivo obrigatório")

    chamado = Chamado.get_by_id(chamado_id)
    if chamado is None:
        return {"sucesso": False, "erro": _t("ticket_not_found")}

    # AOG é prioridade máxima, sempre — nunca pode ter a escalada silenciada
    # por previsão de atendimento, nem por owner nem por admin.
    if chamado.categoria == "AOG":
        logger.warning(
            "solicitar_previsao_atendimento negado: chamado %s é AOG (bloqueio incondicional)",
            chamado_id,
        )
        return {"sucesso": False, "erro": _t("attendance_forecast_not_allowed_aog")}

    if not _permite_solicitar_previsao(usuario, chamado):
        logger.warning(
            "solicitar_previsao_atendimento negado: usuário %s sem permissão no chamado %s",
            usuario.id,
            chamado_id,
        )
        return {"sucesso": False, "erro": _t("no_permission_set_attendance_forecast")}

    # previsao chega naive do <input type="datetime-local">, representando um
    # horário no fuso de negócio (Config.SLA_TIMEZONE) — mesma convenção usada
    # na leitura em sla_escalacao_service.py.
    agora_fuso_negocio = datetime.now(ZoneInfo(Config.SLA_TIMEZONE)).replace(tzinfo=None)
    if previsao <= agora_fuso_negocio:
        return {"sucesso": False, "erro": _t("attendance_forecast_must_be_future")}

    # previsao_atendimento_service nunca ENCURTA o prazo TAT (ver
    # analytics._prazo_efetivo) — uma previsão pedida pra antes do TAT da
    # categoria não teria efeito nenhum se aprovada, e permitir isso só
    # confundia quem decide (bug real, auditoria 2026-08-13: nada validava
    # essa relação, dava pra pedir/aprovar previsão pra "daqui a 2 minutos"
    # num chamado com TAT de dias).
    if chamado.data_abertura is not None:
        dias_tat = _sla_dias_por_categoria(
            chamado.categoria or "", getattr(chamado, "sla_dias", None)
        )
        prazo_tat = chamado.data_abertura + timedelta(days=dias_tat)
        previsao_instante = previsao.replace(tzinfo=ZoneInfo(Config.SLA_TIMEZONE))
        prazo_tat_instante = (
            prazo_tat
            if prazo_tat.tzinfo is not None
            else prazo_tat.replace(tzinfo=ZoneInfo(Config.SLA_TIMEZONE))
        )
        if previsao_instante <= prazo_tat_instante:
            return {"sucesso": False, "erro": _t("attendance_forecast_must_be_after_tat_deadline")}

    pendente_existente = obter_solicitacao_pendente(chamado.id)
    if pendente_existente is not None:
        return {"sucesso": False, "erro": _t("attendance_forecast_request_already_pending")}

    gestor = resolver_gestor_decisor(chamado.area or "")

    try:
        with db_module.SessionLocal() as session, session.begin():
            row = ChamadoPrevisaoSolicitacaoRow(
                chamado_id=chamado.id,
                solicitante_id=usuario.id,
                solicitante_nome=usuario.nome,
                previsao_solicitada=previsao,
                motivo=motivo[:500],
                status="pendente",
                gestor_id=getattr(gestor, "id", None),
                gestor_nome=getattr(gestor, "nome", None),
            )
            session.add(row)
            session.flush()
            solicitacao_id = row.id
    except IntegrityError:
        # Corrida com outro pedido concorrente — o índice único parcial pegou.
        return {"sucesso": False, "erro": _t("attendance_forecast_request_already_pending")}

    Historico(
        chamado_id=chamado_id,
        usuario_id=usuario.id,
        usuario_nome=usuario.nome,
        acao="solicitacao_previsao_atendimento",
        campo_alterado="previsao_atendimento",
        valor_anterior=None,
        valor_novo=str(previsao),
        detalhe=f"Solicitado para {previsao} — {motivo[:500]}",
    ).save()

    logger.info(
        "Chamado %s: previsão de atendimento solicitada para %s por %s (solicitacao=%s, gestor=%s)",
        chamado_id,
        previsao,
        usuario.id,
        solicitacao_id,
        getattr(gestor, "id", None),
    )

    return {
        "sucesso": True,
        "dados": {
            "solicitacao_id": solicitacao_id,
            "previsao_solicitada": str(previsao),
            "gestor_id": getattr(gestor, "id", None),
            "gestor_nome": getattr(gestor, "nome", None),
        },
    }


def solicitar_extensao_automatica(chamado_id: str, usuario) -> dict:
    """Extensão automática (self-service) do prazo — sem aprovação do
    gestor. Até LIMITE_EXTENSOES_AUTOMATICAS por chamado, cada uma somando
    o TAT da categoria (respeitando sla_dias customizado, mesma regra de
    _sla_dias_por_categoria) em cima do prazo efetivo ATUAL — que já pode
    ter sido estendido antes, por uma extensão automática anterior ou por
    uma previsão aprovada pelo gestor.

    Ratchet de mão única: uma vez que decidir_previsao_atendimento trava o
    chamado (previsao_extensao_travada=True), essa função nunca mais aplica
    nada nele, mesmo que ainda "sobrem" extensões no contador — o self-service
    não é reconcedido depois que o gestor precisa intervir.

    Args:
        chamado_id: ID do chamado.
        usuario: quem pede — precisa ser owner-ou-admin, E supervisor+
            (mesma regra de solicitar_previsao_atendimento).

    Returns:
        {"sucesso": True, "dados": {...}} ou {"sucesso": False, "erro": "..."}.
    """
    chamado = Chamado.get_by_id(chamado_id)
    if chamado is None:
        return {"sucesso": False, "erro": _t("ticket_not_found")}

    # AOG é prioridade máxima, sempre — nunca pode ter o prazo alterado,
    # nem pelo fluxo manual nem pela extensão automática.
    if chamado.categoria == "AOG":
        logger.warning(
            "solicitar_extensao_automatica negado: chamado %s é AOG (bloqueio incondicional)",
            chamado_id,
        )
        return {"sucesso": False, "erro": _t("attendance_forecast_not_allowed_aog")}

    if not _permite_solicitar_previsao(usuario, chamado):
        logger.warning(
            "solicitar_extensao_automatica negado: usuário %s sem permissão no chamado %s",
            usuario.id,
            chamado_id,
        )
        return {"sucesso": False, "erro": _t("no_permission_set_attendance_forecast")}

    # Enquanto há um pedido manual pendente, não deixa a extensão automática
    # somar em cima de um prazo que está prestes a ser substituído pela
    # decisão do gestor — evita os dois prazos se pisarem.
    if obter_solicitacao_pendente(chamado.id) is not None:
        return {
            "sucesso": False,
            "erro": _t("attendance_forecast_self_service_blocked_by_pending"),
        }

    with db_module.SessionLocal() as session, session.begin():
        chamado_row = session.execute(
            select(ChamadoRow).where(ChamadoRow.id == chamado.id).with_for_update()
        ).scalar_one_or_none()
        if chamado_row is None:
            return {"sucesso": False, "erro": _t("ticket_not_found")}

        if chamado_row.previsao_extensao_travada:
            return {"sucesso": False, "erro": _t("attendance_forecast_self_service_locked")}

        if chamado_row.previsao_extensoes_automaticas_usadas >= LIMITE_EXTENSOES_AUTOMATICAS:
            return {
                "sucesso": False,
                "erro": _t("attendance_forecast_self_service_limit_reached"),
            }

        dias_tat = _sla_dias_por_categoria(chamado_row.categoria or "", chamado_row.sla_dias)
        baseline = adicionar_dias_uteis(chamado_row.data_abertura, dias_tat)
        prazo_atual = _prazo_efetivo(baseline, chamado_row.previsao_atendimento)
        # prazo_atual sempre sai tz-aware (baseline vem de data_abertura, que
        # é um instante real de verdade; _prazo_efetivo reanexa
        # Config.SLA_TIMEZONE em cima dos dígitos de previsao_atendimento).
        # .replace(tzinfo=None) é obrigatório antes de gravar — a convenção
        # da coluna é dígitos naive = horário local, nunca um instante
        # tz-aware de verdade (ver docstring de analytics._previsao_atendimento_instante).
        nova_previsao = adicionar_dias_uteis(prazo_atual, dias_tat).replace(tzinfo=None)

        extensoes_usadas = chamado_row.previsao_extensoes_automaticas_usadas + 1
        motivo = f"Extensão automática {extensoes_usadas}/{LIMITE_EXTENSOES_AUTOMATICAS}"

        chamado_row.previsao_atendimento = nova_previsao
        chamado_row.motivo_previsao_atendimento = motivo
        chamado_row.previsao_extensoes_automaticas_usadas = extensoes_usadas

        solicitante_id = chamado_row.solicitante_id
        solicitante_nome = chamado_row.solicitante_nome

    Historico(
        chamado_id=chamado_id,
        usuario_id=usuario.id,
        usuario_nome=usuario.nome,
        acao="extensao_automatica_previsao",
        campo_alterado="previsao_atendimento",
        valor_anterior=str(prazo_atual),
        valor_novo=str(nova_previsao),
        detalhe=motivo,
    ).save()

    logger.info(
        "Chamado %s: extensão automática %s/%s aplicada por %s — nova previsão %s",
        chamado_id,
        extensoes_usadas,
        LIMITE_EXTENSOES_AUTOMATICAS,
        usuario.id,
        nova_previsao,
    )

    return {
        "sucesso": True,
        "dados": {
            "previsao_nova": str(nova_previsao),
            "extensoes_usadas": extensoes_usadas,
            "extensoes_restantes": LIMITE_EXTENSOES_AUTOMATICAS - extensoes_usadas,
            "solicitante_id": solicitante_id,
            "solicitante_nome": solicitante_nome,
            "responsavel_id": usuario.id,
            "responsavel_nome": usuario.nome,
        },
    }


def decidir_previsao_atendimento(
    solicitacao_id: int,
    acao: str,
    gestor,
    motivo_rejeicao: str | None = None,
) -> dict:
    """Aprova ou rejeita um pedido pendente. Idempotente contra decisão
    duplicada (clique 2x, token reaproveitado): a segunda chamada encontra
    status != 'pendente' e retorna erro sem reaplicar nada.

    Args:
        solicitacao_id: ID da linha em chamado_previsao_solicitacoes.
        acao: 'aprovar' ou 'rejeitar'.
        gestor: quem decide — precisa passar em usuario_pode_decidir_previsao_atendimento.
        motivo_rejeicao: opcional, só usado quando acao == 'rejeitar'.

    Returns:
        {"sucesso": True, "dados": {...}} ou {"sucesso": False, "erro": "...", "codigo": int}.
    """
    if acao not in ACOES_VALIDAS:
        raise ValueError("acao inválida")

    with db_module.SessionLocal() as session, session.begin():
        row = session.execute(
            select(ChamadoPrevisaoSolicitacaoRow)
            .where(ChamadoPrevisaoSolicitacaoRow.id == solicitacao_id)
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            return {
                "sucesso": False,
                "erro": _t("attendance_forecast_request_not_found"),
                "codigo": 404,
            }

        if row.status != "pendente":
            return {
                "sucesso": False,
                "erro": _t("attendance_forecast_request_already_decided"),
                "codigo": 409,
            }

        chamado_row = session.execute(
            select(ChamadoRow).where(ChamadoRow.id == row.chamado_id).with_for_update()
        ).scalar_one_or_none()
        if chamado_row is None:
            return {"sucesso": False, "erro": _t("ticket_not_found"), "codigo": 404}

        if not usuario_pode_decidir_previsao_atendimento(gestor, chamado_row.area or ""):
            logger.warning(
                "decidir_previsao_atendimento negado: usuário %s sem permissão na área %s",
                getattr(gestor, "id", None),
                chamado_row.area,
            )
            return {
                "sucesso": False,
                "erro": _t("no_permission_decide_attendance_forecast"),
                "codigo": 403,
            }

        # TOCTOU: o pedido fica pendente por tempo arbitrário até o gestor
        # decidir — o chamado pode ter sido cancelado/concluído nesse
        # meio-tempo. Aprovar nesse caso reabriria um prazo pra um chamado
        # que não está mais ativo, então a aprovação vira uma rejeição
        # automática (fecha o pedido sem tocar em chamados.previsao_atendimento).
        # Rejeitar nunca escreve no chamado, então continua permitido mesmo
        # com o chamado já encerrado — fecha formalmente o pedido pendente.
        encerrado_automaticamente = acao == "aprovar" and chamado_row.status in (
            "Cancelado",
            "Concluído",
        )
        acao_efetiva = "rejeitar" if encerrado_automaticamente else acao
        if encerrado_automaticamente:
            logger.warning(
                "decidir_previsao_atendimento: aprovação de %s recusada — chamado %s está %s",
                solicitacao_id,
                row.chamado_id,
                chamado_row.status,
            )

        # Ratchet de mão única: assim que o gestor decide (aprova OU rejeita)
        # um pedido de verdade — não o auto-reject por TOCTOU, que não é
        # decisão de mérito sobre nada — a extensão automática (self-service)
        # fica desabilitada permanentemente pra esse chamado. Não volta a
        # ganhar 3 de novo (ver solicitar_extensao_automatica).
        if not encerrado_automaticamente:
            chamado_row.previsao_extensao_travada = True

        row.status = "aprovada" if acao_efetiva == "aprovar" else "rejeitada"
        row.gestor_id = gestor.id
        row.gestor_nome = gestor.nome
        row.decidido_em = datetime.now(ZoneInfo(Config.SLA_TIMEZONE))
        if acao_efetiva == "rejeitar":
            row.motivo_rejeicao = (
                _t("attendance_forecast_ticket_no_longer_open")[:500]
                if encerrado_automaticamente
                else (motivo_rejeicao or "").strip()[:500] or None
            )

        if acao_efetiva == "aprovar":
            chamado_row.previsao_atendimento = row.previsao_solicitada
            chamado_row.motivo_previsao_atendimento = row.motivo

        chamado_id = row.chamado_id
        solicitante_id = row.solicitante_id
        solicitante_nome = row.solicitante_nome
        previsao_solicitada = row.previsao_solicitada
        motivo_pedido = row.motivo
        motivo_rejeicao_final = row.motivo_rejeicao

    Historico(
        chamado_id=chamado_id,
        usuario_id=gestor.id,
        usuario_nome=gestor.nome,
        acao="aprovacao_previsao_atendimento"
        if acao_efetiva == "aprovar"
        else "rejeicao_previsao_atendimento",
        campo_alterado="previsao_atendimento",
        valor_anterior=motivo_pedido,
        valor_novo=str(previsao_solicitada) if acao_efetiva == "aprovar" else None,
        detalhe=motivo_rejeicao_final if acao_efetiva == "rejeitar" else None,
    ).save()

    logger.info(
        "Chamado %s: pedido de previsão %s (solicitacao=%s) %s por %s",
        chamado_id,
        previsao_solicitada,
        solicitacao_id,
        "aprovado" if acao_efetiva == "aprovar" else "rejeitado",
        gestor.id,
    )

    if encerrado_automaticamente:
        return {
            "sucesso": False,
            "erro": _t("attendance_forecast_ticket_no_longer_open"),
            "codigo": 409,
        }

    return {
        "sucesso": True,
        "dados": {
            "chamado_id": chamado_id,
            "solicitante_id": solicitante_id,
            "solicitante_nome": solicitante_nome,
            "acao": acao,
            "previsao_solicitada": previsao_solicitada,
            "motivo_rejeicao": motivo_rejeicao_final,
        },
    }
