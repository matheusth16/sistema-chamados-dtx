"""Configuração pytest e fixtures compartilhadas."""

import os
from unittest.mock import MagicMock, patch

import pytest

# Garante que o app seja importável (FLASK_ENV=testing evita exigência de SECRET_KEY de produção)
os.environ.setdefault("FLASK_ENV", "testing")


def pytest_configure(config):
    """Registra markers customizados (regressão, api)."""
    config.addinivalue_line("markers", "regression: testes críticos de regressão (suite de smoke).")
    config.addinivalue_line("markers", "api: testes de contrato e validação de API.")


@pytest.fixture(autouse=True)
def _patch_utils_areas_db_default():
    """Evita chamadas ao Firestore via utils_areas em todos os testes.

    Substitui app.utils_areas.db por um mock cujo doc.exists=False, fazendo
    _carregar_mapa_firestore retornar o fallback estático SETOR_PARA_AREA sem
    bloquear na rede. Limpa o cache antes e depois do teste para evitar
    interferência entre testes.

    Testes que precisam de comportamento específico do Firestore (ex.:
    test_carregar_mapa_firestore_*) devem usar patch("app.utils_areas.db") ou
    patch("app.utils_areas._carregar_mapa_firestore") internamente — o patch
    interno tem precedência sobre este autouse.
    """
    from app.cache import static_cache_delete

    static_cache_delete("setor_para_area_map")
    _doc = MagicMock()
    _doc.exists = False
    with patch("app.utils_areas.db") as _mock_db:
        _mock_db.collection.return_value.document.return_value.get.return_value = _doc
        yield
    static_cache_delete("setor_para_area_map")


@pytest.fixture
def app():
    """Cria aplicação Flask para testes."""
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SECRET_KEY"] = "test-secret"
    app.config["NOTIFY_EMAIL_ENABLED"] = False
    # Neutraliza o check de Origin/Referer para que testes não dependam do .env local.
    # Testes de segurança da validação de Origin estão em test_security_origin.py,
    # onde APP_BASE_URL é definida explicitamente por fixture.
    app.config["APP_BASE_URL"] = ""
    # Idem para SSO_REDIRECT_URI: o test client usa host "localhost" (sem porta) por
    # padrão, que não bate com o valor do .env local (ex.: http://localhost:5000/...).
    # Testes do fluxo de SSO definem SSO_REDIRECT_URI explicitamente quando precisam.
    app.config["SSO_REDIRECT_URI"] = ""
    return app


@pytest.fixture
def client(app):
    """Cliente de teste para requisições HTTP."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Runner para comandos CLI."""
    return app.test_cli_runner()


def _usuario_mock(uid, email, nome, perfil, area="Geral", areas=None):
    """Cria um MagicMock de usuário para testes.
    area: string única (usado como u.area e, se areas não for passado, como u.areas = [area]).
    areas: lista de áreas (usado por permissions: supervisor vê só chamados cuja área está em user.areas).
    """
    u = MagicMock()
    u.id = uid
    u.email = email
    u.nome = nome
    u.perfil = perfil
    u.area = area
    u.areas = areas if areas is not None else ([area] if isinstance(area, str) else area)
    u.is_authenticated = True
    u.check_password = MagicMock(return_value=True)
    # Flask-Login serializa user_id na sessão; get_id deve retornar string
    u.get_id = lambda: str(uid)
    # Para testes que assumem acesso após login (dashboard, API): sem obrigação de trocar senha
    u.must_change_password = False
    # MFA já configurado por padrão nos testes — evita redirecionamento para /mfa/configurar
    u.mfa_enabled = True
    u.is_admin_or_above = perfil in ("admin", "admin_global")
    u.is_supervisor_or_above = perfil in ("supervisor", "admin", "admin_global")
    # Onboarding concluído por padrão — evita injeção do tour em testes (F-62)
    u.onboarding_perfis_vistos = [perfil]
    u.onboarding_passo = 0
    # Onda 2: conta ativa por padrão (ativo=False bloqueia login e sessão)
    u.ativo = True
    # Fase 5: sem nivel_gestao por padrão (gestor é opt-in)
    u.nivel_gestao = None
    u.is_gestor = False
    u.is_gestor_only = False
    # Demais campos reais de Usuario.__init__ (F-62) — valores default, evita
    # que atributos "esquecidos" virem MagicMock truthy e mascarem bugs de lógica
    u.senha_hash = None
    u.password_changed_at = None
    u.exp_total = 0
    u.exp_semanal = 0
    u.level = 1
    u.conquistas = []
    u.mfa_secret = None
    u.mfa_backup_codes = []
    u.auth_provider = "local"
    return u


@pytest.fixture
def client_logado_solicitante(client, app):
    """Cliente com usuário solicitante já logado. Use em testes que precisam de sessão ativa."""
    user = _usuario_mock(
        "sol_1", "sol@test.com", "Solicitante Teste", "solicitante", "Planejamento"
    )
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=user),
        patch("app.models_usuario.Usuario.get_by_id", return_value=user),
        patch("app.routes.auth._dispositivo_confiavel", return_value=True),
    ):
        client.post("/login", data={"email": "sol@test.com", "senha": "ok"}, follow_redirects=False)
        yield client


@pytest.fixture
def client_logado_supervisor(client, app):
    """Cliente com usuário supervisor já logado."""
    user = _usuario_mock("sup_1", "sup@test.com", "Supervisor Teste", "supervisor", "Manutencao")
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=user),
        patch("app.models_usuario.Usuario.get_by_id", return_value=user),
        patch("app.routes.auth._dispositivo_confiavel", return_value=True),
    ):
        client.post("/login", data={"email": "sup@test.com", "senha": "ok"}, follow_redirects=False)
        yield client


@pytest.fixture
def client_logado_admin(client, app):
    """Cliente com usuário admin já logado."""
    user = _usuario_mock("admin_1", "admin@test.com", "Admin Teste", "admin", "Geral")
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=user),
        patch("app.models_usuario.Usuario.get_by_id", return_value=user),
        patch("app.routes.auth._dispositivo_confiavel", return_value=True),
    ):
        client.post(
            "/login", data={"email": "admin@test.com", "senha": "ok"}, follow_redirects=False
        )
        yield client


@pytest.fixture
def client_logado_admin_global(client, app):
    """Cliente com usuário admin_global já logado."""
    user = _usuario_mock("ag_1", "ag@test.com", "Admin Global Teste", "admin_global", "Geral")
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=user),
        patch("app.models_usuario.Usuario.get_by_id", return_value=user),
        patch("app.routes.auth._dispositivo_confiavel", return_value=True),
    ):
        client.post("/login", data={"email": "ag@test.com", "senha": "ok"}, follow_redirects=False)
        yield client


@pytest.fixture
def client_logado_supervisor_sem_areas(client, app):
    """Cliente com supervisor sem áreas — testa IDOR de paginação (CT-IDOR-PAG-01)."""
    user = _usuario_mock(
        "sup_sem_areas",
        "sup_sem@test.com",
        "Supervisor Sem Areas",
        "supervisor",
        "Geral",
        areas=[],
    )
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=user),
        patch("app.models_usuario.Usuario.get_by_id", return_value=user),
        patch("app.routes.auth._dispositivo_confiavel", return_value=True),
    ):
        client.post(
            "/login", data={"email": "sup_sem@test.com", "senha": "ok"}, follow_redirects=False
        )
        yield client


@pytest.fixture
def client_logado_gestor(client, app):
    """Cliente com usuário supervisor + nivel_gestao='gestor_setor' (read-only gestor)."""
    user = _usuario_mock("gest_1", "gestor@test.com", "Gestor Teste", "supervisor", "Geral")
    user.nivel_gestao = "gestor_setor"
    user.is_gestor = True
    user.is_gestor_only = True
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=user),
        patch("app.models_usuario.Usuario.get_by_id", return_value=user),
        patch("app.routes.auth._dispositivo_confiavel", return_value=True),
    ):
        client.post(
            "/login", data={"email": "gestor@test.com", "senha": "ok"}, follow_redirects=False
        )
        yield client


@pytest.fixture
def mock_firestore():
    """
    Mock do Firestore para testes que não devem acessar o banco real.
    Use: def test_x(mock_firestore): ... (o mock está em app.database.db).
    """
    with patch("app.database.db", MagicMock()) as mock_db:
        yield mock_db
