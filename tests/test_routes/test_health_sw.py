"""Testes dos endpoints Health Check e Service Worker (CT-HEALTH-01, CT-SW-01)."""


def test_health_check_retorna_200_e_ok(client):
    """CT-HEALTH-01: GET /health retorna 200 e { status: 'ok' }."""
    r = client.get('/health')
    assert r.status_code == 200
    data = r.get_json()
    assert data is not None
    assert data.get('status') == 'ok'


def test_health_nao_exige_autenticacao(client):
    """GET /health não exige login."""
    r = client.get('/health')
    assert r.status_code == 200
    assert r.get_json().get('status') == 'ok'


def test_service_worker_retorna_200_e_javascript(client):
    """CT-SW-01: GET /sw.js retorna 200 e Content-Type JavaScript."""
    r = client.get('/sw.js')
    assert r.status_code == 200
    assert 'javascript' in (r.content_type or '').lower()
    # Deve retornar algum conteúdo (código do service worker)
    assert len(r.data) > 0
