"""Testes das rotas de API: editar chamado, carregar mais, notificações, push."""
import pytest
from unittest.mock import patch, MagicMock


def test_api_editar_chamado_solicitante_recebe_403(client_logado_solicitante):
    """POST /api/editar-chamado como solicitante retorna 403 Acesso negado."""
    r = client_logado_solicitante.post(
        '/api/editar-chamado',
        data={'chamado_id': 'qualquer'},
        content_type='multipart/form-data',
    )
    assert r.status_code == 403
    data = r.get_json()
    assert data is not None and data.get('erro') == 'Acesso negado'


def test_api_editar_chamado_sem_chamado_id_retorna_400(client_logado_supervisor):
    """POST /api/editar-chamado sem chamado_id retorna 400."""
    with patch('app.routes.api.db') as mock_db:
        r = client_logado_supervisor.post(
            '/api/editar-chamado',
            data={},
            content_type='multipart/form-data',
        )
    assert r.status_code == 400
    assert r.get_json().get('erro') and 'obrigatório' in r.get_json().get('erro', '').lower()


def test_api_editar_chamado_chamado_inexistente_retorna_404(client_logado_supervisor):
    """POST /api/editar-chamado com ID inexistente retorna 404."""
    mock_doc = MagicMock()
    mock_doc.exists = False
    with patch('app.routes.api.db') as mock_db:
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        r = client_logado_supervisor.post(
            '/api/editar-chamado',
            data={'chamado_id': 'id_inexistente'},
            content_type='multipart/form-data',
        )
    assert r.status_code == 404
    assert 'não encontrado' in r.get_json().get('erro', '').lower()


def test_api_editar_chamado_supervisor_outra_area_retorna_403(client_logado_supervisor):
    """Edge case: supervisor só pode editar chamados da sua área; chamado de outra área retorna 403."""
    mock_doc = MagicMock()
    mock_doc.exists = True
    # Chamado da área TI; supervisor do conftest tem areas=['Manutencao']
    mock_doc.to_dict.return_value = {
        'area': 'TI',
        'status': 'Aberto',
        'descricao': 'Desc',
        'responsavel': 'Alguém',
        'responsavel_id': 'outro_id',
    }
    with patch('app.routes.api.db') as mock_db:
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        r = client_logado_supervisor.post(
            '/api/editar-chamado',
            data={'chamado_id': 'ch_ti_123'},
            content_type='multipart/form-data',
        )
    assert r.status_code == 403
    data = r.get_json()
    assert data is not None and ('sua área' in data.get('erro', '').lower() or 'área' in data.get('erro', '').lower())


def test_carregar_mais_sem_login_redireciona(client):
    """POST /api/carregar-mais sem login retorna 302."""
    r = client.post('/api/carregar-mais', json={}, content_type='application/json')
    assert r.status_code == 302


def test_carregar_mais_retorna_estrutura_esperada(client_logado_supervisor):
    """POST /api/carregar-mais retorna sucesso, chamados, cursor_proximo, tem_proxima."""
    with patch('app.routes.api.aplicar_filtros_dashboard_com_paginacao') as mock_filtros:
        mock_filtros.return_value = {
            'docs': [],
            'proximo_cursor': None,
            'tem_proxima': False,
        }
        r = client_logado_supervisor.post(
            '/api/carregar-mais',
            json={'cursor': None, 'limite': 20},
            content_type='application/json',
        )
    assert r.status_code == 200
    data = r.get_json()
    assert data.get('sucesso') is True
    assert 'chamados' in data
    assert 'cursor_proximo' in data
    assert 'tem_proxima' in data


def test_api_notificacoes_listar_sem_login_redireciona(client):
    """GET /api/notificacoes sem login retorna 302."""
    r = client.get('/api/notificacoes')
    assert r.status_code == 302


def test_api_notificacoes_listar_retorna_estrutura(client_logado_solicitante):
    """GET /api/notificacoes retorna notificacoes e total_nao_lidas."""
    with patch('app.routes.api.listar_para_usuario', return_value=[]), \
         patch('app.routes.api.contar_nao_lidas', return_value=0):
        r = client_logado_solicitante.get('/api/notificacoes')
    assert r.status_code == 200
    data = r.get_json()
    assert 'notificacoes' in data
    assert 'total_nao_lidas' in data


def test_api_push_subscribe_sem_subscription_retorna_400(client_logado_solicitante):
    """POST /api/push-subscribe sem subscription válida retorna 400."""
    r = client_logado_solicitante.post(
        '/api/push-subscribe',
        json={},
        content_type='application/json',
    )
    assert r.status_code == 400
    data = r.get_json()
    assert data.get('sucesso') is False
    assert 'erro' in data


def test_api_push_subscribe_subscription_sem_endpoint_retorna_400(client_logado_solicitante):
    """POST /api/push-subscribe com subscription sem endpoint retorna 400."""
    r = client_logado_solicitante.post(
        '/api/push-subscribe',
        json={'subscription': {'keys': {}}},
        content_type='application/json',
    )
    assert r.status_code == 400


def test_api_push_vapid_public_requer_login(client):
    """GET /api/push-vapid-public sem login redireciona."""
    r = client.get('/api/push-vapid-public')
    assert r.status_code == 302


def test_api_supervisores_disponibilidade_sem_login_retorna_401_json(client):
    """GET /api/supervisores/disponibilidade sem login retorna 401 JSON (não redirect)."""
    r = client.get('/api/supervisores/disponibilidade')
    assert r.status_code == 401
    data = r.get_json()
    assert data is not None
    assert data.get('sucesso') is False
    assert 'requer_login' in data or 'erro' in data


def test_bulk_status_supervisor_outra_area_retorna_erro_por_chamado(client_logado_supervisor):
    """Edge case: no bulk-status, chamados de outra área do supervisor retornam em erros (sem permissão)."""
    # Supervisor do conftest tem areas=['Manutencao']. Doc 1 = mesma área, Doc 2 = outra área.
    doc_manutencao = MagicMock()
    doc_manutencao.exists = True
    doc_manutencao.to_dict.return_value = {'area': 'Manutencao', 'status': 'Aberto'}
    doc_ti = MagicMock()
    doc_ti.exists = True
    doc_ti.to_dict.return_value = {'area': 'TI', 'status': 'Aberto'}
    with patch('app.routes.api.db') as mock_db:
        col = mock_db.collection.return_value
        def doc_side_effect(doc_id):
            m = MagicMock()
            m.get.return_value = doc_manutencao if doc_id == 'ch_manutencao' else doc_ti
            m.update = MagicMock()
            return m
        col.document.side_effect = doc_side_effect
        with patch('app.routes.api.execute_with_retry'):
            r = client_logado_supervisor.post(
                '/api/bulk-status',
                json={'chamado_ids': ['ch_manutencao', 'ch_ti'], 'novo_status': 'Em Atendimento'},
                content_type='application/json',
            )
    assert r.status_code == 200
    data = r.get_json()
    assert data.get('sucesso') is True
    assert 'erros' in data
    erros_ids = [e.get('id') for e in data['erros']]
    assert 'ch_ti' in erros_ids
    assert data.get('atualizados', 0) >= 0
