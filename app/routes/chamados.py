"""Rotas de criação e listagem de chamados (solicitante)."""

import logging

from flask import Response, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.cache import get_static_cached
from app.database import db
from app.decoradores import requer_solicitante
from app.i18n import flash_t
from app.models_categorias import CategoriaImpacto, CategoriaSetor
from app.routes import main
from app.services.chamados_criacao_service import criar_chamado
from app.services.chamados_listagem_service import (
    _eh_erro_indice_firestore,
    listar_meus_chamados,
    listar_meus_chamados_fallback,
)
from app.services.pagination import obter_total_por_contagem
from app.services.validators import validar_novo_chamado

logger = logging.getLogger(__name__)


@main.route("/", methods=["GET", "POST"])
@requer_solicitante
def index() -> Response:
    """GET: formulário de novo chamado. POST: processa e salva no Firestore."""
    if request.method != "POST":
        setores = get_static_cached("categorias_setor", CategoriaSetor.get_all, ttl_seconds=300)
        impactos = get_static_cached(
            "categorias_impacto", CategoriaImpacto.get_all, ttl_seconds=300
        )

        # Contagem por agregação (count) — sem ler documentos
        status_counts = {"Aberto": 0, "Em Atendimento": 0, "Concluído": 0, "Cancelado": 0}
        try:
            for st in ("Aberto", "Em Atendimento", "Concluído", "Cancelado"):
                q = (
                    db.collection("chamados")
                    .where("solicitante_id", "==", current_user.id)
                    .where("status", "==", st)
                )
                c = obter_total_por_contagem(q)
                status_counts[st] = c if c is not None else 0
        except Exception as e:
            logger.warning("Erro ao contar chamados do solicitante: %s", e)

        return render_template(
            "formulario.html",
            setores=setores,
            impactos=impactos,
            status_counts=status_counts,
        )

    lista_erros = validar_novo_chamado(request.form, request.files.get("anexo"))
    if lista_erros:
        for erro in lista_erros:
            flash(erro, "danger")
        setores = get_static_cached("categorias_setor", CategoriaSetor.get_all, ttl_seconds=300)
        impactos = get_static_cached(
            "categorias_impacto", CategoriaImpacto.get_all, ttl_seconds=300
        )
        return render_template(
            "formulario.html",
            setores=setores,
            impactos=impactos,
        )

    chamado_id, numero_chamado, erro, aviso = criar_chamado(
        form=request.form,
        files=request.files,
        solicitante_id=current_user.id,
        solicitante_nome=current_user.nome,
        area_solicitante=getattr(current_user, "area", None),
        solicitante_email=getattr(current_user, "email", None),
    )
    if erro:
        flash(erro, "danger")
        setores = get_static_cached("categorias_setor", CategoriaSetor.get_all, ttl_seconds=300)
        impactos = get_static_cached(
            "categorias_impacto", CategoriaImpacto.get_all, ttl_seconds=300
        )
        return render_template("formulario.html", setores=setores, impactos=impactos)
    if aviso:
        flash(f"⚠️ {aviso}", "warning")
    flash_t("ticket_created_success", "success")
    return redirect(url_for("main.index"))


@main.route("/meus-chamados")
@requer_solicitante
def meus_chamados() -> Response:
    """GET: lista de chamados do solicitante com paginação por cursor (menos leituras no Firestore)."""
    if not getattr(current_user, "id", None):
        logger.warning("meus_chamados: current_user.id ausente")
        flash_t("error_loading_tickets_session", "danger")
        return redirect(url_for("main.index"))

    status_filtro = request.args.get("status", "")
    rl_codigo = (request.args.get("rl_codigo") or "").strip()
    cursor = request.args.get("cursor", "").strip()
    cursor_prev = request.args.get("cursor_prev", "").strip() or None
    pagina_atual = request.args.get("pagina", 1, type=int)
    itens_por_pagina = 10

    try:
        resultado = listar_meus_chamados(
            user_id=current_user.id,
            status_filtro=status_filtro,
            rl_codigo=rl_codigo,
            cursor=cursor,
            cursor_prev=cursor_prev,
            pagina_atual=pagina_atual,
            itens_por_pagina=itens_por_pagina,
        )
        return render_template(
            "meus_chamados.html",
            itens_por_pagina=itens_por_pagina,
            status_filtro=status_filtro,
            rl_codigo=rl_codigo,
            **resultado,
        )
    except Exception as e:
        if _eh_erro_indice_firestore(e):
            logger.warning(
                "Índice Firestore indisponível, usando fallback para meus_chamados: %s", e
            )
            try:
                resultado = listar_meus_chamados_fallback(
                    current_user.id, status_filtro, itens_por_pagina, pagina_atual, rl_codigo
                )
                return render_template(
                    "meus_chamados.html",
                    itens_por_pagina=itens_por_pagina,
                    status_filtro=status_filtro,
                    rl_codigo=rl_codigo,
                    **resultado,
                )
            except Exception as fallback_err:
                logger.exception("Fallback meus_chamados também falhou: %s", fallback_err)
                flash_t("error_loading_tickets_retry", "danger")
                return redirect(url_for("main.index"))
        logger.exception("Erro ao buscar chamados do solicitante: %s", e)
        flash_t("error_loading_tickets_logs", "danger")
        return redirect(url_for("main.index"))
