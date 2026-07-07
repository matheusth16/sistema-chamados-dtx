"""Serviço de SSO "Entrar com Microsoft" (Entra ID — Authorization Code + PKCE via MSAL).

Restrito ao tenant único da DTX: a authority URL já é tenant-specific (Microsoft
recusa contas de outros tenants antes mesmo de emitir o token) e validar_tenant()
é a checagem de defesa em profundidade do lado da aplicação.
"""

from __future__ import annotations

import logging

import msal
from flask import current_app

logger = logging.getLogger(__name__)

SCOPES = ["User.Read"]


def _msal_app() -> msal.ConfidentialClientApplication:
    return msal.ConfidentialClientApplication(
        client_id=current_app.config["SSO_CLIENT_ID"],
        client_credential=current_app.config["SSO_CLIENT_SECRET"],
        authority=f"https://login.microsoftonline.com/{current_app.config['SSO_TENANT_ID']}",
    )


def iniciar_fluxo_login() -> tuple[str, dict]:
    """Inicia o fluxo de autorização (Authorization Code + PKCE).

    Retorna (auth_uri, flow) — flow deve ser guardado na sessão do servidor e
    devolvido inteiro para concluir_fluxo_login() no callback.
    """
    flow = _msal_app().initiate_auth_code_flow(
        scopes=SCOPES,
        redirect_uri=current_app.config["SSO_REDIRECT_URI"],
    )
    return flow.get("auth_uri"), flow


def concluir_fluxo_login(flow: dict, callback_args: dict) -> dict:
    """Troca o código de autorização pelo token, validando state/PKCE internamente.

    Retorna o dict de resultado do MSAL: contém "id_token_claims" em sucesso,
    ou "error"/"error_description" em falha.
    """
    return _msal_app().acquire_token_by_auth_code_flow(flow, callback_args)


def validar_tenant(id_token_claims: dict) -> bool:
    """True somente se o claim 'tid' do token corresponder ao tenant configurado da DTX."""
    tenant_id = current_app.config.get("SSO_TENANT_ID", "")
    return bool(tenant_id) and id_token_claims.get("tid") == tenant_id


def extrair_identidade(id_token_claims: dict) -> tuple[str, str]:
    """Extrai (email, nome) normalizados dos claims do ID token."""
    email = (
        (id_token_claims.get("preferred_username") or id_token_claims.get("email") or "")
        .strip()
        .lower()
    )
    nome = id_token_claims.get("name") or (email.split("@")[0] if email else "")
    return email, nome
