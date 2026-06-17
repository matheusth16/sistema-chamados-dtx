import os

from dotenv import load_dotenv


def _to_bool(val, default: bool = False) -> bool:
    """Converte env var string para bool de forma case-insensitive."""
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in ("true", "1", "yes")


# 1. Define a "Raiz" do projeto de forma absoluta (C:\Users\Matheus...\sistema_chamados)
basedir = os.path.abspath(os.path.dirname(__file__))

# Carrega as variáveis do arquivo .env
load_dotenv(os.path.join(basedir, ".env"))

# Em produção, exige SECRET_KEY forte (não usar o valor de desenvolvimento)
_dev_secret = "dev-secret-key-change-in-production"
_secret = os.getenv("SECRET_KEY") or _dev_secret
_env = (os.getenv("FLASK_ENV") or os.getenv("ENV") or "production").lower()
if _env == "production" and (not os.getenv("SECRET_KEY") or _secret == _dev_secret):
    raise ValueError(
        "Em produção, defina SECRET_KEY no ambiente com um valor forte e único. "
        "Não use o valor padrão de desenvolvimento."
    )


class Config:
    """Configuração base da aplicação"""

    SECRET_KEY = _secret
    # Ambiente: use sempre app.config.get('ENV') (development, production, testing)
    ENV = _env

    # 2. Caminho ABSOLUTO para a pasta de uploads (Evita erros no Windows/OneDrive)
    UPLOAD_FOLDER = os.path.join(basedir, "app", "static", "uploads")

    # 3. Limites de upload
    # MAX_ANEXO_BYTES: regra de negócio — cada arquivo individualmente pode ter até 10 MB.
    # MAX_CONTENT_LENGTH: guardrail de infraestrutura — teto total do request HTTP.
    #   Sem limite de quantidade de arquivos por chamado, então usamos 500 MB como teto.
    #   A validação real (10 MB/arquivo) fica em validators.py._validar_tamanho.
    MAX_ANEXO_BYTES = 10 * 1024 * 1024
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_UPLOAD_REQUEST_BYTES", str(500 * 1024 * 1024)))

    # 4. Paginação
    ITENS_POR_PAGINA = 10
    # Dashboard: docs por página com cursor-based pagination (Firestore lê limit+1 docs)
    ITENS_POR_PAGINA_DASHBOARD = 50

    # 5. Rate Limiting (limite de requisições por janela de tempo)
    # Em desenvolvimento: desativado para melhor UX
    # Em produção: 200 requisições/hora (~3-4 por minuto), 2000 por dia
    RATELIMIT_ENABLED = os.getenv("FLASK_ENV", "development") == "production"
    RATELIMIT_DEFAULT = "200 per hour, 2000 per day"
    # Redis em produção: defina REDIS_URL para rate limit compartilhado entre workers (Gunicorn/Cloud Run)
    # e para cache (app/cache.py). Sem Redis, usa memória local por processo (limites não compartilhados).
    _redis_url = os.getenv("REDIS_URL", "").strip()
    RATELIMIT_STORAGE_URL = _redis_url or "memory://"
    RATELIMIT_STORAGE_URI = _redis_url or "memory://"  # Flask-Limiter aceita ambos os nomes

    # 6. Segurança CSRF
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 7200  # Tokens CSRF expiram em 2 horas

    # 7. Session Security
    # PERMANENT_SESSION_LIFETIME só tem efeito se session.permanent=True for definido.
    # No fluxo atual isso nunca acontece: sessões expiram pelo checar_inatividade (900s)
    # em app/__init__.py, ou pelo cookie de "lembrar" (REMEMBER_COOKIE_DURATION, 30 dias).
    PERMANENT_SESSION_LIFETIME = 86400  # 24 horas — reservado para uso futuro
    SESSION_COOKIE_SECURE = _to_bool(
        os.getenv("SESSION_COOKIE_SECURE"), default=(_env == "production")
    )  # True em produção (HTTPS), False em desenvolvimento/teste
    SESSION_COOKIE_HTTPONLY = True  # Não acessível via JavaScript
    SESSION_COOKIE_SAMESITE = "Lax"  # Proteção contra CSRF
    REMEMBER_COOKIE_DURATION = 2592000  # 30 dias em segundos (Flask-Login padrão é 31 dias)
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE  # Mesmo padrão de SESSION_COOKIE_SECURE
    REMEMBER_COOKIE_HTTPONLY = True  # Não acessível via JavaScript
    REMEMBER_COOKIE_SAMESITE = "Lax"  # Proteção contra CSRF

    # 8. Validação de Entrada
    MAX_DESCRICAO_CHARS = 5000
    MIN_DESCRICAO_CHARS = 3
    # Anexos: imagens, PDF, Excel (todas as extensões comuns), Word (todas as extensões comuns)
    EXTENSOES_UPLOAD_PERMITIDAS = {
        "png",
        "jpg",
        "jpeg",
        "pdf",
        "xls",
        "xlsx",
        "xlsm",
        "xlsb",
        "xltx",
        "xltm",
        "csv",
        "doc",
        "docx",
        "docm",
        "dotx",
        "dotm",
    }

    # Firebase: Será inicializado em app/database.py
    # As credenciais vão em credentials.json na raiz do projeto

    # Notificações (URL base para links em e-mail/Web Push)
    APP_BASE_URL = os.getenv("APP_BASE_URL", "")

    # Microsoft Graph API (envio de e-mail via client credentials)
    GRAPH_TENANT_ID = os.getenv("GRAPH_TENANT_ID", "").strip()
    GRAPH_CLIENT_ID = os.getenv("GRAPH_CLIENT_ID", "").strip()
    GRAPH_CLIENT_SECRET = os.getenv("GRAPH_CLIENT_SECRET", "").strip()
    GRAPH_SENDER_EMAIL = os.getenv("GRAPH_SENDER_EMAIL", "").strip()

    # Relay monitorado pelo Power Automate (caixa de entrada que dispara os flows)
    NOTIFY_RELAY_EMAIL = os.getenv("NOTIFY_RELAY_EMAIL", "dtxls.support@dtx.aero").strip()

    # Power Automate (modo teste): sobrescreve o destinatário final do evento USUARIO_CADASTRADO
    # Útil para validar visualmente o fluxo sem depender do e-mail real do usuário criado.
    POWER_AUTOMATE_TEST_DEST_EMAIL = os.getenv("POWER_AUTOMATE_TEST_DEST_EMAIL", "").strip()

    # Cloudflare R2 (armazenamento de arquivos/anexos)
    R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID", "").strip()
    R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "").strip()
    R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "").strip()
    R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "").strip()
    R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "").strip()

    # Web Push (notificações no navegador). Gere chaves com: python gerar_vapid_keys.py
    VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
    VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")

    # Notificação e-mail ao solicitante em mudança de status (opt-in)
    NOTIFY_SOLICITANTE_EMAIL = _to_bool(os.getenv("NOTIFY_SOLICITANTE_EMAIL"), default=False)

    # MyMemory Translation API (opcional — aumenta limite de 5k para 10k chars/dia)
    # Cadastre em mymemory.translated.net e defina MYMEMORY_EMAIL no Railway
    MYMEMORY_EMAIL = os.getenv("MYMEMORY_EMAIL", "").strip()

    # Criptografia de PII em repouso (LGPD). Gere chave: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "").strip()
    ENCRYPT_PII_AT_REST = os.getenv("ENCRYPT_PII_AT_REST", "false").lower() in ("true", "1", "yes")

    # Limite por usuário (relatórios/export): 0 = desativado. Ex.: 10 para máx 10 atualizações/export por usuário por dia.
    RELATORIO_MAX_POR_USUARIO_POR_DIA = int(os.getenv("RELATORIO_MAX_POR_USUARIO_POR_DIA", "0"))
    EXPORT_EXCEL_MAX_POR_USUARIO_POR_DIA = int(
        os.getenv("EXPORT_EXCEL_MAX_POR_USUARIO_POR_DIA", "0")
    )

    # Logging: nível (DEBUG, INFO, WARNING, ERROR). Em produção use INFO ou WARNING.
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    # Rotação do arquivo de log: tamanho máximo por arquivo (bytes) e número de backups
    LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", 2 * 1024 * 1024))  # 2 MB
    LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", 5))
