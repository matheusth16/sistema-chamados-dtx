"""
Rotas organizadas em módulos. Blueprint único 'main' para manter url_for('main.xxx').
"""
from flask import Blueprint

main = Blueprint('main', __name__)

# Importa os módulos para registrar as rotas no blueprint
from app.routes import auth        # noqa: E402, F401
from app.routes import chamados    # noqa: E402, F401
from app.routes import dashboard   # noqa: E402, F401
from app.routes import usuarios    # noqa: E402, F401
from app.routes import categorias  # noqa: E402, F401
from app.routes import traducoes   # noqa: E402, F401
from app.routes import api         # noqa: E402, F401

# Exporta a view para CSRF exempt no create_app
from app.routes.api import atualizar_status_ajax  # noqa: E402, F401

__all__ = ['main', 'atualizar_status_ajax']
