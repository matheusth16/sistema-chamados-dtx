from flask import Flask, session, request
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from config import Config
import logging
from pythonjsonlogger import jsonlogger
import os

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Inicializa CSRF Protection
    csrf = CSRFProtect(app)

    # Rate Limiting (limiter definido em app.limiter, usado pelos blueprints)
    from app.limiter import limiter
    limiter.init_app(app)

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

    # Configuração de i18n (Internacionalização)
    _configurar_i18n(app)

    # Importa e registra as rotas
    from app.routes import main
    app.register_blueprint(main)

    # API AJAX já é protegida por @login_required; isenta de CSRF para fetch com JSON
    from app.routes import atualizar_status_ajax
    csrf.exempt(atualizar_status_ajax)

    # Firebase é inicializado em app/database.py
    # Não há tabelas para criar (Firestore é NoSQL)
    
    return app

def _configurar_i18n(app: Flask) -> None:
    """Configura sistema de internacionalização (i18n)"""
    from app.i18n import get_translation, get_translated_sector, get_translated_category
    
    @app.before_request
    def antes_da_requisicao():
        """Define o idioma para a requisição atual"""
        # Obtém idioma do parâmetro URL ou da sessão
        lang = request.args.get('lang') or session.get('language', 'pt_BR')
        session['language'] = lang
    
    @app.context_processor
    def inject_i18n():
        """Injeta função de tradução e idioma no contexto Jinja"""
        def t(key):
            """Função para traduzir uma chave no template"""
            lang = session.get('language', 'pt_BR')
            return get_translation(key, lang)
        
        def translate_sector(sector_name):
            """Traduz o nome de um setor no template"""
            lang = session.get('language', 'pt_BR')
            return get_translated_sector(sector_name, lang)
        
        def translate_category(category_name):
            """Traduz o nome de uma categoria no template"""
            lang = session.get('language', 'pt_BR')
            return get_translated_category(category_name, lang)
        
        return dict(
            t=t,
            translate_sector=translate_sector,
            translate_category=translate_category,
            current_language=session.get('language', 'pt_BR'),
            get_supported_languages=lambda: {
                'pt_BR': 'Português (Brasil)',
                'en': 'English',
                'es': 'Español'
            }
        )


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