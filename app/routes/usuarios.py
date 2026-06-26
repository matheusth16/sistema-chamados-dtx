"""Rotas de gerenciamento de usuários (CRUD). Apenas para admins."""

import logging
import secrets
import string
import threading
import uuid

from flask import Response, current_app, redirect, render_template, request, url_for
from flask_login import current_user

from app.cache import cache_delete
from app.decoradores import requer_perfil
from app.i18n import flash_t
from app.models_categorias import CategoriaSetor
from app.models_usuario import CACHE_KEY_USUARIOS, Usuario
from app.routes import main
from app.services.notifications import notificar_novo_usuario_cadastrado
from app.services.notify_retry import executar_com_retry

logger = logging.getLogger(__name__)


def _gerar_senha_aleatoria(tamanho: int = 12) -> str:
    """Gera senha aleatória segura com maiúsculas, minúsculas, dígitos e símbolos.
    Garante ao menos 1 char de cada classe para satisfazer políticas de complexidade."""
    especiais = "!@#$%&*"
    alfabeto = string.ascii_letters + string.digits + especiais
    # Posições fixas garantem representação mínima de cada classe
    obrigatorios = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice(especiais),
    ]
    restante = [secrets.choice(alfabeto) for _ in range(tamanho - 4)]
    senha = obrigatorios + restante
    secrets.SystemRandom().shuffle(senha)
    return "".join(senha)


@main.route("/admin/usuarios", methods=["GET", "POST"])
@requer_perfil("admin")
def gerenciar_usuarios() -> Response:
    """GET: lista usuários. POST: cria usuário."""
    if request.method == "POST" and request.form.get("acao") == "criar":
        email = request.form.get("email", "").strip().lower()
        nome = request.form.get("nome", "").strip()
        perfil = request.form.get("perfil", "solicitante")
        areas = [a.strip() for a in request.form.getlist("areas") if a.strip()]
        nivel_gestao = request.form.get("nivel_gestao", "").strip() or None
        erros = []
        if not email or "@" not in email:
            erros.append("invalid_email")
        elif Usuario.email_existe(email):
            erros.append("email_exists")
        if not nome or len(nome) < 3:
            erros.append("name_min_chars")
        if perfil not in ["solicitante", "supervisor", "admin"]:
            erros.append("invalid_profile")
        if perfil == "supervisor" and not areas:
            erros.append("area_required_for_supervisor")
        # Sub-admins não podem criar outros admins — apenas admin_global pode
        if perfil == "admin" and current_user.perfil != "admin_global":
            erros.append("access_denied_create_admin")
        if erros:
            for e in erros:
                flash_t(e, "danger")
            return redirect(url_for("main.gerenciar_usuarios"))
        try:
            senha_inicial = _gerar_senha_aleatoria()
            u = Usuario(
                id=f"user_{uuid.uuid4().hex}",
                email=email,
                nome=nome,
                perfil=perfil,
                areas=areas,
                nivel_gestao=nivel_gestao,
                must_change_password=True,
                password_changed_at=None,
            )
            u.set_password(senha_inicial)
            u.save()
            cache_delete(CACHE_KEY_USUARIOS)
            Usuario.invalidar_cache_supervisores_por_area()

            _app = current_app._get_current_object()

            def _notificar_novo_usuario():
                with _app.app_context():
                    executar_com_retry(
                        notificar_novo_usuario_cadastrado,
                        usuario_id=u.id,
                        usuario_email=u.email,
                        usuario_nome=u.nome,
                        perfil=u.perfil,
                        areas=u.areas,
                        senha_inicial=senha_inicial,
                    )

            threading.Thread(target=_notificar_novo_usuario, daemon=True).start()
            flash_t("user_created_success", "success", nome=nome)
            return redirect(url_for("main.gerenciar_usuarios"))
        except Exception as e:
            logger.exception("Erro ao criar usuário: %s", e)
            flash_t("error_creating_user", "danger", error=str(e))
            return redirect(url_for("main.gerenciar_usuarios"))
    try:
        usuarios = Usuario.get_all()
        return render_template("usuarios.html", usuarios=usuarios)
    except Exception as e:
        logger.exception("Erro ao listar usuários: %s", e)
        flash_t("error_loading_users", "danger")
        return redirect(url_for("main.admin"))  # lista de usuários é exclusiva do admin


@main.route("/admin/usuarios/novo", methods=["GET"])
@requer_perfil("admin")
def novo_usuario_form() -> Response:
    """Exibe formulário de criação de usuário."""
    setores = [s for s in CategoriaSetor.get_all() if getattr(s, "ativo", True)]
    return render_template("usuario_form.html", usuario=None, setores=setores)


@main.route("/admin/usuarios/<usuario_id>/editar", methods=["GET", "POST"])
@requer_perfil("admin")
def editar_usuario(usuario_id: str) -> Response:
    """GET: exibe formulário de edição. POST: edita usuário."""
    try:
        usuario = Usuario.get_by_id(usuario_id)
        if not usuario:
            flash_t("user_not_found", "danger")
            return redirect(url_for("main.gerenciar_usuarios"))
        if request.method == "GET":
            setores = [s for s in CategoriaSetor.get_all() if getattr(s, "ativo", True)]
            setor_names = {s.nome_pt for s in setores}
            areas_usuario = usuario.areas if getattr(usuario, "areas", None) else []
            areas_extra = [a for a in areas_usuario if a and a not in setor_names]
            return render_template(
                "usuario_form.html", usuario=usuario, setores=setores, areas_extra=areas_extra
            )
        email = request.form.get("email", "").strip().lower()
        nome = request.form.get("nome", "").strip()
        perfil = request.form.get("perfil", usuario.perfil)
        areas = [a.strip() for a in request.form.getlist("areas") if a.strip()]
        erros = []
        if email and email != usuario.email:
            if "@" not in email:
                erros.append("invalid_email")
            elif Usuario.email_existe(email, usuario_id):
                erros.append("email_exists")
        if not nome or len(nome) < 3:
            erros.append("name_min_chars")
        if perfil not in ["solicitante", "supervisor", "admin"]:
            erros.append("invalid_profile")
        if perfil == "supervisor" and not areas:
            erros.append("area_required_for_supervisor")
        # Sub-admins não podem promover para admin — apenas admin_global pode
        if perfil == "admin" and current_user.perfil != "admin_global":
            erros.append("access_denied_create_admin")
        if erros:
            for e in erros:
                flash_t(e, "danger")
            return redirect(url_for("main.gerenciar_usuarios"))
        update_data = {}
        if email and email != usuario.email:
            update_data["email"] = email
        if nome:
            update_data["nome"] = nome
        if perfil:
            update_data["perfil"] = perfil
        if set(areas) != set(usuario.areas):
            update_data["areas"] = areas
        # Checkbox ativo: presente no form → True; ausente → False
        novo_ativo = request.form.get("ativo") == "on"
        if novo_ativo != getattr(usuario, "ativo", True):
            update_data["ativo"] = novo_ativo
        # nivel_gestao: campo opcional select (vazio = None = sem gestão)
        novo_nivel_gestao = request.form.get("nivel_gestao", "").strip() or None
        if novo_nivel_gestao != getattr(usuario, "nivel_gestao", None):
            update_data["nivel_gestao"] = novo_nivel_gestao
        if update_data:
            usuario.update(**update_data)
            cache_delete(CACHE_KEY_USUARIOS)
            cache_delete(f"usuario_{usuario_id}")
            Usuario.invalidar_cache_supervisores_por_area()
        flash_t("user_updated_success", "success", nome=nome)
        return redirect(url_for("main.gerenciar_usuarios"))
    except Exception as e:
        logger.exception("Erro ao editar usuário: %s", e)
        flash_t("error_editing_user", "danger", error=str(e))
        return redirect(url_for("main.gerenciar_usuarios"))


@main.route("/admin/usuarios/<usuario_id>/deletar", methods=["POST"])
@requer_perfil("admin")
def deletar_usuario(usuario_id: str) -> Response:
    """Deleta usuário (exceto admin@dtx.aero)."""
    try:
        usuario = Usuario.get_by_id(usuario_id)
        if not usuario:
            flash_t("user_not_found", "danger")
            return redirect(url_for("main.gerenciar_usuarios"))
        if usuario_id == current_user.id:
            flash_t("cannot_delete_own_account", "warning")
            return redirect(url_for("main.gerenciar_usuarios"))
        if usuario.email == "admin@dtx.aero":
            flash_t("cannot_delete_root_admin", "danger")
            logger.warning(
                "Tentativa de deletar admin@dtx.aero por %s",
                current_user.email,
            )
            return redirect(url_for("main.gerenciar_usuarios"))
        nome_usuario = usuario.nome
        usuario.delete()
        cache_delete(CACHE_KEY_USUARIOS)
        cache_delete(f"usuario_{usuario_id}")
        Usuario.invalidar_cache_supervisores_por_area()
        flash_t("user_deleted_success", "success", nome=nome_usuario)
        return redirect(url_for("main.gerenciar_usuarios"))
    except Exception as e:
        logger.exception("Erro ao deletar usuário: %s", e)
        flash_t("error_deleting_user", "danger", error=str(e))
        return redirect(url_for("main.gerenciar_usuarios"))


@main.route("/admin/alterar-senha", methods=["GET", "POST"])
@requer_perfil("admin")
def alterar_senha_admin() -> Response:
    """GET: exibe formulário de troca de senha. POST: aplica nova senha ao próprio perfil."""
    from datetime import datetime

    if request.method == "POST":
        senha_atual = request.form.get("senha_atual", "").strip()
        nova_senha = request.form.get("nova_senha", "").strip()
        confirmar_senha = request.form.get("confirmar_senha", "").strip()

        if not senha_atual or not nova_senha or not confirmar_senha:
            flash_t("all_fields_required", "danger")
            return redirect(url_for("main.alterar_senha_admin"))

        if not current_user.check_password(senha_atual):
            flash_t("current_password_incorrect", "danger")
            return redirect(url_for("main.alterar_senha_admin"))

        if len(nova_senha) < 8:
            flash_t("password_min_8_chars", "danger")
            return redirect(url_for("main.alterar_senha_admin"))

        if not any(c.isalpha() for c in nova_senha) or not any(c.isdigit() for c in nova_senha):
            flash_t("password_must_have_letter_and_digit", "danger")
            return redirect(url_for("main.alterar_senha_admin"))

        if nova_senha != confirmar_senha:
            flash_t("passwords_must_match", "danger")
            return redirect(url_for("main.alterar_senha_admin"))

        try:
            sucesso = current_user.update(
                senha=nova_senha,
                must_change_password=False,
                password_changed_at=datetime.now(),
            )
            if sucesso:
                logger.info("Admin %s alterou a própria senha.", current_user.email)
                flash_t("password_changed_admin_success", "success")
            else:
                flash_t("error_updating_password", "danger")
        except Exception as e:
            logger.exception("Erro ao alterar senha do admin %s: %s", current_user.email, e)
            flash_t("error_updating_password", "danger")

        return redirect(url_for("main.alterar_senha_admin"))

    return render_template("alterar_senha_admin.html")


@main.route("/admin/usuarios/<usuario_id>/resetar-senha", methods=["POST"])
@requer_perfil("admin")
def resetar_senha_usuario(usuario_id: str) -> Response:
    """Reseta a senha de um usuário para uma senha aleatória e notifica por e-mail."""
    try:
        usuario = Usuario.get_by_id(usuario_id)
        if not usuario:
            flash_t("user_not_found", "danger")
            return redirect(url_for("main.gerenciar_usuarios"))

        if usuario_id == current_user.id:
            flash_t("cannot_reset_own_password", "warning")
            return redirect(url_for("main.gerenciar_usuarios"))

        nome_usuario = usuario.nome
        senha_inicial = _gerar_senha_aleatoria()
        usuario.set_password(senha_inicial)
        usuario.update(must_change_password=True)

        cache_delete(CACHE_KEY_USUARIOS)
        cache_delete(f"usuario_{usuario_id}")

        logger.info(
            "Senha resetada para %s por %s",
            usuario.email,
            current_user.email,
        )

        _app = current_app._get_current_object()
        _u_email = usuario.email
        _u_nome = usuario.nome
        _u_perfil = usuario.perfil
        _u_areas = list(getattr(usuario, "areas", []) or [])
        _u_id = usuario.id

        def _notificar_reset():
            with _app.app_context():
                executar_com_retry(
                    notificar_novo_usuario_cadastrado,
                    usuario_id=_u_id,
                    usuario_email=_u_email,
                    usuario_nome=_u_nome,
                    perfil=_u_perfil,
                    areas=_u_areas,
                    senha_inicial=senha_inicial,
                )

        threading.Thread(target=_notificar_reset, daemon=True).start()

        flash_t("user_password_reset_success", "success", nome=nome_usuario)
        return redirect(url_for("main.gerenciar_usuarios"))

    except Exception as e:
        logger.exception("Erro ao resetar senha do usuário: %s", e)
        flash_t("error_resetting_password", "danger", error=str(e))
        return redirect(url_for("main.gerenciar_usuarios"))


@main.route("/admin/usuarios/<usuario_id>/desativar", methods=["POST"])
@requer_perfil("admin")
def desativar_usuario(usuario_id: str) -> Response:
    """Soft-delete: marca ativo=False, bloqueando login e invalidando sessão."""
    try:
        usuario = Usuario.get_by_id(usuario_id)
        if not usuario:
            flash_t("user_not_found", "danger")
            return redirect(url_for("main.gerenciar_usuarios"))
        if usuario_id == current_user.id:
            flash_t("cannot_deactivate_own_account", "warning")
            return redirect(url_for("main.gerenciar_usuarios"))
        if usuario.email == "admin@dtx.aero":
            flash_t("cannot_deactivate_root_admin", "danger")
            logger.warning("Tentativa de desativar admin@dtx.aero por %s", current_user.email)
            return redirect(url_for("main.gerenciar_usuarios"))
        nome_usuario = usuario.nome
        usuario.update(ativo=False)
        cache_delete(CACHE_KEY_USUARIOS)
        cache_delete(f"usuario_{usuario_id}")
        Usuario.invalidar_cache_supervisores_por_area()
        flash_t("user_deactivated_success", "success", nome=nome_usuario)
        return redirect(url_for("main.gerenciar_usuarios"))
    except Exception as e:
        logger.exception("Erro ao desativar usuário: %s", e)
        flash_t("error_editing_user", "danger", error=str(e))
        return redirect(url_for("main.gerenciar_usuarios"))


@main.route("/admin/usuarios/<usuario_id>/ativar", methods=["POST"])
@requer_perfil("admin")
def ativar_usuario(usuario_id: str) -> Response:
    """Reativa conta: marca ativo=True, permitindo login novamente."""
    try:
        usuario = Usuario.get_by_id(usuario_id)
        if not usuario:
            flash_t("user_not_found", "danger")
            return redirect(url_for("main.gerenciar_usuarios"))
        nome_usuario = usuario.nome
        usuario.update(ativo=True)
        cache_delete(CACHE_KEY_USUARIOS)
        cache_delete(f"usuario_{usuario_id}")
        Usuario.invalidar_cache_supervisores_por_area()
        flash_t("user_activated_success", "success", nome=nome_usuario)
        return redirect(url_for("main.gerenciar_usuarios"))
    except Exception as e:
        logger.exception("Erro ao reativar usuário: %s", e)
        flash_t("error_editing_user", "danger", error=str(e))
        return redirect(url_for("main.gerenciar_usuarios"))


@main.route("/admin/usuarios/<usuario_id>/reset-exp", methods=["POST"])
@requer_perfil("admin")
def resetar_exp_usuario(usuario_id: str) -> Response:
    """Zera a experiência e nível do usuário."""
    try:
        usuario = Usuario.get_by_id(usuario_id)
        if not usuario:
            flash_t("user_not_found", "danger")
            return redirect(url_for("main.gerenciar_usuarios"))

        nome_usuario = usuario.nome
        usuario.update(
            gamification={"exp_total": 0, "exp_semanal": 0, "level": 1, "conquistas": []}
        )

        cache_delete(CACHE_KEY_USUARIOS)
        cache_delete(f"usuario_{usuario_id}")
        Usuario.invalidar_cache_supervisores_por_area()

        # Opcional: deletar cache do ranking
        cache_delete("ranking_gamificacao_semanal")

        flash_t("user_exp_reset_success", "success", nome=nome_usuario)
        return redirect(url_for("main.gerenciar_usuarios"))

    except Exception as e:
        logger.exception("Erro ao resetar EXP do usuário: %s", e)
        flash_t("error_resetting_exp", "danger", error=str(e))
        return redirect(url_for("main.gerenciar_usuarios"))
