"""Testes dos endpoints Health Check e Service Worker (CT-HEALTH-01, CT-SW-01)."""

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


def test_health_deep_tem_campo_version(client):
    """CT-HEALTH-04: ?deep=1 retorna campo version (commit SHA ou 'dev')."""
    mock_query = MagicMock()
    mock_query.limit.return_value.get.return_value = []

    with patch("app.routes.api.db") as mock_db:
        mock_db.collection.return_value = mock_query
        r = client.get("/health?deep=1")

    data = r.get_json()
    assert "version" in data
    assert isinstance(data["version"], str)
    assert len(data["version"]) > 0


def test_health_shallow_nao_chama_firestore(client):
    """CT-HEALTH-05: GET /health (sem ?deep) não faz chamada ao Firestore."""
    with patch("app.routes.api.db") as mock_db:
        r = client.get("/health")

    assert r.status_code == 200
    mock_db.collection.assert_not_called()


# ---------------------------------------------------------------------------
# Service Worker
# ---------------------------------------------------------------------------


def test_service_worker_retorna_200_e_javascript(client):
    """CT-SW-01: GET /sw.js retorna 200 e Content-Type JavaScript."""
    r = client.get("/sw.js")
    assert r.status_code == 200
    assert "javascript" in (r.content_type or "").lower()
    assert len(r.data) > 0
