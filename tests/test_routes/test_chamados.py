"""Testes das rotas de chamados (formulário, criação, meus-chamados)."""

from unittest.mock import patch, MagicMock


def test_formulario_sem_login_redireciona_para_login(client):
    """GET / (formulário) sem autenticação redireciona para login."""
    r = client.get('/', follow_redirects=False)
    assert r.status_code == 302
    assert 'login' in r.location


def test_meus_chamados_sem_login_redireciona(client):
    """GET /meus-chamados sem login redireciona para login."""
    r = client.get('/meus-chamados', follow_redirects=False)
    assert r.status_code == 302
    assert 'login' in (r.location or '').lower()


def test_meus_chamados_com_solicitante_retorna_200(client_logado_solicitante):
    """GET /meus-chamados com solicitante logado retorna 200 (mock listagem)."""
    with patch('app.routes.chamados.listar_meus_chamados') as mock_listar:
        mock_listar.return_value = {
            'chamados': [],
            'pagina_atual': 1,
            'total_paginas': 1,
            'total_chamados': 0,
            'status_counts': {'Aberto': 0, 'Em Atendimento': 0, 'Concluído': 0, 'Cancelado': 0},
            'cursor_next': None,
            'cursor_prev': None,
        }
        r = client_logado_solicitante.get('/meus-chamados', follow_redirects=False)
    assert r.status_code == 200
    assert b'chamado' in r.data.lower() or b'meus' in r.data.lower()


def test_formulario_com_login_retorna_200(client_logado_solicitante):
    """GET / (formulário) com solicitante logado retorna 200 e página do formulário."""
    with patch('app.routes.chamados.get_static_cached') as mock_cache:
        mock_cache.return_value = []
        with patch('app.routes.chamados.obter_total_por_contagem', return_value=0):
            r = client_logado_solicitante.get('/', follow_redirects=False)
    assert r.status_code == 200
    assert b'formul' in r.data.lower() or b'chamado' in r.data.lower() or b'descri' in r.data.lower()


def test_post_criar_chamado_invalido_retorna_pagina_com_erros(client_logado_solicitante):
    """POST / com dados inválidos (ex.: descrição vazia) retorna 200 com erros no formulário."""
    with patch('app.routes.chamados.get_static_cached') as mock_cache:
        mock_cache.return_value = []
        r = client_logado_solicitante.post('/', data={
            'descricao': '',
            'tipo_solicitacao': 'Manutencao',
            'categoria': 'Manutencao',
        }, follow_redirects=False)
    assert r.status_code == 200
    # Página do formulário com mensagens de validação (flash ou inline)
    assert b'formul' in r.data.lower() or b'descri' in r.data.lower() or b'chamado' in r.data.lower()
