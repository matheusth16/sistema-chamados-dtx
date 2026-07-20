"""Rotas de colaboração no chamado: transferência de área, escalonamento, previsão de atendimento, participantes."""

import logging
import threading

from flask import current_app, jsonify, request, session
from flask_login import current_user, login_required

from app.database import db
from app.decoradores import requer_supervisor_area
from app.i18n import get_translation
from app.models import Chamado
from app.models_usuario import Usuario
from app.routes import main
from app.services.permission_validation import usuario_pode_mutar_chamado
from app.services.permissions import usuario_pode_ver_chamado

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
@requer_supervisor_area
def api_transferir_area(chamado_id: str):
    """Transfere o chamado para outra área com novo responsável obrigatório.

    Body JSON: {"area": str, "supervisor_id": str, "motivo": str}
    Acesso: owner (responsavel_id == current_user.id) ou admin.
    """
    try:
        dados = request.get_json(silent=True)
        if not dados:
            return jsonify({"sucesso": False, "erro": _t("invalid_or_empty_json")}), 400

        area = (dados.get("area") or "").strip()
        supervisor_id = (dados.get("supervisor_id") or "").strip()
        motivo = (dados.get("motivo") or "").strip()

        if not area:
            return jsonify({"sucesso": False, "erro": _t("field_target_area_required")}), 400
        if not supervisor_id:
            return jsonify({"sucesso": False, "erro": _t("field_supervisor_id_required")}), 400
        if not motivo:
            return jsonify({"sucesso": False, "erro": _t("error_reason_required")}), 400

        doc = db.collection("chamados").document(chamado_id).get()
        if not doc.exists:
            return jsonify({"sucesso": False, "erro": _t("ticket_not_found")}), 404

        dados_chamado = doc.to_dict() or {}
        chamado = Chamado.from_dict(dados_chamado, chamado_id)

        if not usuario_pode_ver_chamado(current_user, chamado):
            return jsonify({"sucesso": False, "erro": _t("access_denied_generic")}), 403

        pode_mutar, _ = usuario_pode_mutar_chamado(current_user)
        if not pode_mutar:
            return jsonify({"sucesso": False, "erro": _t("access_denied_generic")}), 403

        from app.services.permission_validation import chamado_aceita_edicao_operacional

        _pode_op, _ = chamado_aceita_edicao_operacional(current_user, chamado)
        if not _pode_op:
            return jsonify({"sucesso": False, "erro": _t("ticket_completed_no_operation")}), 403

        if not (chamado.responsavel_id == current_user.id or current_user.is_admin_or_above):
            return jsonify({"sucesso": False, "erro": _t("only_owner_or_admin_transfer")}), 403

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

        return jsonify(resultado), 200

    except ValueError as exc:
        logger.debug("Validação transferir_area chamado=%s: %s", chamado_id, exc)
        return jsonify({"sucesso": False, "erro": _t("invalid_request_data")}), 400
    except Exception as exc:
        logger.exception("Erro em api_transferir_area chamado=%s: %s", chamado_id, exc)
        return jsonify({"sucesso": False, "erro": _t("internal_error_retry")}), 500


@main.route("/api/chamado/<chamado_id>/previsao-atendimento", methods=["POST"])
@login_required
@requer_supervisor_area
def api_definir_previsao_atendimento(chamado_id: str):
    """Define até quando o chamado fica sem escalar e-mail pros gestores (Escada A/B).

    Body JSON: {"previsao": "2026-07-15T16:00", "motivo": str}
    Acesso: owner (responsavel_id == current_user.id) ou admin, e supervisor+.
    """
    try:
        from datetime import datetime

        dados = request.get_json(silent=True)
        if not dados:
            return jsonify({"sucesso": False, "erro": _t("invalid_or_empty_json")}), 400

        previsao_raw = (dados.get("previsao") or "").strip()
        motivo = (dados.get("motivo") or "").strip()

        if not previsao_raw:
            return jsonify(
                {"sucesso": False, "erro": _t("field_attendance_forecast_required")}
            ), 400
        if not motivo:
            return jsonify({"sucesso": False, "erro": _t("error_reason_required")}), 400

        try:
            previsao = datetime.fromisoformat(previsao_raw)
        except ValueError:
            return jsonify({"sucesso": False, "erro": _t("invalid_request_data")}), 400

        doc = db.collection("chamados").document(chamado_id).get()
        if not doc.exists:
            return jsonify({"sucesso": False, "erro": _t("ticket_not_found")}), 404

        dados_chamado = doc.to_dict() or {}
        chamado = Chamado.from_dict(dados_chamado, chamado_id)

        if not usuario_pode_ver_chamado(current_user, chamado):
            return jsonify({"sucesso": False, "erro": _t("access_denied_generic")}), 403

        pode_mutar, _ = usuario_pode_mutar_chamado(current_user)
        if not pode_mutar:
            return jsonify({"sucesso": False, "erro": _t("access_denied_generic")}), 403

        from app.services.permission_validation import chamado_aceita_edicao_operacional

        _pode_op, _ = chamado_aceita_edicao_operacional(current_user, chamado)
        if not _pode_op:
            return jsonify({"sucesso": False, "erro": _t("ticket_completed_no_operation")}), 403

        eh_supervisor_ou_acima = current_user.perfil in ("supervisor", "admin", "admin_global")
        eh_owner_ou_admin = (
            chamado.responsavel_id == current_user.id or current_user.is_admin_or_above
        )
        if not (eh_supervisor_ou_acima and eh_owner_ou_admin):
            return jsonify(
                {"sucesso": False, "erro": _t("no_permission_set_attendance_forecast")}
            ), 403

        from app.services.escalonamento_service import definir_previsao_atendimento

        resultado = definir_previsao_atendimento(chamado_id, previsao, motivo, current_user)
        if not resultado["sucesso"]:
            return jsonify(resultado), 400

        return jsonify(resultado), 200

    except ValueError as exc:
        logger.debug("Validação previsao_atendimento chamado=%s: %s", chamado_id, exc)
        return jsonify({"sucesso": False, "erro": _t("invalid_request_data")}), 400
    except Exception as exc:
        logger.exception("Erro em api_definir_previsao_atendimento chamado=%s: %s", chamado_id, exc)
        return jsonify({"sucesso": False, "erro": _t("internal_error_retry")}), 500


@main.route("/api/chamado/<chamado_id>/escalonar-colega", methods=["POST"])
@login_required
@requer_supervisor_area
def api_escalonar_colega(chamado_id: str):
    """Escala o chamado para um colega da mesma área sem alterar a área.

    Body JSON: {"supervisor_id": str, "motivo": str}
    Acesso: owner (responsavel_id == current_user.id) ou admin.
    """
    try:
        dados = request.get_json(silent=True)
        if not dados:
            return jsonify({"sucesso": False, "erro": _t("invalid_or_empty_json")}), 400

        supervisor_id = (dados.get("supervisor_id") or "").strip()
        motivo = (dados.get("motivo") or "").strip()

        if not supervisor_id:
            return jsonify({"sucesso": False, "erro": _t("field_supervisor_id_required")}), 400
        if not motivo:
            return jsonify({"sucesso": False, "erro": _t("error_reason_required")}), 400

        doc = db.collection("chamados").document(chamado_id).get()
        if not doc.exists:
            return jsonify({"sucesso": False, "erro": _t("ticket_not_found")}), 404

        dados_chamado = doc.to_dict() or {}
        chamado = Chamado.from_dict(dados_chamado, chamado_id)

        if not usuario_pode_ver_chamado(current_user, chamado):
            return jsonify({"sucesso": False, "erro": _t("access_denied_generic")}), 403

        pode_mutar, _ = usuario_pode_mutar_chamado(current_user)
        if not pode_mutar:
            return jsonify({"sucesso": False, "erro": _t("access_denied_generic")}), 403

        from app.services.permission_validation import chamado_aceita_edicao_operacional

        _pode_op, _ = chamado_aceita_edicao_operacional(current_user, chamado)
        if not _pode_op:
            return jsonify({"sucesso": False, "erro": _t("ticket_completed_no_operation")}), 403

        if not (chamado.responsavel_id == current_user.id or current_user.is_admin_or_above):
            return jsonify({"sucesso": False, "erro": _t("only_owner_or_admin_escalate")}), 403

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

        return jsonify(resultado), 200

    except ValueError as exc:
        logger.debug("Validação escalonar_colega chamado=%s: %s", chamado_id, exc)
        return jsonify({"sucesso": False, "erro": _t("invalid_request_data")}), 400
    except Exception as exc:
        logger.exception("Erro em api_escalonar_colega chamado=%s: %s", chamado_id, exc)
        return jsonify({"sucesso": False, "erro": _t("internal_error_retry")}), 500


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
@requer_supervisor_area
def api_incluir_participantes(chamado_id: str):
    """Adiciona supervisores colaboradores em participantes[].

    Body JSON: {"participantes": [{"supervisor_id": str, "area": str}, ...]}
    Acesso: owner (responsavel_id == current_user.id) ou admin.
    """
    try:
        dados = request.get_json(silent=True)
        if not dados:
            return jsonify({"sucesso": False, "erro": _t("invalid_or_empty_json")}), 400

        participantes_novos = dados.get("participantes")
        if not isinstance(participantes_novos, list) or not participantes_novos:
            return jsonify(
                {"sucesso": False, "erro": _t("participants_must_be_nonempty_list")}
            ), 400

        doc = db.collection("chamados").document(chamado_id).get()
        if not doc.exists:
            return jsonify({"sucesso": False, "erro": _t("ticket_not_found")}), 404

        dados_chamado = doc.to_dict() or {}
        chamado = Chamado.from_dict(dados_chamado, chamado_id)

        if not usuario_pode_ver_chamado(current_user, chamado):
            return jsonify({"sucesso": False, "erro": _t("access_denied_generic")}), 403

        pode_mutar, _ = usuario_pode_mutar_chamado(current_user)
        if not pode_mutar:
            return jsonify({"sucesso": False, "erro": _t("access_denied_generic")}), 403

        from app.services.permission_validation import chamado_aceita_edicao_operacional

        _pode_op, _ = chamado_aceita_edicao_operacional(current_user, chamado)
        if not _pode_op:
            return jsonify({"sucesso": False, "erro": _t("access_denied_generic")}), 403

        if not (chamado.responsavel_id == current_user.id or current_user.is_admin_or_above):
            return jsonify(
                {
                    "sucesso": False,
                    "erro": _t("only_owner_or_admin_participants"),
                }
            ), 403

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

        return jsonify(resultado), 200

    except ValueError as exc:
        logger.debug("Validação incluir_participantes chamado=%s: %s", chamado_id, exc)
        return jsonify({"sucesso": False, "erro": _t("invalid_request_data")}), 400
    except Exception as exc:
        logger.exception("Erro em api_incluir_participantes chamado=%s: %s", chamado_id, exc)
        return jsonify({"sucesso": False, "erro": _t("internal_error_retry")}), 500


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
        return jsonify({"sucesso": False, "erro": _t("access_denied_generic")}), 403
    try:
        doc = db.collection("chamados").document(chamado_id).get()
        if not doc.exists:
            return jsonify({"sucesso": False, "erro": _t("ticket_not_found")}), 404

        dados_chamado = doc.to_dict() or {}
        chamado = Chamado.from_dict(dados_chamado, chamado_id)

        if chamado.status == "Concluído":
            return jsonify({"sucesso": False, "erro": _t("ticket_already_completed")}), 400

        participantes = chamado.participantes or []
        ids_participantes = {p.get("supervisor_id") for p in participantes}
        if current_user.id not in ids_participantes:
            return jsonify({"sucesso": False, "erro": _t("user_not_participant")}), 403

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
        return jsonify({"sucesso": False, "erro": _t("internal_error_retry")}), 500
