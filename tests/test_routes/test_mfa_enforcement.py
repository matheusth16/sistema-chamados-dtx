"""Testes de obrigatoriedade do MFA: nenhum perfil acessa o sistema sem configurá-lo primeiro."""

from unittest.mock import MagicMock, patch

import pytest


def _usuario_mock(uid, email, perfil, mfa_enabled=False, must_change_password=False):
    usuario = MagicMock()
    usuario.id = uid
    usuario.email = email
    usuario.nome = "Usuario Teste"
    usuario.perfil = perfil
    usuario.must_change_password = must_change_password
    usuario.ativo = True
    usuario.get_id = lambda: uid
    usuario.is_authenticated = True
    usuario.is_active = True
    usuario.is_anonymous = False
    usuario.check_password = MagicMock(return_value=True)
    usuario.mfa_enabled = mfa_enabled
    usuario.is_admin_or_above = perfil in ("admin", "admin_global")
    usuario.is_supervisor_or_above = perfil in ("supervisor", "admin", "admin_global")
    usuario.is_gestor = False
    return usuario


@pytest.mark.parametrize("perfil", ["solicitante", "supervisor", "admin", "admin_global"])
def test_login_sem_mfa_configurado_redireciona_para_mfa_configurar(client, perfil):
    """Login com credenciais corretas mas mfa_enabled=False redireciona para /mfa/configurar, para qualquer perfil."""
    usuario = _usuario_mock(f"u_{perfil}", f"{perfil}@test.com", perfil, mfa_enabled=False)
    with patch("app.routes.auth.Usuario.get_by_email", return_value=usuario):
        r = client.post(
            "/login", data={"email": usuario.email, "senha": "ok"}, follow_redirects=False
        )
    assert r.status_code == 302
    assert "mfa" in r.location and "configurar" in r.location


@pytest.mark.parametrize("perfil", ["solicitante", "supervisor", "admin", "admin_global"])
def test_navegar_sem_mfa_configurado_redireciona_para_mfa_configurar(client, perfil):
    """Após o login, qualquer navegação é interceptada e redirecionada para /mfa/configurar até o MFA ser configurado."""
    usuario = _usuario_mock(f"u2_{perfil}", f"nav_{perfil}@test.com", perfil, mfa_enabled=False)
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post("/login", data={"email": usuario.email, "senha": "ok"}, follow_redirects=False)
        r = client.get("/")
    assert r.status_code == 302
    assert "mfa" in r.location and "configurar" in r.location


def test_rotas_isentas_permanecem_acessiveis_sem_mfa_configurado(client):
    """/mfa/configurar e /logout não entram em loop de redirecionamento mesmo com mfa_enabled=False."""
    usuario = _usuario_mock("u_isento", "isento@test.com", "solicitante", mfa_enabled=False)
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post("/login", data={"email": usuario.email, "senha": "ok"}, follow_redirects=False)

        r_configurar = client.get("/mfa/configurar")
        assert r_configurar.status_code == 200

        r_logout = client.get("/logout", follow_redirects=False)
        assert r_logout.status_code == 302
        assert "login" in r_logout.location


def test_troca_de_senha_obrigatoria_tem_prioridade_sobre_mfa(client):
    """Com must_change_password=True e mfa_enabled=False, o usuário vai primeiro para a troca de senha."""
    usuario = _usuario_mock(
        "u_senha",
        "senha@test.com",
        "solicitante",
        mfa_enabled=False,
        must_change_password=True,
    )
    with patch("app.routes.auth.Usuario.get_by_email", return_value=usuario):
        r = client.post(
            "/login", data={"email": usuario.email, "senha": "ok"}, follow_redirects=False
        )
    assert r.status_code == 302
    assert "alterar-senha-obrigatoria" in r.location


def test_apos_configurar_mfa_navegacao_deixa_de_ser_bloqueada(client):
    """Uma vez com mfa_enabled=True, o middleware para de redirecionar para /mfa/configurar."""
    usuario = _usuario_mock("u_done", "done@test.com", "supervisor", mfa_enabled=False)
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
        patch("app.routes.auth._dispositivo_confiavel", return_value=True),
    ):
        client.post("/login", data={"email": usuario.email, "senha": "ok"}, follow_redirects=False)
        usuario.mfa_enabled = True
        r = client.get("/painel", follow_redirects=False)

    assert not (r.status_code == 302 and "mfa" in (r.location or "") and "configurar" in r.location)
