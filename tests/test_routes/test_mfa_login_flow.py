"""Testes do fluxo de MFA integrado ao login (segunda etapa). Ref: CT-MFA-*."""

from unittest.mock import MagicMock, patch

import pyotp

from app.services import mfa_service
from app.services.login_attempts import MAX_LOGIN_ATTEMPTS


def _usuario_mfa_mock(uid="u_mfa", email="mfa@test.com", secret=None, backup_codes=None):
    secret = secret or mfa_service.gerar_secret()
    usuario = MagicMock()
    usuario.id = uid
    usuario.email = email
    usuario.nome = "Usuario MFA"
    usuario.perfil = "solicitante"
    usuario.must_change_password = False
    usuario.ativo = True
    usuario.get_id = lambda: uid
    usuario.is_authenticated = True
    usuario.is_active = True
    usuario.is_anonymous = False
    usuario.check_password = MagicMock(return_value=True)
    usuario.mfa_enabled = True
    usuario.mfa_secret = secret
    usuario.mfa_backup_codes = backup_codes or []
    usuario.update = MagicMock(return_value=True)
    usuario.is_admin_or_above = False
    usuario.is_supervisor_or_above = False
    usuario.is_gestor = False
    return usuario


def test_login_com_mfa_habilitado_redireciona_para_verificar_mfa(client):
    """Login com senha correta e mfa_enabled=True não autentica direto; vai para 2ª etapa."""
    usuario = _usuario_mfa_mock()
    with patch("app.routes.auth.Usuario.get_by_email", return_value=usuario):
        r = client.post(
            "/login", data={"email": usuario.email, "senha": "ok"}, follow_redirects=False
        )
    assert r.status_code == 302
    assert "verificar-mfa" in r.location

    # Sessão ainda não está autenticada
    r2 = client.get("/", follow_redirects=False)
    assert r2.status_code == 302
    assert "login" in r2.location


def test_verificar_mfa_get_sem_pendencia_redireciona_login(client):
    """GET /verificar-mfa sem etapa de senha concluída redireciona para /login."""
    r = client.get("/verificar-mfa", follow_redirects=False)
    assert r.status_code == 302
    assert "login" in r.location


def test_verificar_mfa_get_com_pendencia_retorna_200(client):
    """GET /verificar-mfa após senha validada exibe o formulário de código."""
    usuario = _usuario_mfa_mock()
    with patch("app.routes.auth.Usuario.get_by_email", return_value=usuario):
        client.post("/login", data={"email": usuario.email, "senha": "ok"}, follow_redirects=False)
        r = client.get("/verificar-mfa")
    assert r.status_code == 200


def test_verificar_mfa_codigo_totp_correto_completa_login(client):
    """Código TOTP correto conclui o login (sessão autenticada)."""
    usuario = _usuario_mfa_mock()
    codigo = pyotp.TOTP(usuario.mfa_secret).now()
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.routes.auth.Usuario.get_by_id", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post("/login", data={"email": usuario.email, "senha": "ok"}, follow_redirects=False)
        r = client.post("/verificar-mfa", data={"codigo": codigo}, follow_redirects=False)

    assert r.status_code == 302
    assert "verificar-mfa" not in (r.location or "")
    assert "/login" not in (r.location or "")


def test_verificar_mfa_codigo_invalido_nao_loga_e_mostra_erro(client):
    """Código incorreto não autentica e retorna à tela de verificação com flash."""
    usuario = _usuario_mfa_mock()
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.routes.auth.Usuario.get_by_id", return_value=usuario),
    ):
        client.post("/login", data={"email": usuario.email, "senha": "ok"}, follow_redirects=False)
        r = client.post("/verificar-mfa", data={"codigo": "000000"}, follow_redirects=False)

    assert r.status_code == 302
    assert "verificar-mfa" in r.location

    r2 = client.get("/", follow_redirects=False)
    assert r2.status_code == 302
    assert "login" in r2.location


def test_verificar_mfa_codigo_backup_valido_completa_login_e_consome(client):
    """Código de backup válido autentica e é removido da lista (uso único)."""
    codigos = mfa_service.gerar_codigos_backup(3)
    hashes = mfa_service.hash_codigos_backup(codigos)
    usuario = _usuario_mfa_mock(backup_codes=hashes)

    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.routes.auth.Usuario.get_by_id", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post("/login", data={"email": usuario.email, "senha": "ok"}, follow_redirects=False)
        r = client.post("/verificar-mfa", data={"codigo": codigos[0]}, follow_redirects=False)

    assert r.status_code == 302
    assert "verificar-mfa" not in (r.location or "")
    usuario.update.assert_called_once()
    _, kwargs = usuario.update.call_args
    assert len(kwargs["mfa_backup_codes"]) == 2


def test_verificar_mfa_bloqueia_apos_max_tentativas(client):
    """Após MAX_LOGIN_ATTEMPTS códigos inválidos, aplica lockout do identificador mfa:<id>."""
    usuario = _usuario_mfa_mock()
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.routes.auth.Usuario.get_by_id", return_value=usuario),
        patch("app.routes.auth.LoginAttemptTracker.is_locked_out", return_value=False),
        patch(
            "app.routes.auth.LoginAttemptTracker.increment_attempt",
            return_value=MAX_LOGIN_ATTEMPTS,
        ),
        patch("app.routes.auth.LoginAttemptTracker.apply_lockout") as mock_lockout,
    ):
        client.post("/login", data={"email": usuario.email, "senha": "ok"}, follow_redirects=False)
        r = client.post("/verificar-mfa", data={"codigo": "000000"}, follow_redirects=False)

    assert r.status_code == 302
    assert "login" in r.location
    mock_lockout.assert_called_once_with(f"mfa:{usuario.id}")


def test_verificar_mfa_expira_apos_ttl(client):
    """Sessão pendente de MFA expirada (> 5 min) redireciona para /login."""
    usuario = _usuario_mfa_mock()
    with patch("app.routes.auth.Usuario.get_by_email", return_value=usuario):
        client.post("/login", data={"email": usuario.email, "senha": "ok"}, follow_redirects=False)

    with client.session_transaction() as sess:
        sess["mfa_pendente_ts"] = 0

    r = client.get("/verificar-mfa", follow_redirects=False)
    assert r.status_code == 302
    assert "login" in r.location


def test_login_pula_mfa_quando_dispositivo_confiavel(client):
    """Após marcar 'confiar neste dispositivo', novo login não exige MFA novamente."""
    usuario = _usuario_mfa_mock()
    codigo = pyotp.TOTP(usuario.mfa_secret).now()
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.routes.auth.Usuario.get_by_id", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post("/login", data={"email": usuario.email, "senha": "ok"}, follow_redirects=False)
        client.post(
            "/verificar-mfa",
            data={"codigo": codigo, "confiar-dispositivo": "on"},
            follow_redirects=False,
        )
        client.get("/logout", follow_redirects=False)

        r = client.post(
            "/login", data={"email": usuario.email, "senha": "ok"}, follow_redirects=False
        )

    assert r.status_code == 302
    assert "verificar-mfa" not in (r.location or "")


def test_login_sem_confiar_dispositivo_exige_mfa_novamente(client):
    """Sem marcar 'confiar neste dispositivo', o próximo login volta a exigir MFA."""
    usuario = _usuario_mfa_mock()
    codigo = pyotp.TOTP(usuario.mfa_secret).now()
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.routes.auth.Usuario.get_by_id", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post("/login", data={"email": usuario.email, "senha": "ok"}, follow_redirects=False)
        client.post("/verificar-mfa", data={"codigo": codigo}, follow_redirects=False)
        client.get("/logout", follow_redirects=False)

        r = client.post(
            "/login", data={"email": usuario.email, "senha": "ok"}, follow_redirects=False
        )

    assert r.status_code == 302
    assert "verificar-mfa" in r.location
