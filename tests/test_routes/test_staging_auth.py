"""Testes do middleware de Basic Auth para ambientes staging/HML — CWI 4.1 / Onda 5.

Verifica:
- Middleware desativado em TESTING=True (pytest nunca bloqueado)
- Middleware desativado em ENV=production (VPN/infra é a camada primária)
- 401 + WWW-Authenticate: Basic quando ativo e sem credencial
- Credencial correta passa (próximo guard pode redirecionar normalmente)
- Credencial errada → 401
- Rotas /health, /login, /sw.js excluídas do Basic Auth
- /health?deep=1 excluído do Basic Auth mas protegido por HEALTH_SECRET (Onda 3)
"""

import base64
import os
from unittest.mock import patch

import pytest


def _basic_header(user: str, senha: str) -> str:
    """Gera header Authorization: Basic <base64(user:senha)>."""
    cred = base64.b64encode(f"{user}:{senha}".encode()).decode()
    return f"Basic {cred}"


_STAGING_ENV_VARS = {
    "STAGING_AUTH_ENABLED": "true",
    "STAGING_AUTH_USER": "hml_user",
    "STAGING_AUTH_PASSWORD": "hml_SenhaForte_123!",
}


@pytest.fixture
def client_staging(app):
    """Cliente com Basic Auth de staging ativo.

    Configura TESTING=False e ENV=staging para ativar o middleware.
    Restaura estado original após o teste.
    """
    original_testing = app.config.get("TESTING")
    original_env = app.config.get("ENV")
    app.config["TESTING"] = False
    app.config["ENV"] = "staging"
    with patch.dict(os.environ, _STAGING_ENV_VARS, clear=False):
        yield app.test_client()
    app.config["TESTING"] = original_testing
    app.config["ENV"] = original_env


# ── Testes: middleware desativado ──────────────────────────────────────────────


def test_staging_auth_desativado_em_testing(client):
    """TESTING=True → /dashboard não exige Basic Auth — nunca retorna WWW-Authenticate: Basic."""
    resp = client.get("/dashboard")
    # 302 (redirect login) ou outro código — mas NUNCA 401 com Basic Auth challenge
    assert "Basic" not in resp.headers.get("WWW-Authenticate", "")


def test_staging_auth_desativado_em_production(app, client):
    """ENV=production → middleware não aplica Basic Auth, mesmo com STAGING_AUTH_ENABLED=true."""
    original_testing = app.config.get("TESTING")
    original_env = app.config.get("ENV")
    app.config["TESTING"] = False
    app.config["ENV"] = "production"
    try:
        with patch.dict(os.environ, _STAGING_ENV_VARS, clear=False):
            resp = client.get("/dashboard")
    finally:
        app.config["TESTING"] = original_testing
        app.config["ENV"] = original_env
    # Em produção: 301 HTTPS redirect ou 302 login redirect — nunca 401 Basic Auth
    assert "Basic" not in resp.headers.get("WWW-Authenticate", "")


# ── Testes: middleware ativo ───────────────────────────────────────────────────


def test_staging_auth_ativo_sem_credencial_retorna_401(client_staging):
    """STAGING_AUTH_ENABLED=true, ENV=staging, sem credencial → 401 + WWW-Authenticate: Basic realm="DTX Staging"."""
    resp = client_staging.get("/dashboard")
    assert resp.status_code == 401
    www_auth = resp.headers.get("WWW-Authenticate", "")
    assert "Basic" in www_auth
    assert "DTX Staging" in www_auth


def test_staging_auth_credencial_correta_passa(client_staging):
    """Credencial correta → não 401 Basic (pode ser 302 redirect login ou outro guard)."""
    resp = client_staging.get(
        "/dashboard",
        headers={"Authorization": _basic_header("hml_user", "hml_SenhaForte_123!")},
    )
    # Passou pelo Basic Auth — pode redirect para login (302) mas não 401 Basic
    assert resp.status_code != 401
    assert "Basic" not in resp.headers.get("WWW-Authenticate", "")


def test_staging_auth_credencial_errada_retorna_401(client_staging):
    """Credencial errada → 401 + WWW-Authenticate: Basic."""
    resp = client_staging.get(
        "/dashboard",
        headers={"Authorization": _basic_header("hml_user", "senha_errada_xyz")},
    )
    assert resp.status_code == 401
    assert "Basic" in resp.headers.get("WWW-Authenticate", "")


def test_staging_auth_rotas_excluidas_sem_basic(client_staging):
    """/health, /login, /sw.js excluídos do Basic Auth — não retornam 401 com WWW-Authenticate: Basic."""
    for path in ["/health", "/login", "/sw.js"]:
        resp = client_staging.get(path)
        assert resp.status_code != 401, (
            f"{path} retornou 401, mas deveria ser excluída do Basic Auth de staging"
        )
        www_auth = resp.headers.get("WWW-Authenticate", "")
        assert "Basic" not in www_auth, (
            f"{path} retornou WWW-Authenticate: Basic, mas é rota excluída do staging auth"
        )


def test_staging_auth_deep_health_ainda_usa_health_secret(client_staging):
    """/health?deep=1: excluído do Basic Auth; sem health token → não 401 Basic; com token correto → 200/503."""
    _test_secret = "segredo-teste-health-valido-32ch"
    with (
        patch.dict(os.environ, {"HEALTH_SECRET": _test_secret}, clear=False),
        patch("app.routes.api_chamados.db") as mock_db,
    ):
        mock_db.collection.return_value.limit.return_value.get.side_effect = Exception(
            "Firestore indisponível no teste"
        )
        # Sem health token → não bloqueado por Basic Auth (pode ser 401 pelo guard de HEALTH_SECRET)
        resp_no_token = client_staging.get("/health?deep=1")
        www_auth = resp_no_token.headers.get("WWW-Authenticate", "")
        assert "Basic" not in www_auth, (
            "/health?deep=1 não deve exigir Basic Auth de staging (rota excluída)"
        )
        assert resp_no_token.status_code in (200, 401, 403, 503)

        # Com header X-Health-Token correto → passa pelo guard de health (sem Basic Auth)
        resp_with_token = client_staging.get(
            "/health?deep=1",
            headers={"X-Health-Token": _test_secret},
        )
        assert "Basic" not in resp_with_token.headers.get("WWW-Authenticate", "")
        # 200 (Firestore ok) ou 503 (Firestore indisponível no teste) — mas nunca 401/403 com token correto
        assert resp_with_token.status_code in (200, 503)


# ── Testes: casos extremos ─────────────────────────────────────────────────────


def test_staging_auth_misconfiguration_sem_credenciais_desativa_basic(app):
    """STAGING_AUTH_ENABLED=true + credenciais ausentes → guard 4 desativa Basic Auth.

    Misconfiguration deve resultar em Basic Auth desligado (fail-open da camada 2),
    não em 401 que bloquearia a aplicação. O warning é logado mas a request passa.
    """
    original_testing = app.config.get("TESTING")
    original_env = app.config.get("ENV")
    app.config["TESTING"] = False
    app.config["ENV"] = "staging"
    try:
        miscfg = {
            "STAGING_AUTH_ENABLED": "true",
            "STAGING_AUTH_USER": "",  # ausente — guard 4 detecta
            "STAGING_AUTH_PASSWORD": "",  # ausente — guard 4 detecta
        }
        with patch.dict(os.environ, miscfg, clear=False):
            resp = app.test_client().get("/dashboard")
    finally:
        app.config["TESTING"] = original_testing
        app.config["ENV"] = original_env
    # Basic Auth não deve ser exigido — middleware desativado por misconfiguration
    assert "Basic" not in resp.headers.get("WWW-Authenticate", ""), (
        "Misconfiguration (enabled=true + credenciais ausentes) deve desativar Basic Auth, não retornar 401"
    )


def test_staging_auth_trailing_slash_health_retorna_401(client_staging):
    """/health/ (trailing slash) NÃO está na whitelist — retorna 401 Basic Auth.

    O middleware usa match exato de request.path. A URL canônica é /health (sem slash).
    Monitores de saúde devem usar /health, não /health/.
    Comportamento documentado como esperado: whitelist é explícita, sem normalização de slash.
    """
    resp = client_staging.get("/health/")
    # /health/ não está na frozenset — middleware aplica Basic Auth
    assert resp.status_code == 401
    assert "Basic" in resp.headers.get("WWW-Authenticate", ""), (
        "/health/ (com trailing slash) deve retornar 401 Basic — "
        "somente /health (sem slash) é excluído. Use a URL canônica nos monitores."
    )
