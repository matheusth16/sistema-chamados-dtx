"""Configuração pytest e fixtures compartilhadas."""

import contextlib
import os
from unittest.mock import MagicMock, patch

import pytest

# Garante que o app seja importável (FLASK_ENV=testing evita exigência de SECRET_KEY de produção)
os.environ.setdefault("FLASK_ENV", "testing")

# Módulos que fazem "from app.database import db" — cada um cria seu próprio
# binding, então precisam ser mockados individualmente (patch("app.database.db")
# sozinho NÃO afeta esses). app.utils_areas fica de fora: já tem fixture
# dedicada abaixo com comportamento específico (doc.exists=False).
_MODULOS_COM_DB_FIRESTORE = [
    "app.database",
    "app.routes.api_solicitante",
    "app.routes.api_chamados",
    "app.routes.api_colaboracao",
    "app.routes.dashboard",
    "app.routes.chamados",
    "app.routes.admin_global",
    "app.models_usuario",
    "app.models_historico",
    "app.models_grupo_rl",
    "app.services.lgpd_self_service",
    "app.services.sla_escalacao_service",
    "app.services.edicao_chamado_service",
    "app.services.gestor_dashboard_service",
    "app.services.solicitante_edicao_service",
    "app.services.dashboard_service",
    "app.services.escalonamento_service",
    "app.services.cancelamento_solicitante_service",
    "app.services.chamados_listagem_service",
    "app.services.chamados_criacao_service",
    "app.services.report_service",
    "app.services.onboarding_service",
    "app.services.historico_usuario_service",
    "app.services.status_service",
    "app.services.notifications_inapp",
    "app.services.contadores_uso",
    "app.services.assignment",
    "app.utils",
    "app.services.lembrete_confirmacao_service",
    "app.services.webpush_service",
    "app.services.gamification_service",
]


def _levanta_acesso_real(*args, **kwargs):
    raise RuntimeError(
        "Firestore REAL acessado em teste sem mock explícito. Use "
        "patch('app.<modulo>.db') dentro do teste (ver CLAUDE.md — "
        "'Mock de Firestore'). Incidente 2026-08-03: testes sem mock "
        "escreveram dados de teste em produção."
    )


# Nomes de método que de fato tocam rede no Firestore real. Métodos de
# travessia (collection/document/where/order_by/limit/start_after/...) NÃO
# entram aqui — construir uma referência de query é sempre seguro (não bate
# na rede); só a CHAMADA de um destes é que precisa ser bloqueada. Isso
# importa porque parte do código passa a referência não-invocada adiante
# (ex.: execute_with_retry(db.collection(x).document(y).update, dados)) —
# nesse caso "update" nunca é de fato chamado se o wrapper for mockado.
_METODOS_TERMINAIS_FIRESTORE = {
    "get",
    "stream",
    "add",
    "set",
    "update",
    "delete",
    "get_all",
    "transaction",
    "batch",
}


class _FirestoreVenenoso(MagicMock):
    """MagicMock que levanta ao CHAMAR qualquer método terminal do Firestore,
    em qualquer profundidade da cadeia — mas permite montar a cadeia
    (.collection()/.document()/.where()/.limit()/...) livremente até lá."""

    def _get_child_mock(self, **kw):
        if kw.get("name") in _METODOS_TERMINAIS_FIRESTORE:
            return MagicMock(side_effect=_levanta_acesso_real)
        return _FirestoreVenenoso(**kw)


def _mock_db_venenoso():
    return _FirestoreVenenoso()


@pytest.fixture(autouse=True)
def _bloqueia_firestore_real_sem_mock():
    """Rede de segurança: acesso não-mockado a qualquer app.<módulo>.db levanta
    erro na hora, em vez de silenciosamente tocar o Firestore de PRODUÇÃO.

    Motivo (incidente 2026-08-03): um teste novo da Fase 2 (Postgres) usava a
    fixture db_session mas exercitava um model que ainda não tinha sido
    migrado — o código antigo caiu no Firestore real (credentials.json local
    aponta pra produção) e escreveu 20 documentos de teste lá, sem que
    nenhum teste tivesse mockado app.<modulo>.db explicitamente.

    Testes que fazem patch("app.<modulo>.db") localmente não são afetados —
    o patch do teste (aplicado dentro do corpo do teste) tem precedência
    sobre este autouse.
    """
    with contextlib.ExitStack() as stack:
        for modulo in _MODULOS_COM_DB_FIRESTORE:
            stack.enter_context(patch(f"{modulo}.db", _mock_db_venenoso()))
        yield


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
    # Idem para REQUIRE_HTTPS/SSO_MICROSOFT_ENABLED: fixa os defaults de produção
    # (ambos True) pra não depender do .env local, que pode ter o modo LAN-only
    # ativado (REQUIRE_HTTPS=false, SSO_MICROSOFT_ENABLED=false). Testes que
    # exercitam o modo desativado sobrescrevem explicitamente.
    app.config["REQUIRE_HTTPS"] = True
    app.config["SSO_MICROSOFT_ENABLED"] = True
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


def _alembic_config():
    """Config do Alembic apontando pra raiz do projeto (alembic.ini/alembic/)."""
    from pathlib import Path

    from alembic.config import Config as AlembicConfig

    root = Path(__file__).resolve().parent.parent
    cfg = AlembicConfig(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    return cfg


@pytest.fixture(scope="session")
def db_engine():
    """Engine de teste (Fase 2 — Postgres real, não mock) com o schema aplicado.

    Requer TEST_DATABASE_URL no ambiente (setado automaticamente no CI via
    serviço postgres:16-alpine; em dev local, ver docs/ENV.md). Roda todas as
    migrations do Alembic uma única vez por sessão de teste.
    """
    from sqlalchemy import create_engine

    from alembic import command

    test_url = os.environ.get("TEST_DATABASE_URL")
    if not test_url:
        pytest.skip("TEST_DATABASE_URL não configurada — testes de Postgres pulados.")

    command.upgrade(_alembic_config(), "head")
    engine = create_engine(test_url)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine, monkeypatch, app):
    """Sessão de teste isolada por savepoint — cada teste começa e termina em
    estado limpo (rollback), sem recriar o schema. Substitui app.db.SessionLocal
    pra que o código de produção use esta sessão de teste durante o teste.

    Depende explicitamente de `app`: create_app() chama init_engine(app), que
    sobrescreve app.db.SessionLocal com uma sessão real (sem savepoint) sempre
    que DATABASE_URL está configurada — e em modo teste ela resolve pro mesmo
    valor de TEST_DATABASE_URL (ver config.py). Sem essa dependência explícita,
    se um teste também usar a fixture `app`, a ordem de setup do pytest pode
    rodar create_app() DEPOIS deste monkeypatch, anulando o isolamento e
    fazendo escritas serem commitadas de verdade no banco de teste (achado ao
    investigar dados órfãos sobrevivendo a rollback em 2026-08-03)."""
    from sqlalchemy.orm import scoped_session, sessionmaker

    connection = db_engine.connect()
    trans = connection.begin()
    test_session_factory = scoped_session(
        sessionmaker(
            bind=connection,
            join_transaction_mode="create_savepoint",
            autoflush=False,
            expire_on_commit=False,
        )
    )
    monkeypatch.setattr("app.db.SessionLocal", test_session_factory)

    yield test_session_factory()

    test_session_factory.remove()
    trans.rollback()
    connection.close()
