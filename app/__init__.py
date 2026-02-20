from flask import Flask, session, request, jsonify
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from config import Config
import logging
from logging.handlers import RotatingFileHandler
from pythonjsonlogger import jsonlogger
from urllib.parse import urlparse
import os

# Rotas POST sensíveis que devem validar Origin/Referer quando APP_BASE_URL estiver definido
_POST_ORIGIN_CHECK_PATHS = frozenset({
    '/api/atualizar-status',
    '/api/bulk-status',
    '/api/push-subscribe',
    '/api/carregar-mais',
})


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Inicializa CSRF Protection
    csrf = CSRFProtect(app)

    # Rate Limiting (limiter definido em app.limiter, usado pelos blueprints)
    from app.limiter import limiter
    limiter.init_app(app)

    # Configura Logging Estruturado (com rotação e nível configurável)
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

    # Segurança: headers e validação Origin/Referer em POST sensíveis
    _configurar_seguranca(app)

    # API de status exige CSRF; o frontend envia o token no header X-CSRFToken (meta csrf-token)

    # Firebase é inicializado em app/database.py
    # Não há tabelas para criar (Firestore é NoSQL)
    
    return app


def _configurar_seguranca(app: Flask) -> None:
    """Configura headers de segurança e validação Origin/Referer em POST sensíveis."""
    from flask import current_app

    @app.after_request
    def _adicionar_headers_seguranca(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        if request.is_secure and current_app.env == 'production':
            response.headers['Strict-Transport-Security'] = (
                'max-age=31536000; includeSubDomains'
            )
        return response

    @app.before_request
    def _validar_origin_referer():
        """Rejeita POST sensíveis de origens não autorizadas quando APP_BASE_URL está definido."""
        base_url = (current_app.config.get('APP_BASE_URL') or '').strip()
        if not base_url or request.method != 'POST':
            return None
        path = request.path
        if path not in _POST_ORIGIN_CHECK_PATHS and not (
            path.startswith('/api/notificacoes/') and path.endswith('/ler')
        ):
            return None
        try:
            base_parsed = urlparse(base_url)
            base_origin = f"{base_parsed.scheme or 'https'}://{base_parsed.netloc}".lower()
        except Exception:
            return None
        origin = request.headers.get('Origin') or request.headers.get('Referer') or ''
        if not origin:
            return None
        try:
            req_parsed = urlparse(origin)
            req_origin = f"{req_parsed.scheme}://{req_parsed.netloc}".lower()
        except Exception:
            req_origin = ''
        if req_origin and req_origin != base_origin:
            return jsonify({'sucesso': False, 'erro': 'Origem não autorizada'}), 403
        return None

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
    """Configura logging estruturado em JSON com rotação e nível configurável (LOG_LEVEL)."""
    app.logger.handlers.clear()

    basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    log_dir = os.path.join(basedir, 'logs')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_level_name = app.config.get('LOG_LEVEL', 'INFO').upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    app.logger.setLevel(log_level)

    max_bytes = app.config.get('LOG_MAX_BYTES', 2 * 1024 * 1024)
    backup_count = app.config.get('LOG_BACKUP_COUNT', 5)
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, 'sistema_chamados.log'),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8',
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(jsonlogger.JsonFormatter())
    app.logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    ))
    app.logger.addHandler(console_handler)