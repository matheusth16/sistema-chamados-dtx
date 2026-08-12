"""Rota pública (sem login) pra aprovar/rejeitar um pedido de previsão de
atendimento a partir do link assinado enviado por e-mail ao gestor decisor —
ver app/services/previsao_atendimento_service.py.

GET  mostra uma página de confirmação somente leitura (sem efeito colateral —
     evita que scanner/prefetch de e-mail dispare a decisão sozinho).
POST efetiva a decisão (token revalidado de novo, mesma regra).

Identidade de quem decide: como não há login, usa o gestor_id gravado na
solicitação no momento do pedido (quem recebeu o e-mail) — a autorização
real ainda é reconfirmada em decidir_previsao_atendimento (o gestor precisa
seguir qualificando pra área do chamado HOJE, não só ter recebido o e-mail).
"""

import logging

from flask import current_app, render_template, request

from app.limiter import limiter
from app.models import Chamado
from app.models_usuario import Usuario
from app.routes import main
from app.services.previsao_atendimento_service import (
    decidir_previsao_atendimento,
    obter_solicitacao_por_id,
    validar_token_decisao,
)

logger = logging.getLogger(__name__)


@main.route("/aprovacao-previsao/<token>", methods=["GET", "POST"])
@limiter.limit("20 per minute")
def aprovacao_previsao(token: str):
    payload = validar_token_decisao(token)
    if payload is None:
        return render_template("aprovacao_previsao.html", estado="token_invalido"), 400

    solicitacao = obter_solicitacao_por_id(payload["solicitacao_id"])
    if solicitacao is None:
        return render_template("aprovacao_previsao.html", estado="nao_encontrada"), 404

    acao = payload["acao"]
    chamado = Chamado.get_by_id(solicitacao["chamado_id"])

    def _render(estado: str, **extra):
        return render_template(
            "aprovacao_previsao.html",
            estado=estado,
            acao=acao,
            solicitacao=solicitacao,
            chamado=chamado,
            **extra,
        )

    if solicitacao["status"] != "pendente":
        return _render("ja_decidida"), 409

    if request.method == "GET":
        return _render("confirmar")

    gestor = Usuario.get_by_id(solicitacao["gestor_id"]) if solicitacao.get("gestor_id") else None
    if gestor is None:
        logger.warning(
            "Decisão de previsão via e-mail: gestor %s da solicitação %s não encontrado",
            solicitacao.get("gestor_id"),
            solicitacao["id"],
        )
        return _render("gestor_invalido"), 403

    resultado = decidir_previsao_atendimento(payload["solicitacao_id"], acao, gestor)
    if not resultado["sucesso"]:
        return _render("erro", erro=resultado.get("erro")), resultado.get("codigo", 400)

    from app.services.chamado_notificacao_service import (
        disparar_notificacao_decisao_previsao_em_thread,
    )

    disparar_notificacao_decisao_previsao_em_thread(
        current_app._get_current_object(), resultado["dados"], gestor.nome
    )

    return _render("decidida")
