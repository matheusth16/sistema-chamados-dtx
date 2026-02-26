import os
from dotenv import load_dotenv

# 1. Define a "Raiz" do projeto de forma absoluta (C:\Users\Matheus...\sistema_chamados)
basedir = os.path.abspath(os.path.dirname(__file__))

# Carrega as variáveis do arquivo .env
load_dotenv(os.path.join(basedir, '.env'))

# Em produção, exige SECRET_KEY forte (não usar o valor de desenvolvimento)
_dev_secret = 'dev-secret-key-change-in-production'
_secret = os.getenv('SECRET_KEY') or _dev_secret
_env = (os.getenv('FLASK_ENV') or os.getenv('ENV') or 'development').lower()
if _env == 'production' and (not os.getenv('SECRET_KEY') or _secret == _dev_secret):
    raise ValueError(
        "Em produção, defina SECRET_KEY no ambiente com um valor forte e único. "
        "Não use o valor padrão de desenvolvimento."
    )


class Config:
    """Configuração base da aplicação"""
    SECRET_KEY = _secret
    
    # 2. Caminho ABSOLUTO para a pasta de uploads (Evita erros no Windows/OneDrive)
    UPLOAD_FOLDER = os.path.join(basedir, 'app', 'static', 'uploads')
    
    # 3. Segurança: Limita o tamanho do arquivo a 16MB (Padrão Flask)
    # Se passar disso, o sistema rejeita automaticamente.
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    
    # 4. Paginação
    ITENS_POR_PAGINA = 10
    
    # 5. Rate Limiting (limite de requisições por janela de tempo)
    # Em desenvolvimento: desativado para melhor UX
    # Em produção: 200 requisições/hora (~3-4 por minuto), 2000 por dia
    RATELIMIT_ENABLED = os.getenv('FLASK_ENV', 'development') == 'production'
    RATELIMIT_DEFAULT = "200 per hour, 2000 per day"
    # Redis em produção: defina REDIS_URL para rate limit compartilhado entre workers (Gunicorn/Cloud Run)
    # e para cache (app/cache.py). Sem Redis, usa memória local por processo (limites não compartilhados).
    _redis_url = os.getenv('REDIS_URL', '').strip()
    RATELIMIT_STORAGE_URL = _redis_url or 'memory://'
    RATELIMIT_STORAGE_URI = _redis_url or 'memory://'  # Flask-Limiter aceita ambos os nomes
    
    # 6. Segurança CSRF
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None  # Sem limite de tempo para tokens CSRF
    
    # 7. Session Security
    PERMANENT_SESSION_LIFETIME = 86400  # 24 horas em segundos
    SESSION_COOKIE_SECURE = os.getenv('SESSION_COOKIE_SECURE', 'True') == 'True'  # HTTPS em produção
    SESSION_COOKIE_HTTPONLY = True  # Não acessível via JavaScript
    SESSION_COOKIE_SAMESITE = 'Lax'  # Proteção contra CSRF
    
    # 8. Validação de Entrada
    MAX_DESCRICAO_CHARS = 5000
    MIN_DESCRICAO_CHARS = 3
    EXTENSOES_UPLOAD_PERMITIDAS = {'png', 'jpg', 'jpeg', 'pdf', 'xlsx'}
    
    # Firebase: Será inicializado em app/database.py
    # As credenciais vão em credentials.json na raiz do projeto

    # Notificações (URL base para links em e-mail/Teams/Web Push)
    APP_BASE_URL = os.getenv('APP_BASE_URL', '')
    MAIL_SERVER = os.getenv('MAIL_SERVER', '')
    MAIL_PORT = int(os.getenv('MAIL_PORT', '587'))
    MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'true').lower() in ('true', '1', 'yes')
    MAIL_USERNAME = os.getenv('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD', '')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER', '')
    TEAMS_WEBHOOK_URL = os.getenv('TEAMS_WEBHOOK_URL', '')

    # Web Push (notificações no navegador). Gere chaves com: python gerar_vapid_keys.py
    VAPID_PUBLIC_KEY = os.getenv('VAPID_PUBLIC_KEY', '')
    VAPID_PRIVATE_KEY = os.getenv('VAPID_PRIVATE_KEY', '')

    # Logging: nível (DEBUG, INFO, WARNING, ERROR). Em produção use INFO ou WARNING.
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
    # Rotação do arquivo de log: tamanho máximo por arquivo (bytes) e número de backups
    LOG_MAX_BYTES = int(os.getenv('LOG_MAX_BYTES', 2 * 1024 * 1024))  # 2 MB
    LOG_BACKUP_COUNT = int(os.getenv('LOG_BACKUP_COUNT', 5))