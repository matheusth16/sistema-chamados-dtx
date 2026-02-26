"""Testes da API de atualização de status (AJAX)."""


def test_atualizar_status_sem_login_retorna_401_ou_redirect(client):
    """POST /api/atualizar-status sem login deve falhar."""
    r = client.post(
        '/api/atualizar-status',
        json={'chamado_id': 'x', 'novo_status': 'Em Atendimento'},
        content_type='application/json'
    )
    # Pode ser 302 (redirect login) ou 401
    assert r.status_code in (302, 401)


def test_atualizar_status_json_vazio_retorna_400(client):
    """POST com JSON vazio ou inválido retorna 400 (ou 401 se não logado)."""
    # Sem JSON
    r = client.post('/api/atualizar-status', data={})
    assert r.status_code in (400, 302, 401, 415)  # 401 em rotas /api/ sem login
    # Com JSON vazio: sem login = 401; logado = 400
    r2 = client.post(
        '/api/atualizar-status',
        json={},
        content_type='application/json'
    )
    assert r2.status_code in (400, 302, 401)
