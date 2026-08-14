"""Rotas de self-service do solicitante: download de anexo, edição, cancelamento, resposta, busca de usuários."""

import logging
import os

from flask import abort, current_app, jsonify, redirect, request, send_from_directory, session
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from app.i18n import get_translation
from app.limiter import limiter
from app.models import Chamado
from app.models_usuario import Usuario
from app.routes import main
from app.services.api_response import erro_json, sucesso_json
from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante
from app.services.permissions import usuario_pode_ver_chamado
from app.services.solicitante_edicao_service import (
    adicionar_anexo_tardio,
    editar_descricao_solicitante,
    responder_chamado_solicitante,
)
from app.services.upload import salvar_anexo

logger = logging.getLogger(__name__)


def _t(key, **kwargs):
    """Traduz uma chave i18n para o idioma da sessão atual."""
    return get_translation(key, session.get("language", "en"), **kwargs)


def _enviar_anexo_local(pasta: str, nome_arquivo: str):
    """Serve um anexo local autenticado, com defesa contra path traversal."""
    nome_seguro = secure_filename(nome_arquivo)
    if not nome_seguro or nome_seguro != nome_arquivo:
        abort(400)
    caminho = os.path.realpath(os.path.join(pasta, nome_seguro))
    if not caminho.startswith(os.path.realpath(pasta) + os.sep):
        abort(400)
    if not os.path.isfile(caminho):
        abort(404)
    return send_from_directory(pasta, nome_seguro, as_attachment=True)


@main.route("/api/download-anexo", methods=["GET"])
@login_required
def download_anexo():
    """Gera acesso autenticado a um anexo: URL pré-assinada (R2) ou arquivo
    local servido diretamente (disco local novo ou legado sem prefixo)."""
    from app.services.upload import gerar_url_presignada

    chamado_id = request.args.get("chamado_id", "").strip()
    chave = request.args.get("chave", "").strip()

    if not chamado_id or not chave:
        abort(400)

    chamado = Chamado.get_by_id(chamado_id)
    if not chamado:
        abort(404)

    todos_anexos = list(chamado.anexos or [])
    if chamado.anexo:
        todos_anexos.append(chamado.anexo)

    if chave not in todos_anexos:
        abort(403)

    if not usuario_pode_ver_chamado(current_user, chamado):
        abort(403)

    logger.info(
        "Acesso a anexo: usuario=%s chamado_id=%s chave=%s",
        current_user.email,
        chamado_id,
        chave,
    )

    if chave.startswith("r2:"):
        url = gerar_url_presignada(chave)
        if not url:
            logger.error("Falha ao gerar URL pré-assinada para chave %s", chave)
            abort(503)
        return redirect(url)

    if chave.startswith("local:"):
        return _enviar_anexo_local(current_app.config["ANEXO_LOCAL_DIR"], chave[len("local:") :])

    if chave.startswith(("http://", "https://", "onedrive:")):
        # Firebase (URL pública) e OneDrive/SharePoint não são proxeados por
        # este endpoint — o template já linka direto para eles.
        abort(400)

    # Legado: anexo salvo em disco antes da Fase 1 (dev, sem prefixo) — mesmo
    # tratamento de segurança do "local:", lendo de UPLOAD_FOLDER (onde esses
    # arquivos foram efetivamente gravados).
    return _enviar_anexo_local(current_app.config["UPLOAD_FOLDER"], chave)


@main.route("/api/usuarios/buscar", methods=["GET"])
@login_required
@limiter.limit("5 per minute")
def api_buscar_usuarios():
    """Busca usuários ativos por nome/e-mail para seleção de observadores.

    GET /api/usuarios/buscar?q=<termo>
    Retorna máx. 10, exclui current_user, apenas usuários ativos.
    """
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return sucesso_json(dados=[])
    try:
        todos = Usuario.buscar_ativos(q)
        dados = [
            {"id": u.id, "nome": u.nome}
            for u in todos
            if u.id != current_user.id and u.perfil not in ("admin", "admin_global")
        ][:10]
        return sucesso_json(dados=dados)
    except Exception as exc:
        logger.exception("Erro em buscar_usuarios: %s", exc)
        return erro_json(_t("internal_error_retry"), 500)


@main.route("/api/chamado/<chamado_id>/editar-solicitante", methods=["POST"])
@login_required
def api_editar_solicitante(chamado_id: str):
    """
    Edição de descrição pelo dono do chamado, dentro da janela de 30 min.
    Qualquer perfil não-gestor pode usar; o service valida ownership (solicitante_id).
    """
    if getattr(current_user, "is_gestor_only", False):
        return erro_json(_t("unauthorized_access"), 403)

    from config import Config

    payload = request.get_json(silent=True) or {}
    descricao = (payload.get("descricao") or "").strip()
    if len(descricao) < Config.MIN_DESCRICAO_CHARS:
        return erro_json(_t("description_min_chars", min_chars=Config.MIN_DESCRICAO_CHARS), 400)
    if len(descricao) > Config.MAX_DESCRICAO_CHARS:
        return erro_json(_t("description_max_chars", max_chars=Config.MAX_DESCRICAO_CHARS), 400)

    resultado = editar_descricao_solicitante(
        chamado_id=chamado_id,
        novo_texto=descricao,
        usuario=current_user,
    )

    codigo = resultado.pop("codigo", 200) if not resultado["sucesso"] else 200
    return jsonify(resultado), codigo


@main.route("/api/chamado/<chamado_id>/cancelar-solicitante", methods=["POST"])
@login_required
def api_cancelar_solicitante(chamado_id: str):
    """
    Cancelamento de chamado pelo dono do chamado.
    Qualquer perfil não-gestor pode usar; o service valida ownership (solicitante_id).
    """
    if getattr(current_user, "is_gestor_only", False):
        return erro_json(_t("unauthorized_access"), 403)

    payload = request.get_json(silent=True) or {}
    motivo = (payload.get("motivo") or "").strip()
    if len(motivo) < 10:
        return erro_json(_t("reason_required_min_10_parens"), 400)

    resultado = cancelar_chamado_solicitante(
        chamado_id=chamado_id,
        motivo=motivo,
        usuario=current_user,
    )

    codigo = resultado.pop("codigo", 200) if not resultado["sucesso"] else 200
    return jsonify(resultado), codigo


@main.route("/api/chamado/<chamado_id>/anexo-solicitante", methods=["POST"])
@login_required
def api_anexo_solicitante(chamado_id: str):
    """Anexo tardio enviado pelo dono do chamado (FormData). Qualquer perfil não-gestor."""
    if getattr(current_user, "is_gestor_only", False):
        return erro_json(_t("unauthorized_access"), 403)

    motivo = (request.form.get("motivo") or "").strip()
    if len(motivo) < 10:
        return erro_json(_t("reason_required_min_10_parens"), 400)

    arquivo = request.files.get("anexo")
    if not arquivo or not arquivo.filename:
        return erro_json(_t("file_not_sent"), 400)

    caminho = salvar_anexo(arquivo)
    if not caminho:
        return erro_json(_t("file_type_not_allowed"), 400)

    resultado = adicionar_anexo_tardio(
        chamado_id=chamado_id,
        caminho_anexo=caminho,
        motivo=motivo,
        usuario=current_user,
    )

    codigo = resultado.pop("codigo", 200) if not resultado["sucesso"] else 200
    return jsonify(resultado), codigo


@main.route("/api/chamado/<chamado_id>/responder-solicitante", methods=["POST"])
@login_required
def api_responder_solicitante(chamado_id: str):
    """
    Resposta em texto livre do dono do chamado, sem exigir anexo.
    Fecha a lacuna de pedidos de informação (status Aguardando Informação)
    que exigiam anexar um arquivo só para poder responder por texto.
    """
    if getattr(current_user, "is_gestor_only", False):
        return erro_json(_t("unauthorized_access"), 403)

    payload = request.get_json(silent=True) or {}
    mensagem = (payload.get("mensagem") or "").strip()
    if not mensagem:
        return erro_json(_t("reply_message_required", min_chars=2), 400)

    resultado = responder_chamado_solicitante(
        chamado_id=chamado_id,
        mensagem=mensagem,
        usuario=current_user,
    )

    codigo = resultado.pop("codigo", 200) if not resultado["sucesso"] else 200
    return jsonify(resultado), codigo
