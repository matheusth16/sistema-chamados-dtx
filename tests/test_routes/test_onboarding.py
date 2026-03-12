"""Testes das rotas de onboarding: avancar, concluir, pular."""
import json
import pytest
from unittest.mock import patch, MagicMock


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _post_json(client, url, body=None):
    return client.post(
        url,
        data=json.dumps(body or {}),
        content_type='application/json',
    )


# ─── Autenticação obrigatória ─────────────────────────────────────────────────

def test_avancar_requer_login(client):
    r = _post_json(client, '/api/onboarding/avancar', {'passo': 1})
    assert r.status_code in (302, 401)


def test_concluir_requer_login(client):
    r = _post_json(client, '/api/onboarding/concluir')
    assert r.status_code in (302, 401)


def test_pular_requer_login(client):
    r = _post_json(client, '/api/onboarding/pular')
    assert r.status_code in (302, 401)


# ─── Validação de entrada ──────────────────────────────────────────────────────

def test_avancar_sem_passo_retorna_400(client_logado_solicitante):
    # A validação acontece antes de chamar o serviço — nenhum mock necessário
    r = _post_json(client_logado_solicitante, '/api/onboarding/avancar', {})
    assert r.status_code == 400
    assert r.get_json()['sucesso'] is False


def test_avancar_passo_negativo_retorna_400(client_logado_solicitante):
    r = _post_json(client_logado_solicitante, '/api/onboarding/avancar', {'passo': -1})
    assert r.status_code == 400
    assert r.get_json()['sucesso'] is False


def test_avancar_passo_nao_inteiro_retorna_400(client_logado_solicitante):
    r = _post_json(client_logado_solicitante, '/api/onboarding/avancar', {'passo': 'abc'})
    assert r.status_code == 400


# ─── Fluxo feliz: solicitante ─────────────────────────────────────────────────

def test_avancar_passo_solicitante(client_logado_solicitante):
    with patch('app.services.onboarding_service.db') as mock_db:
        mock_db.collection.return_value.document.return_value.update.return_value = None
        r = _post_json(client_logado_solicitante, '/api/onboarding/avancar', {'passo': 2})
    assert r.status_code == 200
    assert r.get_json()['sucesso'] is True


def test_concluir_solicitante(client_logado_solicitante):
    with patch('app.services.onboarding_service.db') as mock_db:
        mock_db.collection.return_value.document.return_value.update.return_value = None
        r = _post_json(client_logado_solicitante, '/api/onboarding/concluir')
    assert r.status_code == 200
    assert r.get_json()['sucesso'] is True


def test_pular_solicitante(client_logado_solicitante):
    with patch('app.services.onboarding_service.db') as mock_db:
        mock_db.collection.return_value.document.return_value.update.return_value = None
        r = _post_json(client_logado_solicitante, '/api/onboarding/pular')
    assert r.status_code == 200
    assert r.get_json()['sucesso'] is True


# ─── Fluxo feliz: supervisor ──────────────────────────────────────────────────

def test_avancar_passo_supervisor(client_logado_supervisor):
    with patch('app.services.onboarding_service.db') as mock_db:
        mock_db.collection.return_value.document.return_value.update.return_value = None
        r = _post_json(client_logado_supervisor, '/api/onboarding/avancar', {'passo': 3})
    assert r.status_code == 200
    assert r.get_json()['sucesso'] is True


def test_concluir_supervisor(client_logado_supervisor):
    with patch('app.services.onboarding_service.db') as mock_db:
        mock_db.collection.return_value.document.return_value.update.return_value = None
        r = _post_json(client_logado_supervisor, '/api/onboarding/concluir')
    assert r.status_code == 200
    assert r.get_json()['sucesso'] is True


# ─── Fluxo feliz: admin ───────────────────────────────────────────────────────

def test_avancar_passo_admin(client_logado_admin):
    with patch('app.services.onboarding_service.db') as mock_db:
        mock_db.collection.return_value.document.return_value.update.return_value = None
        r = _post_json(client_logado_admin, '/api/onboarding/avancar', {'passo': 5})
    assert r.status_code == 200
    assert r.get_json()['sucesso'] is True


def test_concluir_admin(client_logado_admin):
    with patch('app.services.onboarding_service.db') as mock_db:
        mock_db.collection.return_value.document.return_value.update.return_value = None
        r = _post_json(client_logado_admin, '/api/onboarding/concluir')
    assert r.status_code == 200
    assert r.get_json()['sucesso'] is True


# ─── Serviço: campos persistidos corretamente ─────────────────────────────────

def test_service_avancar_persiste_passo():
    """avancar_passo chama update com o passo correto."""
    from app.services.onboarding_service import avancar_passo
    with patch('app.services.onboarding_service.db') as mock_db:
        mock_update = mock_db.collection.return_value.document.return_value.update
        avancar_passo('uid_test', 4)
        mock_update.assert_called_once_with({'onboarding_passo': 4})


def test_service_concluir_persiste_flag():
    """concluir_onboarding chama update com onboarding_completo=True e passo=0."""
    from app.services.onboarding_service import concluir_onboarding
    with patch('app.services.onboarding_service.db') as mock_db:
        mock_update = mock_db.collection.return_value.document.return_value.update
        concluir_onboarding('uid_test')
        mock_update.assert_called_once_with({'onboarding_completo': True, 'onboarding_passo': 0})


# ─── Template: componente injetado / omitido ──────────────────────────────────

def _usuario_com_onboarding(onboarding_completo, onboarding_passo=0, perfil='solicitante'):
    u = MagicMock()
    u.id = 'uid_ob'
    u.email = 'ob@test.com'
    u.nome = 'Teste Onboarding'
    u.perfil = perfil
    u.area = 'Geral'
    u.areas = ['Geral']
    u.is_authenticated = True
    u.must_change_password = False
    u.onboarding_completo = onboarding_completo
    u.onboarding_passo = onboarding_passo
    u.get_id = lambda: 'uid_ob'
    return u


def test_template_inclui_onboarding_para_usuario_novo(client, app):
    """HTML da página inclui #onboarding-root para usuário com onboarding_completo=False."""
    novo = _usuario_com_onboarding(onboarding_completo=False, onboarding_passo=0)
    with patch('app.routes.auth.Usuario.get_by_email', return_value=novo):
        with patch('app.models_usuario.Usuario.get_by_id', return_value=novo):
            client.post('/login', data={'email': 'ob@test.com', 'senha': 'ok'})
            r = client.get('/meus-chamados')
    assert b'onboarding-root' in r.data


def test_template_omite_onboarding_para_usuario_que_ja_fez(client, app):
    """HTML da página NÃO inclui #onboarding-root para usuário com onboarding_completo=True."""
    veterano = _usuario_com_onboarding(onboarding_completo=True)
    with patch('app.routes.auth.Usuario.get_by_email', return_value=veterano):
        with patch('app.models_usuario.Usuario.get_by_id', return_value=veterano):
            client.post('/login', data={'email': 'ob@test.com', 'senha': 'ok'})
            r = client.get('/meus-chamados')
    assert b'onboarding-root' not in r.data


# ─── data-lang emitido corretamente ──────────────────────────────────────────

@pytest.mark.parametrize('lang,expected', [
    ('pt_BR', b'data-lang="pt_BR"'),
    ('en',    b'data-lang="en"'),
    ('es',    b'data-lang="es"'),
])
def test_template_emite_data_lang_correto(client, app, lang, expected):
    """O componente onboarding emite data-lang com o idioma da sessão."""
    novo = _usuario_com_onboarding(onboarding_completo=False)
    with patch('app.routes.auth.Usuario.get_by_email', return_value=novo):
        with patch('app.models_usuario.Usuario.get_by_id', return_value=novo):
            client.post('/login', data={'email': 'ob@test.com', 'senha': 'ok'})
            r = client.get('/meus-chamados?lang=' + lang)
    assert expected in r.data


# ─── Modelo: campos onboarding no from_dict / to_dict ────────────────────────

def test_model_from_dict_defaults_onboarding():
    """from_dict retorna onboarding_completo=False e onboarding_passo=0 por padrão."""
    from app.models_usuario import Usuario
    u = Usuario.from_dict({'email': 'x@x.com', 'nome': 'X', 'senha_hash': None}, id='uid1')
    assert u.onboarding_completo is False
    assert u.onboarding_passo == 0


def test_model_from_dict_persiste_onboarding_true():
    """from_dict lê onboarding_completo=True quando presente."""
    from app.models_usuario import Usuario
    u = Usuario.from_dict({
        'email': 'x@x.com', 'nome': 'X', 'senha_hash': None,
        'onboarding_completo': True, 'onboarding_passo': 3,
    }, id='uid1')
    assert u.onboarding_completo is True
    assert u.onboarding_passo == 3


def test_model_to_dict_inclui_onboarding():
    """to_dict inclui onboarding_completo e onboarding_passo."""
    from app.models_usuario import Usuario
    u = Usuario(id='uid', email='x@x.com', nome='X', onboarding_completo=True, onboarding_passo=5)
    d = u.to_dict()
    assert d['onboarding_completo'] is True
    assert d['onboarding_passo'] == 5
