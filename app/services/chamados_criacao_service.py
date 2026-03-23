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
from app.models import Chamado
from app.models_grupo_rl import GrupoRL
from app.models_historico import Historico
from app.models_usuario import Usuario
from app.services.assignment import atribuidor
from app.services.notifications import (
    notificar_aprovador_novo_chamado,
    notificar_setores_adicionais_chamado,
)
from app.services.notifications_inapp import criar_notificacao
from app.services.notify_retry import executar_com_retry
from app.services.upload import salvar_anexo
from app.services.webpush_service import enviar_webpush_usuario
from app.utils import gerar_numero_chamado
from app.utils_areas import setor_para_area

logger = logging.getLogger(__name__)


def _resolver_responsavel(
    form: dict[str, Any],
    solicitante_id: str,
    solicitante_nome: str,
    area_solicitante: str | None,
) -> tuple[str, str, str]:
    """
    Retorna (responsavel_nome, responsavel_id, motivo_atribuicao).
    Usa responsável escolhido no formulário ou atribuição automática.
    """
    responsavel_id_form = (form.get("responsavel_id") or "").strip()
    responsavel_nome_form = (form.get("responsavel_nome") or "").strip()
    if responsavel_id_form and responsavel_nome_form:
        usuario_escolhido = Usuario.get_by_id(responsavel_id_form)
        if usuario_escolhido and usuario_escolhido.perfil in ("supervisor", "admin"):
            return (
                responsavel_nome_form,
                responsavel_id_form,
                f"Escolhido pelo solicitante: {responsavel_nome_form}",
            )
    tipo = form.get("tipo")
    categoria = form.get("categoria")
    area_para_atribuicao = setor_para_area(tipo) if tipo else (area_solicitante or "Geral")
    resultado = atribuidor.atribuir(
        area=area_para_atribuicao,
        categoria=categoria,
        prioridade=0 if categoria == "Projetos" else 1,
    )
    if resultado["sucesso"]:
        return (
            resultado["supervisor"]["nome"],
            resultado["supervisor"]["id"],
            f"Atribuído automaticamente a {resultado['supervisor']['nome']}",
        )
    return (
        solicitante_nome,
        solicitante_id,
        f"Aguardando atribuição manual: {resultado['motivo']}",
    )


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

    try:
        caminho_anexo = salvar_anexo(files.get("anexo") if files else None)
    except ValueError as e:
        return (None, None, str(e), None)

    responsavel, responsavel_id, motivo_atribuicao = _resolver_responsavel(
        form, solicitante_id, solicitante_nome, area_solicitante
    )
    area_chamado = (
        setor_para_area(tipo) if tipo else (area_solicitante if area_solicitante else "Geral")
    )

    grupo_rl_id = None
    if categoria == "Projetos" and rl_codigo:
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
        novo_chamado = Chamado(
            numero_chamado=numero_chamado,
            categoria=categoria,
            rl_codigo=rl_codigo if categoria == "Projetos" else None,
            tipo_solicitacao=tipo,
            gate=gate,
            impacto=impacto,
            descricao=descricao,
            anexo=caminho_anexo,
            responsavel=responsavel,
            responsavel_id=responsavel_id,
            motivo_atribuicao=motivo_atribuicao,
            solicitante_id=solicitante_id,
            solicitante_nome=solicitante_nome,
            area=area_chamado,
            status="Aberto",
            grupo_rl_id=grupo_rl_id,
            setores_adicionais=setores_adicionais_lista,
        )
        doc_ref = execute_with_retry(
            db.collection("chamados").add,
            novo_chamado.to_dict(),
            max_retries=3,
        )
        chamado_id = doc_ref[1].id
        Historico(
            chamado_id=chamado_id,
            usuario_id=solicitante_id,
            usuario_nome=solicitante_nome,
            acao="criacao",
        ).save()

        _app = current_app._get_current_object()

        def _notificar():
            """Envia todas as notificações em background para não bloquear o request."""
            try:
                with _app.app_context():
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
                    if responsavel_id:
                        try:
                            criar_notificacao(
                                usuario_id=responsavel_id,
                                chamado_id=chamado_id,
                                numero_chamado=numero_chamado,
                                titulo=f"Novo chamado: {numero_chamado}",
                                mensagem=f"{categoria} · Solicitante: {solicitante_nome}",
                                tipo="novo_chamado",
                            )
                            base_url = _app.config.get("APP_BASE_URL", "").rstrip("/")
                            url_chamado = (
                                f"{base_url}/chamado/{chamado_id}/historico" if base_url else None
                            )
                            enviar_webpush_usuario(
                                responsavel_id,
                                titulo=f"Novo chamado: {numero_chamado}",
                                corpo=f"{categoria} · {solicitante_nome}",
                                url=url_chamado,
                            )
                        except Exception as e:
                            logger.debug("Notificação in-app/Web Push não enviada: %s", e)
            except Exception as e:
                logger.exception("Erro na thread de notificações do chamado %s: %s", chamado_id, e)

        threading.Thread(target=_notificar, daemon=True, name=f"notif-{chamado_id[:8]}").start()

        logger.info("Chamado criado: %s (ID: %s)", numero_chamado, chamado_id)
        aviso = motivo_atribuicao if "Aguardando atribuição" in motivo_atribuicao else None
        return (chamado_id, numero_chamado, None, aviso)
    except Exception as e:
        logger.exception("Erro ao salvar chamado no Firestore: %s", e)
        return (None, None, "Não foi possível salvar o chamado. Tente novamente.", None)
