"""
Serviço de Notificações: E-mail via Microsoft Graph API (client credentials).

- Aprovador (responsável): notificado na criação do chamado.
- Solicitante: notificado em mudança de status (Em Atendimento / Concluído).
- Responsável: alerta de prazo 24h.
- Setores adicionais: supervisor do setor é notificado quando setor é adicionado.
- Novo usuário: recebe credenciais por e-mail ao ser cadastrado.

Variáveis de ambiente obrigatórias:
  GRAPH_TENANT_ID     — Directory (tenant) ID do Azure AD
  GRAPH_CLIENT_ID     — Application (client) ID
  GRAPH_CLIENT_SECRET — Client secret value
  GRAPH_SENDER_EMAIL  — Caixa de envio (ex: dtxls.support@dtx.aero)
"""

import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from html import escape

from flask import current_app, request

from app.services.email_templates import (
    build_cta_button,
    build_detail_table,
    build_email_shell,
    build_two_ctas,
)

logger = logging.getLogger(__name__)


def _config(key: str, default=None):
    """Lê valor do Flask config. Retorna default se fora de app context."""
    try:
        return current_app.config.get(key, default)
    except RuntimeError:
        return default


def _enviar_via_graph(
    destinatario: str,
    assunto: str,
    corpo_html: str,
    corpo_texto: str | None,
    from_addr: str,
) -> tuple:
    """Envia e-mail via Microsoft Graph API (client credentials)."""
    import json

    tenant_id = os.getenv("GRAPH_TENANT_ID", "").strip()
    client_id = os.getenv("GRAPH_CLIENT_ID", "").strip()
    client_secret = os.getenv("GRAPH_CLIENT_SECRET", "").strip()
    sender_email = os.getenv("GRAPH_SENDER_EMAIL", "").strip() or from_addr.strip()

    if not all([tenant_id, client_id, client_secret, sender_email]):
        return (
            False,
            "Configuração incompleta: defina GRAPH_TENANT_ID, GRAPH_CLIENT_ID, "
            "GRAPH_CLIENT_SECRET e GRAPH_SENDER_EMAIL",
        )

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    token_data = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
        }
    ).encode("utf-8")

    try:
        req_token = urllib.request.Request(token_url, data=token_data, method="POST")
        with urllib.request.urlopen(req_token, timeout=10) as resp:  # nosec B310
            token_resp = json.loads(resp.read().decode("utf-8"))
            access_token = token_resp.get("access_token")
            if not access_token:
                err = f"Token não obtido: {list(token_resp.keys())}"
                logger.warning(err)
                return (False, err)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        err = f"Graph token HTTP {e.code}: {body}"
        logger.warning("Falha ao obter token Graph: %s", err)
        return (False, err)
    except Exception as e:
        logger.exception("Falha ao obter token Graph para %s: %s", destinatario, e)
        return (False, f"Falha ao obter token OAuth2: {e}")

    payload = json.dumps(
        {
            "message": {
                "subject": assunto,
                "body": {"contentType": "HTML", "content": corpo_html},
                "toRecipients": [{"emailAddress": {"address": destinatario}}],
            },
            "saveToSentItems": False,
        }
    ).encode("utf-8")

    send_url = f"https://graph.microsoft.com/v1.0/users/{urllib.parse.quote(sender_email)}/sendMail"
    req_send = urllib.request.Request(
        send_url,
        data=payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req_send, timeout=15) as resp:  # nosec B310
            if resp.status == 202:
                logger.info("E-mail enviado via Graph para %s: %s", destinatario, assunto[:60])
                return (True, None)
            err = f"Graph sendMail status inesperado: {resp.status}"
            logger.warning(err)
            return (False, err)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        err = f"Graph sendMail HTTP {e.code}: {body}"
        logger.warning("Falha Graph sendMail para %s: %s", destinatario, err)
        return (False, err)
    except Exception as e:
        logger.exception("Falha ao enviar via Graph para %s: %s", destinatario, e)
        return (False, str(e))


def enviar_email(destinatario: str, assunto: str, corpo_html: str, corpo_texto: str = None):
    """Envia e-mail via Microsoft Graph API. Retorna (True, None) ou (False, erro)."""
    if not destinatario or not destinatario.strip():
        logger.warning("Notificação ignorada: destinatário vazio")
        return (False, None)
    from_addr = os.getenv("GRAPH_SENDER_EMAIL", "").strip() or "noreply@localhost"
    return _enviar_via_graph(destinatario.strip(), assunto, corpo_html, corpo_texto, from_addr)


def _base_url() -> str:
    base = (_config("APP_BASE_URL") or os.getenv("APP_BASE_URL") or "").strip()
    if not base:
        try:
            if request and getattr(request, "url_root", None):
                base = request.url_root.rstrip("/")
        except RuntimeError:
            pass
    return base.rstrip("/") if base else ""


def _link_chamado(chamado_id: str) -> str:
    base = _base_url()
    return f"{base}/chamado/{chamado_id}/historico" if base else ""


def _link_dashboard() -> str:
    base = _base_url()
    return f"{base}/admin" if base else ""


# ---------------------------------------------------------------------------
# Novo chamado — notifica responsável (supervisor)
# ---------------------------------------------------------------------------


def notificar_aprovador_novo_chamado(
    chamado_id: str,
    numero_chamado: str,
    categoria: str,
    tipo_solicitacao: str,
    descricao_resumo: str,
    area: str,
    solicitante_nome: str,
    responsavel_usuario,
    solicitante_email: str = None,
) -> None:
    """Notifica o responsável que um novo chamado foi atribuído a ele."""
    if not responsavel_usuario or not getattr(responsavel_usuario, "email", None):
        logger.debug("Aprovador sem e-mail; notificação não enviada")
        return

    email_dest = responsavel_usuario.email.strip()
    link = _link_chamado(chamado_id)
    link_dash = _link_dashboard()
    resumo_truncado = descricao_resumo[:500] + ("..." if len(descricao_resumo) > 500 else "")
    solicitante_linha = solicitante_nome
    if solicitante_email and solicitante_email.strip():
        solicitante_linha += f" ({solicitante_email.strip()})"

    assunto = f"Novo chamado atribuído: {numero_chamado}"

    detalhes_html = build_detail_table(
        [
            ("Número", numero_chamado),
            ("Categoria", categoria),
            ("Tipo", tipo_solicitacao),
            ("Área", area),
            ("Solicitante", solicitante_linha),
        ]
    )
    summary_html = f'<p style="margin: 12px 0;">{escape(resumo_truncado)}</p>'

    ctas = []
    if link:
        ctas.append(("Ver histórico do chamado", link, "#2563eb"))
    if link_dash:
        ctas.append(("Ver chamados do setor", link_dash, "#6b7280"))
    botoes_html = build_two_ctas(ctas) if ctas else ""

    corpo_html = build_email_shell(
        header_title="Novo chamado atribuído",
        header_color="#2563eb",
        body_html=(
            "<p>Olá, um novo chamado foi atribuído a você.</p>"
            + detalhes_html
            + summary_html
            + botoes_html
        ),
    )
    corpo_texto = (
        f"Número: {numero_chamado}\n"
        f"Categoria: {categoria}\nTipo: {tipo_solicitacao}\n"
        f"Área: {area}\nSolicitante: {solicitante_linha}\n"
        f"Resumo: {resumo_truncado}"
    )

    ok, err = enviar_email(email_dest, assunto, corpo_html, corpo_texto)
    if ok:
        logger.info("Notificação de novo chamado enviada para %s", email_dest)
    else:
        logger.warning("Falha ao notificar aprovador %s: %s", email_dest, err)


# ---------------------------------------------------------------------------
# Alerta de prazo 24h — notifica responsável
# ---------------------------------------------------------------------------


def notificar_responsavel_prazo_24h(
    chamado_id: str,
    numero_chamado: str,
    responsavel_email: str,
    categoria: str = "",
    tipo_solicitacao: str = "",
    area: str = "",
    solicitante_nome: str = "",
    descricao_resumo: str = "",
) -> None:
    """Avisa o responsável que o chamado está prestes a vencer o SLA (24h)."""
    if not responsavel_email or not str(responsavel_email).strip():
        logger.warning("Alerta 24h ignorado para %s: responsável sem e-mail", numero_chamado)
        return

    email_dest = responsavel_email.strip()
    link = _link_chamado(chamado_id)
    link_dash = _link_dashboard()
    resumo_truncado = (descricao_resumo or "")[:500] + (
        "..." if len(descricao_resumo or "") > 500 else ""
    )
    assunto = f"Chamado {numero_chamado}: prazo se encerrando em 24h"

    detalhes_html = build_detail_table(
        [
            ("Número", numero_chamado),
            ("Categoria", categoria),
            ("Tipo", tipo_solicitacao),
            ("Área", area),
            ("Solicitante", solicitante_nome),
        ]
    )
    summary_html = (
        f'<p style="margin: 12px 0;">{escape(resumo_truncado)}</p>' if resumo_truncado else ""
    )

    ctas = []
    if link:
        ctas.append(("Ver histórico do chamado", link, "#d97706"))
    if link_dash:
        ctas.append(("Ver chamados do setor", link_dash, "#6b7280"))
    botoes_html = build_two_ctas(ctas) if ctas else ""

    corpo_html = build_email_shell(
        header_title="Chamado próximo do vencimento (24h)",
        header_color="#d97706",
        body_html=(
            "<p>Olá, este chamado está próximo de vencer o prazo de atendimento.</p>"
            + detalhes_html
            + summary_html
            + botoes_html
        ),
    )
    corpo_texto = (
        f"Número: {numero_chamado}\n"
        "Aviso: este chamado está prestes a vencer o SLA (24h restantes).\n"
        f"Categoria: {categoria}\nTipo: {tipo_solicitacao}\n"
        f"Área: {area}\nSolicitante: {solicitante_nome}"
    )

    ok, err = enviar_email(email_dest, assunto, corpo_html, corpo_texto)
    if ok:
        logger.info("Alerta 24h enviado para %s (chamado %s)", email_dest, numero_chamado)
    else:
        logger.warning("Falha ao enviar alerta 24h para %s: %s", email_dest, err)


# ---------------------------------------------------------------------------
# Novo usuário cadastrado — envia credenciais
# ---------------------------------------------------------------------------


def notificar_novo_usuario_cadastrado(
    usuario_id: str,
    usuario_email: str,
    usuario_nome: str = "",
    perfil: str = "",
    areas: list | None = None,
    senha_inicial: str = "",
) -> None:
    """Envia e-mail de boas-vindas com credenciais ao usuário recém-cadastrado."""
    if not usuario_email or not str(usuario_email).strip():
        logger.warning("Aviso de novo usuário ignorado: e-mail vazio")
        return

    email_dest = usuario_email.strip()
    areas_str = ", ".join(areas or [])
    link_dash = _link_dashboard()
    assunto = "Bem-vindo ao DTX Digital Andon — suas credenciais de acesso"

    detalhes_html = build_detail_table(
        [
            ("Perfil", perfil or "N/A"),
            ("Áreas", areas_str or "N/A"),
            ("E-mail", email_dest),
            ("Senha inicial", senha_inicial),
        ]
    )
    acesso_html = (
        f'<p style="margin-top: 20px;">{build_cta_button("Acessar o sistema", link_dash, "#2563eb")}</p>'
        if link_dash
        else ""
    )

    corpo_html = build_email_shell(
        header_title="Novo cadastro — DTX Digital Andon",
        header_color="#2563eb",
        body_html=(
            f"<p>Olá, <strong>{escape(usuario_nome or 'usuário')}</strong>! "
            "Um acesso foi criado para você no DTX Digital Andon.</p>"
            + detalhes_html
            + "<p>Você será solicitado a trocar a senha no primeiro acesso.</p>"
            + "<p>Se não reconhecer este cadastro, entre em contato com o suporte imediatamente.</p>"
            + acesso_html
        ),
    )
    corpo_texto = (
        f"Olá {usuario_nome or 'usuário'},\n\n"
        "Um acesso foi criado para você no DTX Digital Andon.\n"
        f"Perfil: {perfil}\nÁreas: {areas_str or 'N/A'}\n"
        f"E-mail: {email_dest}\nSenha inicial: {senha_inicial}\n\n"
        "Você será solicitado a trocar a senha no primeiro acesso.\n"
        "Se não reconhecer este cadastro, entre em contato com o suporte."
    )

    ok, err = enviar_email(email_dest, assunto, corpo_html, corpo_texto)
    if ok:
        logger.info("E-mail de cadastro enviado para %s", email_dest)
    else:
        logger.warning("Falha ao enviar e-mail de cadastro para %s: %s", email_dest, err)


# ---------------------------------------------------------------------------
# Setor adicional incluído no chamado — notifica supervisor do setor
# ---------------------------------------------------------------------------


def notificar_responsavel_setor_adicional(
    chamado_id: str,
    numero_chamado: str,
    email_responsavel_setor: str,
    setor_adicional: str,
    categoria: str = "",
    tipo_solicitacao: str = "",
    solicitante_nome: str = "",
    quem_adicionou_nome: str = "",
    descricao_resumo: str = "",
) -> None:
    """Notifica o responsável de um setor adicional incluído no chamado."""
    if not email_responsavel_setor or not str(email_responsavel_setor).strip():
        logger.warning("Aviso setor adicional ignorado para %s: e-mail vazio", numero_chamado)
        return

    email_dest = email_responsavel_setor.strip()
    link = _link_chamado(chamado_id)
    link_dash = _link_dashboard()
    resumo_truncado = (descricao_resumo or "")[:500] + (
        "..." if len(descricao_resumo or "") > 500 else ""
    )
    assunto = f"Chamado {numero_chamado}: seu setor foi incluído"

    detalhes_html = build_detail_table(
        [
            ("Número", numero_chamado),
            ("Setor", setor_adicional),
            ("Incluído por", quem_adicionou_nome),
            ("Categoria", categoria),
            ("Tipo", tipo_solicitacao),
            ("Solicitante", solicitante_nome),
        ]
    )
    summary_html = (
        f'<p style="margin: 12px 0;">{escape(resumo_truncado)}</p>' if resumo_truncado else ""
    )

    ctas = []
    if link:
        ctas.append(("Ver histórico do chamado", link, "#2563eb"))
    if link_dash:
        ctas.append(("Ver chamados do setor", link_dash, "#6b7280"))
    botoes_html = build_two_ctas(ctas) if ctas else ""

    corpo_html = build_email_shell(
        header_title="Seu setor foi incluído em um chamado",
        header_color="#2563eb",
        body_html=(
            "<p>Olá, seu setor foi incluído neste chamado.</p>"
            + detalhes_html
            + summary_html
            + botoes_html
        ),
    )
    corpo_texto = (
        f"Número: {numero_chamado}\nSetor: {setor_adicional}\n"
        f"Incluído por: {quem_adicionou_nome}\nCategoria: {categoria}\n"
        f"Tipo: {tipo_solicitacao}\nSolicitante: {solicitante_nome}"
    )

    ok, err = enviar_email(email_dest, assunto, corpo_html, corpo_texto)
    if ok:
        logger.info(
            "Notif. setor adicional enviada para %s (chamado %s)", email_dest, numero_chamado
        )
    else:
        logger.warning("Falha ao notificar setor adicional %s: %s", email_dest, err)


def notificar_setores_adicionais_chamado(
    chamado_id: str,
    numero_chamado: str,
    setores_novos: list,
    categoria: str,
    tipo_solicitacao: str,
    descricao_resumo: str,
    solicitante_nome: str,
    quem_adicionou_nome: str,
    setores_nomes: str = None,
) -> None:
    """Notifica todos os supervisores dos setores adicionados ao chamado."""
    if not setores_novos:
        return

    from app.models_usuario import Usuario
    from app.utils_areas import setor_para_area

    link = _link_chamado(chamado_id)
    link_dash = _link_dashboard()
    setores_str = setores_nomes or ", ".join(setores_novos)
    resumo_truncado = (descricao_resumo or "")[:500] + (
        "..." if len(descricao_resumo or "") > 500 else ""
    )

    usuarios_unicos: dict = {}
    for setor in setores_novos:
        areas_busca = [setor]
        area_norm = setor_para_area(setor)
        if area_norm and area_norm != setor:
            areas_busca.append(area_norm)
        for area in areas_busca:
            for u in Usuario.get_supervisores_por_area(area):
                if u and u.id and u.id not in usuarios_unicos:
                    usuarios_unicos[u.id] = u

    for usuario in usuarios_unicos.values():
        email = getattr(usuario, "email", None)
        if not email or not str(email).strip():
            continue

        assunto = f"Chamado {numero_chamado}: seu setor foi incluído"
        detalhes_html = build_detail_table(
            [
                ("Número", numero_chamado),
                ("Categoria", categoria),
                ("Tipo", tipo_solicitacao),
                ("Solicitante", solicitante_nome),
                ("Incluído por", quem_adicionou_nome),
                ("Setores adicionados", setores_str),
            ]
        )
        summary_html = (
            f'<p style="margin: 12px 0;">{escape(resumo_truncado)}</p>' if resumo_truncado else ""
        )

        ctas = []
        if link:
            ctas.append(("Ver histórico do chamado", link, "#2563eb"))
        if link_dash:
            ctas.append(("Ver chamados do setor", link_dash, "#6b7280"))
        botoes_html = build_two_ctas(ctas) if ctas else ""

        corpo_html = build_email_shell(
            header_title="Chamado: seu setor foi incluído",
            header_color="#2563eb",
            body_html=(
                f"<p>Olá, o chamado <strong>{escape(numero_chamado)}</strong> "
                f"teve seu setor incluído por <strong>{escape(quem_adicionou_nome)}</strong>.</p>"
                + detalhes_html
                + summary_html
                + botoes_html
            ),
        )
        corpo_texto = (
            f"Número: {numero_chamado}\nSolicitante: {solicitante_nome}\n"
            f"Incluído por: {quem_adicionou_nome}\nSetores: {setores_str}"
        )

        ok, err = enviar_email(email.strip(), assunto, corpo_html, corpo_texto)
        if ok:
            logger.info(
                "Notif. setores adicionados enviada para %s (chamado %s)", email, numero_chamado
            )
        else:
            logger.warning("Falha ao notificar setores adicionados para %s: %s", email, err)


# ---------------------------------------------------------------------------
# Mudança de status — notifica solicitante
# ---------------------------------------------------------------------------


def notificar_solicitante_status(
    chamado_id: str,
    numero_chamado: str,
    novo_status: str,
    categoria: str,
    solicitante_usuario,
) -> None:
    """Notifica o solicitante sobre mudança de status (Em Atendimento / Concluído)."""
    if not solicitante_usuario:
        return

    email = (getattr(solicitante_usuario, "email", None) or "").strip()
    if not email:
        return

    nome = getattr(solicitante_usuario, "nome", None) or "Solicitante"
    link = _link_chamado(chamado_id)

    if novo_status == "Concluído":
        assunto = f"Chamado {numero_chamado}: concluído"
        header_title = f"Chamado {numero_chamado}: Concluído"
        header_color = "#059669"
        msg_status = "seu chamado foi <strong>concluído</strong>"
    else:
        assunto = f"Chamado {numero_chamado}: em atendimento"
        header_title = f"Chamado {numero_chamado}: Em Atendimento"
        header_color = "#2563eb"
        msg_status = "seu chamado está <strong>em atendimento</strong>"

    detalhes_html = build_detail_table(
        [("Chamado", numero_chamado), ("Categoria", categoria), ("Status", novo_status)]
    )
    botoes_html = (
        f'<p style="margin-top:20px;">{build_cta_button("Ver chamado", link, "#2563eb")}</p>'
        if link
        else '<p style="color:#6b7280;">Acesse o sistema para acompanhar.</p>'
    )

    corpo_html = build_email_shell(
        header_title=header_title,
        header_color=header_color,
        body_html=(
            f"<p>Olá, <strong>{escape(nome)}</strong>! Informamos que {msg_status}.</p>"
            + detalhes_html
            + botoes_html
        ),
    )
    corpo_texto = (
        f"Olá, {nome}!\n\n"
        f"Chamado: {numero_chamado}\nCategoria: {categoria}\nStatus: {novo_status}"
        + (f"\n\nVer chamado: {link}" if link else "")
    )

    ok, err = enviar_email(email, assunto, corpo_html, corpo_texto)
    if ok:
        logger.info(
            "E-mail de status (%s) enviado para %s (chamado %s)", novo_status, email, numero_chamado
        )
    else:
        logger.warning("Falha ao enviar e-mail de status para %s: %s", email, err)
