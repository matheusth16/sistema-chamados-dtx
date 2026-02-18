from flask import Flask
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from config import Config
import logging
from pythonjsonlogger import jsonlogger
import os

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Inicializa CSRF Protection
    csrf = CSRFProtect(app)

    # Inicializa Rate Limiting
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="memory://",
        storage_options={}
    )

    # Configura Logging Estruturado
    _configurar_logging(app)

    # Inicializa Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'main.login'  # Redireciona para login se não autenticado
    login_manager.login_message = 'Por favor, faça login para continuar.'
    login_manager.login_message_category = 'info'
    
    # Carregador de usuários para Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        from app.models_usuario import Usuario
        return Usuario.get_by_id(user_id)

    # Importa e registra as rotas
    from app.routes import main
    app.register_blueprint(main)

    # API AJAX já é protegida por @login_required; isenta de CSRF para fetch com JSON
    from app.routes import atualizar_status_ajax
    csrf.exempt(atualizar_status_ajax)

    # Firebase é inicializado em app/database.py
    # Não há tabelas para criar (Firestore é NoSQL)
    
    return app


def _configurar_logging(app: Flask) -> None:
    """Configura logging estruturado em formato JSON"""
    # Remove handlers padrão
    app.logger.handlers.clear()
    
    # Cria pasta de logs se não existir
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Handler para arquivo com formato JSON
    file_handler = logging.FileHandler(os.path.join(log_dir, 'sistema_chamados.log'))
    file_handler.setLevel(logging.INFO)
    
    # Formatter JSON estruturado
    json_formatter = jsonlogger.JsonFormatter()
    file_handler.setFormatter(json_formatter)
    
    # Handler para console em desenvolvimento
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    
    # Adiciona handlers ao logger da aplicação
    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)
    app.logger.setLevel(logging.DEBUG)