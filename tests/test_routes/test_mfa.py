"""Testes das rotas de auto-serviço de MFA (setup, backup codes, desativar)."""

from unittest.mock import MagicMock, patch

import pyotp

from app.services import mfa_service


def _usuario_mock(uid="u_mfa_setup", email="setup@test.com"):
    """Usuario mock com mfa_enabled=False — login normal sem exigir 2ª etapa.

    Testes que precisam simular conta com MFA já habilitado devem setar
    `usuario.mfa_enabled = True` **após** o POST /login (a etapa de senha),
    para não disparar o redirecionamento a /verificar-mfa durante o login.
    """
    usuario = MagicMock()
    usuario.id = uid
    usuario.email = email
    usuario.nome = "Usuario Setup"
    usuario.perfil = "solicitante"
    usuario.must_change_password = False
    usuario.ativo = True
    usuario.get_id = lambda: uid
    usuario.is_authenticated = True
    usuario.is_active = True
    usuario.is_anonymous = False
    usuario.check_password = MagicMock(return_value=True)
    usuario.mfa_enabled = False
    usuario.mfa_secret = None
    usuario.mfa_backup_codes = []
    usuario.update = MagicMock(return_value=True)
    usuario.is_admin_or_above = False
    usuario.is_supervisor_or_above = False
    usuario.is_gestor = False
    return usuario


def test_mfa_configurar_sem_login_redireciona_login(client):
    """GET /mfa/configurar sem sessão autenticada redireciona para /login."""
    r = client.get("/mfa/configurar", follow_redirects=False)
    assert r.status_code == 302
    assert "login" in r.location


def test_mfa_configurar_get_retorna_200_com_qr(client):
    """GET /mfa/configurar (MFA ainda não habilitado) retorna 200 com QR code."""
    usuario = _usuario_mock()
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post("/login", data={"email": usuario.email, "senha": "ok"})
        r = client.get("/mfa/configurar")

    assert r.status_code == 200
    assert b"data:image/png;base64," in r.data


def test_mfa_configurar_get_gera_secret_na_sessao(client):
    """GET /mfa/configurar armazena um secret temporário na sessão."""
    usuario = _usuario_mock()
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post("/login", data={"email": usuario.email, "senha": "ok"})
        client.get("/mfa/configurar")
        with client.session_transaction() as sess:
            assert sess.get("mfa_setup_secret")


def test_mfa_configurar_post_codigo_correto_habilita_mfa(client):
    """POST /mfa/configurar com código TOTP correto habilita o MFA e redireciona p/ backup codes."""
    usuario = _usuario_mock()
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post("/login", data={"email": usuario.email, "senha": "ok"})
        client.get("/mfa/configurar")
        with client.session_transaction() as sess:
            secret = sess["mfa_setup_secret"]
        codigo = pyotp.TOTP(secret).now()

        r = client.post("/mfa/configurar", data={"codigo": codigo}, follow_redirects=False)

    assert r.status_code == 302
    assert "codigos-backup" in r.location
    usuario.update.assert_called_once()
    _, kwargs = usuario.update.call_args
    assert kwargs["mfa_enabled"] is True
    assert kwargs["mfa_secret"] == secret
    assert len(kwargs["mfa_backup_codes"]) == mfa_service.BACKUP_CODES_COUNT


def test_mfa_configurar_post_codigo_incorreto_nao_habilita(client):
    """POST /mfa/configurar com código incorreto não habilita MFA."""
    usuario = _usuario_mock()
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post("/login", data={"email": usuario.email, "senha": "ok"})
        client.get("/mfa/configurar")
        r = client.post("/mfa/configurar", data={"codigo": "000000"}, follow_redirects=False)

    assert r.status_code == 302
    assert "configurar" in r.location
    usuario.update.assert_not_called()


def test_mfa_configurar_post_sem_secret_na_sessao_redireciona(client):
    """POST /mfa/configurar sem GET prévio (sem secret na sessão) redireciona para GET."""
    usuario = _usuario_mock()
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post("/login", data={"email": usuario.email, "senha": "ok"})
        r = client.post("/mfa/configurar", data={"codigo": "123456"}, follow_redirects=False)

    assert r.status_code == 302
    assert "configurar" in r.location


def test_mfa_codigos_backup_sem_sessao_redireciona_configurar(client):
    """GET /mfa/codigos-backup sem códigos pendentes na sessão redireciona para /mfa/configurar."""
    usuario = _usuario_mock()
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post("/login", data={"email": usuario.email, "senha": "ok"})
        r = client.get("/mfa/codigos-backup", follow_redirects=False)

    assert r.status_code == 302
    assert "configurar" in r.location


def test_mfa_codigos_backup_exibe_uma_unica_vez(client):
    """GET /mfa/codigos-backup exibe os códigos e os remove da sessão (uso único)."""
    usuario = _usuario_mock()
    codigos = mfa_service.gerar_codigos_backup(3)
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post("/login", data={"email": usuario.email, "senha": "ok"})
        with client.session_transaction() as sess:
            sess["mfa_backup_codes_display"] = codigos

        r = client.get("/mfa/codigos-backup")
        assert r.status_code == 200
        for c in codigos:
            assert c.encode() in r.data

        with client.session_transaction() as sess:
            assert "mfa_backup_codes_display" not in sess

        r2 = client.get("/mfa/codigos-backup", follow_redirects=False)

    assert r2.status_code == 302
    assert "configurar" in r2.location


def test_mfa_codigos_backup_tem_botao_imprimir(client):
    """Tela de backup codes tem botão de imprimir (window.print())."""
    usuario = _usuario_mock()
    codigos = mfa_service.gerar_codigos_backup(3)
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post("/login", data={"email": usuario.email, "senha": "ok"})
        with client.session_transaction() as sess:
            sess["mfa_backup_codes_display"] = codigos
        r = client.get("/mfa/codigos-backup")

    assert r.status_code == 200
    assert b'data-testid="mfa-backup-codes-print-btn"' in r.data
    assert b"window.print()" in r.data


def test_mfa_codigos_backup_botao_continuar_solicitante_vai_para_index(client):
    """Botão 'Continuar' da tela de backup codes leva solicitante para / (não de volta ao setup)."""
    usuario = _usuario_mock()
    codigos = mfa_service.gerar_codigos_backup(3)
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post("/login", data={"email": usuario.email, "senha": "ok"})
        with client.session_transaction() as sess:
            sess["mfa_backup_codes_display"] = codigos
        r = client.get("/mfa/codigos-backup")

    assert r.status_code == 200
    assert b'href="/" data-testid="mfa-backup-codes-continue-btn"' in r.data


def test_mfa_codigos_backup_botao_continuar_supervisor_vai_para_painel(client):
    """Botão 'Continuar' leva supervisor (não-gestor) para /painel."""
    usuario = _usuario_mock(uid="u_sup_mfa", email="sup_mfa@test.com")
    usuario.perfil = "supervisor"
    usuario.is_supervisor_or_above = True
    usuario.is_gestor_only = False
    codigos = mfa_service.gerar_codigos_backup(3)
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post("/login", data={"email": usuario.email, "senha": "ok"})
        with client.session_transaction() as sess:
            sess["mfa_backup_codes_display"] = codigos
        r = client.get("/mfa/codigos-backup")

    assert r.status_code == 200
    assert b'href="/painel" data-testid="mfa-backup-codes-continue-btn"' in r.data


def test_mfa_codigos_backup_botao_continuar_admin_vai_para_admin(client):
    """Botão 'Continuar' leva admin para /admin."""
    usuario = _usuario_mock(uid="u_admin_mfa", email="admin_mfa@test.com")
    usuario.perfil = "admin"
    usuario.is_admin_or_above = True
    usuario.is_supervisor_or_above = True
    usuario.is_gestor_only = False
    codigos = mfa_service.gerar_codigos_backup(3)
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post("/login", data={"email": usuario.email, "senha": "ok"})
        with client.session_transaction() as sess:
            sess["mfa_backup_codes_display"] = codigos
        r = client.get("/mfa/codigos-backup")

    assert r.status_code == 200
    assert b'href="/admin" data-testid="mfa-backup-codes-continue-btn"' in r.data


def test_mfa_desativar_com_senha_correta_desabilita(client):
    """POST /mfa/desativar com senha correta desabilita o MFA."""
    usuario = _usuario_mock()
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post("/login", data={"email": usuario.email, "senha": "ok"})
        usuario.mfa_enabled = True
        r = client.post("/mfa/desativar", data={"senha_atual": "ok"}, follow_redirects=False)

    assert r.status_code == 302
    usuario.update.assert_called_once_with(
        mfa_enabled=False, mfa_secret=None, mfa_backup_codes=None
    )


def test_mfa_desativar_com_senha_incorreta_nao_desabilita(client):
    """POST /mfa/desativar com senha incorreta não desabilita o MFA."""
    usuario = _usuario_mock()
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post("/login", data={"email": usuario.email, "senha": "ok"})
        usuario.mfa_enabled = True
        usuario.check_password = MagicMock(return_value=False)
        r = client.post("/mfa/desativar", data={"senha_atual": "errada"}, follow_redirects=False)

    assert r.status_code == 302
    usuario.update.assert_not_called()


def test_mfa_regenerar_backup_codes_com_senha_correta(client):
    """POST /mfa/regenerar-backup-codes com senha correta gera novos códigos."""
    usuario = _usuario_mock()
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post("/login", data={"email": usuario.email, "senha": "ok"})
        usuario.mfa_enabled = True
        r = client.post(
            "/mfa/regenerar-backup-codes", data={"senha_atual": "ok"}, follow_redirects=False
        )

    assert r.status_code == 302
    assert "codigos-backup" in r.location
    usuario.update.assert_called_once()
    _, kwargs = usuario.update.call_args
    assert len(kwargs["mfa_backup_codes"]) == mfa_service.BACKUP_CODES_COUNT


def test_mfa_regenerar_backup_codes_com_senha_incorreta_nao_gera(client):
    """POST /mfa/regenerar-backup-codes com senha incorreta não altera os códigos."""
    usuario = _usuario_mock()
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post("/login", data={"email": usuario.email, "senha": "ok"})
        usuario.mfa_enabled = True
        usuario.check_password = MagicMock(return_value=False)
        r = client.post(
            "/mfa/regenerar-backup-codes",
            data={"senha_atual": "errada"},
            follow_redirects=False,
        )

    assert r.status_code == 302
    usuario.update.assert_not_called()
