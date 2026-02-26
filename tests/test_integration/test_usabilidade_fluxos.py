"""
Testes de usabilidade: fluxos do usuário e comportamento esperado para facilidade de uso.

Valida redirects corretos, feedback de erro (sem tela quebrada), estrutura de resposta
consistente para o frontend e mensagens claras (U-AUTH-*, U-CHAM-*, U-DASH-*, U-STAT-*, U-EDIT-*, U-NOT-*, U-HEALTH-*).
"""
import pytest
from unittest.mock import patch, MagicMock


# --- U-AUTH: Autenticação ---


def test_usabilidade_nao_logado_acessa_rota_protegida_redireciona_para_login(client):
    """U-AUTH-01: Acesso a página protegida sem login redireciona para login (não 500 nem tela em branco)."""
    r = client.get('/', follow_redirects=False)
    assert r.status_code == 302
    assert 'login' in r.location

    r2 = client.get('/admin', follow_redirects=False)
    assert r2.status_code == 302
    assert 'login' in r2.location


def test_usabilidade_login_sucesso_redireciona_por_perfil(client):
    """U-AUTH-02: Após login, redirecionamento correto: solicitante → /, supervisor/admin → /admin."""
    usuario_sol = MagicMock()
    usuario_sol.id = 'sol_1'
    usuario_sol.perfil = 'solicitante'
    usuario_sol.email = 'sol@test.com'
    usuario_sol.check_password = MagicMock(return_value=True)
    usuario_sol.get_id = lambda: 'sol_1'
    with patch('app.routes.auth.Usuario.get_by_email', return_value=usuario_sol):
        r = client.post('/login', data={'email': 'sol@test.com', 'senha': 'ok'}, follow_redirects=False)
    assert r.status_code == 302
    assert r.location.endswith('/') or '/' in r.location
    assert 'admin' not in r.location

    usuario_sup = MagicMock()
    usuario_sup.id = 'sup_1'
    usuario_sup.perfil = 'supervisor'
    usuario_sup.email = 'sup@test.com'
    usuario_sup.check_password = MagicMock(return_value=True)
    usuario_sup.get_id = lambda: 'sup_1'
    with patch('app.routes.auth.Usuario.get_by_email', return_value=usuario_sup):
        r2 = client.post('/login', data={'email': 'sup@test.com', 'senha': 'ok'}, follow_redirects=False)
    assert r2.status_code == 302
    assert 'admin' in r2.location


def test_usabilidade_login_credenciais_invalidas_permanece_em_login_com_feedback(client):
    """U-AUTH-03: Credenciais inválidas exibem feedback (página de login com mensagem, não 500)."""
    with patch('app.routes.auth.Usuario.get_by_email', return_value=None):
        r = client.post('/login', data={'email': 'x@y.com', 'senha': 'errada'}, follow_redirects=True)
    assert r.status_code == 200
    assert b'login' in r.data.lower() or b'email' in r.data.lower()


def test_usabilidade_login_campos_vazios_mensagem_clara(client):
    """U-AUTH-04: Email ou senha vazios mantêm usuário na tela de login com mensagem."""
    r = client.post('/login', data={'email': '', 'senha': 'x'}, follow_redirects=True)
    assert r.status_code == 200
    assert b'login' in r.data.lower() or b'email' in r.data.lower()


def test_usabilidade_logout_encerra_sessao_proximo_acesso_pede_login(client_logado_solicitante):
    """U-AUTH-05: Logout redireciona para login; próximo acesso a rota protegida pede login."""
    r = client_logado_solicitante.get('/logout', follow_redirects=False)
    assert r.status_code == 302
    assert 'login' in r.location

    r2 = client_logado_solicitante.get('/', follow_redirects=False)
    assert r2.status_code == 302
    assert 'login' in r2.location


# --- U-CHAM: Criação de chamado ---


def test_usabilidade_formulario_invalido_retorna_erros_na_pagina(client_logado_solicitante):
    """U-CHAM-01: Formulário com dados inválidos mostra erros (não 500)."""
    with patch('app.routes.chamados.CategoriaSetor.get_all', return_value=[]), \
         patch('app.routes.chamados.CategoriaImpacto.get_all', return_value=[]):
        r = client_logado_solicitante.post('/', data={
            'descricao': '',  # inválido
            'tipo': '',
            'categoria': 'Chamado',
        }, follow_redirects=True)
    assert r.status_code == 200
    # Página de formulário com mensagens de erro (flash ou no body)
    body = r.data.decode('utf-8', errors='replace').lower()
    assert 'descricao' in body or 'descrição' in body or 'obrigat' in body or 'formulario' in body or 'formulário' in body


def test_usabilidade_criar_chamado_valido_redireciona(client_logado_solicitante):
    """U-CHAM-02: Após criar chamado com sucesso, usuário é redirecionado."""
    with patch('app.routes.chamados.db') as mock_db:
        mock_db.collection.return_value.add.return_value = (None, 'doc_123')
        with patch('app.routes.chamados.gerar_numero_chamado', return_value='CHM-0001'):
            with patch('app.routes.chamados.atribuidor') as mock_atr:
                mock_atr.atribuir.return_value = {
                    'sucesso': True,
                    'supervisor': {'id': 's1', 'nome': 'Sup'},
                    'motivo': 'Ok',
                }
                with patch('app.routes.chamados.salvar_anexo', return_value=None):
                    with patch('app.routes.chamados.Historico'):
                        with patch('app.routes.chamados.notificar_aprovador_novo_chamado'):
                            with patch('app.routes.chamados.criar_notificacao'):
                                with patch('app.routes.chamados.enviar_webpush_usuario'):
                                    r = client_logado_solicitante.post('/', data={
                                        'categoria': 'Chamado',
                                        'tipo': 'Manutencao',
                                        'descricao': 'Descrição válida com mais de 3 caracteres',
                                    }, follow_redirects=False)
    assert r.status_code == 302
    assert r.location


# --- U-DASH: API para frontend ---


def test_usabilidade_api_sem_login_retorna_401_json_nao_500(client):
    """U-DASH-02: Chamadas à API sem login retornam 401 JSON (não 500 nem HTML)."""
    r = client.get('/api/notificacoes')
    assert r.status_code == 401
    data = r.get_json()
    assert data is not None
    assert data.get('requer_login') is True or 'erro' in data


def test_usabilidade_carregar_mais_estrutura_consistente(client_logado_supervisor):
    """U-DASH-01: API de listagem retorna estrutura consistente (chamados, cursor, tem_proxima)."""
    with patch('app.routes.api.aplicar_filtros_dashboard_com_paginacao') as mock_f:
        mock_f.return_value = {'docs': [], 'proximo_cursor': None, 'tem_proxima': False}
        r = client_logado_supervisor.post('/api/carregar-mais', json={'cursor': None, 'limite': 20}, content_type='application/json')
    assert r.status_code == 200
    data = r.get_json()
    assert 'chamados' in data
    assert 'cursor_proximo' in data
    assert 'tem_proxima' in data


# --- U-STAT / U-EDIT: Ações e feedback ---


def test_usabilidade_atualizar_status_resposta_sucesso_ou_erro_explicito(client_logado_supervisor):
    """U-STAT-01: Atualização de status retorna sucesso ou erro explícito (200/400/404)."""
    with patch('app.routes.api.atualizar_status_chamado') as mock_st:
        mock_st.return_value = {'sucesso': True, 'mensagem': 'Ok', 'novo_status': 'Em Atendimento'}
        r = client_logado_supervisor.post('/api/atualizar-status', json={'chamado_id': 'ch1', 'novo_status': 'Em Atendimento'}, content_type='application/json')
    assert r.status_code == 200
    data = r.get_json()
    assert data.get('sucesso') is True
    assert 'mensagem' in data or 'novo_status' in data


def test_usabilidade_bulk_status_retorna_resumo_atualizados_e_erros(client_logado_supervisor):
    """U-STAT-02: Bulk status retorna resumo (atualizados, total_solicitados, erros)."""
    with patch('app.routes.api.db') as mock_db:
        doc = MagicMock()
        doc.exists = True
        doc.to_dict.return_value = {'area': 'Manutencao', 'status': 'Aberto'}
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        with patch('app.routes.api.execute_with_retry'):
            with patch('app.routes.api.Historico'):
                r = client_logado_supervisor.post('/api/bulk-status', json={'chamado_ids': ['ch1'], 'novo_status': 'Concluído'}, content_type='application/json')
    assert r.status_code == 200
    data = r.get_json()
    assert data.get('sucesso') is True
    assert 'atualizados' in data
    assert 'total_solicitados' in data
    assert 'erros' in data


def test_usabilidade_editar_sem_permissao_retorna_403_mensagem_clara(client_logado_solicitante):
    """U-EDIT-01: Edição negada retorna 403 com mensagem de acesso negado."""
    r = client_logado_solicitante.post('/api/editar-chamado', data={'chamado_id': 'ch1'}, content_type='multipart/form-data')
    assert r.status_code == 403
    data = r.get_json()
    assert data is not None
    assert 'acesso negado' in data.get('erro', '').lower() or 'negado' in data.get('erro', '').lower()


# --- U-NOT / U-HEALTH ---


def test_usabilidade_notificacoes_estrutura_fixa(client_logado_solicitante):
    """U-NOT-01: Listagem de notificações retorna notificacoes e total_nao_lidas."""
    with patch('app.routes.api.listar_para_usuario', return_value=[]), \
         patch('app.routes.api.contar_nao_lidas', return_value=0):
        r = client_logado_solicitante.get('/api/notificacoes')
    assert r.status_code == 200
    data = r.get_json()
    assert 'notificacoes' in data
    assert 'total_nao_lidas' in data


def test_usabilidade_health_resposta_previsivel(client):
    """U-HEALTH-01: Health check retorna status ok para monitoramento."""
    r = client.get('/health')
    assert r.status_code == 200
    data = r.get_json()
    assert data == {'status': 'ok'}
