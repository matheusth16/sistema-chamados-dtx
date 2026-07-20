"""Rotas de notificações in-app, Web Push e service worker."""

import logging
import os

from flask import current_app, jsonify, request, send_from_directory, session
from flask_login import current_user, login_required

from app.i18n import get_translation
from app.limiter import limiter
from app.routes import main
from app.services.notifications_inapp import (
    contar_nao_lidas,
    listar_para_usuario,
    marcar_como_lida,
    marcar_todas_como_lidas,
)
from app.services.webpush_service import salvar_inscricao

logger = logging.getLogger(__name__)


def _t(key, **kwargs):
    """Traduz uma chave i18n para o idioma da sessão atual."""
    return get_translation(key, session.get("language", "en"), **kwargs)


@main.route("/api/notificacoes", methods=["GET"])
@login_required
def api_notificacoes_listar():
    """Lista notificações do usuário (sino), traduzidas para o idioma da sessão."""
    try:
        apenas_nao_lidas = request.args.get("nao_lidas") == "1"
        lang = session.get("language", "en")
        lista = listar_para_usuario(
            current_user.id, limite=30, apenas_nao_lidas=apenas_nao_lidas, language=lang
        )
        total_nao_lidas = contar_nao_lidas(current_user.id)
        lista_degradada = total_nao_lidas > 0 and len(lista) == 0
        return jsonify(
            {
                "sucesso": True,
                "notificacoes": lista,
                "total_nao_lidas": total_nao_lidas,
                "lista_degradada": lista_degradada,
            }
        ), 200
    except Exception as e:
        logger.exception("Erro ao listar notificações: %s", e)
        return jsonify(
            {
                "sucesso": False,
                "erro": _t("internal_error_retry"),
                "notificacoes": [],
                "total_nao_lidas": 0,
            }
        ), 500


@main.route("/api/notificacoes/contar", methods=["GET"])
@login_required
def api_notificacoes_contar():
    """Retorna apenas o total de notificações não lidas (sem transferir os documentos)."""
    try:
        total = contar_nao_lidas(current_user.id)
        return jsonify({"total_nao_lidas": total}), 200
    except Exception as e:
        logger.exception("Erro ao contar notificações: %s", e)
        return jsonify({"total_nao_lidas": 0}), 200


@main.route("/api/notificacoes/<notificacao_id>/ler", methods=["POST"])
@login_required
def api_notificacoes_marcar_lida(notificacao_id):
    """Marca notificação como lida."""
    try:
        ok = marcar_como_lida(notificacao_id, current_user.id)
        return jsonify({"sucesso": ok}), 200
    except Exception as e:
        logger.exception("Erro ao marcar notificação: %s", e)
        return jsonify({"sucesso": False, "erro": _t("internal_error_retry")}), 500


@main.route("/api/notificacoes/ler-todas", methods=["POST"])
@login_required
def api_notificacoes_ler_todas():
    """Marca todas as notificações do usuário como lidas."""
    try:
        count = marcar_todas_como_lidas(current_user.id)
        return jsonify({"sucesso": True, "atualizadas": count}), 200
    except Exception as e:
        logger.exception("Erro ao marcar todas notificações: %s", e)
        return jsonify({"sucesso": False, "erro": _t("internal_error_retry")}), 500


@main.route("/sw.js")
def service_worker_js():
    """Serve o service worker na raiz (scope do app)."""
    return send_from_directory(
        os.path.join(current_app.root_path, "static"), "sw.js", mimetype="application/javascript"
    )


@main.route("/api/push-vapid-public")
@login_required
def api_push_vapid_public():
    """Retorna chave pública VAPID para Web Push."""
    key = current_app.config.get("VAPID_PUBLIC_KEY") or ""
    return jsonify({"vapid_public_key": key}), 200


@main.route("/api/push-subscribe", methods=["POST"])
@login_required
@limiter.limit("5 per minute", methods=["POST"])
def api_push_subscribe():
    """Salva inscrição Web Push do navegador."""
    try:
        data = request.get_json() or {}
        subscription = data.get("subscription")
        if not subscription or not subscription.get("endpoint"):
            return jsonify({"sucesso": False, "erro": _t("invalid_subscription")}), 400
        ok = salvar_inscricao(current_user.id, subscription)
        return jsonify({"sucesso": ok}), 200
    except Exception as e:
        logger.exception("Erro ao salvar inscrição push: %s", e)
        return jsonify({"sucesso": False, "erro": _t("internal_error_retry")}), 500
