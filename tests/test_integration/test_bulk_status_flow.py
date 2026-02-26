"""Testes de integração: fluxo de atualização de status em lote (bulk)."""
import pytest
from unittest.mock import patch, MagicMock


def test_bulk_status_sem_login_retorna_401_ou_redirect(client):
    """POST /api/bulk-status sem autenticação deve falhar."""
    r = client.post('/api/bulk-status', json={
        'chamado_ids': ['id1', 'id2'],
        'novo_status': 'Concluído',
    }, content_type='application/json', follow_redirects=False)
    assert r.status_code in (302, 401, 404)


def test_bulk_status_com_login_json_invalido_retorna_400(client_logado_supervisor):
    """POST /api/bulk-status com payload inválido (JSON vazio) retorna 400."""
    r = client_logado_supervisor.post(
        '/api/bulk-status',
        json={},
        content_type='application/json',
    )
    assert r.status_code == 400
    data = r.get_json()
    assert data is not None and (data.get('erro') or '').lower().find('json') >= 0 or data.get('erro')
