"""
Edições que o solicitante pode fazer após a criação do chamado:
  - editar_descricao_solicitante: janela de 30 min, só status Aberto
  - adicionar_anexo_tardio: qualquer status não-terminal, requer motivo
"""

import logging
from datetime import datetime, timedelta

import pytz

from app.database import db
from app.i18n import get_translation_session
from app.models_historico import Historico

logger = logging.getLogger(__name__)

JANELA_EDICAO_TEXTO_MIN = 30
_BRASILIA = pytz.timezone("America/Sao_Paulo")
_STATUS_PERMITIDOS_ANEXO = {"Aberto", "Em Atendimento", "Aguardando Informação"}
_STATUS_PERMITIDOS_EDICAO = {"Aberto"}
_MOTIVO_MIN_CHARS = 10


def _t(key, **kwargs):
    return get_translation_session(key, **kwargs)


def _get_chamado_doc(chamado_id: str):
    return db.collection("chamados").document(chamado_id).get()


def _agora_brasilia() -> datetime:
    return datetime.now(_BRASILIA)


def _dentro_da_janela(data_abertura) -> bool:
    agora = _agora_brasilia()
    if isinstance(data_abertura, datetime):
        if data_abertura.tzinfo is None:
            data_abertura = _BRASILIA.localize(data_abertura)
        else:
            data_abertura = data_abertura.astimezone(_BRASILIA)
    else:
        return False
    return agora - data_abertura <= timedelta(minutes=JANELA_EDICAO_TEXTO_MIN)


def segundos_restantes_janela_edicao(data_abertura) -> int:
    """Segundos restantes na janela de edição de texto (0 se expirada ou data inválida)."""
    if not isinstance(data_abertura, datetime):
        return 0
    agora = _agora_brasilia()
    ab = data_abertura if data_abertura.tzinfo else _BRASILIA.localize(data_abertura)
    ab = ab.astimezone(_BRASILIA)
    restante = timedelta(minutes=JANELA_EDICAO_TEXTO_MIN) - (agora - ab)
    return max(0, int(restante.total_seconds()))


def editar_descricao_solicitante(
    chamado_id: str,
    novo_texto: str,
    usuario,
) -> dict:
    """
    Edita a descrição de um chamado dentro da janela de 30 min.
    Só o solicitante dono pode editar; só quando status = Aberto.
    """
    doc = _get_chamado_doc(chamado_id)
    if not doc.exists:
        return {"sucesso": False, "erro": _t("ticket_not_found_dot"), "codigo": 404}

    data = doc.to_dict()
    solicitante_id = data.get("solicitante_id")
    status = data.get("status", "")
    descricao_atual = data.get("descricao", "")
    data_abertura = data.get("data_abertura")

    if solicitante_id != usuario.id:
        return {"sucesso": False, "erro": _t("no_permission_edit_ticket"), "codigo": 403}

    if status not in _STATUS_PERMITIDOS_EDICAO:
        return {
            "sucesso": False,
            "erro": _t("cannot_edit_description_status", status=status),
            "codigo": 403,
        }

    if not _dentro_da_janela(data_abertura):
        return {
            "sucesso": False,
            "erro": _t("edit_window_closed", minutos=JANELA_EDICAO_TEXTO_MIN),
            "codigo": 403,
        }

    try:
        db.collection("chamados").document(chamado_id).update({"descricao": novo_texto})

        Historico(
            chamado_id=chamado_id,
            usuario_id=usuario.id,
            usuario_nome=usuario.nome,
            acao="edicao_descricao",
            campo_alterado="descricao",
            valor_anterior=descricao_atual,
            valor_novo=novo_texto,
        ).save()

        _notificar_edicao_descricao(
            chamado_id=chamado_id,
            dados=data,
            usuario=usuario,
            valor_anterior=descricao_atual,
            valor_novo=novo_texto,
        )

        return {"sucesso": True}

    except Exception as exc:
        logger.exception("Erro ao editar descrição do chamado %s: %s", chamado_id, exc)
        return {"sucesso": False, "erro": _t("internal_error_saving_edit"), "codigo": 500}


def _notificar_edicao_descricao(
    chamado_id: str, dados: dict, usuario, valor_anterior: str, valor_novo: str
) -> None:
    """Dispara notificação de edição de descrição em thread background."""
    import threading

    from flask import current_app

    app = current_app._get_current_object()  # noqa: SLF001

    def _run():
        with app.app_context():
            try:
                from app.services.chamado_notificacao_service import (
                    notificar_edicao_descricao_solicitante,
                )

                notificar_edicao_descricao_solicitante(
                    chamado_id=chamado_id,
                    numero_chamado=dados.get("numero_chamado") or "N/A",
                    categoria=dados.get("categoria") or "Chamado",
                    solicitante_nome=usuario.nome,
                    valor_anterior=valor_anterior,
                    valor_novo=valor_novo,
                    dados_chamado=dados,
                )
            except Exception as exc:
                logger.warning("Notificação de edição de descrição não enviada: %s", exc)

    threading.Thread(target=_run, daemon=True).start()


def adicionar_anexo_tardio(
    chamado_id: str,
    caminho_anexo: str,
    motivo: str,
    usuario,
) -> dict:
    """
    Adiciona um anexo a um chamado já criado.
    Requer motivo (mín. 10 chars) e status não-terminal.
    """
    doc = _get_chamado_doc(chamado_id)
    if not doc.exists:
        return {"sucesso": False, "erro": _t("ticket_not_found_dot"), "codigo": 404}

    data = doc.to_dict()
    solicitante_id = data.get("solicitante_id")
    status = data.get("status", "")

    if solicitante_id != usuario.id:
        return {"sucesso": False, "erro": _t("no_permission_add_attachment"), "codigo": 403}

    motivo = (motivo or "").strip()
    if len(motivo) < _MOTIVO_MIN_CHARS:
        return {
            "sucesso": False,
            "erro": _t("reason_required_min_chars", min_chars=_MOTIVO_MIN_CHARS),
            "codigo": 400,
        }

    if status not in _STATUS_PERMITIDOS_ANEXO:
        return {
            "sucesso": False,
            "erro": _t("cannot_add_attachment_status", status=status),
            "codigo": 403,
        }

    try:
        from google.cloud.firestore_v1 import ArrayUnion

        db.collection("chamados").document(chamado_id).update(
            {"anexos": ArrayUnion([caminho_anexo])}
        )

        Historico(
            chamado_id=chamado_id,
            usuario_id=usuario.id,
            usuario_nome=usuario.nome,
            acao="anexo_tardio",
            campo_alterado="anexos",
            valor_anterior=None,
            valor_novo=caminho_anexo,
            detalhe=motivo,
        ).save()

        _notificar_anexo_tardio(
            chamado_id=chamado_id,
            dados=data,
            usuario=usuario,
            caminho_anexo=caminho_anexo,
            motivo=motivo,
        )

        return {"sucesso": True}

    except Exception as exc:
        logger.exception("Erro ao adicionar anexo tardio no chamado %s: %s", chamado_id, exc)
        return {"sucesso": False, "erro": _t("internal_error_adding_attachment"), "codigo": 500}


def _notificar_anexo_tardio(
    chamado_id: str, dados: dict, usuario, caminho_anexo: str, motivo: str
) -> None:
    """Dispara notificação de anexo tardio em thread background."""
    import threading

    from flask import current_app

    app = current_app._get_current_object()  # noqa: SLF001

    def _run():
        with app.app_context():
            try:
                import os

                from app.services.chamado_notificacao_service import notificar_anexo_tardio_chamado

                notificar_anexo_tardio_chamado(
                    chamado_id=chamado_id,
                    numero_chamado=dados.get("numero_chamado") or "N/A",
                    categoria=dados.get("categoria") or "Chamado",
                    solicitante_nome=usuario.nome,
                    nome_arquivo=os.path.basename(caminho_anexo),
                    motivo=motivo,
                    dados_chamado=dados,
                )
            except Exception as exc:
                logger.warning("Notificação de anexo tardio não enviada: %s", exc)

    threading.Thread(target=_run, daemon=True).start()
