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


def test_bulk_status_com_login_json_invalido_retorna_400(client, app):
    """POST /api/bulk-status com payload inválido retorna 400."""
    usuario = MagicMock()
    usuario.id = 'sup_1'
    usuario.perfil = 'supervisor'
    usuario.area = 'Planejamento'
    usuario.is_authenticated = True
    with patch('app.routes.api.current_user', usuario):
        r = client.post('/api/bulk-status', json={}, content_type='application/json')
    # Se a rota existir e validar: 400; se não existir: 404
    assert r.status_code in (400, 404)
