"""Notificações de ciclo de vida de usuário: cadastro, SSO, mudança de perfil."""

import logging
from html import escape

from app.i18n import get_translated_role, get_translated_sector_list
from app.services.email_templates import build_cta_button, build_detail_table, build_email_shell
from app.services.notifications_core import _base_url, _link_dashboard, enviar_email

logger = logging.getLogger(__name__)


def _link_usuarios() -> str:
    base = _base_url()
    return f"{base}/admin/usuarios" if base else ""


def notificar_novo_usuario_cadastrado(
    usuario_id: str,
    usuario_email: str,
    usuario_nome: str = "",
    perfil: str = "",
    areas: list | None = None,
    senha_inicial: str = "",
) -> None:
    """Send a welcome e-mail with credentials to a newly registered user."""
    if not usuario_email or not str(usuario_email).strip():
        logger.warning("New user notification skipped: empty e-mail")
        return

    email_dest = usuario_email.strip()
    perfil_display = get_translated_role(perfil, "en") if perfil else "N/A"
    areas_display = get_translated_sector_list(", ".join(areas or []), "en") or "N/A"
    link_dash = _link_dashboard()
    assunto = "Welcome to Andon — your access credentials"

    detalhes_html = build_detail_table(
        [
            ("Role", perfil_display),
            ("Areas", areas_display),
            ("E-mail", email_dest),
            ("Initial password", senha_inicial),
        ]
    )
    acesso_html = (
        f'<p style="margin-top: 20px;">{build_cta_button("Open system", link_dash, "#2563eb")}</p>'
        if link_dash
        else ""
    )

    corpo_html = build_email_shell(
        header_title="New account — Andon",
        header_color="#2563eb",
        body_html=(
            f"<p>Hello, <strong>{escape(usuario_nome or 'user')}</strong>! "
            "An account has been created for you in Andon.</p>"
            + detalhes_html
            + "<p>You will be asked to change your password on first login.</p>"
            + "<p>If you do not recognize this account, contact support immediately.</p>"
            + acesso_html
        ),
    )
    corpo_texto = (
        f"Hello {usuario_nome or 'user'},\n\n"
        "An account has been created for you in Andon.\n"
        f"Role: {perfil_display}\nAreas: {areas_display}\n"
        f"E-mail: {email_dest}\nInitial password: {senha_inicial}\n\n"
        "You will be asked to change your password on first login.\n"
        "If you do not recognize this account, contact support immediately."
    )

    ok, err = enviar_email(email_dest, assunto, corpo_html, corpo_texto, importance="normal")
    if ok:
        logger.info("Registration e-mail sent to %s", email_dest)
    else:
        logger.warning("Failed to send registration e-mail to %s: %s", email_dest, err)


def notificar_novo_usuario_sso(
    usuario_id: str,
    usuario_email: str,
    usuario_nome: str = "",
) -> None:
    """Send a welcome e-mail to a user auto-provisioned via Microsoft sign-in (no password)."""
    if not usuario_email or not str(usuario_email).strip():
        logger.warning("New SSO user notification skipped: empty e-mail")
        return

    email_dest = usuario_email.strip()
    assunto = "Welcome to Andon — account created via Microsoft sign-in"

    corpo_html = build_email_shell(
        header_title="New account — Andon",
        header_color="#2563eb",
        body_html=(
            f"<p>Hello, <strong>{escape(usuario_nome or 'user')}</strong>! "
            "An account has been created for you in Andon.</p>"
            "<p>You signed in using your Microsoft (DTX) account — no password was "
            "created for this account. Keep signing in with the "
            '"Sign in with Microsoft" button.</p>'
            "<p>If you do not recognize this account, contact support immediately.</p>"
        ),
    )
    corpo_texto = (
        f"Hello {usuario_nome or 'user'},\n\n"
        "An account has been created for you in Andon.\n"
        "You signed in using your Microsoft (DTX) account — no password was created "
        "for this account. Keep signing in with the 'Sign in with Microsoft' button.\n\n"
        "If you do not recognize this account, contact support immediately."
    )

    ok, err = enviar_email(email_dest, assunto, corpo_html, corpo_texto, importance="normal")
    if ok:
        logger.info("SSO registration e-mail sent to %s", email_dest)
    else:
        logger.warning("Failed to send SSO registration e-mail to %s: %s", email_dest, err)


def notificar_admins_novo_usuario_sso(
    admin_emails: list[str],
    usuario_email: str,
    usuario_nome: str = "",
) -> None:
    """Notify admins that a new user was auto-provisioned via Microsoft sign-in."""
    if not admin_emails:
        return

    link_usuarios = _link_usuarios()
    assunto = "New user auto-provisioned via Microsoft sign-in — review recommended"
    detalhes_html = build_detail_table(
        [
            ("Name", escape(usuario_nome or "N/A")),
            ("E-mail", escape(usuario_email or "N/A")),
            ("Role", "Requester (default, least privilege)"),
        ]
    )
    acesso_html = (
        f'<p style="margin-top: 20px;">{build_cta_button("Review users", link_usuarios, "#2563eb")}</p>'
        if link_usuarios
        else ""
    )
    corpo_html = build_email_shell(
        header_title="New user via Microsoft sign-in",
        header_color="#2563eb",
        body_html=(
            "<p>A new user just signed in with Microsoft for the first time and was "
            "auto-provisioned with the <strong>Requester</strong> profile.</p>"
            + detalhes_html
            + "<p>Promote this user if a different role is appropriate.</p>"
            + acesso_html
        ),
    )
    corpo_texto = (
        "A new user just signed in with Microsoft for the first time and was "
        "auto-provisioned with the Requester profile.\n"
        f"Name: {usuario_nome or 'N/A'}\nE-mail: {usuario_email or 'N/A'}\n\n"
        "Promote this user if a different role is appropriate."
    )

    for admin_email in admin_emails:
        ok, err = enviar_email(admin_email, assunto, corpo_html, corpo_texto, importance="normal")
        if ok:
            logger.info("Admin SSO new-user e-mail sent to %s", admin_email)
        else:
            logger.warning("Failed to send admin SSO new-user e-mail to %s: %s", admin_email, err)


def notificar_mudanca_perfil(
    usuario_email: str,
    usuario_nome: str,
    novo_perfil: str,
) -> None:
    """Notify a user that their profile/role was changed by an admin."""
    if not usuario_email or not str(usuario_email).strip():
        logger.warning("Profile change notification skipped: empty e-mail")
        return

    email_dest = usuario_email.strip()
    perfil_display = get_translated_role(novo_perfil, "en") if novo_perfil else "N/A"
    link_dash = _link_dashboard()
    assunto = "Your Andon role has changed"

    acesso_html = (
        f'<p style="margin-top: 20px;">{build_cta_button("Open system", link_dash, "#2563eb")}</p>'
        if link_dash
        else ""
    )
    corpo_html = build_email_shell(
        header_title="Role updated — Andon",
        header_color="#2563eb",
        body_html=(
            f"<p>Hello, <strong>{escape(usuario_nome or 'user')}</strong>! "
            f"Your role in Andon has been changed to <strong>{escape(perfil_display)}</strong>.</p>"
            "<p>If you do not recognize this change, contact support immediately.</p>" + acesso_html
        ),
    )
    corpo_texto = (
        f"Hello {usuario_nome or 'user'},\n\n"
        f"Your role in Andon has been changed to {perfil_display}.\n\n"
        "If you do not recognize this change, contact support immediately."
    )

    ok, err = enviar_email(email_dest, assunto, corpo_html, corpo_texto, importance="normal")
    if ok:
        logger.info("Role-change e-mail sent to %s", email_dest)
    else:
        logger.warning("Failed to send role-change e-mail to %s: %s", email_dest, err)
