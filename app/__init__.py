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

    # Desabilita cache de arquivos estáticos em desenvolvimento
    if app.config.get('ENV') == 'development' or app.debug:
        app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

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

    # Rotas /api/* sem login retornam 401 JSON em vez de redirect (para clientes AJAX/SPA)
    @login_manager.unauthorized_handler
    def unauthorized():
        from flask import request, jsonify, redirect, url_for, flash
        if request.path.startswith('/api/'):
            return jsonify({'sucesso': False, 'requer_login': True, 'erro': 'Login necessário'}), 401
        flash(login_manager.login_message, login_manager.login_message_category or 'info')
        return redirect(url_for(login_manager.login_view))

    # Configuração de i18n (Internacionalização)
    _configurar_i18n(app)

    # Importa e registra as rotas
    from app.routes import main
    app.register_blueprint(main)

    # Segurança: headers e validação Origin/Referer em POST sensíveis
    _configurar_seguranca(app)
    
    # Timeout de inatividade (15 minutos)
    _configurar_timeout_sessao(app)

    # 404 amigável para anexos em /static/uploads/ (arquivo não encontrado → página "Anexo não disponível")
    _configurar_erro_404(app)

    # API de status exige CSRF; o frontend envia o token no header X-CSRFToken (meta csrf-token)

    # Firebase é inicializado em app/database.py
    # Não há tabelas para criar (Firestore é NoSQL)
    
    return app


def _configurar_erro_404(app: Flask) -> None:
    """Resposta amigável para 404. Requisições a /static/uploads/ sem arquivo exibem 'Anexo não disponível'."""
    from flask import render_template, request

    @app.errorhandler(404)
    def pagina_nao_encontrada(e):
        if request.path.startswith('/static/uploads/'):
            return render_template('erro_anexo_nao_encontrado.html'), 404
        return render_template('erro_404.html'), 404


def _configurar_seguranca(app: Flask) -> None:
    """
    Configura headers de segurança e validação Origin/Referer em POST sensíveis.
    
    Implementa:
    1. Headers de segurança (X-Content-Type-Options, X-Frame-Options, HSTS)
    2. Validação Origin/Referer para rotas POST críticas
    
    A validação é ativada quando APP_BASE_URL está definida em config.
    Impede ataques CSRF através de forjamento de origem.
    """
    from flask import current_app

    @app.after_request
    def _adicionar_headers_seguranca(response):
        """Adiciona headers de segurança a todas as respostas."""
        response.headers['X-Content-Type-Options'] = 'nosniff'  # Impede MIME sniffing
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'      # Proteção contra clickjacking
        if request.is_secure and current_app.env == 'production':
            # HSTS força HTTPS em conexões futuras (31536000 = 1 ano)
            response.headers['Strict-Transport-Security'] = (
                'max-age=31536000; includeSubDomains'
            )
        return response

    @app.before_request
    def _validar_origin_referer():
        """
        Valida Origin/Referer para POST em rotas sensíveis.
        
        Se APP_BASE_URL está definida em config:
        - Rejeita requisições POST de origem diferente
        - Usa headers Origin (moderno) ou Referer (fallback)
        - Registra tentativas suspeitas em logs
        
        Rotas protegidas (quando APP_BASE_URL está configurada):
        - /api/atualizar-status
        - /api/bulk-status
        - /api/push-subscribe
        - /api/carregar-mais
        - /api/notificacoes/*/ler
        
        Examples:
            GET /admin    → Passa (não é POST)
            POST /api/atualizar-status com Origin válida    → Passa
            POST /api/atualizar-status com Origin inválida  → 403 Forbidden
            POST /api/atualizar-status sem Origin/Referer   → 403 Forbidden
        """
        # Obtém URL base configurada (ex: https://sistema-chamados.dtx.com)
        base_url = (current_app.config.get('APP_BASE_URL') or '').strip()
        
        # Se não está configurada ou não é POST, pula validação
        if not base_url or request.method != 'POST':
            return None
        
        # Verifica se a rota é crítica (precisa validação)
        path = request.path
        eh_rota_critica = (
            path in _POST_ORIGIN_CHECK_PATHS or
            (path.startswith('/api/notificacoes/') and path.endswith('/ler'))
        )
        
        if not eh_rota_critica:
            return None
        
        # ============================================================
        # VALIDAÇÃO DE ORIGEM
        # ============================================================
        
        try:
            # Parse URL base para obter scheme + netloc (ex: https://sistema-chamados.dtx.com)
            base_parsed = urlparse(base_url)
            base_origin = f"{base_parsed.scheme or 'https'}://{base_parsed.netloc}".lower()
        except Exception as e:
            app.logger.error(f"Erro ao parsear APP_BASE_URL '{base_url}': {e}")
            return None
        
        # Obtém origin da requisição (tenta Origin header primeiro, depois Referer)
        origin_header = request.headers.get('Origin', '').strip().lower()
        referer_header = request.headers.get('Referer', '').strip().lower()
        origin = origin_header or referer_header
        
        # ============================================================
        # REJEITA SE: Sem origin E sem referer
        # ============================================================
        if not origin:
            app.logger.warning(
                f"[CSRF] POST {path} sem Origin/Referer. "
                f"IP: {request.remote_addr}. User Agent: {request.user_agent}"
            )
            return jsonify({
                'sucesso': False,
                'erro': 'Origem não informada'
            }), 403
        
        # ============================================================
        # VALIDA A ORIGEM
        # ============================================================
        
        try:
            req_parsed = urlparse(origin)
            req_origin = f"{req_parsed.scheme}://{req_parsed.netloc}".lower()
        except Exception as e:
            app.logger.error(f"Erro ao parsear origin '{origin}': {e}")
            req_origin = ''
        
        # Compara origem da requisição com a autorizada
        if req_origin and req_origin != base_origin:
            app.logger.warning(
                f"[CSRF] POST {path} de origem não autorizada. "
                f"Origem: {req_origin}, Autorizada: {base_origin}. "
                f"IP: {request.remote_addr}"
            )
            return jsonify({
                'sucesso': False,
                'erro': 'Origem não autorizada'
            }), 403
        
        # Passou na validação
        return None

def _configurar_i18n(app: Flask) -> None:
    """Configura sistema de internacionalização (i18n)"""
    from flask import session
    from app.i18n import get_translation, get_translated_sector, get_translated_category, get_translated_status

    def translate_sector_filter(sector_name):
        """Traduz setor para o idioma da sessão. Usado como função no contexto e como filter (map) no Jinja."""
        if not sector_name:
            return sector_name
        lang = session.get('language', 'pt_BR')
        return get_translated_sector(sector_name, lang)

    app.jinja_env.filters['translate_sector'] = translate_sector_filter

    @app.before_request
    def antes_da_requisicao():
        """Define o idioma para a requisição atual"""
        # Obtém idioma do parâmetro URL ou da sessão
        lang = request.args.get('lang') or session.get('language', 'pt_BR')
        session['language'] = lang
    
    @app.context_processor
    def inject_i18n():
        """Injeta função de tradução e idioma no contexto Jinja"""
        def t(key, **kwargs):
            """Função para traduzir uma chave no template. Aceita kwargs para formatação (ex: area=..., nome=..., pct=...)."""
            lang = session.get('language', 'pt_BR')
            return get_translation(key, lang, **kwargs)

        def translate_category(category_name):
            """Traduz o nome de uma categoria no template"""
            lang = session.get('language', 'pt_BR')
            return get_translated_category(category_name, lang)
        
        def translate_status(status_name):
            """Traduz o status de um chamado no template"""
            lang = session.get('language', 'pt_BR')
            return get_translated_status(status_name, lang)

        def nome_curto(nome):
            """Retorna versão curta do nome para exibição (ex.: 'Maria Santos' -> 'Maria S.')."""
            if not nome or not isinstance(nome, str):
                return None
            nome = nome.strip()
            if not nome:
                return None
            partes = nome.split()
            if len(partes) >= 2:
                return f"{partes[0]} {partes[-1][0]}."
            return nome[:25] + ('...' if len(nome) > 25 else '')

        return dict(
            t=t,
            translate_sector=translate_sector_filter,
            translate_category=translate_category,
            translate_status=translate_status,
            nome_curto=nome_curto,
            current_language=session.get('language', 'pt_BR'),
            get_supported_languages=lambda: {
                'pt_BR': 'Português (Brasil)',
                'en': 'English',
                'es': 'Español'
            }
        )

def _configurar_timeout_sessao(app: Flask) -> None:
    """Configura logout automático por inatividade de sessão (15 minutos)"""
    from flask import session, redirect, url_for, flash, request
    from flask_login import current_user, logout_user
    from datetime import datetime, timezone
    
    @app.before_request
    def checar_inatividade():
        # Ignora rotas de arquivos estáticos
        if request.endpoint and request.endpoint.startswith('static'):
            return None
            
        if current_user.is_authenticated:
            # Pega o timestamp atual
            agora = datetime.now(timezone.utc).timestamp()
            limite_segundos = 900  # 15 minutos
            
            ultima_atividade = session.get('last_activity')
            
            # Checa se excedeu os 15 minutos sem atividade
            if ultima_atividade is not None and (agora - ultima_atividade > limite_segundos):
                logout_user()
                session.clear() # Limpa a sessão
                flash('Sua sessão expirou por inatividade. Faça login novamente.', 'info')
                # Redireciona para login e impede a requisição atual de continuar
                return redirect(url_for('main.login'))
                
            # Atualiza o timestamp da última atividade da sessão com a hora atual
            session['last_activity'] = agora


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