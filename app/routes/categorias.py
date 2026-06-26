"""Rotas de administração de categorias: setores, gates, impactos. Apenas para admins."""

import logging

from flask import Response, redirect, render_template, request, url_for

from app.cache import cache_delete, static_cache_delete
from app.decoradores import requer_perfil
from app.gates_config import GATE_PAI_OPCOES
from app.i18n import flash_t
from app.models_categorias import (
    CACHE_KEY_GATES,
    CACHE_KEY_IMPACTOS,
    CACHE_KEY_SETORES,
    STATIC_CACHE_KEY_GATES,
    STATIC_CACHE_KEY_IMPACTOS,
    STATIC_CACHE_KEY_SETORES,
    CategoriaGate,
    CategoriaImpacto,
    CategoriaSetor,
)
from app.routes import main
from app.services.translation_service import adicionar_traducao_customizada, traduzir_categoria

logger = logging.getLogger(__name__)

# Allowlist de gate pais aceitos (sem N/A — N/A não é um gate pai válido)
_GATE_PAI_VALIDOS = {"Gate 1", "Gate 2", "Gate 3", "Gate 4"}


def _invalidar_cache_setores():
    cache_delete(CACHE_KEY_SETORES)
    static_cache_delete(STATIC_CACHE_KEY_SETORES)


def _invalidar_cache_gates():
    cache_delete(CACHE_KEY_GATES)
    static_cache_delete(STATIC_CACHE_KEY_GATES)
    static_cache_delete("gates_validos_set")


def _invalidar_cache_impactos():
    cache_delete(CACHE_KEY_IMPACTOS)
    static_cache_delete(STATIC_CACHE_KEY_IMPACTOS)


@main.route("/admin/categorias", methods=["GET"])
@requer_perfil("admin")
def admin_categorias() -> Response:
    """Página de administração de categorias (setores, gates, impactos)."""
    try:
        setores = CategoriaSetor.get_all_incluindo_inativos()
        gates = CategoriaGate.get_all()
        impactos = CategoriaImpacto.get_all_incluindo_inativos()

        return render_template(
            "admin_categorias.html",
            setores=setores,
            gates=gates,
            impactos=impactos,
            gate_pai_opcoes=GATE_PAI_OPCOES,
        )
    except Exception as e:
        logger.exception("Erro ao carregar categorias: %s", e)
        flash_t("error_loading_categories", "danger")
        return redirect(url_for("main.admin"))


@main.route("/admin/categorias/setor/nova", methods=["POST"])
@requer_perfil("admin")
def criar_setor() -> Response:
    """Cria um novo setor."""
    try:
        nome_pt = request.form.get("nome_pt", "").strip()
        descricao_pt = request.form.get("descricao_pt", "").strip()

        if not nome_pt:
            flash_t("sector_name_required", "danger")
            return redirect(url_for("main.admin_categorias"))

        setor = CategoriaSetor(
            nome_pt=nome_pt,
            descricao_pt=descricao_pt,
        )
        setor.save()
        _invalidar_cache_setores()
        adicionar_traducao_customizada(nome_pt, setor.nome_en, setor.nome_es)
        flash_t("sector_created_success", "success", nome=nome_pt)
        return redirect(url_for("main.admin_categorias"))
    except Exception as e:
        logger.exception("Erro ao criar setor: %s", e)
        flash_t("error_creating_sector", "danger", error=str(e))
        return redirect(url_for("main.admin_categorias"))


@main.route("/admin/categorias/gate/nova", methods=["POST"])
@requer_perfil("admin")
def criar_gate() -> Response:
    """Cria um novo gate (gate pai + sub-etapa)."""
    try:
        gate_pai = request.form.get("gate_pai", "").strip()
        etapa = request.form.get("etapa", "").strip()
        descricao_pt = request.form.get("descricao_pt", "").strip()

        if not gate_pai or not etapa:
            flash_t("gate_name_required", "danger")
            return redirect(url_for("main.admin_categorias"))

        if gate_pai not in _GATE_PAI_VALIDOS:
            flash_t("gate_pai_invalido", "danger")
            return redirect(url_for("main.admin_categorias"))

        nome_pt = f"{gate_pai} - {etapa}"

        # Calcula próxima ordem dentro do gate pai
        gates_existentes = CategoriaGate.get_all()
        gates_mesmo_pai = [g for g in gates_existentes if g.gate_pai == gate_pai]
        proxima_ordem = (max((g.ordem for g in gates_mesmo_pai), default=0)) + 1

        gate = CategoriaGate(
            nome_pt=nome_pt,
            descricao_pt=descricao_pt,
            gate_pai=gate_pai,
            etapa=etapa,
            ordem=proxima_ordem,
        )
        gate.save()
        _invalidar_cache_gates()
        adicionar_traducao_customizada(nome_pt, gate.nome_en, gate.nome_es)
        flash_t("gate_created_success", "success", nome=nome_pt, ordem=proxima_ordem)
        return redirect(url_for("main.admin_categorias"))
    except Exception as e:
        logger.exception("Erro ao criar gate: %s", e)
        flash_t("error_creating_gate", "danger", error=str(e))
        return redirect(url_for("main.admin_categorias"))


@main.route("/admin/categorias/impacto/nova", methods=["POST"])
@requer_perfil("admin")
def criar_impacto() -> Response:
    """Cria um novo impacto."""
    try:
        nome_pt = request.form.get("nome_pt", "").strip()
        descricao_pt = request.form.get("descricao_pt", "").strip()

        if not nome_pt:
            flash_t("impact_name_required", "danger")
            return redirect(url_for("main.admin_categorias"))

        impacto = CategoriaImpacto(
            nome_pt=nome_pt,
            descricao_pt=descricao_pt,
        )
        impacto.save()
        _invalidar_cache_impactos()
        adicionar_traducao_customizada(nome_pt, impacto.nome_en, impacto.nome_es)
        flash_t("impact_created_success", "success", nome=nome_pt)
        return redirect(url_for("main.admin_categorias"))
    except Exception as e:
        logger.exception("Erro ao criar impacto: %s", e)
        flash_t("error_creating_impact", "danger", error=str(e))
        return redirect(url_for("main.admin_categorias"))


@main.route("/admin/categorias/setor/<setor_id>/editar", methods=["POST"])
@requer_perfil("admin")
def editar_setor(setor_id: str) -> Response:
    """Edita um setor existente."""
    try:
        setor = CategoriaSetor.get_by_id(setor_id)
        if not setor:
            flash_t("sector_not_found", "danger")
            return redirect(url_for("main.admin_categorias"))

        novo_nome = request.form.get("nome_pt", setor.nome_pt).strip()
        if novo_nome != setor.nome_pt:
            traducao = traduzir_categoria(novo_nome)
            setor.nome_pt = novo_nome
            setor.nome_en = traducao["en"]
            setor.nome_es = traducao["es"]
        setor.descricao_pt = request.form.get("descricao_pt", setor.descricao_pt or "").strip()
        setor.ativo = request.form.get("ativo") == "on"

        setor.save()
        _invalidar_cache_setores()
        adicionar_traducao_customizada(setor.nome_pt, setor.nome_en, setor.nome_es)
        flash_t("sector_updated_success", "success", nome=setor.nome_pt)
        return redirect(url_for("main.admin_categorias"))
    except Exception as e:
        logger.exception("Erro ao editar setor: %s", e)
        flash_t("error_editing_sector", "danger", error=str(e))
        return redirect(url_for("main.admin_categorias"))


@main.route("/admin/categorias/setor/<setor_id>/excluir", methods=["POST"])
@requer_perfil("admin")
def excluir_setor(setor_id: str) -> Response:
    """Exclui um setor."""
    try:
        setor = CategoriaSetor.get_by_id(setor_id)
        if not setor:
            flash_t("sector_not_found", "danger")
            return redirect(url_for("main.admin_categorias"))
        nome = setor.nome_pt
        setor.delete()
        _invalidar_cache_setores()
        flash_t("sector_deleted_success", "success", nome=nome)
        return redirect(url_for("main.admin_categorias"))
    except Exception as e:
        logger.exception("Erro ao excluir setor: %s", e)
        flash_t("error_deleting_sector", "danger", error=str(e))
        return redirect(url_for("main.admin_categorias"))


@main.route("/admin/categorias/gate/<gate_id>/editar", methods=["POST"])
@requer_perfil("admin")
def editar_gate(gate_id: str) -> Response:
    """Edita um gate existente (gate pai + sub-etapa)."""
    try:
        gate = CategoriaGate.get_by_id(gate_id)
        if not gate:
            flash_t("gate_not_found", "danger")
            return redirect(url_for("main.admin_categorias"))

        gate_pai = request.form.get("gate_pai", "").strip()
        etapa = request.form.get("etapa", "").strip()
        descricao_pt = request.form.get("descricao_pt", gate.descricao_pt or "").strip()
        ativo = request.form.get("ativo") == "on"

        if gate_pai and etapa:
            if gate_pai not in _GATE_PAI_VALIDOS:
                flash_t("gate_pai_invalido", "danger")
                return redirect(url_for("main.admin_categorias"))
            novo_nome_pt = f"{gate_pai} - {etapa}"
            traducao = traduzir_categoria(novo_nome_pt)
            gate.gate_pai = gate_pai
            gate.etapa = etapa
            gate.nome_pt = novo_nome_pt
            gate.nome_en = traducao["en"]
            gate.nome_es = traducao["es"]
        elif request.form.get("nome_pt"):
            gate.nome_pt = request.form.get("nome_pt").strip()

        gate.descricao_pt = descricao_pt
        gate.ativo = ativo

        gate.save()
        _invalidar_cache_gates()
        flash_t("gate_updated_success", "success", nome=gate.nome_pt)
        return redirect(url_for("main.admin_categorias"))
    except Exception as e:
        logger.exception("Erro ao editar gate: %s", e)
        flash_t("error_editing_gate", "danger", error=str(e))
        return redirect(url_for("main.admin_categorias"))


@main.route("/admin/categorias/gate/<gate_id>/excluir", methods=["POST"])
@requer_perfil("admin")
def excluir_gate(gate_id: str) -> Response:
    """Exclui um gate."""
    try:
        gate = CategoriaGate.get_by_id(gate_id)
        if not gate:
            flash_t("gate_not_found", "danger")
            return redirect(url_for("main.admin_categorias"))
        nome = gate.nome_pt
        gate.delete()
        _invalidar_cache_gates()
        flash_t("gate_deleted_success", "success", nome=nome)
        return redirect(url_for("main.admin_categorias"))
    except Exception as e:
        logger.exception("Erro ao excluir gate: %s", e)
        flash_t("error_deleting_gate", "danger", error=str(e))
        return redirect(url_for("main.admin_categorias"))


@main.route("/admin/categorias/impacto/<impacto_id>/editar", methods=["POST"])
@requer_perfil("admin")
def editar_impacto(impacto_id: str) -> Response:
    """Edita um impacto existente."""
    try:
        impacto = CategoriaImpacto.get_by_id(impacto_id)
        if not impacto:
            flash_t("impact_not_found", "danger")
            return redirect(url_for("main.admin_categorias"))

        novo_nome = request.form.get("nome_pt", impacto.nome_pt).strip()
        if novo_nome != impacto.nome_pt:
            traducao = traduzir_categoria(novo_nome)
            impacto.nome_pt = novo_nome
            impacto.nome_en = traducao["en"]
            impacto.nome_es = traducao["es"]
        impacto.descricao_pt = request.form.get("descricao_pt", impacto.descricao_pt or "").strip()
        impacto.ativo = request.form.get("ativo") == "on"

        impacto.save()
        _invalidar_cache_impactos()
        adicionar_traducao_customizada(impacto.nome_pt, impacto.nome_en, impacto.nome_es)
        flash_t("impact_updated_success", "success", nome=impacto.nome_pt)
        return redirect(url_for("main.admin_categorias"))
    except Exception as e:
        logger.exception("Erro ao editar impacto: %s", e)
        flash_t("error_editing_impact", "danger", error=str(e))
        return redirect(url_for("main.admin_categorias"))


@main.route("/admin/categorias/setor/lote", methods=["POST"])
@requer_perfil("admin")
def acao_lote_setores() -> Response:
    """Ações em lote sobre setores: excluir, ativar, desativar."""
    acao = request.form.get("acao", "").strip()
    ids = [i for i in request.form.getlist("ids") if i.strip()]
    if not ids:
        flash_t("no_items_selected", "danger")
        return redirect(url_for("main.admin_categorias"))
    try:
        if acao == "excluir":
            for sid in ids:
                setor = CategoriaSetor.get_by_id(sid)
                if setor:
                    setor.delete()
            _invalidar_cache_setores()
            flash_t("batch_items_deleted", "success", count=len(ids))
        elif acao in ("ativar", "desativar"):
            novo_ativo = acao == "ativar"
            for sid in ids:
                setor = CategoriaSetor.get_by_id(sid)
                if setor:
                    setor.ativo = novo_ativo
                    setor.save()
            _invalidar_cache_setores()
            key = "batch_items_activated" if novo_ativo else "batch_items_deactivated"
            flash_t(key, "success", count=len(ids))
    except Exception as e:
        logger.exception("Erro em acao_lote_setores: %s", e)
        flash_t("error_editing_sector", "danger", error=str(e))
    return redirect(url_for("main.admin_categorias"))


@main.route("/admin/categorias/gate/lote", methods=["POST"])
@requer_perfil("admin")
def acao_lote_gates() -> Response:
    """Ações em lote sobre gates: excluir, ativar, desativar."""
    acao = request.form.get("acao", "").strip()
    ids = [i for i in request.form.getlist("ids") if i.strip()]
    if not ids:
        flash_t("no_items_selected", "danger")
        return redirect(url_for("main.admin_categorias"))
    try:
        if acao == "excluir":
            for gid in ids:
                gate = CategoriaGate.get_by_id(gid)
                if gate:
                    gate.delete()
            _invalidar_cache_gates()
            flash_t("batch_items_deleted", "success", count=len(ids))
        elif acao in ("ativar", "desativar"):
            novo_ativo = acao == "ativar"
            for gid in ids:
                gate = CategoriaGate.get_by_id(gid)
                if gate:
                    gate.ativo = novo_ativo
                    gate.save()
            _invalidar_cache_gates()
            key = "batch_items_activated" if novo_ativo else "batch_items_deactivated"
            flash_t(key, "success", count=len(ids))
    except Exception as e:
        logger.exception("Erro em acao_lote_gates: %s", e)
        flash_t("error_editing_gate", "danger", error=str(e))
    return redirect(url_for("main.admin_categorias"))


@main.route("/admin/categorias/impacto/lote", methods=["POST"])
@requer_perfil("admin")
def acao_lote_impactos() -> Response:
    """Ações em lote sobre impactos: excluir, ativar, desativar."""
    acao = request.form.get("acao", "").strip()
    ids = [i for i in request.form.getlist("ids") if i.strip()]
    if not ids:
        flash_t("no_items_selected", "danger")
        return redirect(url_for("main.admin_categorias"))
    try:
        if acao == "excluir":
            for iid in ids:
                impacto = CategoriaImpacto.get_by_id(iid)
                if impacto:
                    impacto.delete()
            _invalidar_cache_impactos()
            flash_t("batch_items_deleted", "success", count=len(ids))
        elif acao in ("ativar", "desativar"):
            novo_ativo = acao == "ativar"
            for iid in ids:
                impacto = CategoriaImpacto.get_by_id(iid)
                if impacto:
                    impacto.ativo = novo_ativo
                    impacto.save()
            _invalidar_cache_impactos()
            key = "batch_items_activated" if novo_ativo else "batch_items_deactivated"
            flash_t(key, "success", count=len(ids))
    except Exception as e:
        logger.exception("Erro em acao_lote_impactos: %s", e)
        flash_t("error_editing_impact", "danger", error=str(e))
    return redirect(url_for("main.admin_categorias"))


@main.route("/admin/categorias/impacto/<impacto_id>/excluir", methods=["POST"])
@requer_perfil("admin")
def excluir_impacto(impacto_id: str) -> Response:
    """Exclui um impacto."""
    try:
        impacto = CategoriaImpacto.get_by_id(impacto_id)
        if not impacto:
            flash_t("impact_not_found", "danger")
            return redirect(url_for("main.admin_categorias"))
        nome = impacto.nome_pt
        impacto.delete()
        _invalidar_cache_impactos()
        flash_t("impact_deleted_success", "success", nome=nome)
        return redirect(url_for("main.admin_categorias"))
    except Exception as e:
        logger.exception("Erro ao excluir impacto: %s", e)
        flash_t("error_deleting_impact", "danger", error=str(e))
        return redirect(url_for("main.admin_categorias"))
