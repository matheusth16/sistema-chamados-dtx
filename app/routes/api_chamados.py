"""Rotas núcleo de chamados: status, edição, bulk, paginação, confirmação, onboarding."""

import contextlib
import logging
import threading

from flask import current_app, jsonify, request, session
from flask_login import current_user, login_required

from app.db.models.chamado import ChamadoRow
from app.i18n import get_translation
from app.limiter import limiter
from app.models import Chamado
from app.models_historico import Historico
from app.models_usuario import Usuario
from app.routes import main
from app.services.analytics import obter_sla_para_exibicao
from app.services.api_response import erro_json, sucesso_json
from app.services.assignment import atribuidor  # noqa: F401  # usado em testes via patch
from app.services.filters import aplicar_filtros_dashboard_com_paginacao
from app.services.permissions import usuario_pode_operar_chamado, usuario_pode_ver_chamado
from app.services.permissoes_edicao_chamado import (
    verificar_permissao_mudanca_status,
)
from app.services.status_service import atualizar_status_chamado
from app.utils_areas import setor_para_area

logger = logging.getLogger(__name__)


def _t(key, **kwargs):
    """Traduz uma chave i18n para o idioma da sessão atual."""
    return get_translation(key, session.get("language", "en"), **kwargs)


def _dados_chamado_reaberto_valido(chamado_id: str) -> dict | None:
    """Retorna dados do chamado se ainda existir e estiver reaberto; senão None."""
    chamado = Chamado.get_by_id(chamado_id)
    if chamado is None:
        return None
    atual = chamado.to_dict()
    if atual.get("status") != "Aberto" or atual.get("confirmacao_solicitante") != "reaberto":
        return None
    return atual


def _enviar_notificacao_reabrir(
    app, chamado_id: str, data: dict, motivo: str, solicitante_nome: str
) -> None:
    """Notifica o responsável em background que o chamado foi reaberto pelo solicitante."""

    def _run():
        with app.app_context():
            from app.services.notifications import notificar_supervisor_chamado_reaberto

            try:
                atual = _dados_chamado_reaberto_valido(chamado_id)
                if not atual:
                    logger.info(
                        "Notificação reabrir ignorada: chamado %s inexistente ou não reaberto",
                        chamado_id,
                    )
                    return
                responsavel_id = atual.get("responsavel_id") or data.get("responsavel_id")
                responsavel = Usuario.get_by_id(responsavel_id)
                notificar_supervisor_chamado_reaberto(
                    chamado_id=chamado_id,
                    numero_chamado=atual.get("numero_chamado")
                    or data.get("numero_chamado")
                    or "N/A",
                    categoria=atual.get("categoria") or data.get("categoria") or "Chamado",
                    motivo=motivo,
                    solicitante_nome=solicitante_nome,
                    responsavel_usuario=responsavel,
                )
            except Exception as exc:
                logger.warning("Notificação reabrir não enviada: %s", exc)

    threading.Thread(target=_run, daemon=True).start()


def _dados_chamado_confirmado_valido(chamado_id: str) -> dict | None:
    """Retorna dados do chamado se confirmacao_solicitante == 'confirmado'; senão None."""
    chamado = Chamado.get_by_id(chamado_id)
    if chamado is None:
        return None
    atual = chamado.to_dict()
    if atual.get("confirmacao_solicitante") != "confirmado":
        return None
    return atual


def _enviar_notificacao_confirmar(app, chamado_id: str, data: dict, solicitante_nome: str) -> None:
    """Notifica o responsável em background que o solicitante confirmou a resolução."""

    def _run():
        with app.app_context():
            from app.services.notifications import notificar_responsavel_chamado_confirmado

            try:
                atual = _dados_chamado_confirmado_valido(chamado_id)
                if not atual:
                    logger.info(
                        "Notificação confirmar ignorada: chamado %s inexistente ou não confirmado",
                        chamado_id,
                    )
                    return
                responsavel_id = atual.get("responsavel_id") or data.get("responsavel_id")
                if not responsavel_id:
                    logger.debug(
                        "Notificação confirmar: responsavel_id ausente no chamado %s", chamado_id
                    )
                    return
                responsavel = Usuario.get_by_id(responsavel_id)
                notificar_responsavel_chamado_confirmado(
                    chamado_id=chamado_id,
                    numero_chamado=atual.get("numero_chamado")
                    or data.get("numero_chamado")
                    or "N/A",
                    categoria=atual.get("categoria") or data.get("categoria") or "Chamado",
                    solicitante_nome=solicitante_nome,
                    responsavel_usuario=responsavel,
                )
            except Exception as exc:
                logger.warning("Notificação confirmar não enviada: %s", exc)

    threading.Thread(target=_run, daemon=True).start()


@main.route("/api/atualizar-status", methods=["POST"])
@login_required
@limiter.limit("30 per minute", methods=["POST"])
def atualizar_status_ajax():
    """Atualiza status do chamado via JSON. Requer CSRF; o frontend deve enviar o token no header X-CSRFToken (ex.: valor da meta tag csrf-token)."""
    try:
        dados = request.get_json()
        if not dados:
            return erro_json(_t("invalid_or_empty_json"), 400)
        chamado_id = (dados.get("chamado_id") or "").strip()
        novo_status = (dados.get("novo_status") or "").strip()
        if not chamado_id:
            return erro_json(_t("field_chamado_id_required"), 400)
        if not novo_status:
            return erro_json(_t("field_novo_status_required"), 400)
        if novo_status not in ["Aberto", "Em Atendimento", "Concluído", "Cancelado"]:
            return erro_json(_t("invalid_status_value", status=novo_status), 400)
        motivo_cancelamento = (dados.get("motivo_cancelamento") or "").strip()
        if novo_status == "Cancelado" and not motivo_cancelamento:
            return erro_json(_t("cancellation_reason_required_field"), 400)

        chamado_obj = Chamado.get_by_id(chamado_id)
        if chamado_obj is None:
            return erro_json(_t("ticket_not_found"), 404)

        permitido, erro_perm = verificar_permissao_mudanca_status(
            current_user, chamado_obj, novo_status
        )
        if not permitido:
            return erro_json(erro_perm, 403)

        from app.services.permissoes_edicao_chamado import chamado_aceita_transicao_status

        pode_trans, _ = chamado_aceita_transicao_status(current_user, chamado_obj, novo_status)
        if not pode_trans:
            return erro_json(_t("ticket_completed_no_status_transition"), 403)

        motivo_reabertura = (dados.get("motivo_reabertura") or "").strip()

        # Lacuna 4: reabertura de Concluído requer motivo explícito (mín. 3 chars)
        if (
            novo_status == "Aberto"
            and chamado_obj.status == "Concluído"
            and len(motivo_reabertura) < 3
        ):
            return erro_json(_t("reopen_reason_min_3"), 400)

        resultado = atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status=novo_status,
            usuario_id=current_user.id,
            usuario_nome=current_user.nome,
            motivo_cancelamento=motivo_cancelamento if novo_status == "Cancelado" else None,
            motivo_reabertura=motivo_reabertura if novo_status == "Aberto" else None,
            data_chamado=chamado_obj.to_dict(),
        )
        if resultado["sucesso"]:
            return sucesso_json(mensagem=resultado["mensagem"], novo_status=novo_status)
        else:
            return erro_json(
                resultado.get("erro") or _t("error_unknown"), resultado.get("codigo", 500)
            )
    except Exception as e:
        logger.exception("Erro em atualizar_status_ajax: %s", e)
        return erro_json(_t("internal_error_retry"), 500)


@main.route("/api/editar-chamado", methods=["POST"])
@login_required
def api_editar_chamado():
    """Edita chamado de forma completa via FormData (incluindo arquivo, status, responsavel, descricao). Apenas supervisor/admin."""
    if not current_user.is_supervisor_or_above:
        return erro_json(_t("access_denied_generic"), 403)
    if getattr(current_user, "is_gestor_only", None) is True:
        return erro_json(_t("access_denied_generic"), 403)

    try:
        chamado_id = request.form.get("chamado_id")
        novo_status = request.form.get("novo_status")
        motivo_cancelamento = (request.form.get("motivo_cancelamento") or "").strip()
        if not motivo_cancelamento and request.get_json(silent=True):
            motivo_cancelamento = (request.get_json() or {}).get("motivo_cancelamento") or ""
            motivo_cancelamento = str(motivo_cancelamento).strip()
        nova_descricao = request.form.get("nova_descricao")
        novo_responsavel_id = request.form.get("novo_responsavel_id")
        arquivos_novos = request.files.getlist("anexos_novos")

        if not chamado_id:
            return erro_json(_t("field_ticket_id_required"), 400)

        from app.services.edicao_chamado_service import processar_edicao_chamado

        setores_adicionais_form = request.form.getlist("setores_adicionais")
        if not setores_adicionais_form and request.get_json(silent=True):
            setores_adicionais_form = (request.get_json(silent=True) or {}).get(
                "setores_adicionais"
            ) or []

        resultado = processar_edicao_chamado(
            usuario_atual=current_user,
            chamado_id=chamado_id,
            novo_status=novo_status,
            motivo_cancelamento=motivo_cancelamento,
            nova_descricao=nova_descricao,
            novo_responsavel_id=novo_responsavel_id,
            novo_sla_str=(request.form.get("sla_dias") or "").strip(),
            arquivos_novos=arquivos_novos,
            setores_adicionais_lista=setores_adicionais_form,
        )

        if resultado.get("sucesso"):
            return sucesso_json(
                mensagem=resultado.get("mensagem"), dados=resultado.get("dados", {})
            )
        else:
            http_code = resultado.get("codigo", 400)
            return erro_json(resultado.get("erro"), http_code)

    except Exception as e:
        logger.exception("Erro em api_editar_chamado: %s", e)
        return erro_json(_t("internal_error_retry"), 500)


@main.route("/api/bulk-status", methods=["POST"])
@login_required
@limiter.limit("10 per minute", methods=["POST"])
def bulk_atualizar_status():
    """Atualiza status de múltiplos chamados em lote. Apenas supervisor/admin."""
    if not current_user.is_supervisor_or_above:
        return erro_json(_t("access_denied_generic"), 403)
    # Gestor read-only: bloqueio total antes do loop
    if getattr(current_user, "is_gestor_only", None) is True:
        return erro_json(_t("access_denied_generic"), 403)
    try:
        dados = request.get_json()
        if not dados:
            return erro_json(_t("invalid_or_empty_json"), 400)
        ids = dados.get("chamado_ids")
        if not isinstance(ids, list):
            return erro_json(_t("field_chamado_ids_list"), 400)
        novo_status = (dados.get("novo_status") or "").strip()
        if novo_status not in ("Aberto", "Em Atendimento", "Concluído"):
            return erro_json(_t("invalid_new_status_generic"), 400)
        ids = [str(i).strip() for i in ids if i][:50]
        if not ids:
            return erro_json(_t("no_ticket_provided"), 400)

        atualizados = 0
        erros = []
        for chamado_id in ids:
            try:
                chamado_obj = Chamado.get_by_id(chamado_id)
                if chamado_obj is None:
                    erros.append({"id": chamado_id, "erro": _t("not_found_short")})
                    continue
                doc_data = chamado_obj.to_dict()
                if not usuario_pode_operar_chamado(current_user, chamado_obj):
                    erros.append({"id": chamado_id, "erro": _t("no_permission_for_ticket")})
                    continue
                from app.services.permissoes_edicao_chamado import chamado_aceita_transicao_status

                pode_trans, _ = chamado_aceita_transicao_status(
                    current_user, chamado_obj, novo_status
                )
                if not pode_trans:
                    erros.append(
                        {"id": chamado_id, "erro": _t("ticket_completed_no_transition_short")}
                    )
                    continue
                resultado = atualizar_status_chamado(
                    chamado_id=chamado_id,
                    novo_status=novo_status,
                    usuario_id=current_user.id,
                    usuario_nome=current_user.nome,
                    data_chamado=doc_data,
                )
                if resultado.get("sucesso"):
                    atualizados += 1
                else:
                    erros.append(
                        {
                            "id": chamado_id,
                            "erro": resultado.get("erro") or _t("error_processing_ticket"),
                        }
                    )
            except Exception as e:
                logger.warning("Bulk status: falha em %s: %s", chamado_id, e)
                erros.append({"id": chamado_id, "erro": _t("error_processing_ticket")})
        return sucesso_json(atualizados=atualizados, total_solicitados=len(ids), erros=erros)
    except Exception as e:
        logger.exception("Erro em bulk_atualizar_status: %s", e)
        return erro_json(_t("internal_error_retry"), 500)


@main.route("/api/chamado/<chamado_id>", methods=["GET"])
@login_required
def api_chamado_por_id(chamado_id: str):
    """Retorna um chamado por ID (JSON). Usado pelo dashboard para atualizar a linha após fechar o modal/aba de detalhes."""
    try:
        chamado = Chamado.get_by_id(chamado_id)
        if chamado is None:
            return erro_json(_t("ticket_not_found"), 404)
        if not usuario_pode_ver_chamado(current_user, chamado):
            return erro_json(_t("no_permission_generic"), 403)
        sla_info = obter_sla_para_exibicao(chamado)
        chamado_dict = {
            "id": chamado_id,
            "numero_chamado": chamado.numero_chamado,
            "rl_codigo": chamado.rl_codigo,
            "categoria": chamado.categoria,
            "tipo_solicitacao": chamado.tipo_solicitacao,
            "gate": chamado.gate,
            "responsavel": chamado.responsavel,
            "descricao": chamado.descricao,
            "data_abertura": chamado.data_abertura_formatada(),
            "status": chamado.status,
            "sla_info": sla_info,
        }
        return sucesso_json(chamado=chamado_dict)
    except Exception as e:
        logger.exception("Erro ao buscar chamado %s: %s", chamado_id, e)
        return erro_json(_t("internal_error_retry"), 500)


def _aplicar_filtro_perfil(user):
    """Condições de escopo de chamados por perfil — evita IDOR por omissão de filtro.

    Supervisor: usa campo desnormalizado supervisor_ids_com_acesso (array contains).
    Retorna None quando o supervisor não tem áreas configuradas:
    callers devem tratar None como lista vazia (não chamar aplicar_filtros).
    """
    if user.perfil == "solicitante":
        return [ChamadoRow.solicitante_id == user.id]
    if user.perfil == "supervisor":
        areas = list(getattr(user, "areas", None) or [])
        if not areas:
            return None  # Supervisor sem áreas não deve ver nenhum chamado
        return [ChamadoRow.supervisor_ids_com_acesso.contains([user.id])]
    return []  # admin/admin_global: sem restrição


@main.route("/api/chamados/paginar", methods=["GET"])
@login_required
def api_chamados_paginar():
    """Paginação com cursor para chamados."""
    try:
        limite = request.args.get("limite", 50, type=int)
        cursor = request.args.get("cursor")
        if limite < 1 or limite > 100:
            limite = 50
        condicoes = _aplicar_filtro_perfil(current_user)
        if condicoes is None:
            return sucesso_json(
                chamados=[],
                paginacao={
                    "cursor_proximo": None,
                    "tem_proxima": False,
                    "total_pagina": 0,
                    "limite": limite,
                },
            )
        resultado = aplicar_filtros_dashboard_com_paginacao(
            condicoes, request.args, limite=limite, cursor=cursor
        )
        chamados_dict = []
        for c in resultado["docs"]:
            chamados_dict.append(
                {
                    "id": c.id,
                    "numero": c.numero_chamado,
                    "categoria": c.categoria,
                    "rl_codigo": c.rl_codigo or "-",
                    "tipo": c.tipo_solicitacao,
                    "responsavel": c.responsavel,
                    "status": c.status,
                    "prioridade": c.prioridade,
                    "descricao_resumida": c.descricao[:100] + "..."
                    if len(c.descricao) > 100
                    else c.descricao,
                    "data_abertura": c.data_abertura_formatada(),
                    "data_conclusao": c.data_conclusao_formatada(),
                }
            )
        return sucesso_json(
            chamados=chamados_dict,
            paginacao={
                "cursor_proximo": resultado["proximo_cursor"],
                "tem_proxima": resultado["tem_proxima"],
                "total_pagina": len(chamados_dict),
                "limite": limite,
            },
        )
    except Exception as e:
        logger.exception("Erro em api_chamados_paginar: %s", e)
        return erro_json(_t("internal_error_retry"), 500)


@main.route("/api/carregar-mais", methods=["POST"])
@login_required
def carregar_mais():
    """Carregar mais chamados (infinite scroll)."""
    try:
        dados = request.get_json() or {}
        cursor = dados.get("cursor")
        limite = min(dados.get("limite", 20), 50)
        condicoes = _aplicar_filtro_perfil(current_user)
        if condicoes is None:
            return sucesso_json(chamados=[], cursor_proximo=None, tem_proxima=False)
        resultado = aplicar_filtros_dashboard_com_paginacao(
            condicoes, request.args, limite=limite, cursor=cursor
        )
        chamados_dict = []
        for c in resultado["docs"]:
            chamados_dict.append(
                {
                    "id": c.id,
                    "numero": c.numero_chamado,
                    "categoria": c.categoria,
                    "status": c.status,
                    "responsavel": c.responsavel,
                    "data_abertura": c.data_abertura_formatada(),
                }
            )
        return sucesso_json(
            chamados=chamados_dict,
            cursor_proximo=resultado["proximo_cursor"],
            tem_proxima=resultado["tem_proxima"],
        )
    except Exception as e:
        logger.exception("Erro em carregar_mais: %s", e)
        return erro_json(_t("internal_error_retry"), 500)


@main.route("/api/onboarding/avancar", methods=["POST"])
@login_required
def api_onboarding_avancar():
    """Salva o passo atual do tour de onboarding."""
    try:
        dados = request.get_json() or {}
        passo = dados.get("passo")
        if passo is None or not isinstance(passo, int) or passo < 0:
            return erro_json(_t("invalid_step"), 400)
        from app.services.onboarding_service import avancar_passo

        ok = avancar_passo(current_user.id, passo)
        return jsonify({"sucesso": ok}), 200
    except Exception as e:
        logger.exception("Erro em api_onboarding_avancar: %s", e)
        return erro_json(_t("internal_error_retry"), 500)


@main.route("/api/onboarding/concluir", methods=["POST"])
@login_required
def api_onboarding_concluir():
    """Marca o onboarding como concluído."""
    try:
        from app.services.onboarding_service import concluir_onboarding

        ok = concluir_onboarding(current_user.id, current_user.perfil)
        return jsonify({"sucesso": ok}), 200
    except Exception as e:
        logger.exception("Erro em api_onboarding_concluir: %s", e)
        return erro_json(_t("internal_error_retry"), 500)


@main.route("/api/onboarding/pular", methods=["POST"])
@login_required
def api_onboarding_pular():
    """Pula o tour e marca onboarding como concluído."""
    try:
        from app.services.onboarding_service import concluir_onboarding

        ok = concluir_onboarding(current_user.id, current_user.perfil)
        return jsonify({"sucesso": ok}), 200
    except Exception as e:
        logger.exception("Erro em api_onboarding_pular: %s", e)
        return erro_json(_t("internal_error_retry"), 500)


@main.route("/api/chamado/<chamado_id>/confirmar-resolucao", methods=["POST"])
@login_required
def api_confirmar_resolucao(chamado_id: str):
    """Solicitante confirma ou rejeita a resolução de um chamado Concluído."""

    dados = request.get_json(silent=True) or {}
    acao = dados.get("acao", "")
    motivo = (dados.get("motivo") or "").strip()

    if acao not in ("confirmar", "reabrir"):
        return erro_json("Ação inválida", 400)

    if acao == "reabrir" and not motivo:
        return erro_json(_t("ticket_reopen_reason_required"), 400)

    try:
        chamado = Chamado.get_by_id(chamado_id)
        if chamado is None:
            return erro_json(_t("ticket_not_found"), 404)

        data = chamado.to_dict()

        if data.get("solicitante_id") != current_user.id:
            return erro_json(_t("access_denied_generic"), 403)

        if data.get("status") != "Concluído" or data.get("confirmacao_solicitante") != "pendente":
            return erro_json(_t("ticket_not_awaiting_confirmation"), 400)

        if acao == "confirmar":
            chamado.atualizar_campos(confirmacao_solicitante="confirmado")
            with contextlib.suppress(RuntimeError):
                _enviar_notificacao_confirmar(
                    current_app._get_current_object(),
                    chamado_id,
                    data,
                    current_user.nome,
                )
        else:
            reaberturas_atual = data.get("reaberturas_solicitante_count", 0)
            if reaberturas_atual >= LIMITE_REABERTURAS_SOLICITANTE:
                return erro_json(
                    _t("reopen_limit_reached", limite=LIMITE_REABERTURAS_SOLICITANTE), 403
                )

            chamado.atualizar_campos(
                status="Aberto",
                confirmacao_solicitante="reaberto",
                data_conclusao=None,
                escalacao_resposta_nivel=0,  # ADR-004: Escada A reinicia na reabertura
                # Fase 7 — Escada B: reinicia junto com Escada A na reabertura
                escalacao_resolucao_nivel=0,
                alerta_supervisor_50_enviado=False,
                alerta_supervisor_80_enviado=False,
                # Lembretes resetados para que o próximo ciclo de conclusão funcione
                lembrete_confirmacao_1_enviado=False,
                lembrete_confirmacao_2_enviado=False,
                # Limite de auto-reabertura (Nível 1): supervisor/admin reabrem sem esse teto
                reaberturas_solicitante_count=reaberturas_atual + 1,
            )
            Historico(
                chamado_id=chamado_id,
                usuario_id=current_user.id,
                usuario_nome=current_user.nome,
                acao="reabertura",
                campo_alterado="status",
                valor_anterior="Concluído",
                valor_novo="Aberto",
                detalhe=motivo[:500],
            ).save()
            with contextlib.suppress(RuntimeError):
                _enviar_notificacao_reabrir(
                    current_app._get_current_object(),
                    chamado_id,
                    data,
                    motivo,
                    current_user.nome,
                )

        return sucesso_json()

    except Exception as e:
        logger.exception("Erro ao confirmar resolução do chamado %s: %s", chamado_id, e)
        return erro_json(_t("internal_error_retry"), 500)


@main.route("/api/supervisores/lista", methods=["GET"])
@login_required
def api_lista_supervisores():
    """Lista simples de supervisores por área para o formulário (rápida, sem contar carga)."""
    area = request.args.get("area", "").strip() or "Geral"
    try:
        area_resolvida = setor_para_area(area) or area
        supervisores = Usuario.get_supervisores_por_area(area_resolvida)
        dados = [
            {
                "id": u.id,
                "nome": u.nome,
            }
            for u in supervisores
            if u.id != current_user.id
        ]
        return sucesso_json(area=area_resolvida, supervisores=dados)
    except Exception as e:
        logger.exception("Erro ao listar supervisores: %s", e)
        return jsonify(
            {
                "sucesso": False,
                "area": area,
                "supervisores": [],
                "erro": _t("internal_error_retry"),
            }
        ), 200


LIMITE_REABERTURAS_SOLICITANTE = 3
