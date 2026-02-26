"""Testes da API de atualização de status (AJAX). Ref: CT-STAT-*."""
from unittest.mock import patch


def test_atualizar_status_sem_login_retorna_401_ou_redirect(client):
    """POST /api/atualizar-status sem login deve falhar."""
    r = client.post(
        '/api/atualizar-status',
        json={'chamado_id': 'x', 'novo_status': 'Em Atendimento'},
        content_type='application/json'
    )
    assert r.status_code in (302, 401)


def test_atualizar_status_json_vazio_retorna_400(client):
    """POST com JSON vazio ou inválido retorna 400 (ou 401 se não logado)."""
    r = client.post('/api/atualizar-status', data={})
    assert r.status_code in (400, 302, 401, 415)
    r2 = client.post(
        '/api/atualizar-status',
        json={},
        content_type='application/json'
    )
    assert r2.status_code in (400, 302, 401)


def test_atualizar_status_sem_chamado_id_retorna_400(client_logado_supervisor):
    """CT-STAT-02: POST /api/atualizar-status sem chamado_id retorna 400."""
    r = client_logado_supervisor.post(
        '/api/atualizar-status',
        json={'novo_status': 'Aberto'},
        content_type='application/json',
    )
    assert r.status_code == 400
    data = r.get_json()
    assert data is not None and data.get('sucesso') is False
    assert 'chamado_id' in data.get('erro', '').lower()


def test_atualizar_status_status_invalido_retorna_400(client_logado_supervisor):
    """CT-STAT-03: novo_status diferente de Aberto/Em Atendimento/Concluído retorna 400."""
    r = client_logado_supervisor.post(
        '/api/atualizar-status',
        json={'chamado_id': 'ch_123', 'novo_status': 'Cancelado'},
        content_type='application/json',
    )
    assert r.status_code == 400
    data = r.get_json()
    assert data is not None and data.get('sucesso') is False
    assert 'inválido' in data.get('erro', '').lower() or 'status' in data.get('erro', '').lower()


def test_atualizar_status_com_sucesso_retorna_200(client_logado_supervisor):
    """CT-STAT-01: POST /api/atualizar-status com payload válido e chamado existente retorna 200."""
    with patch('app.routes.api.atualizar_status_chamado') as mock_atualizar:
        mock_atualizar.return_value = {
            'sucesso': True,
            'mensagem': 'Status alterado para Em Atendimento',
            'novo_status': 'Em Atendimento',
        }
        r = client_logado_supervisor.post(
            '/api/atualizar-status',
            json={'chamado_id': 'ch_valido_123', 'novo_status': 'Em Atendimento'},
            content_type='application/json',
        )
    assert r.status_code == 200
    data = r.get_json()
    assert data.get('sucesso') is True
    assert data.get('novo_status') == 'Em Atendimento'


def test_atualizar_status_chamado_inexistente_retorna_404(client_logado_supervisor):
    """CT-STAT-04: Chamado não encontrado retorna 404."""
    with patch('app.routes.api.atualizar_status_chamado') as mock_atualizar:
        mock_atualizar.return_value = {'sucesso': False, 'erro': 'Chamado não encontrado'}
        r = client_logado_supervisor.post(
            '/api/atualizar-status',
            json={'chamado_id': 'ch_inexistente', 'novo_status': 'Em Atendimento'},
            content_type='application/json',
        )
    assert r.status_code == 404
    data = r.get_json()
    assert data.get('sucesso') is False
    assert 'não encontrado' in data.get('erro', '').lower()


def test_bulk_status_como_solicitante_retorna_403(client_logado_solicitante):
    """CT-STAT-05: POST /api/bulk-status como solicitante retorna 403 Acesso negado."""
    r = client_logado_solicitante.post(
        '/api/bulk-status',
        json={'chamado_ids': ['ch_1'], 'novo_status': 'Concluído'},
        content_type='application/json',
    )
    assert r.status_code == 403
    data = r.get_json()
    assert data is not None and data.get('sucesso') is False
    assert 'acesso negado' in data.get('erro', '').lower() or 'negado' in data.get('erro', '').lower()


def test_bulk_status_chamado_ids_nao_lista_retorna_400(client_logado_supervisor):
    """CT-STAT-06: chamado_ids deve ser uma lista; string ou ausente retorna 400."""
    r = client_logado_supervisor.post(
        '/api/bulk-status',
        json={'chamado_ids': 'id_unico', 'novo_status': 'Concluído'},
        content_type='application/json',
    )
    assert r.status_code == 400
    data = r.get_json()
    assert data.get('sucesso') is False
    assert 'lista' in data.get('erro', '').lower() or 'chamado_ids' in data.get('erro', '').lower()


def test_bulk_status_novo_status_invalido_retorna_400(client_logado_supervisor):
    """CT-STAT-07: novo_status inválido (ex: Fechado) retorna 400."""
    r = client_logado_supervisor.post(
        '/api/bulk-status',
        json={'chamado_ids': ['ch_1'], 'novo_status': 'Fechado'},
        content_type='application/json',
    )
    assert r.status_code == 400
    data = r.get_json()
    assert data.get('sucesso') is False
    assert 'inválido' in data.get('erro', '').lower() or 'novo_status' in data.get('erro', '').lower()
