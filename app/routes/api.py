"""Rotas de API (JSON) e service worker: status, notificações, push, paginação, disponibilidade."""

import contextlib
import hmac
import logging
import os
import threading

from flask import abort, current_app, jsonify, redirect, request, session
from flask_login import current_user, login_required
from google.cloud.firestore_v1.base_query import FieldFilter

from app.cache import cache_set
from app.database import db
from app.decoradores import requer_supervisor_area
from app.i18n import get_translation
from app.limiter import limiter
from app.models import Chamado
from app.models_historico import Historico
from app.models_usuario import Usuario
from app.routes import main
from app.services.analytics import obter_sla_para_exibicao
from app.services.assignment import atribuidor  # noqa: F401  # usado em testes via patch
from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante
from app.services.filters import aplicar_filtros_dashboard_com_paginacao
from app.services.permission_validation import (
    usuario_pode_mutar_chamado,
    verificar_permissao_mudanca_status,
)
from app.services.permissions import usuario_pode_operar_chamado, usuario_pode_ver_chamado
from app.services.solicitante_edicao_service import (
    adicionar_anexo_tardio,
    editar_descricao_solicitante,
    responder_chamado_solicitante,
)
from app.services.status_service import atualizar_status_chamado
from app.services.upload import salvar_anexo
from app.utils_areas import setor_para_area

logger = logging.getLogger(__name__)


def _t(key, **kwargs):
    """Traduz uma chave i18n para o idioma da sessão atual."""
    return get_translation(key, session.get("language", "en"), **kwargs)


def _dados_chamado_reaberto_valido(chamado_id: str) -> dict | None:
    """Retorna dados do chamado se ainda existir e estiver reaberto; senão None."""
    doc = db.collection("chamados").document(chamado_id).get()
    if not doc.exists:
        return None
    atual = doc.to_dict() or {}
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
    doc = db.collection("chamados").document(chamado_id).get()
    if not doc.exists:
        return None
    atual = doc.to_dict() or {}
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


def _obter_health_token_request() -> str:
    """Lê token de autenticação do health check.

    Canal primário: header X-Health-Token (não aparece em access logs).
    Canal deprecado: query string ?token= (compat UptimeRobot legado — migrar para header).
    """
    header = request.headers.get("X-Health-Token", "").strip()
    if header:
        return header
    return request.args.get("token", "").strip()


@main.route("/health", methods=["GET"])
def health():
    """Health check para monitoramento externo.

    Modo raso (padrão): apenas confirma que a app está no ar — rápido, sem I/O.
    Modo deep (?deep=1): verifica conectividade com Firestore — para UptimeRobot/BetterUptime.

    Autenticação (quando HEALTH_SECRET estiver configurado):
      Exigida em AMBOS os modos (raso e deep) — impede mapeamento de liveness por atacantes.
      Canal primário  : header X-Health-Token: <secret>  ← não aparece em access logs
      Canal deprecado : query string ?token=<secret>     ← migrar para header

    Sem HEALTH_SECRET (dev/CI): sem autenticação em nenhum modo.

    Configuração de monitoramento:
      curl -H "X-Health-Token: $HEALTH_SECRET" "https://host/health"
      curl -H "X-Health-Token: $HEALTH_SECRET" "https://host/health?deep=1"

    Returns:
        200 {"status": "ok"}        — tudo saudável
        401                         — token ausente ou inválido (quando HEALTH_SECRET configurado)
        503 {"status": "degraded"}  — alguma dependência falhou (apenas no modo deep)
    """
    import time

    # Quando HEALTH_SECRET estiver configurado, exige token em AMBOS os modos.
    # Sem HEALTH_SECRET (dev/CI): sem autenticação.
    secret = os.getenv("HEALTH_SECRET", "").strip()
    if secret:
        provided = _obter_health_token_request()
        if not provided or not hmac.compare_digest(provided, secret):
            abort(401)

    shallow = request.args.get("deep") not in ("1", "true")

    if shallow:
        return jsonify({"status": "ok"}), 200

    # checks críticos: impactam overall; checks opcionais: apenas informativos
    critical_checks: dict[str, str] = {}
    optional_checks: dict[str, str] = {}
    start = time.perf_counter()

    # Firestore: dependência crítica — sem ela a app não funciona
    try:
        db.collection("__health__").limit(1).get()
        critical_checks["firestore"] = "ok"
    except Exception as exc:
        critical_checks["firestore"] = f"error:{type(exc).__name__}"
        logger.error("health_check firestore falhou: %s", exc)

    # Redis / cache em memória — opcional, degrada performance mas não bloqueia
    try:
        cache_set("__health__", "1", ttl_seconds=10)
        optional_checks["cache"] = "ok"
    except Exception as exc:
        optional_checks["cache"] = f"degraded:{type(exc).__name__}"

    duration_ms = round((time.perf_counter() - start) * 1000, 1)
    all_critical_ok = all(v == "ok" for v in critical_checks.values())
    overall = "ok" if all_critical_ok else "degraded"
    status_code = 200 if all_critical_ok else 503
    checks = {**critical_checks, **optional_checks}

    payload = {
        "status": overall,
        "checks": checks,
        "duration_ms": duration_ms,
    }
    logger.info("health_check status=%s duration_ms=%.1f checks=%s", overall, duration_ms, checks)
    return jsonify(payload), status_code


@main.route("/api/download-anexo", methods=["GET"])
@login_required
def download_anexo():
    """Gera URL pré-assinada temporária (1h) para download de anexo privado no R2."""
    from app.services.upload import gerar_url_presignada

    chamado_id = request.args.get("chamado_id", "").strip()
    chave = request.args.get("chave", "").strip()

    if not chamado_id or not chave or not chave.startswith("r2:"):
        abort(400)

    doc = db.collection("chamados").document(chamado_id).get()
    if not doc.exists:
        abort(404)

    dados = doc.to_dict() or {}
    todos_anexos = list(dados.get("anexos") or [])
    if dados.get("anexo"):
        todos_anexos.append(dados["anexo"])

    if chave not in todos_anexos:
        abort(403)

    chamado = Chamado.from_dict(dados, chamado_id)
    if not usuario_pode_ver_chamado(current_user, chamado):
        abort(403)

    url = gerar_url_presignada(chave)
    if not url:
        logger.error("Falha ao gerar URL pré-assinada para chave %s", chave)
        abort(503)

    logger.info(
        "Acesso a anexo: usuario=%s chamado_id=%s chave=%s",
        current_user.email,
        chamado_id,
        chave,
    )
    return redirect(url)


@main.route("/api/atualizar-status", methods=["POST"])
@login_required
@limiter.limit("30 per minute", methods=["POST"])
def atualizar_status_ajax():
    """Atualiza status do chamado via JSON. Requer CSRF; o frontend deve enviar o token no header X-CSRFToken (ex.: valor da meta tag csrf-token)."""
    try:
        dados = request.get_json()
        if not dados:
            return jsonify({"sucesso": False, "erro": _t("invalid_or_empty_json")}), 400
        chamado_id = (dados.get("chamado_id") or "").strip()
        novo_status = (dados.get("novo_status") or "").strip()
        if not chamado_id:
            return jsonify({"sucesso": False, "erro": _t("field_chamado_id_required")}), 400
        if not novo_status:
            return jsonify({"sucesso": False, "erro": _t("field_novo_status_required")}), 400
        if novo_status not in ["Aberto", "Em Atendimento", "Concluído", "Cancelado"]:
            return jsonify(
                {"sucesso": False, "erro": _t("invalid_status_value", status=novo_status)}
            ), 400
        motivo_cancelamento = (dados.get("motivo_cancelamento") or "").strip()
        if novo_status == "Cancelado" and not motivo_cancelamento:
            return jsonify(
                {"sucesso": False, "erro": _t("cancellation_reason_required_field")}
            ), 400

        doc_chamado = db.collection("chamados").document(chamado_id).get()
        if not doc_chamado.exists:
            return jsonify({"sucesso": False, "erro": _t("ticket_not_found")}), 404

        chamado_obj = Chamado.from_dict(doc_chamado.to_dict(), chamado_id)

        permitido, erro_perm = verificar_permissao_mudanca_status(
            current_user, chamado_obj, novo_status
        )
        if not permitido:
            return jsonify({"sucesso": False, "erro": erro_perm}), 403

        from app.services.permission_validation import chamado_aceita_transicao_status

        pode_trans, _ = chamado_aceita_transicao_status(current_user, chamado_obj, novo_status)
        if not pode_trans:
            return jsonify(
                {
                    "sucesso": False,
                    "erro": _t("ticket_completed_no_status_transition"),
                }
            ), 403

        motivo_reabertura = (dados.get("motivo_reabertura") or "").strip()

        # Lacuna 4: reabertura de Concluído requer motivo explícito (mín. 3 chars)
        if (
            novo_status == "Aberto"
            and chamado_obj.status == "Concluído"
            and len(motivo_reabertura) < 3
        ):
            return jsonify(
                {
                    "sucesso": False,
                    "erro": _t("reopen_reason_min_3"),
                }
            ), 400

        resultado = atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status=novo_status,
            usuario_id=current_user.id,
            usuario_nome=current_user.nome,
            motivo_cancelamento=motivo_cancelamento if novo_status == "Cancelado" else None,
            motivo_reabertura=motivo_reabertura if novo_status == "Aberto" else None,
            data_chamado=doc_chamado.to_dict(),
        )
        if resultado["sucesso"]:
            return jsonify(
                {"sucesso": True, "mensagem": resultado["mensagem"], "novo_status": novo_status}
            ), 200
        else:
            return jsonify(
                {"sucesso": False, "erro": resultado.get("erro") or _t("error_unknown")}
            ), resultado.get("codigo", 500)
    except Exception as e:
        logger.exception("Erro em atualizar_status_ajax: %s", e)
        return jsonify({"sucesso": False, "erro": _t("internal_error_retry")}), 500


@main.route("/api/editar-chamado", methods=["POST"])
@login_required
def api_editar_chamado():
    """Edita chamado de forma completa via FormData (incluindo arquivo, status, responsavel, descricao). Apenas supervisor/admin."""
    if not current_user.is_supervisor_or_above:
        return jsonify({"sucesso": False, "erro": _t("access_denied_generic")}), 403
    if getattr(current_user, "is_gestor_only", None) is True:
        return jsonify({"sucesso": False, "erro": _t("access_denied_generic")}), 403

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
            return jsonify({"sucesso": False, "erro": _t("field_ticket_id_required")}), 400

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
            return jsonify(
                {
                    "sucesso": True,
                    "mensagem": resultado.get("mensagem"),
                    "dados": resultado.get("dados", {}),
                }
            ), 200
        else:
            http_code = resultado.get("codigo", 400)
            return jsonify({"sucesso": False, "erro": resultado.get("erro")}), http_code

    except Exception as e:
        logger.exception("Erro em api_editar_chamado: %s", e)
        return jsonify({"sucesso": False, "erro": _t("internal_error_retry")}), 500


@main.route("/api/bulk-status", methods=["POST"])
@login_required
@limiter.limit("10 per minute", methods=["POST"])
def bulk_atualizar_status():
    """Atualiza status de múltiplos chamados em lote. Apenas supervisor/admin."""
    if not current_user.is_supervisor_or_above:
        return jsonify({"sucesso": False, "erro": _t("access_denied_generic")}), 403
    # Gestor read-only: bloqueio total antes do loop
    if getattr(current_user, "is_gestor_only", None) is True:
        return jsonify({"sucesso": False, "erro": _t("access_denied_generic")}), 403
    try:
        dados = request.get_json()
        if not dados:
            return jsonify({"sucesso": False, "erro": _t("invalid_or_empty_json")}), 400
        ids = dados.get("chamado_ids")
        if not isinstance(ids, list):
            return jsonify({"sucesso": False, "erro": _t("field_chamado_ids_list")}), 400
        novo_status = (dados.get("novo_status") or "").strip()
        if novo_status not in ("Aberto", "Em Atendimento", "Concluído"):
            return jsonify({"sucesso": False, "erro": _t("invalid_new_status_generic")}), 400
        ids = [str(i).strip() for i in ids if i][:50]
        if not ids:
            return jsonify({"sucesso": False, "erro": _t("no_ticket_provided")}), 400

        atualizados = 0
        erros = []
        for chamado_id in ids:
            try:
                doc = db.collection("chamados").document(chamado_id).get()
                if not doc.exists:
                    erros.append({"id": chamado_id, "erro": _t("not_found_short")})
                    continue
                doc_data = doc.to_dict()
                chamado_obj = Chamado.from_dict(doc_data, chamado_id)
                if not usuario_pode_operar_chamado(current_user, chamado_obj):
                    erros.append({"id": chamado_id, "erro": _t("no_permission_for_ticket")})
                    continue
                from app.services.permission_validation import chamado_aceita_transicao_status

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
        return jsonify(
            {
                "sucesso": True,
                "atualizados": atualizados,
                "total_solicitados": len(ids),
                "erros": erros,
            }
        ), 200
    except Exception as e:
        logger.exception("Erro em bulk_atualizar_status: %s", e)
        return jsonify({"sucesso": False, "erro": _t("internal_error_retry")}), 500


@main.route("/api/chamado/<chamado_id>", methods=["GET"])
@login_required
def api_chamado_por_id(chamado_id: str):
    """Retorna um chamado por ID (JSON). Usado pelo dashboard para atualizar a linha após fechar o modal/aba de detalhes."""
    try:
        doc_chamado = db.collection("chamados").document(chamado_id).get()
        if not doc_chamado.exists:
            return jsonify({"sucesso": False, "erro": _t("ticket_not_found")}), 404
        chamado = Chamado.from_dict(doc_chamado.to_dict(), chamado_id)
        if not usuario_pode_ver_chamado(current_user, chamado):
            return jsonify({"sucesso": False, "erro": _t("no_permission_generic")}), 403
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
        return jsonify({"sucesso": True, "chamado": chamado_dict}), 200
    except Exception as e:
        logger.exception("Erro ao buscar chamado %s: %s", chamado_id, e)
        return jsonify({"sucesso": False, "erro": _t("internal_error_retry")}), 500


def _aplicar_filtro_perfil(ref, user):
    """Restringe a query de chamados ao escopo do perfil — evita IDOR por omissão de filtro.

    Supervisor: usa campo desnormalizado supervisor_ids_com_acesso (array_contains).
    Retorna None quando o supervisor não tem áreas configuradas:
    callers devem tratar None como lista vazia (não chamar aplicar_filtros).
    """
    if user.perfil == "solicitante":
        return ref.where(filter=FieldFilter("solicitante_id", "==", user.id))
    if user.perfil == "supervisor":
        areas = list(getattr(user, "areas", None) or [])
        if not areas:
            return None  # Supervisor sem áreas não deve ver nenhum chamado
        return ref.where(filter=FieldFilter("supervisor_ids_com_acesso", "array_contains", user.id))
    return ref  # admin/admin_global: sem restrição


@main.route("/api/chamados/paginar", methods=["GET"])
@login_required
def api_chamados_paginar():
    """Paginação com cursor para chamados."""
    try:
        limite = request.args.get("limite", 50, type=int)
        cursor = request.args.get("cursor")
        if limite < 1 or limite > 100:
            limite = 50
        chamados_ref = _aplicar_filtro_perfil(db.collection("chamados"), current_user)
        if chamados_ref is None:
            return jsonify(
                {
                    "sucesso": True,
                    "chamados": [],
                    "paginacao": {
                        "cursor_proximo": None,
                        "tem_proxima": False,
                        "total_pagina": 0,
                        "limite": limite,
                    },
                }
            ), 200
        resultado = aplicar_filtros_dashboard_com_paginacao(
            chamados_ref, request.args, limite=limite, cursor=cursor
        )
        chamados_dict = []
        for doc in resultado["docs"]:
            data = doc.to_dict()
            c = Chamado.from_dict(data, doc.id)
            chamados_dict.append(
                {
                    "id": doc.id,
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
        return jsonify(
            {
                "sucesso": True,
                "chamados": chamados_dict,
                "paginacao": {
                    "cursor_proximo": resultado["proximo_cursor"],
                    "tem_proxima": resultado["tem_proxima"],
                    "total_pagina": len(chamados_dict),
                    "limite": limite,
                },
            }
        ), 200
    except Exception as e:
        logger.exception("Erro em api_chamados_paginar: %s", e)
        return jsonify({"sucesso": False, "erro": _t("internal_error_retry")}), 500


@main.route("/api/carregar-mais", methods=["POST"])
@login_required
def carregar_mais():
    """Carregar mais chamados (infinite scroll)."""
    try:
        dados = request.get_json() or {}
        cursor = dados.get("cursor")
        limite = min(dados.get("limite", 20), 50)
        chamados_ref = _aplicar_filtro_perfil(db.collection("chamados"), current_user)
        if chamados_ref is None:
            return jsonify(
                {
                    "sucesso": True,
                    "chamados": [],
                    "cursor_proximo": None,
                    "tem_proxima": False,
                }
            ), 200
        resultado = aplicar_filtros_dashboard_com_paginacao(
            chamados_ref, request.args, limite=limite, cursor=cursor
        )
        chamados_dict = []
        for doc in resultado["docs"]:
            data = doc.to_dict()
            c = Chamado.from_dict(data, doc.id)
            chamados_dict.append(
                {
                    "id": doc.id,
                    "numero": c.numero_chamado,
                    "categoria": c.categoria,
                    "status": c.status,
                    "responsavel": c.responsavel,
                    "data_abertura": c.data_abertura_formatada(),
                }
            )
        return jsonify(
            {
                "sucesso": True,
                "chamados": chamados_dict,
                "cursor_proximo": resultado["proximo_cursor"],
                "tem_proxima": resultado["tem_proxima"],
            }
        ), 200
    except Exception as e:
        logger.exception("Erro em carregar_mais: %s", e)
        return jsonify({"sucesso": False, "erro": _t("internal_error_retry")}), 500


@main.route("/api/onboarding/avancar", methods=["POST"])
@login_required
def api_onboarding_avancar():
    """Salva o passo atual do tour de onboarding."""
    try:
        dados = request.get_json() or {}
        passo = dados.get("passo")
        if passo is None or not isinstance(passo, int) or passo < 0:
            return jsonify({"sucesso": False, "erro": _t("invalid_step")}), 400
        from app.services.onboarding_service import avancar_passo

        ok = avancar_passo(current_user.id, passo)
        return jsonify({"sucesso": ok}), 200
    except Exception as e:
        logger.exception("Erro em api_onboarding_avancar: %s", e)
        return jsonify({"sucesso": False, "erro": _t("internal_error_retry")}), 500


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
        return jsonify({"sucesso": False, "erro": _t("internal_error_retry")}), 500


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
        return jsonify({"sucesso": False, "erro": _t("internal_error_retry")}), 500


@main.route("/api/chamado/<chamado_id>/confirmar-resolucao", methods=["POST"])
@login_required
def api_confirmar_resolucao(chamado_id: str):
    """Solicitante confirma ou rejeita a resolução de um chamado Concluído."""

    dados = request.get_json(silent=True) or {}
    acao = dados.get("acao", "")
    motivo = (dados.get("motivo") or "").strip()

    if acao not in ("confirmar", "reabrir"):
        return jsonify({"sucesso": False, "erro": "Ação inválida"}), 400

    if acao == "reabrir" and not motivo:
        return jsonify({"sucesso": False, "erro": _t("ticket_reopen_reason_required")}), 400

    try:
        doc = db.collection("chamados").document(chamado_id).get()
        if not doc.exists:
            return jsonify({"sucesso": False, "erro": _t("ticket_not_found")}), 404

        data = doc.to_dict()

        if data.get("solicitante_id") != current_user.id:
            return jsonify({"sucesso": False, "erro": _t("access_denied_generic")}), 403

        if data.get("status") != "Concluído" or data.get("confirmacao_solicitante") != "pendente":
            return jsonify({"sucesso": False, "erro": _t("ticket_not_awaiting_confirmation")}), 400

        if acao == "confirmar":
            db.collection("chamados").document(chamado_id).update(
                {"confirmacao_solicitante": "confirmado"}
            )
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
                return jsonify(
                    {
                        "sucesso": False,
                        "erro": _t("reopen_limit_reached", limite=LIMITE_REABERTURAS_SOLICITANTE),
                    }
                ), 403

            db.collection("chamados").document(chamado_id).update(
                {
                    "status": "Aberto",
                    "confirmacao_solicitante": "reaberto",
                    "data_conclusao": None,
                    "escalacao_resposta_nivel": 0,  # ADR-004: Escada A reinicia na reabertura
                    # Fase 7 — Escada B: reinicia junto com Escada A na reabertura
                    "escalacao_resolucao_nivel": 0,
                    "alerta_supervisor_50_enviado": False,
                    "alerta_supervisor_80_enviado": False,
                    # Lembretes resetados para que o próximo ciclo de conclusão funcione
                    "lembrete_confirmacao_1_enviado": False,
                    "lembrete_confirmacao_2_enviado": False,
                    # Limite de auto-reabertura (Nível 1): supervisor/admin reabrem sem esse teto
                    "reaberturas_solicitante_count": reaberturas_atual + 1,
                }
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

        return jsonify({"sucesso": True}), 200

    except Exception as e:
        logger.exception("Erro ao confirmar resolução do chamado %s: %s", chamado_id, e)
        return jsonify({"sucesso": False, "erro": _t("internal_error_retry")}), 500


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
        return jsonify(
            {
                "sucesso": True,
                "area": area_resolvida,
                "supervisores": dados,
            }
        ), 200
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


# ---------------------------------------------------------------------------
# Observadores — Nível 1 Requester
# ---------------------------------------------------------------------------


@main.route("/api/usuarios/buscar", methods=["GET"])
@login_required
def api_buscar_usuarios():
    """Busca usuários ativos por nome/e-mail para seleção de observadores.

    GET /api/usuarios/buscar?q=<termo>
    Retorna máx. 10, exclui current_user, apenas usuários ativos.
    """
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify({"sucesso": True, "dados": []}), 200
    try:
        todos = Usuario.buscar_ativos(q)
        dados = [
            {"id": u.id, "nome": u.nome}
            for u in todos
            if u.id != current_user.id and u.perfil not in ("admin", "admin_global")
        ][:10]
        return jsonify({"sucesso": True, "dados": dados}), 200
    except Exception as exc:
        logger.exception("Erro em buscar_usuarios: %s", exc)
        return jsonify({"sucesso": False, "erro": _t("internal_error_retry")}), 500


# ---------------------------------------------------------------------------
# Edição pelo solicitante — Nível 1 Requester
# ---------------------------------------------------------------------------

DESCRICAO_MIN_CHARS = 3
LIMITE_REABERTURAS_SOLICITANTE = 3


@main.route("/api/chamado/<chamado_id>/editar-solicitante", methods=["POST"])
@login_required
def api_editar_solicitante(chamado_id: str):
    """
    Edição de descrição pelo dono do chamado, dentro da janela de 30 min.
    Qualquer perfil não-gestor pode usar; o service valida ownership (solicitante_id).
    """
    if getattr(current_user, "is_gestor_only", False):
        return jsonify({"sucesso": False, "erro": _t("unauthorized_access")}), 403

    payload = request.get_json(silent=True) or {}
    descricao = (payload.get("descricao") or "").strip()
    if len(descricao) < DESCRICAO_MIN_CHARS:
        return (
            jsonify(
                {
                    "sucesso": False,
                    "erro": _t("description_min_chars", min_chars=DESCRICAO_MIN_CHARS),
                }
            ),
            400,
        )

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
        return jsonify({"sucesso": False, "erro": _t("unauthorized_access")}), 403

    payload = request.get_json(silent=True) or {}
    motivo = (payload.get("motivo") or "").strip()
    if len(motivo) < 10:
        return jsonify({"sucesso": False, "erro": _t("reason_required_min_10_parens")}), 400

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
        return jsonify({"sucesso": False, "erro": _t("unauthorized_access")}), 403

    motivo = (request.form.get("motivo") or "").strip()
    if len(motivo) < 10:
        return (
            jsonify({"sucesso": False, "erro": _t("reason_required_min_10_parens")}),
            400,
        )

    arquivo = request.files.get("anexo")
    if not arquivo or not arquivo.filename:
        return jsonify({"sucesso": False, "erro": _t("file_not_sent")}), 400

    caminho = salvar_anexo(arquivo)
    if not caminho:
        return jsonify({"sucesso": False, "erro": _t("file_type_not_allowed")}), 400

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
        return jsonify({"sucesso": False, "erro": _t("unauthorized_access")}), 403

    payload = request.get_json(silent=True) or {}
    mensagem = (payload.get("mensagem") or "").strip()
    if not mensagem:
        return jsonify({"sucesso": False, "erro": _t("reply_message_required", min_chars=2)}), 400

    resultado = responder_chamado_solicitante(
        chamado_id=chamado_id,
        mensagem=mensagem,
        usuario=current_user,
    )

    codigo = resultado.pop("codigo", 200) if not resultado["sucesso"] else 200
    return jsonify(resultado), codigo


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


_csp_logger = logging.getLogger("app.csp")


@main.route("/api/csp-report", methods=["POST"])
@limiter.limit("20 per minute", methods=["POST"])
def csp_report():
    """Recebe relatórios de violação CSP enviados pelo browser (sem autenticação, sem CSRF)."""
    body = request.get_json(silent=True, force=True) or {}
    report = body.get("csp-report", body)
    _csp_logger.warning(
        "CSP violation: blocked-uri=%s violated-directive=%s document-uri=%s",
        report.get("blocked-uri", ""),
        report.get("violated-directive", ""),
        report.get("document-uri", ""),
    )
    return "", 204
