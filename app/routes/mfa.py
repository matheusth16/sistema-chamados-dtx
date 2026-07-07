"""Rotas de auto-serviço de MFA: configurar, exibir backup codes, desativar."""

import logging

from flask import Response, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from app.i18n import flash_t
from app.routes import main
from app.services import mfa_service
from app.utils import mask_email_for_log

logger = logging.getLogger(__name__)


@main.route("/mfa/configurar", methods=["GET", "POST"])
@login_required
def mfa_configurar() -> Response:
    """GET: exibe QR code para configurar o app autenticador. POST: confirma e habilita o MFA."""
    if request.method == "POST":
        secret = session.get("mfa_setup_secret")
        if not secret:
            return redirect(url_for("main.mfa_configurar"))

        codigo = request.form.get("codigo", "").strip()
        if not mfa_service.verificar_codigo_totp(secret, codigo):
            flash_t("mfa_invalid_code", "danger")
            return redirect(url_for("main.mfa_configurar"))

        codigos_backup = mfa_service.gerar_codigos_backup()
        hashes = mfa_service.hash_codigos_backup(codigos_backup)
        current_user.update(mfa_enabled=True, mfa_secret=secret, mfa_backup_codes=hashes)

        session.pop("mfa_setup_secret", None)
        session["mfa_backup_codes_display"] = codigos_backup

        logger.info("MFA habilitado: %s", mask_email_for_log(current_user.email))
        flash_t("mfa_enabled_success", "success")
        return redirect(url_for("main.mfa_codigos_backup"))

    if current_user.mfa_enabled is True:
        return render_template("mfa_configurar.html", mfa_habilitado=True)

    secret = session.get("mfa_setup_secret")
    if not secret:
        secret = mfa_service.gerar_secret()
        session["mfa_setup_secret"] = secret

    qr_data_uri = mfa_service.gerar_qr_code_data_uri(current_user.email, secret)
    return render_template(
        "mfa_configurar.html",
        mfa_habilitado=False,
        qr_data_uri=qr_data_uri,
        secret_manual=secret,
    )


@main.route("/mfa/codigos-backup", methods=["GET"])
@login_required
def mfa_codigos_backup() -> Response:
    """Exibe os códigos de backup uma única vez (removidos da sessão após a exibição)."""
    codigos = session.pop("mfa_backup_codes_display", None)
    if not codigos:
        return redirect(url_for("main.mfa_configurar"))
    return render_template("mfa_codigos_backup.html", codigos=codigos)


@main.route("/mfa/desativar", methods=["POST"])
@login_required
def mfa_desativar() -> Response:
    """Desativa o MFA da própria conta — exige confirmação da senha atual."""
    senha_atual = request.form.get("senha_atual", "")
    if not current_user.check_password(senha_atual):
        flash_t("current_password_incorrect", "danger")
        return redirect(url_for("main.mfa_configurar"))

    current_user.update(mfa_enabled=False, mfa_secret=None, mfa_backup_codes=None)
    logger.info("MFA desativado: %s", mask_email_for_log(current_user.email))
    flash_t("mfa_disabled_success", "success")
    return redirect(url_for("main.mfa_configurar"))


@main.route("/mfa/regenerar-backup-codes", methods=["POST"])
@login_required
def mfa_regenerar_backup_codes() -> Response:
    """Gera um novo conjunto de códigos de backup, invalidando os anteriores."""
    senha_atual = request.form.get("senha_atual", "")
    if not current_user.check_password(senha_atual):
        flash_t("current_password_incorrect", "danger")
        return redirect(url_for("main.mfa_configurar"))

    codigos_backup = mfa_service.gerar_codigos_backup()
    hashes = mfa_service.hash_codigos_backup(codigos_backup)
    current_user.update(mfa_backup_codes=hashes)

    session["mfa_backup_codes_display"] = codigos_backup
    logger.info("Backup codes MFA regenerados: %s", mask_email_for_log(current_user.email))
    return redirect(url_for("main.mfa_codigos_backup"))
