"""Rotas de colaboração no chamado: transferência de área, escalonamento, previsão de atendimento, participantes."""

import logging
import threading

from flask import current_app, jsonify, request, session
from flask_login import current_user, login_required

from app.decoradores import requer_supervisor_area, requer_supervisor_area_ou_gestor_setor
from app.i18n import flash_t, get_translation
from app.models import Chamado
from app.models_usuario import Usuario
from app.routes import main
from app.services.api_response import erro_json
from app.services.permissions import usuario_gestor_setor_pode_escalonar, usuario_pode_ver_chamado
from app.services.permissoes_edicao_chamado import usuario_pode_mutar_chamado

logger = logging.getLogger(__name__)


def _t(key, **kwargs):
    """Traduz uma chave i18n para o idioma da sessão atual."""
    return get_translation(key, session.get("language", "en"), **kwargs)


# ---------------------------------------------------------------------------
# Escalonamento — Fase 3
# ---------------------------------------------------------------------------


def _notificar_escalonamento(
    app, chamado_id: str, dados_chamado: dict, tipo: str, destino_id: str
) -> None:
    """Dispara notificação de escalonamento em background."""

    def _run():
        with app.app_context():
            try:
                destino = Usuario.get_by_id(destino_id)
                if not destino:
                    return
                numero = dados_chamado.get("numero_chamado") or "N/A"
                area = dados_chamado.get("area") or ""
                categoria = dados_chamado.get("categoria") or ""
                if tipo == "transferencia_area":
                    from app.services.notifications import notificar_supervisor_transferencia_area

                    notificar_supervisor_transferencia_area(
                        chamado_id=chamado_id,
                        numero_chamado=numero,
                        area=area,
                        categoria=categoria,
                        motivo=dados_chamado.get("motivo_ultima_escalacao") or "",
                        responsavel_usuario=destino,
                    )
                else:
                    from app.services.notifications import notificar_supervisor_escalonamento_colega

                    notificar_supervisor_escalonamento_colega(
                        chamado_id=chamado_id,
                        numero_chamado=numero,
                        area=area,
                        categoria=categoria,
                        motivo=dados_chamado.get("motivo_ultima_escalacao") or "",
                        responsavel_usuario=destino,
                    )
            except Exception as exc:
                logger.warning("Notificação de escalonamento não enviada: %s", exc)

    threading.Thread(target=_run, daemon=True).start()


@main.route("/api/chamado/<chamado_id>/transferir-area", methods=["POST"])
@login_required
@requer_supervisor_area_ou_gestor_setor
def api_transferir_area(chamado_id: str):
    """Transfere o chamado para outra área com novo responsável obrigatório.

    Body JSON: {"area": str, "supervisor_id": str, "motivo": str}
    Acesso: owner (responsavel_id == current_user.id), admin, ou gestor_setor
    da área do chamado (Ações de Escalonamento — decisão de escopo 2026-08-20).
    """
    try:
        dados = request.get_json(silent=True)
        if not dados:
            return erro_json(_t("invalid_or_empty_json"), 400)

        area = (dados.get("area") or "").strip()
        supervisor_id = (dados.get("supervisor_id") or "").strip()
        motivo = (dados.get("motivo") or "").strip()

        if not area:
            return erro_json(_t("field_target_area_required"), 400)
        if not supervisor_id:
            return erro_json(_t("field_supervisor_id_required"), 400)
        if not motivo:
            return erro_json(_t("error_reason_required"), 400)

        chamado = Chamado.get_by_id(chamado_id)
        if not chamado:
            return erro_json(_t("ticket_not_found"), 404)

        dados_chamado = chamado.to_dict()

        if not usuario_pode_ver_chamado(current_user, chamado):
            return erro_json(_t("access_denied_generic"), 403)

        pode_mutar, _ = usuario_pode_mutar_chamado(current_user, chamado)
        if not pode_mutar:
            return erro_json(_t("access_denied_generic"), 403)

        from app.services.permissoes_edicao_chamado import chamado_aceita_edicao_operacional

        _pode_op, _ = chamado_aceita_edicao_operacional(current_user, chamado)
        if not _pode_op:
            return erro_json(_t("ticket_completed_no_operation"), 403)

        if not (
            chamado.responsavel_id == current_user.id
            or current_user.is_admin_or_above
            or usuario_gestor_setor_pode_escalonar(current_user, chamado)
        ):
            return erro_json(_t("only_owner_or_admin_transfer"), 403)

        from app.services.escalonamento_service import transferir_area

        resultado = transferir_area(chamado_id, area, supervisor_id, motivo, current_user)
        if not resultado["sucesso"]:
            return jsonify(resultado), 400

        # Notifica destino em background — usa área destino (não a do doc original)
        dados_notif = {**dados_chamado, "area": area, "motivo_ultima_escalacao": motivo}
        _notificar_escalonamento(
            current_app._get_current_object(),
            chamado_id,
            dados_notif,
            "transferencia_area",
            supervisor_id,
        )

        if resultado["dados"].get("ainda_tem_acesso") is False:
            flash_t("acao_escalonamento_sucesso_sem_acesso", "success")

        return jsonify(resultado), 200

    except ValueError as exc:
        logger.debug("Validação transferir_area chamado=%s: %s", chamado_id, exc)
        return erro_json(_t("invalid_request_data"), 400)
    except Exception as exc:
        logger.exception("Erro em api_transferir_area chamado=%s: %s", chamado_id, exc)
        return erro_json(_t("internal_error_retry"), 500)


@main.route("/api/chamado/<chamado_id>/previsao-atendimento", methods=["POST"])
@login_required
@requer_supervisor_area
def api_solicitar_previsao_atendimento(chamado_id: str):
    """Solicita uma nova previsão de atendimento — botão único.

    Se a data enviada bate com a sugestão de extensão automática (ver
    calcular_sugestao_extensao_automatica — o modal já vem com essa data
    pré-preenchida) e o chamado ainda está elegível pro self-service, aplica
    na hora (resultado["tipo"] == "auto"). Qualquer outra data cria um
    pedido pendente que só passa a valer depois que o gestor do setor
    aprovar (resultado["tipo"] == "manual" — ver
    app/services/previsao_atendimento_service.py).

    Body JSON: {"previsao": "2026-07-15T16:00", "motivo": str}
    Acesso: owner (responsavel_id == current_user.id) ou admin, e supervisor+.
    """
    try:
        from datetime import datetime

        dados = request.get_json(silent=True)
        if not dados:
            return erro_json(_t("invalid_or_empty_json"), 400)

        previsao_raw = (dados.get("previsao") or "").strip()
        motivo = (dados.get("motivo") or "").strip()

        if not previsao_raw:
            return erro_json(_t("field_attendance_forecast_required"), 400)
        if not motivo:
            return erro_json(_t("error_reason_required"), 400)

        try:
            previsao = datetime.fromisoformat(previsao_raw)
        except ValueError:
            return erro_json(_t("invalid_request_data"), 400)

        chamado = Chamado.get_by_id(chamado_id)
        if not chamado:
            return erro_json(_t("ticket_not_found"), 404)

        if not usuario_pode_ver_chamado(current_user, chamado):
            return erro_json(_t("access_denied_generic"), 403)

        pode_mutar, _ = usuario_pode_mutar_chamado(current_user)
        if not pode_mutar:
            return erro_json(_t("access_denied_generic"), 403)

        from app.services.permissoes_edicao_chamado import chamado_aceita_edicao_operacional

        _pode_op, _ = chamado_aceita_edicao_operacional(current_user, chamado)
        if not _pode_op:
            return erro_json(_t("ticket_completed_no_operation"), 403)

        from app.services.previsao_atendimento_service import solicitar_previsao_atendimento

        resultado = solicitar_previsao_atendimento(chamado_id, previsao, motivo, current_user)
        if not resultado["sucesso"]:
            return jsonify(resultado), 400

        if resultado.get("tipo") == "auto":
            # Botão único: a data enviada bateu com a sugestão de extensão
            # automática — já aplicada na hora pelo service, sem pedido
            # pendente. Notifica como extensão automática, não como
            # solicitação aguardando decisão do gestor.
            from app.services.chamado_notificacao_service import (
                disparar_notificacao_extensao_automatica_em_thread,
            )

            disparar_notificacao_extensao_automatica_em_thread(
                current_app._get_current_object(),
                chamado_id=chamado_id,
                numero_chamado=chamado.numero_chamado or "N/A",
                categoria=chamado.categoria or "",
                previsao_nova=resultado["dados"]["previsao_nova"],
                extensoes_usadas=resultado["dados"]["extensoes_usadas"],
                extensoes_restantes=resultado["dados"]["extensoes_restantes"],
                solicitante_id=resultado["dados"].get("solicitante_id"),
                responsavel_id=current_user.id,
                chamado_area=chamado.area or "",
            )
        else:
            from app.services.chamado_notificacao_service import (
                disparar_notificacao_solicitacao_previsao_em_thread,
            )

            disparar_notificacao_solicitacao_previsao_em_thread(
                current_app._get_current_object(),
                chamado_id=chamado_id,
                numero_chamado=chamado.numero_chamado or "N/A",
                categoria=chamado.categoria or "",
                solicitante_nome=current_user.nome,
                previsao_solicitada=resultado["dados"]["previsao_solicitada"],
                motivo=motivo,
                solicitacao_id=resultado["dados"]["solicitacao_id"],
                gestor_id=resultado["dados"].get("gestor_id"),
            )

        return jsonify(resultado), 200

    except ValueError as exc:
        logger.debug("Validação previsao_atendimento chamado=%s: %s", chamado_id, exc)
        return erro_json(_t("invalid_request_data"), 400)
    except Exception as exc:
        logger.exception(
            "Erro em api_solicitar_previsao_atendimento chamado=%s: %s", chamado_id, exc
        )
        return erro_json(_t("internal_error_retry"), 500)


@main.route(
    "/api/chamado/<chamado_id>/previsao-atendimento/<int:solicitacao_id>/decidir",
    methods=["POST"],
)
@login_required
def api_decidir_previsao_atendimento(chamado_id: str, solicitacao_id: int):
    """Aprova/rejeita um pedido de previsão de atendimento pelo sistema
    (alternativa ao link de e-mail — ver app/routes/aprovacao_previsao.py).

    Body JSON: {"acao": "aprovar"|"rejeitar", "motivo_rejeicao"?: str}
    Acesso: gestor_setor da área do chamado, ou admin.
    """
    try:
        dados = request.get_json(silent=True) or {}
        acao = (dados.get("acao") or "").strip()
        if acao not in ("aprovar", "rejeitar"):
            return erro_json(_t("invalid_request_data"), 400)

        from app.services.previsao_atendimento_service import decidir_previsao_atendimento

        resultado = decidir_previsao_atendimento(
            solicitacao_id,
            acao,
            current_user,
            motivo_rejeicao=(dados.get("motivo_rejeicao") or "").strip() or None,
        )
        if not resultado["sucesso"]:
            return jsonify(resultado), resultado.get("codigo", 400)

        from app.services.chamado_notificacao_service import (
            disparar_notificacao_decisao_previsao_em_thread,
        )

        disparar_notificacao_decisao_previsao_em_thread(
            current_app._get_current_object(), resultado["dados"], current_user.nome
        )

        return jsonify(resultado), 200

    except ValueError as exc:
        logger.debug(
            "Validação decidir_previsao_atendimento solicitacao=%s: %s", solicitacao_id, exc
        )
        return erro_json(_t("invalid_request_data"), 400)
    except Exception as exc:
        logger.exception(
            "Erro em api_decidir_previsao_atendimento solicitacao=%s: %s", solicitacao_id, exc
        )
        return erro_json(_t("internal_error_retry"), 500)


@main.route("/api/chamado/<chamado_id>/escalonar-colega", methods=["POST"])
@login_required
@requer_supervisor_area_ou_gestor_setor
def api_escalonar_colega(chamado_id: str):
    """Escala o chamado para um colega da mesma área sem alterar a área.

    Body JSON: {"supervisor_id": str, "motivo": str}
    Acesso: owner (responsavel_id == current_user.id), admin, ou gestor_setor
    da área do chamado (Ações de Escalonamento — decisão de escopo 2026-08-20).
    """
    try:
        dados = request.get_json(silent=True)
        if not dados:
            return erro_json(_t("invalid_or_empty_json"), 400)

        supervisor_id = (dados.get("supervisor_id") or "").strip()
        motivo = (dados.get("motivo") or "").strip()

        if not supervisor_id:
            return erro_json(_t("field_supervisor_id_required"), 400)
        if not motivo:
            return erro_json(_t("error_reason_required"), 400)

        chamado = Chamado.get_by_id(chamado_id)
        if not chamado:
            return erro_json(_t("ticket_not_found"), 404)

        dados_chamado = chamado.to_dict()

        if not usuario_pode_ver_chamado(current_user, chamado):
            return erro_json(_t("access_denied_generic"), 403)

        pode_mutar, _ = usuario_pode_mutar_chamado(current_user, chamado)
        if not pode_mutar:
            return erro_json(_t("access_denied_generic"), 403)

        from app.services.permissoes_edicao_chamado import chamado_aceita_edicao_operacional

        _pode_op, _ = chamado_aceita_edicao_operacional(current_user, chamado)
        if not _pode_op:
            return erro_json(_t("ticket_completed_no_operation"), 403)

        if not (
            chamado.responsavel_id == current_user.id
            or current_user.is_admin_or_above
            or usuario_gestor_setor_pode_escalonar(current_user, chamado)
        ):
            return erro_json(_t("only_owner_or_admin_escalate"), 403)

        from app.services.escalonamento_service import escalonar_colega

        resultado = escalonar_colega(chamado_id, supervisor_id, motivo, current_user)
        if not resultado["sucesso"]:
            return jsonify(resultado), 400

        # Notifica destino em background
        dados_notif = {**dados_chamado, "motivo_ultima_escalacao": motivo}
        _notificar_escalonamento(
            current_app._get_current_object(),
            chamado_id,
            dados_notif,
            "escalonamento_colega",
            supervisor_id,
        )

        if resultado["dados"].get("ainda_tem_acesso") is False:
            flash_t("acao_escalonamento_sucesso_sem_acesso", "success")

        return jsonify(resultado), 200

    except ValueError as exc:
        logger.debug("Validação escalonar_colega chamado=%s: %s", chamado_id, exc)
        return erro_json(_t("invalid_request_data"), 400)
    except Exception as exc:
        logger.exception("Erro em api_escalonar_colega chamado=%s: %s", chamado_id, exc)
        return erro_json(_t("internal_error_retry"), 500)


# ---------------------------------------------------------------------------
# Participantes — Fase 4
# ---------------------------------------------------------------------------


def _notificar_participante_incluido(
    app, chamado_id: str, dados_chamado: dict, adicionados: list
) -> None:
    """Dispara notificações triplas (e-mail + in-app + Web Push) de inclusão de participante."""

    def _run():
        with app.app_context():
            try:
                from app.services.notifications import notificar_participante_incluido
                from app.services.notifications_inapp import criar_notificacao
                from app.services.webpush_service import enviar_webpush_usuario

                numero = dados_chamado.get("numero_chamado") or "N/A"
                categoria = dados_chamado.get("categoria") or ""
                base_url = current_app.config.get("APP_BASE_URL", "").rstrip("/")
                url_chamado = f"{base_url}/chamado/{chamado_id}" if base_url else None

                for item in adicionados:
                    sup_id = item.get("supervisor_id")
                    destino = Usuario.get_by_id(sup_id)
                    if not destino:
                        continue

                    notificar_participante_incluido(
                        chamado_id=chamado_id,
                        numero_chamado=numero,
                        categoria=categoria,
                        area=item.get("area") or "",
                        responsavel_usuario=destino,
                    )

                    criar_notificacao(
                        usuario_id=sup_id,
                        chamado_id=chamado_id,
                        numero_chamado=numero,
                        titulo=get_translation(
                            "notification_participant_included_title", "en", numero=numero
                        ),
                        mensagem=get_translation(
                            "notification_participant_included_message",
                            "en",
                            numero=numero,
                            categoria=categoria,
                        ),
                        tipo="participante_incluido",
                        categoria=categoria,
                    )

                    enviar_webpush_usuario(
                        sup_id,
                        titulo=get_translation(
                            "push_participant_included_title", "en", numero=numero
                        ),
                        corpo=get_translation("push_participant_included_body", "en"),
                        url=url_chamado,
                    )
            except Exception as exc:
                logger.warning("Notificação de participante incluído não enviada: %s", exc)

    threading.Thread(target=_run, daemon=True).start()


def _notificar_owner_todos_concluiram(
    app, chamado_id: str, dados_chamado: dict, owner_id: str
) -> None:
    """Notifica o owner que todos os participantes concluíram."""

    def _run():
        with app.app_context():
            try:
                from app.services.notifications import (
                    notificar_owner_todos_participantes_concluiram,
                )
                from app.services.notifications_inapp import criar_notificacao
                from app.services.webpush_service import enviar_webpush_usuario

                owner = Usuario.get_by_id(owner_id)
                numero = dados_chamado.get("numero_chamado") or "N/A"
                categoria = dados_chamado.get("categoria") or ""

                notificar_owner_todos_participantes_concluiram(
                    chamado_id=chamado_id,
                    numero_chamado=numero,
                    categoria=categoria,
                    owner_usuario=owner,
                )

                criar_notificacao(
                    usuario_id=owner_id,
                    chamado_id=chamado_id,
                    numero_chamado=numero,
                    titulo=get_translation(
                        "notification_all_participants_done_title", "en", numero=numero
                    ),
                    mensagem=get_translation(
                        "notification_all_participants_done_message",
                        "en",
                        numero=numero,
                        categoria=categoria,
                    ),
                    tipo="todos_participantes_concluidos",
                    categoria=categoria,
                )

                base_url = current_app.config.get("APP_BASE_URL", "").rstrip("/")
                url = f"{base_url}/chamado/{chamado_id}/historico" if base_url else None
                enviar_webpush_usuario(
                    owner_id,
                    titulo=get_translation("push_all_participants_done_title", "en", numero=numero),
                    corpo=get_translation("push_all_participants_done_body", "en"),
                    url=url,
                )
            except Exception as exc:
                logger.warning("Notificação owner todos concluíram não enviada: %s", exc)

    threading.Thread(target=_run, daemon=True).start()


@main.route("/api/chamado/<chamado_id>/incluir-participantes", methods=["POST"])
@login_required
@requer_supervisor_area_ou_gestor_setor
def api_incluir_participantes(chamado_id: str):
    """Adiciona supervisores colaboradores em participantes[].

    Body JSON: {"participantes": [{"supervisor_id": str, "area": str}, ...]}
    Acesso: owner (responsavel_id == current_user.id), admin, ou gestor_setor
    da área do chamado (Ações de Escalonamento — decisão de escopo 2026-08-20).
    """
    try:
        dados = request.get_json(silent=True)
        if not dados:
            return erro_json(_t("invalid_or_empty_json"), 400)

        participantes_novos = dados.get("participantes")
        if not isinstance(participantes_novos, list) or not participantes_novos:
            return erro_json(_t("participants_must_be_nonempty_list"), 400)

        chamado = Chamado.get_by_id(chamado_id)
        if not chamado:
            return erro_json(_t("ticket_not_found"), 404)

        dados_chamado = chamado.to_dict()

        if not usuario_pode_ver_chamado(current_user, chamado):
            return erro_json(_t("access_denied_generic"), 403)

        pode_mutar, _ = usuario_pode_mutar_chamado(current_user, chamado)
        if not pode_mutar:
            return erro_json(_t("access_denied_generic"), 403)

        from app.services.permissoes_edicao_chamado import chamado_aceita_edicao_operacional

        _pode_op, _ = chamado_aceita_edicao_operacional(current_user, chamado)
        if not _pode_op:
            return erro_json(_t("access_denied_generic"), 403)

        if not (
            chamado.responsavel_id == current_user.id
            or current_user.is_admin_or_above
            or usuario_gestor_setor_pode_escalonar(current_user, chamado)
        ):
            return erro_json(_t("only_owner_or_admin_participants"), 403)

        from app.services.escalonamento_service import incluir_participantes

        resultado = incluir_participantes(chamado_id, participantes_novos, current_user)
        if not resultado["sucesso"]:
            return jsonify(resultado), 400

        adicionados = resultado.get("dados", {}).get("adicionados", [])
        if adicionados:
            _notificar_participante_incluido(
                current_app._get_current_object(),
                chamado_id,
                dados_chamado,
                adicionados,
            )

        if resultado["dados"].get("ainda_tem_acesso") is False:
            flash_t("acao_escalonamento_sucesso_sem_acesso", "success")

        return jsonify(resultado), 200

    except ValueError as exc:
        logger.debug("Validação incluir_participantes chamado=%s: %s", chamado_id, exc)
        return erro_json(_t("invalid_request_data"), 400)
    except Exception as exc:
        logger.exception("Erro em api_incluir_participantes chamado=%s: %s", chamado_id, exc)
        return erro_json(_t("internal_error_retry"), 500)


@main.route("/api/chamado/<chamado_id>/concluir-minha-parte", methods=["POST"])
@login_required
def api_concluir_minha_parte(chamado_id: str):
    """Participante marca sua parte como concluída.

    Body JSON: {} (pode ser omitido)
    Acesso: qualquer usuário logado que seja participante do chamado.
    """
    # Gestor read-only: bloqueado mesmo que seja participante (edge case fail-closed)
    pode_mutar, _ = usuario_pode_mutar_chamado(current_user)
    if not pode_mutar:
        return erro_json(_t("access_denied_generic"), 403)
    try:
        chamado = Chamado.get_by_id(chamado_id)
        if not chamado:
            return erro_json(_t("ticket_not_found"), 404)

        dados_chamado = chamado.to_dict()

        if chamado.status == "Concluído":
            return erro_json(_t("ticket_already_completed"), 400)

        participantes = chamado.participantes or []
        ids_participantes = {p.get("supervisor_id") for p in participantes}
        if current_user.id not in ids_participantes:
            return erro_json(_t("user_not_participant"), 403)

        from app.services.escalonamento_service import concluir_minha_parte

        resultado = concluir_minha_parte(chamado_id, current_user)
        if not resultado["sucesso"]:
            return jsonify(resultado), 400

        if resultado.get("dados", {}).get("pode_concluir_global"):
            owner_id = chamado.responsavel_id
            if owner_id:
                _notificar_owner_todos_concluiram(
                    current_app._get_current_object(),
                    chamado_id,
                    dados_chamado,
                    owner_id,
                )

        return jsonify(resultado), 200

    except Exception as exc:
        logger.exception("Erro em api_concluir_minha_parte chamado=%s: %s", chamado_id, exc)
        return erro_json(_t("internal_error_retry"), 500)
