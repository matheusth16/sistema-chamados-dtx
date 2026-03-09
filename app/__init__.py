from flask import Flask, session, request, jsonify, g
from flask_login import LoginManager
import secrets
from flask_wtf.csrf import CSRFProtect
from config import Config
import logging
import time
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

    # Configuração de i18n (Internacionalização)
    _configurar_i18n(app)

    # Importa e registra as rotas
    from app.routes import main
    app.register_blueprint(main)

    # Segurança: headers e validação Origin/Referer em POST sensíveis
    _configurar_seguranca(app)
    
    # Timeout de inatividade (15 minutos)
    _configurar_timeout_sessao(app)

    # Métricas de tempo de resposta por rota (log para análise de gargalos)
    _configurar_metricas_performance(app)

    # API de status exige CSRF; o frontend envia o token no header X-CSRFToken (meta csrf-token)

    # Firebase é inicializado em app/database.py
    # Não há tabelas para criar (Firestore é NoSQL)

    # Agendamento: relatório semanal toda sexta-feira às 10h (Brasília)
    if not app.testing:
        _iniciar_scheduler(app)

    return app


def _iniciar_scheduler(app: Flask) -> None:
    """Inicia APScheduler com o job de relatório semanal (sexta 10h BRT)."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        import pytz

        def _job_relatorio():
            with app.app_context():
                try:
                    from app.services.report_service import enviar_relatorio_semanal
                    resultado = enviar_relatorio_semanal()
                    app.logger.info("Relatório semanal concluído: %s", resultado)
                except Exception as exc:
                    app.logger.exception("Erro no job de relatório semanal: %s", exc)

        scheduler = BackgroundScheduler(
            timezone=pytz.timezone("America/Sao_Paulo"),
            job_defaults={"coalesce": True, "max_instances": 1},
        )
        scheduler.add_job(
            _job_relatorio,
            trigger="cron",
            day_of_week="fri",
            hour=10,
            minute=0,
            id="relatorio_semanal",
        )
        scheduler.start()
        app.logger.info("Scheduler iniciado — relatório semanal toda sexta às 10h (BRT)")

        import atexit
        atexit.register(lambda: scheduler.shutdown(wait=False))

    except ImportError:
        app.logger.warning(
            "APScheduler não instalado; relatório semanal não será agendado. "
            "Execute: pip install 'APScheduler>=3.10.0'"
        )


def _configurar_metricas_performance(app: Flask) -> None:
    """Registra tempo de resposta por rota em log (path, status, duração em ms) para análise de gargalos."""
    logger_perf = logging.getLogger("app.performance")

    @app.before_request
    def _iniciar_tempo():
        request._inicio_request = time.perf_counter()

    @app.after_request
    def _logar_tempo(response):
        if hasattr(request, "_inicio_request"):
            duracao_ms = (time.perf_counter() - request._inicio_request) * 1000
            logger_perf.info(
                "request path=%s method=%s status=%s duration_ms=%.2f",
                request.path,
                request.method,
                response.status_code,
                duracao_ms,
            )
        return response


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

    @app.before_request
    def _gerar_csp_nonce():
        """Gera nonce por requisição para CSP (permite remover 'unsafe-inline')."""
        g.csp_nonce = secrets.token_urlsafe(16)

    @app.context_processor
    def _injetar_csp_nonce():
        """Disponibiliza nonce CSP nos templates para uso em <script nonce=""> e <style nonce="">."""
        return {'csp_nonce': g.get('csp_nonce', '')}

    @app.after_request
    def _adicionar_headers_seguranca(response):
        """Adiciona headers de segurança a todas as respostas."""
        response.headers['X-Content-Type-Options'] = 'nosniff'  # Impede MIME sniffing
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'      # Proteção contra clickjacking
        # Permissions-Policy: desabilita APIs do browser não usadas (câmera, microfone, geolocalização)
        response.headers['Permissions-Policy'] = (
            'camera=(), microphone=(), geolocation=(), payment=()'
        )
        if request.is_secure and current_app.config.get('ENV') == 'production':
            # HSTS força HTTPS em conexões futuras (31536000 = 1 ano)
            response.headers['Strict-Transport-Security'] = (
                'max-age=31536000; includeSubDomains'
            )
            # CSP em produção: nonce para scripts/estilos inline (sem 'unsafe-inline')
            nonce = g.get('csp_nonce', '')
            csp = (
                "default-src 'self'; "
                "script-src 'self' https://cdn.tailwindcss.com https://cdnjs.cloudflare.com https://cdn.jsdelivr.net 'nonce-{nonce}'; "
                "style-src 'self' https://fonts.googleapis.com https://cdn.jsdelivr.net 'nonce-{nonce}'; "
                "img-src 'self' data: https: blob:; "
                "font-src 'self' https://cdn.jsdelivr.net https://fonts.gstatic.com; "
                "connect-src 'self'; "
                "frame-ancestors 'self';"
            ).format(nonce=nonce)
            response.headers['Content-Security-Policy'] = csp
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
        
        # Origens aceitas: APP_BASE_URL e, em desenvolvimento, a própria URL do servidor (localhost)
        origens_aceitas = {base_origin}
        if app.config.get('ENV') == 'development' or app.debug:
            try:
                server_origin = f"{request.scheme}://{request.host}".lower()
                if server_origin not in origens_aceitas:
                    origens_aceitas.add(server_origin)
            except Exception:
                pass

        # Compara origem da requisição com as autorizadas
        if req_origin and req_origin not in origens_aceitas:
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
    from app.i18n import get_translation, get_translated_sector, get_translated_category, get_translated_status, get_translated_field_label
    
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
            """Função para traduzir uma chave no template"""
            lang = session.get('language', 'pt_BR')
            return get_translation(key, lang, **kwargs)
        
        def translate_sector(sector_name):
            """Traduz o nome de um setor no template"""
            lang = session.get('language', 'pt_BR')
            return get_translated_sector(sector_name, lang)
        
        def translate_category(category_name):
            """Traduz o nome de uma categoria no template"""
            lang = session.get('language', 'pt_BR')
            return get_translated_category(category_name, lang)
        
        def translate_status(status_name):
            """Traduz o status de um chamado no template"""
            lang = session.get('language', 'pt_BR')
            return get_translated_status(status_name, lang)

        def nome_curto(nome):
            """Retorna versão curta do nome para exibição (ex: 'João Silva' -> 'João S.')."""
            if not nome or not isinstance(nome, str):
                return ''
            partes = nome.strip().split()
            if not partes:
                return ''
            if len(partes) == 1:
                return partes[0]
            return f"{partes[0]} {partes[-1][0]}."
        
        # Extensões de anexo permitidas (para exibir e para o atributo accept do input file)
        _ext = sorted(app.config.get('EXTENSOES_UPLOAD_PERMITIDAS', set()))
        extensoes_permitidas = _ext
        accept_anexo = ','.join('.' + e for e in _ext)

        return dict(
            t=t,
            translate_sector=translate_sector,
            translate_category=translate_category,
            translate_status=translate_status,
            nome_curto=nome_curto,
            current_language=session.get('language', 'pt_BR'),
            get_supported_languages=lambda: {
                'pt_BR': 'Português (Brasil)',
                'en': 'English',
                'es': 'Español'
            },
            extensoes_permitidas=extensoes_permitidas,
            accept_anexo=accept_anexo,
        )
        
    # Registra funções as Jinja filters (para usar com o pipe |)
    @app.template_filter('translate_sector')
    def filter_translate_sector(sector_name):
        lang = session.get('language', 'pt_BR')
        return get_translated_sector(sector_name, lang)

    @app.template_filter('translate_category')
    def filter_translate_category(category_name):
        lang = session.get('language', 'pt_BR')
        return get_translated_category(category_name, lang)

    @app.template_filter('translate_status')
    def filter_translate_status(status_name):
        lang = session.get('language', 'pt_BR')
        return get_translated_status(status_name, lang)

    @app.template_filter('translate_field_label')
    def filter_translate_field_label(field_name):
        lang = session.get('language', 'pt_BR')
        return get_translated_field_label(field_name, lang)

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
    
    @app.before_request
    def verificar_troca_senha_obrigatoria():
        """Intercepta requisições para forçar troca de senha no primeiro acesso"""
        # Ignora rotas de arquivos estáticos
        if request.endpoint and request.endpoint.startswith('static'):
            return None
        
        # Lista de rotas isentas da verificação
        rotas_isentas = [
            'main.alterar_senha_obrigatoria',
            'main.logout',
            'main.login'
        ]
        
        # Verifica se usuário está autenticado e precisa trocar senha
        if current_user.is_authenticated:
            # Admins estão isentos da troca obrigatória
            if current_user.perfil != 'admin' and current_user.must_change_password:
                # Se não está em uma rota isenta, redireciona
                if request.endpoint not in rotas_isentas:
                    return redirect(url_for('main.alterar_senha_obrigatoria'))


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