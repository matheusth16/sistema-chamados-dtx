"""
Rotas organizadas em módulos. Blueprint único 'main' para manter url_for('main.xxx').
"""

from flask import Blueprint

main = Blueprint("main", __name__)

# Importa os módulos para registrar as rotas no blueprint
from app.routes import (  # noqa: E402
    admin_global,  # noqa: E402, F401
    api,  # noqa: E402, F401
    api_notificacoes,  # noqa: E402, F401
    auth,  # noqa: E402, F401
    categorias,  # noqa: E402, F401
    chamados,  # noqa: E402, F401
    dashboard,  # noqa: E402, F401
    mfa,  # noqa: E402, F401
    usuarios,  # noqa: E402, F401
)

# Exporta as views para CSRF exempt no create_app
from app.routes.api import atualizar_status_ajax, csp_report  # noqa: E402, F401

__all__ = ["main", "atualizar_status_ajax", "csp_report"]
