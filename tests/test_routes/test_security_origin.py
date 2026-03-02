"""Testes de segurança: validação Origin/Referer em POST sensíveis (CSRF por origem)."""

from unittest.mock import patch


def test_post_atualizar_status_sem_origin_com_app_base_url_retorna_403(app, client):
    """
    Quando APP_BASE_URL está definida, POST em /api/atualizar-status sem header Origin/Referer
    deve retornar 403 (origem não informada). A validação ocorre em before_request, antes do login.
    """
    app.config['APP_BASE_URL'] = 'https://app.example.com'
    r = client.post(
        '/api/atualizar-status',
        json={'chamado_id': 'ch1', 'novo_status': 'Em Atendimento'},
        headers={'Content-Type': 'application/json'},
    )
    assert r.status_code == 403
    data = r.get_json()
    assert data is not None and data.get('erro') == 'Origem não informada'


def test_post_atualizar_status_origin_invalida_retorna_403(app, client):
    """
    Quando APP_BASE_URL está definida, POST com Origin de outro domínio retorna 403.
    """
    app.config['APP_BASE_URL'] = 'https://app.example.com'
    r = client.post(
        '/api/atualizar-status',
        json={'chamado_id': 'ch1', 'novo_status': 'Em Atendimento'},
        headers={
            'Content-Type': 'application/json',
            'Origin': 'https://evil.com',
        },
    )
    assert r.status_code == 403
    data = r.get_json()
    assert data is not None and data.get('erro') == 'Origem não autorizada'
