"""
Decoradores para controle de acesso baseado em perfil (RBAC)

Uso:
    @requer_perfil('admin')  # Apenas admins
    @requer_perfil(['supervisor', 'admin'])  # Supervisores ou admins
    @requer_supervisor_area  # Supervisor pode ver/editar apenas sua área
"""

import logging
from functools import wraps

from flask import current_app, jsonify, redirect, request, url_for
from flask_login import current_user

from app.i18n import flash_t

logger = logging.getLogger(__name__)


def _resposta_api_acesso_negado(codigo: int):
    """Retorna o contrato JSON de autenticação/autorização das rotas REST."""
    from app.i18n import get_translation_session

    return jsonify(
        {"sucesso": False, "erro": get_translation_session("unauthorized_access")}
    ), codigo


def requer_perfil(*perfis_permitidos):
    """
    Decorador que verifica se o usuário tem um dos perfis permitidos

    Parâmetros:
        *perfis_permitidos: String ou lista de strings com os perfis permitidos
                            Exemplos: 'admin', 'supervisor', ['admin', 'supervisor']

    Exemplo:
        @requer_perfil('admin')
        def rota_admin():
            pass

        @requer_perfil('supervisor', 'admin')
        def rota_gestao():
            pass
    """

    def decorador(f):
        @wraps(f)
        def funcao_decorada(*args, **kwargs):
            # Se não está autenticado, redireciona para login
            if not current_user.is_authenticated:
                logger.warning(
                    "Acesso negado: usuário não autenticado tentou acessar %s", f.__name__
                )
                if request.path.startswith("/api/"):
                    return _resposta_api_acesso_negado(401)
                flash_t("login_required_msg", "danger")
                return redirect(url_for("main.login"))

            # Normaliza perfis_permitidos para uma lista
            perfis_lista = []
            for perfil in perfis_permitidos:
                if isinstance(perfil, list | tuple):
                    perfis_lista.extend(perfil)
                else:
                    perfis_lista.append(perfil)

            # admin_global herda tudo que admin tem
            if "admin" in perfis_lista and "admin_global" not in perfis_lista:
                perfis_lista.append("admin_global")

            # Verifica se o perfil do usuário está na lista
            if current_user.perfil not in perfis_lista:
                logger.warning(
                    "Acesso negado: usuário %s (perfil %s) tentou acessar %s",
                    current_user.email,
                    current_user.perfil,
                    f.__name__,
                )
                flash_t("access_denied_profiles", "danger", profiles=", ".join(perfis_lista))

                # Redireciona para a página apropriada conforme o perfil
                if current_user.perfil == "solicitante":
                    return redirect(url_for("main.index"))
                if current_user.perfil == "supervisor":
                    return redirect(url_for("main.painel"))
                return redirect(url_for("main.admin"))

            # Perfil autorizado, executa a função
            return f(*args, **kwargs)

        return funcao_decorada

    return decorador


def requer_supervisor_area(f):
    """
    Decorador especial para verificar se é supervisor/admin
    Se for supervisor, adiciona filtro automático por área

    Uso:
        @requer_supervisor_area
        def rota_gestao():
            # current_user.area contém a área do supervisor
            # Você já pode usar current_user.area para filtrar
            pass
    """

    @wraps(f)
    def funcao_decorada(*args, **kwargs):
        # Se não está autenticado, redireciona para login
        if not current_user.is_authenticated:
            logger.warning("Acesso negado: usuário não autenticado tentou acessar %s", f.__name__)
            if request.path.startswith("/api/"):
                return _resposta_api_acesso_negado(401)
            flash_t("login_required_msg", "danger")
            return redirect(url_for("main.login"))

        # Apenas supervisores e admins podem acessar
        if current_user.perfil not in ["supervisor", "admin", "admin_global"]:
            logger.warning(
                "Acesso negado: solicitante %s tentou acessar %s",
                current_user.email,
                f.__name__,
            )
            if request.path.startswith("/api/"):
                return _resposta_api_acesso_negado(403)
            flash_t("access_denied_supervisors", "danger")
            return redirect(url_for("main.index"))

        # Se é supervisor, registra a área dele para uso posterior
        if current_user.perfil in ("supervisor",):
            current_app.logger.debug(
                f"Supervisor {current_user.email} acessando {f.__name__} (Área: {current_user.area})"
            )

        # Executa a função
        return f(*args, **kwargs)

    return funcao_decorada


def requer_supervisor_area_ou_gestor_setor(f):
    """Como requer_supervisor_area, mas também libera gestor_setor — mesmo
    "puro" (sem perfil supervisor) — usado só nas rotas de Ações de
    Escalonamento (transferir área/colega, incluir participantes), onde o
    gestor_setor pode agir em chamado do time que não é dele, restrito à
    própria área (decisão de escopo 2026-08-20). O escopo por área é
    responsabilidade do corpo da rota/service (aqui só libera pelo perfil/
    nivel_gestao, sem ainda ter o chamado em mãos).

    gerente_producao/assistente_gm/gm (company-wide) NÃO entram aqui —
    continuam 100% read-only.
    """

    @wraps(f)
    def funcao_decorada(*args, **kwargs):
        if not current_user.is_authenticated:
            logger.warning("Acesso negado: usuário não autenticado tentou acessar %s", f.__name__)
            if request.path.startswith("/api/"):
                return _resposta_api_acesso_negado(401)
            flash_t("login_required_msg", "danger")
            return redirect(url_for("main.login"))

        eh_gestor_setor = getattr(current_user, "nivel_gestao", None) == "gestor_setor"
        if (
            current_user.perfil not in ["supervisor", "admin", "admin_global"]
            and not eh_gestor_setor
        ):
            logger.warning(
                "Acesso negado: %s (%s) tentou acessar %s",
                current_user.email,
                current_user.perfil,
                f.__name__,
            )
            if request.path.startswith("/api/"):
                return _resposta_api_acesso_negado(403)
            flash_t("access_denied_supervisors", "danger")
            return redirect(url_for("main.index"))

        return f(*args, **kwargs)

    return funcao_decorada


def requer_solicitante(f):
    """
    Decorador para rotas de criação e listagem de chamados.
    Permite: solicitante, supervisor e admin (todos podem abrir e ver seus chamados).
    """

    @wraps(f)
    def funcao_decorada(*args, **kwargs):
        # Se não está autenticado, redireciona para login
        if not current_user.is_authenticated:
            logger.warning("Acesso negado: usuário não autenticado tentou acessar %s", f.__name__)
            flash_t("login_required_msg", "danger")
            return redirect(url_for("main.login"))

        # Solicitantes, supervisores e admins podem criar e ver seus chamados
        if current_user.perfil not in ("solicitante", "supervisor", "admin", "admin_global"):
            logger.warning(
                "Acesso negado: %s %s tentou acessar rota %s",
                current_user.perfil,
                current_user.email,
                f.__name__,
            )
            flash_t("access_denied_requesters", "danger")
            return redirect(url_for("main.login"))

        # Executa a função
        return f(*args, **kwargs)

    return funcao_decorada


def requer_gestor(f):
    """Exige que o usuário tenha nivel_gestao preenchido (is_gestor=True).

    Fail-closed: qualquer usuário sem nivel_gestao recebe flash + redirect.
    """

    @wraps(f)
    def funcao_decorada(*args, **kwargs):
        if not current_user.is_authenticated:
            logger.warning("Acesso negado: usuário não autenticado tentou acessar %s", f.__name__)
            flash_t("login_required_msg", "danger")
            return redirect(url_for("main.login"))

        if not getattr(current_user, "is_gestor", False):
            logger.warning(
                "Acesso negado: %s (%s) sem nivel_gestao tentou acessar %s",
                current_user.email,
                current_user.perfil,
                f.__name__,
            )
            flash_t("access_denied_profiles", "danger", profiles="gestor")
            if current_user.perfil == "solicitante":
                return redirect(url_for("main.index"))
            if current_user.perfil == "supervisor":
                return redirect(url_for("main.painel"))
            return redirect(url_for("main.admin"))

        return f(*args, **kwargs)

    return funcao_decorada


def requer_gestor_ou_admin(f):
    """Exige is_gestor OR is_admin_or_above.

    Usado no /gestor/dashboard: gestor acessa read-only; admin acessa com privilégios totais.
    Fail-closed: qualquer outro perfil recebe flash + redirect.
    """

    @wraps(f)
    def funcao_decorada(*args, **kwargs):
        if not current_user.is_authenticated:
            logger.warning("Acesso negado: usuário não autenticado tentou acessar %s", f.__name__)
            flash_t("login_required_msg", "danger")
            return redirect(url_for("main.login"))

        is_gestor = getattr(current_user, "is_gestor", False)
        is_admin = getattr(current_user, "is_admin_or_above", False)

        if not (is_gestor or is_admin):
            logger.warning(
                "Acesso negado: %s (%s) não é gestor nem admin, tentou acessar %s",
                current_user.email,
                current_user.perfil,
                f.__name__,
            )
            flash_t("access_denied_profiles", "danger", profiles="gestor, admin")
            if current_user.perfil == "solicitante":
                return redirect(url_for("main.index"))
            if current_user.perfil == "supervisor":
                return redirect(url_for("main.painel"))
            return redirect(url_for("main.admin"))

        return f(*args, **kwargs)

    return funcao_decorada
