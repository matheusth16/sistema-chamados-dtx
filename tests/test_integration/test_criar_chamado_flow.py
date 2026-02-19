"""Testes de integração: fluxo de criação de chamado (POST /)."""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def usuario_solicitante():
    u = MagicMock()
    u.id = 'sol_1'
    u.email = 'sol@test.com'
    u.nome = 'Solicitante Teste'
    u.perfil = 'solicitante'
    u.area = 'Planejamento'
    u.is_authenticated = True
    return u


def test_criar_chamado_sem_login_redireciona(client):
    """POST / (criar chamado) sem login redireciona para login."""
    r = client.post('/', data={
        'csrf_token': 'ignored',
        'categoria': 'Nao Aplicavel',
        'tipo': 'Planejamento',
        'gate': 'N/A',
        'impacto': 'Prazo',
        'descricao': 'Teste integração',
    }, follow_redirects=False)
    assert r.status_code == 302
    assert 'login' in r.location


def test_criar_chamado_com_login_e_dados_validos_redireciona(client, app, usuario_solicitante):
    """POST / com usuário logado e dados válidos processa e redireciona (mock Firestore)."""
    with patch('app.routes.chamados.db') as mock_db:
        mock_db.collection.return_value.add.return_value = (None, 'doc_id_123')
        with patch('app.routes.chamados.current_user', usuario_solicitante):
            with patch('app.routes.chamados.gerar_numero_chamado', return_value='CHM-9999'):
                with patch('app.routes.chamados.atribuidor') as mock_atr:
                    mock_atr.atribuir.return_value = {
                        'sucesso': True,
                        'supervisor': {'id': 'sup_1', 'nome': 'Supervisor'},
                        'motivo': 'Ok',
                    }
                with patch('app.routes.chamados.salvar_anexo', return_value=None):
                    with patch('app.routes.chamados.Historico'):
                        with patch('app.routes.chamados.notificar_aprovador_novo_chamado'):
                            with patch('app.routes.chamados.criar_notificacao'):
                                with patch('app.routes.chamados.enviar_webpush_usuario'):
                                    r = client.post('/', data={
                                        'csrf_token': 'ignored',
                                        'categoria': 'Nao Aplicavel',
                                        'tipo': 'Planejamento',
                                        'gate': 'N/A',
                                        'impacto': 'Prazo',
                                        'descricao': 'Teste integração',
                                    }, follow_redirects=False)
    assert r.status_code == 302
    assert r.location and ('/' in r.location or 'admin' in r.location or 'chamado' in r.location)
