"""Testes de /admin/alterar-senha — GET e POST para perfis admin e admin_global."""

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ROTA = "/admin/alterar-senha"
_DADOS_VALIDOS = {
    "senha_atual": "SenhaAtual@1",
    "nova_senha": "NovaSenha@2",
    "confirmar_senha": "NovaSenha@2",
}


def _mock_usuario(perfil, check_ok=True, update_ok=True):
    u = MagicMock()
    u.id = f"{perfil}_1"
    u.email = f"{perfil}@test.com"
    u.nome = f"Usuário {perfil}"
    u.perfil = perfil
    u.areas = ["Geral"]
    u.area = "Geral"
    u.is_authenticated = True
    u.is_active = True
    u.is_anonymous = False
    u.must_change_password = False
    u.onboarding_completo = True
    u.is_admin_or_above = perfil in ("admin", "admin_global")
    u.is_supervisor_or_above = perfil in ("supervisor", "admin", "admin_global")
    u.get_id = lambda: f"{perfil}_1"
    u.check_password = MagicMock(return_value=check_ok)
    u.update = MagicMock(return_value=update_ok)
    return u


def _login(client, usuario):
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post("/login", data={"email": usuario.email, "senha": "ok"}, follow_redirects=False)


# ---------------------------------------------------------------------------
# Controle de acesso — GET
# ---------------------------------------------------------------------------


def test_get_sem_login_redireciona_para_login(client):
    r = client.get(_ROTA, follow_redirects=False)
    assert r.status_code == 302
    assert "login" in r.location


def test_get_solicitante_nao_acessa(client, app):
    u = _mock_usuario("solicitante")
    _login(client, u)
    with patch("app.models_usuario.Usuario.get_by_id", return_value=u):
        r = client.get(_ROTA, follow_redirects=False)
    assert r.status_code in (302, 403)
    if r.status_code == 302:
        assert "/admin/alterar-senha" not in (r.location or "")


def test_get_supervisor_nao_acessa(client, app):
    u = _mock_usuario("supervisor")
    _login(client, u)
    with patch("app.models_usuario.Usuario.get_by_id", return_value=u):
        r = client.get(_ROTA, follow_redirects=False)
    assert r.status_code in (302, 403)
    if r.status_code == 302:
        assert "/admin/alterar-senha" not in (r.location or "")


def test_get_admin_retorna_200(client_logado_admin):
    r = client_logado_admin.get(_ROTA, follow_redirects=False)
    assert r.status_code == 200


def test_get_admin_global_retorna_200(client_logado_admin_global):
    r = client_logado_admin_global.get(_ROTA, follow_redirects=False)
    assert r.status_code == 200


def test_get_exibe_campo_senha_atual(client_logado_admin):
    r = client_logado_admin.get(_ROTA)
    assert b"senha_atual" in r.data


def test_get_exibe_campo_nova_senha(client_logado_admin):
    r = client_logado_admin.get(_ROTA)
    assert b"nova_senha" in r.data


def test_get_exibe_campo_confirmar_senha(client_logado_admin):
    r = client_logado_admin.get(_ROTA)
    assert b"confirmar_senha" in r.data


# ---------------------------------------------------------------------------
# Controle de acesso — POST
# ---------------------------------------------------------------------------


def test_post_sem_login_redireciona(client):
    r = client.post(_ROTA, data=_DADOS_VALIDOS, follow_redirects=False)
    assert r.status_code == 302
    assert "login" in r.location


def test_post_solicitante_nao_acessa(client, app):
    u = _mock_usuario("solicitante")
    _login(client, u)
    with patch("app.models_usuario.Usuario.get_by_id", return_value=u):
        r = client.post(_ROTA, data=_DADOS_VALIDOS, follow_redirects=False)
    assert r.status_code in (302, 403)


# ---------------------------------------------------------------------------
# Validações de formulário (admin)
# ---------------------------------------------------------------------------


def test_post_campos_vazios_redireciona_com_erro(client_logado_admin):
    r = client_logado_admin.post(_ROTA, data={}, follow_redirects=True)
    assert r.status_code == 200
    # O formulário deve recarregar com os campos — confirma que não houve 500 ou redirect inesperado
    assert b"senha_atual" in r.data


def test_post_senha_atual_incorreta_redireciona_com_erro(client, app):
    u = _mock_usuario("admin", check_ok=True)  # True para o login funcionar
    _login(client, u)
    # Após login, substitui o mock para simular senha atual incorreta na rota
    u.check_password = MagicMock(return_value=False)
    with patch("app.models_usuario.Usuario.get_by_id", return_value=u):
        r = client.post(_ROTA, data=_DADOS_VALIDOS, follow_redirects=True)
    assert r.status_code == 200
    u.check_password.assert_called_once_with("SenhaAtual@1")
    u.update.assert_not_called()


def test_post_nova_senha_curta_redireciona_com_erro(client, app):
    u = _mock_usuario("admin", check_ok=True)
    _login(client, u)
    dados = {**_DADOS_VALIDOS, "nova_senha": "Ab1", "confirmar_senha": "Ab1"}
    with patch("app.models_usuario.Usuario.get_by_id", return_value=u):
        r = client.post(_ROTA, data=dados, follow_redirects=True)
    assert r.status_code == 200
    u.update.assert_not_called()


def test_post_nova_senha_sem_letra_redireciona_com_erro(client, app):
    u = _mock_usuario("admin", check_ok=True)
    _login(client, u)
    dados = {**_DADOS_VALIDOS, "nova_senha": "12345678", "confirmar_senha": "12345678"}
    with patch("app.models_usuario.Usuario.get_by_id", return_value=u):
        r = client.post(_ROTA, data=dados, follow_redirects=True)
    assert r.status_code == 200
    u.update.assert_not_called()


def test_post_nova_senha_sem_digito_redireciona_com_erro(client, app):
    u = _mock_usuario("admin", check_ok=True)
    _login(client, u)
    dados = {**_DADOS_VALIDOS, "nova_senha": "SenhaSemNum", "confirmar_senha": "SenhaSemNum"}
    with patch("app.models_usuario.Usuario.get_by_id", return_value=u):
        r = client.post(_ROTA, data=dados, follow_redirects=True)
    assert r.status_code == 200
    u.update.assert_not_called()


def test_post_senhas_nao_conferem_redireciona_com_erro(client, app):
    u = _mock_usuario("admin", check_ok=True)
    _login(client, u)
    dados = {**_DADOS_VALIDOS, "confirmar_senha": "OutraSenha@9"}
    with patch("app.models_usuario.Usuario.get_by_id", return_value=u):
        r = client.post(_ROTA, data=dados, follow_redirects=True)
    assert r.status_code == 200
    u.update.assert_not_called()


# ---------------------------------------------------------------------------
# Sucesso
# ---------------------------------------------------------------------------


def test_post_admin_sucesso_chama_update(client, app):
    u = _mock_usuario("admin", check_ok=True, update_ok=True)
    _login(client, u)
    with patch("app.models_usuario.Usuario.get_by_id", return_value=u):
        r = client.post(_ROTA, data=_DADOS_VALIDOS, follow_redirects=False)
    assert r.status_code == 302
    u.update.assert_called_once()
    kwargs = u.update.call_args[1]
    assert kwargs["senha"] == "NovaSenha@2"
    assert kwargs["must_change_password"] is False


def test_post_admin_global_sucesso_chama_update(client, app):
    u = _mock_usuario("admin_global", check_ok=True, update_ok=True)
    _login(client, u)
    with patch("app.models_usuario.Usuario.get_by_id", return_value=u):
        r = client.post(_ROTA, data=_DADOS_VALIDOS, follow_redirects=False)
    assert r.status_code == 302
    u.update.assert_called_once()


def test_post_sucesso_redireciona_para_alterar_senha(client, app):
    """Após sucesso, redireciona de volta para a própria página (onde o flash aparece)."""
    u = _mock_usuario("admin", check_ok=True, update_ok=True)
    _login(client, u)
    with patch("app.models_usuario.Usuario.get_by_id", return_value=u):
        r = client.post(_ROTA, data=_DADOS_VALIDOS, follow_redirects=False)
    assert "alterar-senha" in r.location


# ---------------------------------------------------------------------------
# Falha de update (DB down)
# ---------------------------------------------------------------------------


def test_post_update_retorna_false_nao_quebra(client, app):
    u = _mock_usuario("admin", check_ok=True, update_ok=False)
    _login(client, u)
    with patch("app.models_usuario.Usuario.get_by_id", return_value=u):
        r = client.post(_ROTA, data=_DADOS_VALIDOS, follow_redirects=False)
    assert r.status_code == 302


def test_post_update_lanca_excecao_redireciona(client, app):
    u = _mock_usuario("admin", check_ok=True)
    u.update = MagicMock(side_effect=Exception("db error"))
    _login(client, u)
    with patch("app.models_usuario.Usuario.get_by_id", return_value=u):
        r = client.post(_ROTA, data=_DADOS_VALIDOS, follow_redirects=False)
    assert r.status_code == 302
