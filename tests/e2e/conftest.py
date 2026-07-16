"""
Fixtures compartilhadas para testes E2E.

Uso:
    pytest tests/e2e --base-url http://127.0.0.1:5000

Variáveis de ambiente esperadas (para testes que fazem login):
    TEST_SOLICITANTE_EMAIL  / TEST_SOLICITANTE_PASSWORD
    TEST_SUPERVISOR_EMAIL   / TEST_SUPERVISOR_PASSWORD
    TEST_ADMIN_EMAIL        / TEST_ADMIN_PASSWORD
    TEST_ADMIN_GLOBAL_EMAIL / TEST_ADMIN_GLOBAL_PASSWORD

MFA é obrigatório para todos os perfis (usuario.mfa_enabled=True bloqueia login
sem segundo fator). Se a conta de teste tiver MFA habilitado, forneça também o
secret TOTP (base32) correspondente — senão o login para em /verificar-mfa e o
teste é pulado:
    TEST_SOLICITANTE_TOTP_SECRET
    TEST_SUPERVISOR_TOTP_SECRET
    TEST_ADMIN_TOTP_SECRET
    TEST_ADMIN_GLOBAL_TOTP_SECRET

Modo stub para CI (sem servidor externo):
    FLASK_E2E_STUB=1 pytest tests/e2e -m smoke
    (também ativa quando CI=true e FLASK_TEST_URL não estiver definido)

Exemplo de .env.test:
    TEST_SOLICITANTE_EMAIL=sol@dtx.com
    TEST_SOLICITANTE_PASSWORD=senha123
    TEST_SOLICITANTE_TOTP_SECRET=JBSWY3DPEHPK3PXP
    TEST_SUPERVISOR_EMAIL=sup@dtx.com
    TEST_SUPERVISOR_PASSWORD=senha123
    TEST_SUPERVISOR_TOTP_SECRET=JBSWY3DPEHPK3PXP
    TEST_ADMIN_EMAIL=admin@dtx.com
    TEST_ADMIN_PASSWORD=senha123
    TEST_ADMIN_TOTP_SECRET=JBSWY3DPEHPK3PXP
"""

import os
import threading
import urllib.error
import urllib.request
from collections.abc import Generator

import pytest
from playwright.sync_api import Page

DEFAULT_TIMEOUT = 10_000  # ms — tempo padrão de espera para assertions E2E


# ---------------------------------------------------------------------------
# Stub server para CI (sem Firebase real, sem servidor externo)
# ---------------------------------------------------------------------------


def _fake_usuarios_por_id() -> dict[str, dict]:
    """Monta os documentos falsos de usuário (id -> dict estilo Firestore) a partir das
    variáveis TEST_<PERFIL>_EMAIL/PASSWORD/TOTP_SECRET já definidas no workflow do E2E.

    Um perfil só aparece aqui se TEST_<PERFIL>_EMAIL estiver definido — sem isso, o
    fixture `creds_<perfil>` já faz pytest.skip normalmente, então nenhum dado é preciso.
    """
    from werkzeug.security import generate_password_hash

    especificacoes = [
        ("e2e-solicitante", "SOLICITANTE", "solicitante", "E2E Solicitante", ["Planejamento"]),
        ("e2e-supervisor", "SUPERVISOR", "supervisor", "E2E Supervisor", ["Planejamento"]),
        ("e2e-admin", "ADMIN", "admin", "E2E Admin", []),
    ]

    usuarios: dict[str, dict] = {}
    for uid, env_prefix, perfil, nome, areas in especificacoes:
        email = os.environ.get(f"TEST_{env_prefix}_EMAIL", "")
        senha = os.environ.get(f"TEST_{env_prefix}_PASSWORD", "")
        totp_secret = os.environ.get(f"TEST_{env_prefix}_TOTP_SECRET", "")
        if not email or not senha:
            continue
        usuarios[uid] = {
            "email": email,
            "nome": nome,
            "perfil": perfil,
            "areas": areas,
            "senha_hash": generate_password_hash(senha),
            "ativo": True,
            "must_change_password": False,
            # MFA é obrigatório pra todos os perfis (ver auth.py) — sem secret configurado
            # o login para em /verificar-mfa e _do_login pula o teste, não falha.
            "mfa_enabled": bool(totp_secret),
            "mfa_secret": totp_secret or None,
            "mfa_backup_codes": [],
            "onboarding_perfis_vistos": [perfil],
        }
    return usuarios


def _build_usuarios_collection_mock(usuarios_por_id: dict[str, dict]):
    """Mock de db.collection('usuarios') com lookup real por email e por id,
    usando os usuários falsos gerados por _fake_usuarios_por_id().
    """
    from unittest.mock import MagicMock

    def _fake_doc(uid: str, data: dict):
        doc = MagicMock()
        doc.exists = True
        doc.id = uid
        doc.to_dict.return_value = dict(data)
        return doc

    docs_por_email = {data["email"]: (uid, data) for uid, data in usuarios_por_id.items()}

    def _where(*_args, **kwargs):
        filtro = kwargs.get("filter")
        resultado = MagicMock()
        campo = getattr(filtro, "field_path", None)
        valor = getattr(filtro, "value", None)
        if campo == "email" and valor in docs_por_email:
            uid, data = docs_por_email[valor]
            resultado.stream.return_value = iter([_fake_doc(uid, data)])
        else:
            resultado.stream.return_value = iter([])
        resultado.limit.return_value.stream.return_value = resultado.stream.return_value
        return resultado

    def _document(uid: str):
        doc_ref = MagicMock()
        if uid in usuarios_por_id:
            doc_ref.get.return_value = _fake_doc(uid, usuarios_por_id[uid])
        else:
            doc_ref.get.return_value = MagicMock(exists=False)
        # .update(**kwargs) só precisa não travar — não persiste de verdade no stub.
        doc_ref.update = MagicMock()
        return doc_ref

    mock_usuarios = MagicMock()
    mock_usuarios.where.side_effect = _where
    mock_usuarios.document.side_effect = _document
    mock_usuarios.stream.return_value = iter(
        _fake_doc(uid, data) for uid, data in usuarios_por_id.items()
    )
    return mock_usuarios


@pytest.fixture(scope="session")
def _stub_server() -> Generator[str | None, None, None]:
    """Inicia Flask em background para CI quando nenhum servidor externo está disponível.

    Ativado quando FLASK_E2E_STUB=1 ou CI=true e FLASK_TEST_URL não está definido.
    Retorna a URL base do servidor stub, ou None se o modo stub não estiver ativo.

    Smoke tests que não precisam de login (SMOKE-01, 02, 03) funcionam com o stub
    pois o Flask trata /login e o redirect de rotas protegidas sem acessar Firestore.
    Para os demais smokes (login por perfil, permissões, dashboard etc.), a coleção
    "usuarios" é populada com usuários falsos derivados de TEST_<PERFIL>_EMAIL/PASSWORD/
    TOTP_SECRET (ver _fake_usuarios_por_id) — as outras coleções continuam retornando
    vazio, capturado silenciosamente pelos try/except já existentes nos services.

    A credencial usada em CI (GOOGLE_CREDENTIALS_JSON fake) é sintaticamente válida mas
    não corresponde a nenhum projeto GCP real: qualquer chamada a uma coleção não
    populada aqui falha, só que não instantaneamente — o SDK do Google tenta novamente
    por até ~60s antes de levantar a exceção, estourando o timeout de 30s do pytest
    (pytest.ini) e derrubando o teste. Como o stub roda no mesmo processo (thread, não
    subprocess), mockar os métodos do objeto `db` aqui afeta todos os módulos que já
    importaram essa mesma instância — sem precisar tocar em cada rota/serviço
    individualmente.
    """
    ci_mode = (
        os.environ.get("CI") == "true" or os.environ.get("FLASK_E2E_STUB") == "1"
    ) and not os.environ.get("FLASK_TEST_URL")

    if not ci_mode:
        yield None
        return

    from unittest.mock import MagicMock, patch

    from werkzeug.serving import make_server

    import app.database
    from app import create_app

    # `db` é um singleton do Firestore importado por referência em vários módulos
    # (models_usuario.py, models.py, etc.) — mockar os métodos do objeto existente,
    # em vez de reatribuir app.database.db, garante que todos esses módulos também
    # vejam o mock, sem precisar descobrir e patchar cada um individualmente.
    mock_collection_vazia = MagicMock()
    mock_collection_vazia.where.return_value.stream.return_value = iter([])
    mock_collection_vazia.where.return_value.limit.return_value.stream.return_value = iter([])
    mock_collection_vazia.document.return_value.get.return_value = MagicMock(exists=False)
    mock_collection_vazia.limit.return_value.stream.return_value = iter([])
    mock_collection_vazia.stream.return_value = iter([])

    mock_collection_usuarios = _build_usuarios_collection_mock(_fake_usuarios_por_id())

    def _collection(nome: str):
        if nome == "usuarios":
            return mock_collection_usuarios
        return mock_collection_vazia

    with patch.object(app.database.db, "collection", side_effect=_collection):
        stub = create_app()
        stub.config["TESTING"] = True
        stub.config["WTF_CSRF_ENABLED"] = False
        stub.config["SECRET_KEY"] = "test-stub-e2e-secret"
        stub.config["APP_BASE_URL"] = ""
        # Desativa rate limiting no stub para que SMOKE-02 (login inválido) não bloqueie
        stub.config["RATELIMIT_ENABLED"] = False

        # Porta 0 = OS escolhe uma porta livre (sem race condition)
        server = make_server("127.0.0.1", 0, stub)
        port = server.socket.getsockname()[1]
        url = f"http://127.0.0.1:{port}"

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        yield url

        server.shutdown()


# ---------------------------------------------------------------------------
# Configuração de base_url
# ---------------------------------------------------------------------------


def pytest_configure(config):
    """Registra os markers customizados para evitar warnings."""
    config.addinivalue_line("markers", "e2e: testes end-to-end contra servidor ativo")
    config.addinivalue_line(
        "markers",
        "capture: ferramenta de captura de screenshots (não é um teste de correção; "
        "não roda em CI/pytest normal, apenas quando explicitamente selecionada)",
    )


@pytest.fixture(scope="session")
def base_url(_stub_server: str | None) -> str:
    """URL base do servidor Flask.

    Prioridade:
    1. URL do stub server (quando FLASK_E2E_STUB=1 ou CI=true)
    2. FLASK_TEST_URL env var
    3. Padrão: http://127.0.0.1:5000
    """
    if _stub_server:
        return _stub_server
    return os.environ.get("FLASK_TEST_URL", "http://127.0.0.1:5000")


@pytest.fixture(scope="session", autouse=True)
def require_server(base_url: str) -> None:
    """Auto-skip da suíte inteira quando o servidor Flask não está disponível."""
    try:
        urllib.request.urlopen(f"{base_url}/login", timeout=3)
    except Exception:
        pytest.skip(f"Servidor Flask não disponível em {base_url} — skipping E2E suite")


# ---------------------------------------------------------------------------
# Credenciais de teste (de variáveis de ambiente)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def creds_solicitante() -> dict:
    return {
        "email": os.environ.get("TEST_SOLICITANTE_EMAIL", ""),
        "password": os.environ.get("TEST_SOLICITANTE_PASSWORD", ""),
        "totp_secret": os.environ.get("TEST_SOLICITANTE_TOTP_SECRET", ""),
    }


@pytest.fixture(scope="session")
def creds_supervisor() -> dict:
    return {
        "email": os.environ.get("TEST_SUPERVISOR_EMAIL", ""),
        "password": os.environ.get("TEST_SUPERVISOR_PASSWORD", ""),
        "totp_secret": os.environ.get("TEST_SUPERVISOR_TOTP_SECRET", ""),
    }


@pytest.fixture(scope="session")
def creds_admin() -> dict:
    return {
        "email": os.environ.get("TEST_ADMIN_EMAIL", ""),
        "password": os.environ.get("TEST_ADMIN_PASSWORD", ""),
        "totp_secret": os.environ.get("TEST_ADMIN_TOTP_SECRET", ""),
    }


@pytest.fixture(scope="session")
def creds_admin_global() -> dict:
    return {
        "email": os.environ.get("TEST_ADMIN_GLOBAL_EMAIL", ""),
        "password": os.environ.get("TEST_ADMIN_GLOBAL_PASSWORD", ""),
        "totp_secret": os.environ.get("TEST_ADMIN_GLOBAL_TOTP_SECRET", ""),
    }


# ---------------------------------------------------------------------------
# Configuração do Playwright
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Configuração padrão do contexto de browser para todos os testes E2E."""
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 720},
        "locale": "pt-BR",
    }


# ---------------------------------------------------------------------------
# Helpers de autenticação
# ---------------------------------------------------------------------------


def _do_login(page: Page, base_url: str, email: str, password: str, totp_secret: str = "") -> None:
    """Realiza login na aplicação via UI, incluindo a etapa de MFA quando exigida.

    MFA é obrigatório para todos os perfis (ver app/routes/auth.py): login com
    senha correta redireciona para /verificar-mfa antes de autenticar de fato.
    Sem tratar essa etapa, a página fica pendente de 2º fator e qualquer
    asserção de acesso pós-login é um falso positivo/negativo.
    """
    page.goto(f"{base_url}/login")
    page.get_by_test_id("email-input").fill(email)
    page.get_by_test_id("password-input").fill(password)
    page.get_by_test_id("login-submit-btn").click()
    page.wait_for_load_state("networkidle")

    if "/verificar-mfa" in page.url:
        if not totp_secret:
            pytest.skip(
                "Conta de teste tem MFA habilitado mas nenhum *_TOTP_SECRET foi configurado"
            )
        import pyotp

        codigo = pyotp.TOTP(totp_secret).now()
        page.get_by_test_id("mfa-code-input").fill(codigo)
        page.get_by_test_id("mfa-verify-submit-btn").click()
        page.wait_for_load_state("networkidle")

        # Sem isso, um código TOTP inválido (secret errado/clock drift) deixa a
        # página presa em /verificar-mfa e o teste segue como se tivesse logado —
        # asserções fracas tipo `"/login" not in page.url` passam por acidente
        # mesmo sem sessão autenticada (mesma classe de falso-positivo corrigida
        # nesta mesma função para a etapa de senha).
        if "/verificar-mfa" in page.url:
            pytest.fail(
                f"Falha ao completar verificação de MFA para {email} — "
                "código TOTP inválido ou *_TOTP_SECRET incorreto."
            )


@pytest.fixture
def logged_in_solicitante(page: Page, base_url: str, creds_solicitante: dict):
    """Page já autenticada como solicitante."""
    if not creds_solicitante["email"]:
        pytest.skip("TEST_SOLICITANTE_EMAIL não configurado")
    _do_login(
        page,
        base_url,
        creds_solicitante["email"],
        creds_solicitante["password"],
        creds_solicitante["totp_secret"],
    )
    return page


@pytest.fixture
def logged_in_supervisor(page: Page, base_url: str, creds_supervisor: dict):
    """Page já autenticada como supervisor."""
    if not creds_supervisor["email"]:
        pytest.skip("TEST_SUPERVISOR_EMAIL não configurado")
    _do_login(
        page,
        base_url,
        creds_supervisor["email"],
        creds_supervisor["password"],
        creds_supervisor["totp_secret"],
    )
    return page


@pytest.fixture
def logged_in_admin(page: Page, base_url: str, creds_admin: dict):
    """Page já autenticada como admin."""
    if not creds_admin["email"]:
        pytest.skip("TEST_ADMIN_EMAIL não configurado")
    _do_login(
        page, base_url, creds_admin["email"], creds_admin["password"], creds_admin["totp_secret"]
    )
    return page


@pytest.fixture
def logged_in_admin_global(page: Page, base_url: str, creds_admin_global: dict):
    """Page já autenticada como admin_global."""
    if not creds_admin_global["email"]:
        pytest.skip("TEST_ADMIN_GLOBAL_EMAIL não configurado")
    _do_login(
        page,
        base_url,
        creds_admin_global["email"],
        creds_admin_global["password"],
        creds_admin_global["totp_secret"],
    )
    return page
