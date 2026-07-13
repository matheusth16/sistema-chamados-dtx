"""
Cancelamento de chamado iniciado pelo próprio solicitante.
  - Só o dono (solicitante_id) pode cancelar
  - Motivo obrigatório (mín 10 chars)
  - Statuses canceláveis: Aberto, Em Atendimento, Aguardando Informação
"""

import logging

from firebase_admin import firestore

from app.database import db
from app.i18n import get_translation_session
from app.models_historico import Historico

logger = logging.getLogger(__name__)

_STATUS_CANCELAVEIS = {"Aberto", "Em Atendimento", "Aguardando Informação"}
_MOTIVO_MIN_CHARS = 10


def _t(key, **kwargs):
    return get_translation_session(key, **kwargs)


def cancelar_chamado_solicitante(chamado_id: str, motivo: str, usuario) -> dict:
    """Cancela um chamado a pedido do solicitante dono."""
    doc = db.collection("chamados").document(chamado_id).get()
    if not doc.exists:
        return {"sucesso": False, "erro": _t("ticket_not_found_dot"), "codigo": 404}

    data = doc.to_dict()
    solicitante_id = data.get("solicitante_id")
    status_atual = data.get("status", "")

    if solicitante_id != usuario.id:
        return {
            "sucesso": False,
            "erro": _t("no_permission_cancel_ticket"),
            "codigo": 403,
        }

    motivo = (motivo or "").strip()
    if len(motivo) < _MOTIVO_MIN_CHARS:
        return {
            "sucesso": False,
            "erro": _t("reason_required_min_chars", min_chars=_MOTIVO_MIN_CHARS),
            "codigo": 400,
        }

    if status_atual not in _STATUS_CANCELAVEIS:
        return {
            "sucesso": False,
            "erro": _t("cannot_cancel_status", status=status_atual),
            "codigo": 403,
        }

    try:
        db.collection("chamados").document(chamado_id).update(
            {
                "status": "Cancelado",
                "motivo_cancelamento": motivo,
                "data_cancelamento": firestore.SERVER_TIMESTAMP,
            }
        )

        Historico(
            chamado_id=chamado_id,
            usuario_id=usuario.id,
            usuario_nome=usuario.nome,
            acao="alteracao_status",
            campo_alterado="status",
            valor_anterior=status_atual,
            valor_novo="Cancelado",
            detalhe=motivo,
        ).save()

        _notificar_cancelamento(chamado_id=chamado_id, dados=data, motivo=motivo, usuario=usuario)

        return {"sucesso": True}

    except Exception as exc:
        logger.exception("Erro ao cancelar chamado %s: %s", chamado_id, exc)
        return {"sucesso": False, "erro": _t("internal_error_canceling_ticket"), "codigo": 500}


def _notificar_cancelamento(chamado_id: str, dados: dict, motivo: str, usuario) -> None:
    """Dispara notificações assíncronas de cancelamento (responsável + observadores)."""
    import threading

    from flask import current_app

    app = current_app._get_current_object()  # noqa: SLF001
    # Captura o nome ANTES de entrar na thread: usuario é o current_user do
    # Flask-Login, um proxy ligado ao request context. A thread abaixo só
    # empurra app_context (sem request context), então usuario.nome resolve
    # para None ali dentro e explode silenciosamente (notificação nunca sai).
    solicitante_nome = usuario.nome

    def _run():
        with app.app_context():
            try:
                from app.services.chamado_notificacao_service import (
                    notificar_cancelamento_chamado,
                )

                notificar_cancelamento_chamado(
                    chamado_id=chamado_id,
                    numero_chamado=dados.get("numero_chamado") or "N/A",
                    categoria=dados.get("categoria") or "Chamado",
                    motivo=motivo,
                    solicitante_nome=solicitante_nome,
                    dados_chamado=dados,
                )
            except Exception as exc:
                logger.warning("Notificação de cancelamento não enviada: %s", exc)

    threading.Thread(target=_run, daemon=True).start()
