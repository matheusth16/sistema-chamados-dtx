"""Rotas exclusivas para o perfil admin_global — inacessíveis a qualquer sub-admin."""

import logging
import threading

from flask import Response, current_app, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.database import db
from app.decoradores import requer_perfil
from app.i18n import flash_t
from app.models_usuario import Usuario
from app.routes import main
from app.services.notifications import notificar_mudanca_perfil
from app.services.notify_retry import executar_com_retry

logger = logging.getLogger(__name__)


def _disparar_notificacao_mudanca_perfil(usuario: Usuario, novo_perfil: str) -> None:
    """Dispara em background o e-mail avisando o usuário sobre o novo perfil."""
    _app = current_app._get_current_object()
    email_notif = usuario.email
    nome_notif = usuario.nome

    def _notificar():
        with _app.app_context():
            executar_com_retry(
                notificar_mudanca_perfil,
                usuario_email=email_notif,
                usuario_nome=nome_notif,
                novo_perfil=novo_perfil,
            )

    threading.Thread(target=_notificar, daemon=True).start()


def _kwargs_reset_onboarding(usuario: Usuario, novo_perfil: str) -> dict:
    """{'onboarding_passo': 0} se o novo perfil ainda não foi visto pelo usuário; senão {}."""
    if novo_perfil not in (usuario.onboarding_perfis_vistos or []):
        return {"onboarding_passo": 0}
    return {}


def requer_admin_global(f):
    """Permite apenas admin_global — sem expansão automática."""
    return requer_perfil("admin_global")(f)

    # Nota: requer_perfil("admin_global") NÃO expande para incluir "admin" porque
    # a expansão só ocorre quando "admin" está na lista, não "admin_global".


@main.route("/admin-global")
@login_required
def admin_global_dashboard() -> Response:
    """Dashboard exclusivo do admin_global."""
    if current_user.perfil != "admin_global":
        flash_t("access_denied_profiles", "danger", profiles="admin_global")
        if current_user.perfil == "solicitante":
            return redirect(url_for("main.index"))
        if current_user.perfil == "supervisor":
            return redirect(url_for("main.painel"))
        return redirect(url_for("main.admin"))

    try:
        todos_usuarios = Usuario.get_all()
        sub_admins = [u for u in todos_usuarios if u.perfil == "admin"]
        supervisores = [u for u in todos_usuarios if u.perfil == "supervisor"]
        solicitantes = [u for u in todos_usuarios if u.perfil == "solicitante"]

        total_chamados = 0
        try:
            resultado_agregacao = db.collection("chamados").count().get()
            total_chamados = resultado_agregacao[0][0].value
        except Exception as e:
            logger.warning("Erro ao contar total de chamados (admin_global): %s", e)

        return render_template(
            "admin_global.html",
            sub_admins=sub_admins,
            supervisores=supervisores,
            solicitantes=solicitantes,
            total_chamados=total_chamados,
            total_usuarios=len(todos_usuarios),
        )
    except Exception as e:
        logger.exception("Erro ao carregar admin_global dashboard: %s", e)
        flash_t("error_server", "danger")
        return redirect(url_for("main.admin"))


@main.route("/admin-global/admins/<usuario_id>/rebaixar", methods=["POST"])
@login_required
def admin_global_rebaixar_admin(usuario_id: str) -> Response:
    """Rebaixa um sub-admin para supervisor."""
    if current_user.perfil != "admin_global":
        flash_t("access_denied_profiles", "danger", profiles="admin_global")
        return redirect(url_for("main.admin"))

    try:
        usuario = Usuario.get_by_id(usuario_id)
        if not usuario or usuario.perfil != "admin":
            flash_t("user_not_found", "danger")
            return redirect(url_for("main.admin_global_dashboard"))
        usuario.update(perfil="supervisor", **_kwargs_reset_onboarding(usuario, "supervisor"))
        _disparar_notificacao_mudanca_perfil(usuario, "supervisor")
        logger.info(
            "admin_global %s rebaixou %s para supervisor", current_user.email, usuario.email
        )
        flash_t("user_updated_success", "success", nome=usuario.nome)
    except Exception as e:
        logger.exception("Erro ao rebaixar admin %s: %s", usuario_id, e)
        flash_t("error_server", "danger")
    return redirect(url_for("main.admin_global_dashboard"))


@main.route("/admin-global/admins/<usuario_id>/promover", methods=["POST"])
@login_required
def admin_global_promover_supervisor(usuario_id: str) -> Response:
    """Promove supervisor para sub-admin."""
    if current_user.perfil != "admin_global":
        flash_t("access_denied_profiles", "danger", profiles="admin_global")
        return redirect(url_for("main.admin"))

    try:
        usuario = Usuario.get_by_id(usuario_id)
        if not usuario or usuario.perfil != "supervisor":
            flash_t("user_not_found", "danger")
            return redirect(url_for("main.admin_global_dashboard"))
        usuario.update(perfil="admin", **_kwargs_reset_onboarding(usuario, "admin"))
        _disparar_notificacao_mudanca_perfil(usuario, "admin")
        logger.info("admin_global %s promoveu %s para admin", current_user.email, usuario.email)
        flash_t("user_updated_success", "success", nome=usuario.nome)
    except Exception as e:
        logger.exception("Erro ao promover supervisor %s: %s", usuario_id, e)
        flash_t("error_server", "danger")
    return redirect(url_for("main.admin_global_dashboard"))
