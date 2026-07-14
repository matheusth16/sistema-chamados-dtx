import os
import warnings

from dotenv import load_dotenv


def _to_bool(val, default: bool = False) -> bool:
    """Converte env var string para bool de forma case-insensitive."""
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in ("true", "1", "yes")


def _validar_fernet_key(env: str, encrypt_pii: bool, key: str) -> None:
    """Valida ENCRYPTION_KEY quando ENCRYPT_PII_AT_REST=true.

    Produção: fail-fast (ValueError) se chave ausente ou inválida.
    Dev/testing: apenas warning.
    """
    if not encrypt_pii:
        return
    if not key:
        msg = (
            "ENCRYPT_PII_AT_REST=true mas ENCRYPTION_KEY não está definida. "
            "Gere com: python scripts/gerar_chave_criptografia.py"
        )
        if env == "production":
            raise ValueError(msg)
        warnings.warn(msg, stacklevel=3)
        return
    try:
        from cryptography.fernet import Fernet

        raw = key.encode("ascii") if isinstance(key, str) else key
        Fernet(raw)
    except Exception as exc:
        msg = (
            f"ENCRYPTION_KEY inválida: {exc}. Gere com: python scripts/gerar_chave_criptografia.py"
        )
        if env == "production":
            raise ValueError(msg) from exc
        warnings.warn(msg, stacklevel=3)


def _validar_config_producao(
    env: str,
    app_base_url: str,
    health_secret: str,
    redis_url: str,
    require_redis: bool,
    gunicorn_workers: int,
) -> None:
    """Valida configurações obrigatórias em produção (fail-fast no boot).

    Skip se env != 'production'. Levanta ValueError para vars ausentes ou
    inválidas que impediriam operação segura.

    Regras Redis (ver ADR-003):
    - Ausente + 1 worker + REQUIRE_REDIS=false → warning (cenário DTX atual)
    - Ausente + workers > 1 → ValueError (rate limit não compartilhado)
    - Ausente + REQUIRE_REDIS=true → ValueError (opt-in explícito)
    """
    if env != "production":
        return

    if not app_base_url:
        raise ValueError(
            "Em produção, APP_BASE_URL é obrigatória (ex: https://chamados.empresa.com). "
            "Defina a variável de ambiente APP_BASE_URL."
        )
    if not app_base_url.startswith("https://"):
        raise ValueError(
            f"Em produção, APP_BASE_URL deve usar HTTPS (https://...). "
            f"Valor atual: '{app_base_url}'. Corrija para evitar mixed-content e falhas CWI 2.1."
        )

    if not health_secret:
        raise ValueError(
            "Em produção, HEALTH_SECRET é obrigatório (mínimo 16 caracteres). "
            'Gere com: python -c "import secrets; print(secrets.token_urlsafe(32))"'
        )
    if len(health_secret) < 16:
        raise ValueError(
            f"Em produção, HEALTH_SECRET deve ter pelo menos 16 caracteres "
            f"(atual: {len(health_secret)}). Gere um valor forte."
        )

    if not redis_url:
        if require_redis:
            raise ValueError(
                "REQUIRE_REDIS=true mas REDIS_URL não está definida. "
                "Defina REDIS_URL ou ajuste REQUIRE_REDIS=false."
            )
        if gunicorn_workers > 1:
            raise ValueError(
                f"REDIS_URL é obrigatória com GUNICORN_WORKERS={gunicorn_workers} > 1. "
                "Rate limit e cache não são compartilhados entre processos sem Redis. "
                "Defina REDIS_URL ou use GUNICORN_WORKERS=1."
            )
        warnings.warn(
            "REDIS_URL não definida em produção. Rate limit e cache operam em memória local "
            "por processo. Aceitável com 1 worker (GUNICORN_WORKERS=1). "
            "Defina REDIS_URL para escalar horizontalmente.",
            stacklevel=2,
        )


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
if _env == "production" and len(_secret) < 32:
    raise ValueError(
        f"Em produção, SECRET_KEY deve ter pelo menos 32 caracteres (atual: {len(_secret)}). "
        'Gere com: python -c "import secrets; print(secrets.token_urlsafe(32))"'
    )

# Fail-fast para vars obrigatórias em produção (APP_BASE_URL, HEALTH_SECRET) e
# warning/fail para Redis (ver ADR docs/adr/003-fail-fast-config-producao.md)
_validar_config_producao(
    env=_env,
    app_base_url=os.getenv("APP_BASE_URL", "").strip(),
    health_secret=os.getenv("HEALTH_SECRET", "").strip(),
    redis_url=os.getenv("REDIS_URL", "").strip(),
    require_redis=_to_bool(os.getenv("REQUIRE_REDIS"), default=False),
    gunicorn_workers=int(os.getenv("GUNICORN_WORKERS", "1")),
)
_validar_fernet_key(
    env=_env,
    encrypt_pii=_to_bool(os.getenv("ENCRYPT_PII_AT_REST"), default=False),
    key=os.getenv("ENCRYPTION_KEY", "").strip(),
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
    # Dashboard: docs por página com cursor-based pagination (Firestore lê limit+1 docs).
    # Reduzido de 50 para 25 para economizar leituras Firestore no free tier (Spark).
    ITENS_POR_PAGINA_DASHBOARD = 25

    # 5. Rate Limiting (limite de requisições por janela de tempo)
    # Em desenvolvimento: desativado para melhor UX
    # Em produção: 200 requisições/hora (~3-4 por minuto), 2000 por dia
    # Usa _env (já resolve FLASK_ENV ou ENV) em vez de os.getenv("FLASK_ENV") direto para
    # garantir que ENV=production sem FLASK_ENV também ative o rate limit.
    RATELIMIT_ENABLED = _env == "production"
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
        os.getenv("SESSION_COOKIE_SECURE") or None, default=(_env == "production")
    )  # True em produção (HTTPS), False em desenvolvimento/teste; string vazia = não-definido
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

    # Segurança operacional (obrigatórias em produção — ver ADR docs/adr/003-fail-fast-config-producao.md)
    # HEALTH_SECRET: protege /health?deep=1 (expõe status Firestore/Redis)
    HEALTH_SECRET = os.getenv("HEALTH_SECRET", "").strip()
    # GUNICORN_WORKERS: informa quantos workers o servidor tem (usado para validar REDIS_URL)
    GUNICORN_WORKERS = int(os.getenv("GUNICORN_WORKERS", "1"))
    # REQUIRE_REDIS: true força fail-fast se REDIS_URL ausente (opt-in explícito)
    REQUIRE_REDIS = _to_bool(os.getenv("REQUIRE_REDIS"), default=False)

    # Microsoft Graph API (envio de e-mail via client credentials)
    GRAPH_TENANT_ID = os.getenv("GRAPH_TENANT_ID", "").strip()
    GRAPH_CLIENT_ID = os.getenv("GRAPH_CLIENT_ID", "").strip()
    GRAPH_CLIENT_SECRET = os.getenv("GRAPH_CLIENT_SECRET", "").strip()
    GRAPH_SENDER_EMAIL = os.getenv("GRAPH_SENDER_EMAIL", "").strip()

    # Microsoft SSO (login "Entrar com Microsoft" — Authorization Code + PKCE, delegado).
    # Por padrão reaproveita o mesmo App Registration do Graph acima; sobrescreva
    # SSO_CLIENT_ID/SSO_CLIENT_SECRET/SSO_TENANT_ID apenas se usar um registro separado.
    SSO_MICROSOFT_ENABLED = _to_bool(os.getenv("SSO_MICROSOFT_ENABLED"), default=True)
    SSO_CLIENT_ID = os.getenv("SSO_CLIENT_ID", "").strip() or GRAPH_CLIENT_ID
    SSO_CLIENT_SECRET = os.getenv("SSO_CLIENT_SECRET", "").strip() or GRAPH_CLIENT_SECRET
    SSO_TENANT_ID = os.getenv("SSO_TENANT_ID", "").strip() or GRAPH_TENANT_ID
    SSO_REDIRECT_URI = os.getenv("SSO_REDIRECT_URI", "").strip()

    # Relay monitorado pelo Power Automate (caixa de entrada que dispara os flows)
    NOTIFY_RELAY_EMAIL = os.getenv("NOTIFY_RELAY_EMAIL", "dtxls.support@dtx.aero").strip()

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

    # Envio global de e-mails transacionais (Graph API).
    # Desligado por padrão fora de produção — evita disparos acidentais em dev/testes locais.
    NOTIFY_EMAIL_ENABLED = _to_bool(
        os.getenv("NOTIFY_EMAIL_ENABLED"), default=(_env == "production")
    )

    # MyMemory Translation API (opcional — aumenta limite de 5k para 10k chars/dia)
    # Cadastre em mymemory.translated.net e defina MYMEMORY_EMAIL nas variáveis de ambiente
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

    # Escalada gerencial (Fase 6 — prep): emails por nivel_gestao
    # Formato JSON: '{"gestor_setor":"x@dtx.aero","gerente_producao":"...","assistente_gm":"...","gm":"..."}'
    _gestor_emails_raw = os.getenv("GESTOR_EMAILS", "{}")
    try:
        import json as _json

        GESTOR_EMAILS: dict[str, str] = _json.loads(_gestor_emails_raw)
    except Exception:
        GESTOR_EMAILS: dict[str, str] = {}

    @classmethod
    def get_gestor_email(cls, nivel: str) -> str | None:
        """Retorna o e-mail do gestor para o nivel_gestao informado, ou None se não configurado."""
        return cls.GESTOR_EMAILS.get(nivel)

    # SLA / Tempo útil DTX
    SLA_HORARIO_INICIO = os.getenv("SLA_HORARIO_INICIO", "07:00")
    SLA_HORARIO_FIM = os.getenv("SLA_HORARIO_FIM", "16:30")
    SLA_ALMOCO_INICIO = os.getenv("SLA_ALMOCO_INICIO", "11:30")
    SLA_ALMOCO_FIM = os.getenv("SLA_ALMOCO_FIM", "13:00")
    SLA_DIAS_RESOLUCAO_PROJETOS = int(os.getenv("SLA_DIAS_RESOLUCAO_PROJETOS", "2"))
    SLA_DIAS_RESOLUCAO_PADRAO = int(os.getenv("SLA_DIAS_RESOLUCAO_PADRAO", "3"))
    SLA_ESCALADA_A_HORAS_UTEIS = [1, 2, 3, 4]
    SLA_ESCALADA_B_HORAS_UTEIS = [0, 4, 8, 12]
    SLA_INCLUI_FIM_DE_SEMANA = os.getenv("SLA_INCLUI_FIM_DE_SEMANA", "false").lower() == "true"
    SLA_TIMEZONE = os.getenv("SLA_TIMEZONE", "America/Sao_Paulo")

    # SLA AOG (Aircraft On Ground): tempo corrido (calendário), não útil — 24/7.
    # Abertura já notifica os 4 níveis de gestor de uma vez (ver notifications.py);
    # a escalada abaixo cobre só a resolução (prazo vencido), sequencial como um
    # chamado normal.
    SLA_AOG_MINUTOS_RESOLUCAO_DEADLINE = int(os.getenv("SLA_AOG_MINUTOS_RESOLUCAO_DEADLINE", "240"))
    SLA_AOG_MINUTOS_RESOLUCAO_ESCALADA = [0, 30, 60, 120]
