"""
Serviço de criação de chamados.

Centraliza a lógica de: validação, upload, atribuição de responsável,
Grupo RL, persistência e notificações. Usado pela rota de novo chamado.
"""

import logging
import threading
from typing import Any

from flask import current_app

from app.database import db
from app.firebase_retry import execute_with_retry
from app.i18n import get_translation_session
from app.models import Chamado
from app.models_grupo_rl import GrupoRL
from app.models_historico import Historico
from app.models_usuario import Usuario
from app.services.assignment import atribuidor
from app.services.notifications import (
    notificar_abertura_aog_todos_gestores,
    notificar_aprovador_novo_chamado,
    notificar_setores_adicionais_chamado,
)
from app.services.notifications_inapp import criar_notificacao
from app.services.notify_retry import executar_com_retry
from app.services.permissions import calcular_supervisor_ids_com_acesso
from app.services.upload import salvar_anexo
from app.services.webpush_service import enviar_webpush_usuario
from app.utils import gerar_numero_chamado
from app.utils_areas import setor_para_area

logger = logging.getLogger(__name__)


def _t(key, **kwargs):
    return get_translation_session(key, **kwargs)


def _resolver_responsavel(
    form: dict[str, Any],
    solicitante_id: str,
    solicitante_nome: str,
    area_solicitante: str | None,
) -> tuple[str, str, str, bool]:
    """
    Retorna (responsavel_nome, responsavel_id, motivo_atribuicao, atribuicao_manual).
    Usa responsável escolhido no formulário ou atribuição automática.
    atribuicao_manual indica se o chamado ficou aguardando atribuição manual
    (sem depender do texto traduzido de motivo_atribuicao).
    """
    responsavel_id_form = (form.get("responsavel_id") or "").strip()
    responsavel_nome_form = (form.get("responsavel_nome") or "").strip()
    # Bloqueia self-assignment: solicitante não pode ser o próprio responsável
    if responsavel_id_form and responsavel_nome_form and responsavel_id_form != solicitante_id:
        usuario_escolhido = Usuario.get_by_id(responsavel_id_form)
        if usuario_escolhido and usuario_escolhido.perfil in ("supervisor", "admin"):
            return (
                responsavel_nome_form,
                responsavel_id_form,
                _t("assignment_chosen_by_requester", nome=responsavel_nome_form),
                False,
            )
    tipo = form.get("tipo")
    categoria = form.get("categoria")
    area_para_atribuicao = setor_para_area(tipo) if tipo else (area_solicitante or "Geral")
    resultado = atribuidor.atribuir(
        area=area_para_atribuicao,
        categoria=categoria,
        prioridade=-1 if categoria == "AOG" else (0 if categoria == "Projetos" else 1),
    )
    if resultado["sucesso"]:
        return (
            resultado["supervisor"]["nome"],
            resultado["supervisor"]["id"],
            _t("assignment_auto_assigned", nome=resultado["supervisor"]["nome"]),
            False,
        )
    return (
        solicitante_nome,
        solicitante_id,
        _t("assignment_awaiting_manual", motivo=resultado["motivo"]),
        True,
    )


def _notificar_observadores_inclusao(
    app,
    chamado_id: str,
    numero_chamado: str,
    categoria: str,
    solicitante_nome: str,
    observadores: list,
) -> None:
    """Notifica cada observador que foi incluído no chamado no momento da criação."""

    def _run():
        with app.app_context():
            try:
                from app.services.chamado_notificacao_service import (
                    notificar_observadores_criacao,
                )

                notificar_observadores_criacao(
                    chamado_id=chamado_id,
                    numero_chamado=numero_chamado,
                    categoria=categoria,
                    solicitante_nome=solicitante_nome,
                    observadores=observadores,
                )
            except Exception as exc:
                logger.warning("Notif. observadores inclusão não enviada: %s", exc)

    threading.Thread(target=_run, daemon=True).start()


def criar_chamado(
    form: dict[str, Any],
    files: Any,
    solicitante_id: str,
    solicitante_nome: str,
    area_solicitante: str | None = None,
    solicitante_email: str | None = None,
) -> tuple[str | None, str | None, str | None, str | None]:
    """
    Cria um novo chamado no Firestore e dispara notificações.

    Args:
        form: request.form (categoria, rl_codigo, tipo, descricao, impacto, gate, etc.)
        files: request.files (para anexo)
        solicitante_id: ID do usuário solicitante
        solicitante_nome: Nome do solicitante
        area_solicitante: Área do solicitante (opcional)
        solicitante_email: Email do solicitante para notificações (opcional)

    Returns:
        (chamado_id, numero_chamado, erro, aviso_atribuicao)
        Em sucesso: (id, numero, None, aviso ou None). Em falha: (None, None, mensagem_erro, None).
    """
    import bleach

    categoria = form.get("categoria")
    rl_codigo = form.get("rl_codigo")
    tipo = form.get("tipo")
    descricao = bleach.clean(form.get("descricao") or "", tags=[], strip=True)
    impacto = form.get("impacto")
    gate = form.get("gate")
    if hasattr(form, "getlist"):
        setores_adicionais_lista = [
            str(s).strip() for s in form.getlist("setores_adicionais") if s and str(s).strip()
        ]
    else:
        setores_adicionais_bruto = form.get("setores_adicionais", [])
        if isinstance(setores_adicionais_bruto, list):
            setores_adicionais_lista = [
                str(s).strip() for s in setores_adicionais_bruto if s and str(s).strip()
            ]
        elif setores_adicionais_bruto:
            setores_adicionais_lista = [str(setores_adicionais_bruto).strip()]
        else:
            setores_adicionais_lista = []

    caminhos_anexos: list[str] = []
    for arq in files.getlist("anexo") if files else []:
        if not arq or not getattr(arq, "filename", ""):
            continue
        try:
            caminho = salvar_anexo(arq)
            if caminho:
                caminhos_anexos.append(caminho)
        except ValueError as e:
            return (None, None, str(e), None)

    # Links externos OneDrive/SharePoint (alternativa a upload >10 MB)
    if hasattr(form, "getlist"):
        links_externos = [
            lnk.strip() for lnk in form.getlist("links_externos") if lnk and lnk.strip()
        ]
    else:
        raw = form.get("links_externos", [])
        if isinstance(raw, str):
            links_externos = [raw.strip()] if raw.strip() else []
        else:
            links_externos = [lnk.strip() for lnk in raw if lnk and lnk.strip()]
    for link in links_externos:
        caminhos_anexos.append(f"onedrive:{link}")

    # Observadores (em cópia, read-only) — JSON [{usuario_id, nome, email}]
    import json as _json

    _obs_raw = (form.get("observadores_json") or "").strip()
    try:
        observadores_list = _json.loads(_obs_raw) if _obs_raw else []
        if not isinstance(observadores_list, list):
            observadores_list = []
    except Exception:
        logger.warning("observadores_json inválido, ignorando: %.80r", _obs_raw)
        observadores_list = []

    if observadores_list:
        from app.services.validators import validar_observadores

        erros_obs = validar_observadores(observadores_list, solicitante_id)
        if erros_obs:
            return (None, None, erros_obs[0], None)

    area_chamado = (
        setor_para_area(tipo) if tipo else (area_solicitante if area_solicitante else "Geral")
    )

    # Fase 2 — Supervisor obrigatório quando área tem supervisores cadastrados
    responsavel_id_form = (form.get("responsavel_id") or "").strip()
    supervisores_da_area = Usuario.get_supervisores_por_area(area_chamado)
    if not responsavel_id_form:
        if supervisores_da_area:
            return (
                None,
                None,
                _t("select_supervisor_for_area"),
                None,
            )
    elif supervisores_da_area:
        ids_validos = {s.id for s in supervisores_da_area}
        if responsavel_id_form not in ids_validos:
            return (None, None, _t("supervisor_invalid_for_area"), None)

    responsavel, responsavel_id, motivo_atribuicao, atribuicao_manual = _resolver_responsavel(
        form, solicitante_id, solicitante_nome, area_solicitante
    )

    grupo_rl_id = None
    if categoria in ("Projetos", "AOG") and rl_codigo:
        try:
            grupo = GrupoRL.get_or_create(
                rl_codigo=rl_codigo,
                criado_por_id=solicitante_id,
                area=area_chamado,
            )
            grupo_rl_id = grupo.id
        except Exception as e:
            logger.exception("Erro ao obter/criar GrupoRL para RL %s: %s", rl_codigo, e)

    try:
        numero_chamado = gerar_numero_chamado()
        ids_com_acesso = calcular_supervisor_ids_com_acesso(
            area_chamado, responsavel_id or None, []
        )
        novo_chamado = Chamado(
            numero_chamado=numero_chamado,
            categoria=categoria,
            rl_codigo=rl_codigo if categoria in ("Projetos", "AOG") else None,
            tipo_solicitacao=tipo,
            gate=gate,
            impacto=impacto,
            descricao=descricao,
            anexo=caminhos_anexos[0] if caminhos_anexos else None,
            anexos=caminhos_anexos,
            responsavel=responsavel,
            responsavel_id=responsavel_id,
            motivo_atribuicao=motivo_atribuicao,
            solicitante_id=solicitante_id,
            solicitante_nome=solicitante_nome,
            area=area_chamado,
            status="Aberto",
            grupo_rl_id=grupo_rl_id,
            setores_adicionais=setores_adicionais_lista,
            supervisor_ids_com_acesso=ids_com_acesso,
            observadores=observadores_list,
            # AOG já avisa todos os 4 níveis de gestor na abertura (ver notificar_abertura_aog_
            # todos_gestores abaixo) — Escada A normal (escalada gradual) não se aplica mais.
            escalacao_resposta_nivel=4 if categoria == "AOG" else 0,
        )
        chamado_dict = novo_chamado.to_dict()
        chamado_dict["observadores_ids"] = [
            obs.get("usuario_id") for obs in observadores_list if obs.get("usuario_id")
        ]
        doc_ref = execute_with_retry(
            db.collection("chamados").add,
            chamado_dict,
            max_retries=3,
        )
        chamado_id = doc_ref[1].id
        Historico(
            chamado_id=chamado_id,
            usuario_id=solicitante_id,
            usuario_nome=solicitante_nome,
            acao="criacao",
        ).save()

        if observadores_list:
            nomes_obs = ", ".join(o.get("nome", "") for o in observadores_list if o.get("nome"))
            Historico(
                chamado_id=chamado_id,
                usuario_id=solicitante_id,
                usuario_nome=solicitante_nome,
                acao="inclusao_observadores",
                campo_alterado="observadores",
                valor_anterior=None,
                valor_novo=nomes_obs or str(len(observadores_list)) + " observador(es)",
            ).save()

        _app = current_app._get_current_object()

        def _notificar():
            """Envia todas as notificações em background para não bloquear o request."""
            try:
                with _app.app_context():
                    if categoria == "AOG":
                        try:
                            notificar_abertura_aog_todos_gestores(
                                chamado_data=chamado_dict,
                                chamado_id=chamado_id,
                            )
                        except Exception as exc:
                            logger.warning(
                                "AOG: broadcast pros gestores falhou (chamado %s): %s",
                                chamado_id,
                                exc,
                            )
                    responsavel_usuario = (
                        Usuario.get_by_id(responsavel_id) if responsavel_id else None
                    )
                    executar_com_retry(
                        notificar_aprovador_novo_chamado,
                        chamado_id=chamado_id,
                        numero_chamado=numero_chamado,
                        categoria=categoria,
                        tipo_solicitacao=tipo,
                        descricao_resumo=(descricao or "")[:500],
                        area=area_solicitante or "Geral",
                        solicitante_nome=solicitante_nome,
                        responsavel_usuario=responsavel_usuario,
                        solicitante_email=solicitante_email,
                    )
                    if observadores_list:
                        _notificar_observadores_inclusao(
                            _app,
                            chamado_id=chamado_id,
                            numero_chamado=numero_chamado,
                            categoria=categoria or "",
                            solicitante_nome=solicitante_nome,
                            observadores=observadores_list,
                        )
                    if setores_adicionais_lista:
                        executar_com_retry(
                            notificar_setores_adicionais_chamado,
                            chamado_id=chamado_id,
                            numero_chamado=numero_chamado,
                            setores_novos=setores_adicionais_lista,
                            categoria=categoria,
                            tipo_solicitacao=tipo,
                            descricao_resumo=(descricao or "")[:500],
                            solicitante_nome=solicitante_nome,
                            quem_adicionou_nome=solicitante_nome,
                            setores_nomes=", ".join(setores_adicionais_lista),
                        )
                    if responsavel_id and responsavel_id != solicitante_id:
                        try:
                            from app.services.notifications_inapp import (
                                texto_notificacao_novo_chamado,
                            )

                            titulo_notif, mensagem_notif = texto_notificacao_novo_chamado(
                                numero_chamado, categoria or "", solicitante_nome, language="en"
                            )
                            criar_notificacao(
                                usuario_id=responsavel_id,
                                chamado_id=chamado_id,
                                numero_chamado=numero_chamado,
                                titulo=titulo_notif,
                                mensagem=mensagem_notif,
                                tipo="novo_chamado",
                                categoria=categoria or "",
                                solicitante_nome=solicitante_nome,
                            )
                            base_url = _app.config.get("APP_BASE_URL", "").rstrip("/")
                            url_chamado = (
                                f"{base_url}/chamado/{chamado_id}/historico" if base_url else None
                            )
                            enviar_webpush_usuario(
                                responsavel_id,
                                titulo=titulo_notif,
                                corpo=f"{categoria} · {solicitante_nome}",
                                url=url_chamado,
                            )
                        except Exception as e:
                            logger.debug("Notificação in-app/Web Push não enviada: %s", e)
            except Exception as e:
                logger.exception("Erro na thread de notificações do chamado %s: %s", chamado_id, e)

        threading.Thread(target=_notificar, daemon=True, name=f"notif-{chamado_id[:8]}").start()

        logger.info("Chamado criado: %s (ID: %s)", numero_chamado, chamado_id)
        aviso = motivo_atribuicao if atribuicao_manual else None
        return (chamado_id, numero_chamado, None, aviso)
    except Exception as e:
        logger.exception("Erro ao salvar chamado no Firestore: %s", e)
        return (None, None, _t("error_saving_ticket"), None)
