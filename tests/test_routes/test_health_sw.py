"""Testes dos endpoints Health Check e Service Worker (CT-HEALTH-01, CT-SW-01)."""

import os
from unittest.mock import MagicMock, patch


def test_health_check_retorna_200_e_ok(client):
    """CT-HEALTH-01: GET /health retorna 200 e { status: 'ok' } sem autenticação."""
    r = client.get("/health")
    assert r.status_code == 200
    data = r.get_json()
    assert data is not None
    assert data.get("status") == "ok"


def test_health_nao_exige_autenticacao(client):
    """GET /health não exige login."""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json().get("status") == "ok"


# ---------------------------------------------------------------------------
# Deep health check (?deep=1)
# ---------------------------------------------------------------------------


def test_health_deep_firestore_ok(client):
    """CT-HEALTH-02: ?deep=1 com Firestore saudável retorna status 'ok' e campo checks."""
    mock_query = MagicMock()
    mock_query.limit.return_value.get.return_value = []

    with patch("app.routes.api.db") as mock_db:
        mock_db.collection.return_value = mock_query
        r = client.get("/health?deep=1")

    assert r.status_code == 200
    data = r.get_json()
    assert data is not None
    assert data.get("status") == "ok"
    assert "checks" in data
    assert data["checks"].get("firestore") == "ok"
    assert "duration_ms" in data


def test_health_deep_firestore_falha(client):
    """CT-HEALTH-03: ?deep=1 com Firestore falhando retorna status 'degraded'."""
    with patch("app.routes.api.db") as mock_db:
        mock_db.collection.side_effect = Exception("Firestore unreachable")
        r = client.get("/health?deep=1")

    assert r.status_code in (200, 503)
    data = r.get_json()
    assert data is not None
    assert data.get("status") in ("degraded", "error")
    assert "firestore" in data.get("checks", {})
    assert data["checks"]["firestore"].startswith("error:")


def test_health_deep_nao_expoe_versao(client):
    """CT-HEALTH-04: ?deep=1 não expõe commit SHA — campo version removido por segurança."""
    mock_query = MagicMock()
    mock_query.limit.return_value.get.return_value = []

    with patch("app.routes.api.db") as mock_db:
        mock_db.collection.return_value = mock_query
        r = client.get("/health?deep=1")

    data = r.get_json()
    assert "version" not in data
    assert "status" in data
    assert "checks" in data
    assert "duration_ms" in data


def test_health_shallow_nao_chama_firestore(client):
    """CT-HEALTH-05: GET /health (sem ?deep) não faz chamada ao Firestore."""
    with patch("app.routes.api.db") as mock_db:
        r = client.get("/health")

    assert r.status_code == 200
    mock_db.collection.assert_not_called()


# ---------------------------------------------------------------------------
# Deep health check — proteção por token (HEALTH_SECRET)
# ---------------------------------------------------------------------------


def test_health_deep_sem_token_retorna_401_quando_secret_configurado(client):
    """CT-HEALTH-06: ?deep=1 sem token retorna 401 quando HEALTH_SECRET está configurado."""
    with patch.dict(os.environ, {"HEALTH_SECRET": "supersecret"}):
        r = client.get("/health?deep=1")
    assert r.status_code == 401


def test_health_deep_com_token_errado_retorna_401(client):
    """CT-HEALTH-07: ?deep=1 com token errado retorna 401."""
    with patch.dict(os.environ, {"HEALTH_SECRET": "supersecret"}):
        r = client.get("/health?deep=1&token=errado")
    assert r.status_code == 401


def test_health_deep_com_token_correto_retorna_200(client):
    """CT-HEALTH-08: ?deep=1 com token correto retorna 200."""
    mock_query = MagicMock()
    mock_query.limit.return_value.get.return_value = []
    with (
        patch.dict(os.environ, {"HEALTH_SECRET": "supersecret"}),
        patch("app.routes.api.db") as mock_db,
    ):
        mock_db.collection.return_value = mock_query
        r = client.get("/health?deep=1&token=supersecret")
    assert r.status_code == 200


def test_health_shallow_nunca_exige_token(client):
    """CT-HEALTH-09: GET /health (shallow) nunca exige token, mesmo com HEALTH_SECRET."""
    with patch.dict(os.environ, {"HEALTH_SECRET": "supersecret"}):
        r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json().get("status") == "ok"


# ---------------------------------------------------------------------------
# Service Worker
# ---------------------------------------------------------------------------


def test_service_worker_retorna_200_e_javascript(client):
    """CT-SW-01: GET /sw.js retorna 200 e Content-Type JavaScript."""
    r = client.get("/sw.js")
    assert r.status_code == 200
    assert "javascript" in (r.content_type or "").lower()
    assert len(r.data) > 0


# ---------------------------------------------------------------------------
# CT-HEALTH-CACHE: branch cache OK no deep health check
# ---------------------------------------------------------------------------


def test_health_deep_cache_branch_ok_com_cache_set(client):
    """CT-HEALTH-CACHE-01 (RED→GREEN): cache branch deve retornar 'ok' quando cache_set funciona.

    Antes do fix: `from app.cache import cache` lançava ImportError,
    marcando cache como 'degraded:ImportError'.
    Após fix com cache_set: cache fica 'ok' quando não há exceção.
    """
    mock_query = MagicMock()
    mock_query.limit.return_value.get.return_value = []

    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.cache_set") as mock_cache_set,
    ):
        mock_db.collection.return_value = mock_query
        r = client.get("/health?deep=1")

    data = r.get_json()
    assert data is not None
    assert data.get("status") == "ok"
    assert "checks" in data
    assert data["checks"].get("cache") == "ok", (
        f"cache deve ser 'ok', obteve: {data['checks'].get('cache')!r}"
    )
    mock_cache_set.assert_called_once_with("__health__", "1", ttl_seconds=10)


def test_health_deep_cache_branch_degraded_quando_excecao(client):
    """CT-HEALTH-CACHE-02: quando cache_set lança exceção, cache fica 'degraded'."""
    mock_query = MagicMock()
    mock_query.limit.return_value.get.return_value = []

    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.cache_set", side_effect=RuntimeError("redis down")),
    ):
        mock_db.collection.return_value = mock_query
        r = client.get("/health?deep=1")

    data = r.get_json()
    assert data is not None
    cache_status = data.get("checks", {}).get("cache", "")
    assert cache_status.startswith("degraded:"), (
        f"cache deveria iniciar com 'degraded:', obteve: {cache_status!r}"
    )


# ---------------------------------------------------------------------------
# CT-HEALTH-10 a 13: autenticação via header X-Health-Token (R1 — Onda 3b)
# ---------------------------------------------------------------------------


def test_health_deep_com_header_x_health_token_correto_retorna_200(client):
    """CT-HEALTH-10: ?deep=1 com header X-Health-Token correto → 200 (canal primário)."""
    mock_query = MagicMock()
    mock_query.limit.return_value.get.return_value = []
    with (
        patch.dict(os.environ, {"HEALTH_SECRET": "supersecret"}),
        patch("app.routes.api.db") as mock_db,
    ):
        mock_db.collection.return_value = mock_query
        r = client.get("/health?deep=1", headers={"X-Health-Token": "supersecret"})
    assert r.status_code == 200


def test_health_deep_com_header_x_health_token_errado_retorna_401(client):
    """CT-HEALTH-11: ?deep=1 com header X-Health-Token inválido → 401 (fail-closed)."""
    with patch.dict(os.environ, {"HEALTH_SECRET": "supersecret"}):
        r = client.get("/health?deep=1", headers={"X-Health-Token": "errado"})
    assert r.status_code == 401


def test_health_deep_header_sem_query_token_retorna_200(client):
    """CT-HEALTH-12: header X-Health-Token correto, sem ?token= na URL → 200 (sem secret na URL)."""
    mock_query = MagicMock()
    mock_query.limit.return_value.get.return_value = []
    with (
        patch.dict(os.environ, {"HEALTH_SECRET": "minhachavefort32x"}),
        patch("app.routes.api.db") as mock_db,
    ):
        mock_db.collection.return_value = mock_query
        # sem ?token= na URL — token apenas no header
        r = client.get("/health?deep=1", headers={"X-Health-Token": "minhachavefort32x"})
    assert r.status_code == 200
    data = r.get_json()
    assert data is not None
    assert data.get("status") == "ok"


def test_health_deep_query_token_deprecado_ainda_funciona(client):
    """CT-HEALTH-13: ?token= query string ainda funciona (compat UptimeRobot legado)."""
    mock_query = MagicMock()
    mock_query.limit.return_value.get.return_value = []
    with (
        patch.dict(os.environ, {"HEALTH_SECRET": "supersecret"}),
        patch("app.routes.api.db") as mock_db,
    ):
        mock_db.collection.return_value = mock_query
        r = client.get("/health?deep=1&token=supersecret")
    assert r.status_code == 200
