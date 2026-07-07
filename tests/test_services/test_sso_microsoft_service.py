"""Testes do serviço de SSO Microsoft (Entra ID — Authorization Code + PKCE via MSAL).

Nunca acessa endpoints reais da Microsoft — msal.ConfidentialClientApplication é mockado.
"""

from unittest.mock import MagicMock, patch


def _configurar_app_sso(app):
    app.config["SSO_CLIENT_ID"] = "client-123"
    app.config["SSO_CLIENT_SECRET"] = "secret-abc"
    app.config["SSO_TENANT_ID"] = "tenant-dtx"
    app.config["SSO_REDIRECT_URI"] = "https://chamados.dtx.aero/login/microsoft/callback"
    return app


# ── validar_tenant ─────────────────────────────────────────────────────────────


def test_validar_tenant_aceita_tid_correspondente(app):
    from app.services import sso_microsoft_service

    _configurar_app_sso(app)
    with app.app_context():
        assert sso_microsoft_service.validar_tenant({"tid": "tenant-dtx"}) is True


def test_validar_tenant_rejeita_tid_diferente(app):
    from app.services import sso_microsoft_service

    _configurar_app_sso(app)
    with app.app_context():
        assert sso_microsoft_service.validar_tenant({"tid": "outro-tenant"}) is False


def test_validar_tenant_rejeita_claim_ausente(app):
    from app.services import sso_microsoft_service

    _configurar_app_sso(app)
    with app.app_context():
        assert sso_microsoft_service.validar_tenant({}) is False


# ── extrair_identidade ───────────────────────────────────────────────────────────


def test_extrair_identidade_usa_preferred_username():
    from app.services import sso_microsoft_service

    email, nome = sso_microsoft_service.extrair_identidade(
        {"preferred_username": "Maria.Silva@DTX.aero", "name": "Maria Silva"}
    )
    assert email == "maria.silva@dtx.aero"
    assert nome == "Maria Silva"


def test_extrair_identidade_fallback_email_claim():
    from app.services import sso_microsoft_service

    email, nome = sso_microsoft_service.extrair_identidade(
        {"email": "joao@dtx.aero", "name": "João"}
    )
    assert email == "joao@dtx.aero"
    assert nome == "João"


def test_extrair_identidade_nome_ausente_usa_local_part():
    from app.services import sso_microsoft_service

    email, nome = sso_microsoft_service.extrair_identidade({"preferred_username": "ana@dtx.aero"})
    assert email == "ana@dtx.aero"
    assert nome == "ana"


# ── iniciar_fluxo_login ─────────────────────────────────────────────────────────


def test_iniciar_fluxo_login_chama_msal_com_scopes_e_redirect_corretos(app):
    from app.services import sso_microsoft_service

    _configurar_app_sso(app)
    mock_flow = {"auth_uri": "https://login.microsoftonline.com/authorize?x=1", "state": "abc"}
    mock_msal_instance = MagicMock()
    mock_msal_instance.initiate_auth_code_flow.return_value = mock_flow

    with (
        app.app_context(),
        patch(
            "app.services.sso_microsoft_service.msal.ConfidentialClientApplication",
            return_value=mock_msal_instance,
        ) as mock_cca,
    ):
        auth_uri, flow = sso_microsoft_service.iniciar_fluxo_login()

    mock_cca.assert_called_once_with(
        client_id="client-123",
        client_credential="secret-abc",
        authority="https://login.microsoftonline.com/tenant-dtx",
    )
    mock_msal_instance.initiate_auth_code_flow.assert_called_once_with(
        scopes=["User.Read"],
        redirect_uri="https://chamados.dtx.aero/login/microsoft/callback",
    )
    assert auth_uri == mock_flow["auth_uri"]
    assert flow == mock_flow


# ── concluir_fluxo_login ─────────────────────────────────────────────────────────


def test_concluir_fluxo_login_retorna_claims_em_sucesso(app):
    from app.services import sso_microsoft_service

    _configurar_app_sso(app)
    flow = {"state": "abc"}
    callback_args = {"code": "xyz", "state": "abc"}
    mock_result = {"id_token_claims": {"tid": "tenant-dtx", "preferred_username": "a@dtx.aero"}}
    mock_msal_instance = MagicMock()
    mock_msal_instance.acquire_token_by_auth_code_flow.return_value = mock_result

    with (
        app.app_context(),
        patch(
            "app.services.sso_microsoft_service.msal.ConfidentialClientApplication",
            return_value=mock_msal_instance,
        ),
    ):
        result = sso_microsoft_service.concluir_fluxo_login(flow, callback_args)

    mock_msal_instance.acquire_token_by_auth_code_flow.assert_called_once_with(flow, callback_args)
    assert result == mock_result


def test_concluir_fluxo_login_retorna_erro_quando_msal_retorna_error(app):
    from app.services import sso_microsoft_service

    _configurar_app_sso(app)
    mock_result = {"error": "invalid_grant", "error_description": "code expired"}
    mock_msal_instance = MagicMock()
    mock_msal_instance.acquire_token_by_auth_code_flow.return_value = mock_result

    with (
        app.app_context(),
        patch(
            "app.services.sso_microsoft_service.msal.ConfidentialClientApplication",
            return_value=mock_msal_instance,
        ),
    ):
        result = sso_microsoft_service.concluir_fluxo_login({}, {})

    assert result["error"] == "invalid_grant"
