"""
Teste de integração com Microsoft Graph usando MSAL.

Uso:
    python scripts/testar_graph_msal.py

Pré-requisitos:
    - pip install -r requirements.txt
    - Variáveis no .env:
        GRAPH_TENANT_ID
        GRAPH_CLIENT_ID
        GRAPH_CLIENT_SECRET
        GRAPH_SEND_AS_USER (ex.: dtxls.support@dtx.aero)

O script:
    1. Obtém um access token via client credentials.
    2. Envia um e-mail simples via Graph (sendMail) para o próprio GRAPH_SEND_AS_USER,
       apenas para testar permissão Mail.Send e credenciais.
"""

import os
import json

from dotenv import load_dotenv
import msal
import requests


def carregar_env() -> None:
    """Carrega .env da raiz do projeto."""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    env_path = os.path.join(root, ".env")
    if os.path.isfile(env_path):
        load_dotenv(env_path)


def main() -> None:
    carregar_env()

    tenant_id = os.getenv("GRAPH_TENANT_ID", "").strip()
    client_id = os.getenv("GRAPH_CLIENT_ID", "").strip()
    client_secret = os.getenv("GRAPH_CLIENT_SECRET", "").strip().strip('"')
    send_as_user = os.getenv("GRAPH_SEND_AS_USER", "").strip()

    if not tenant_id or not client_id or not client_secret or not send_as_user:
        print("ERRO: Configure GRAPH_TENANT_ID, GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET e GRAPH_SEND_AS_USER no .env")
        return

    authority = f"https://login.microsoftonline.com/{tenant_id}"
    scopes = ["https://graph.microsoft.com/.default"]

    print("Obtendo token com MSAL...")
    app = msal.ConfidentialClientApplication(
        client_id=client_id,
        authority=authority,
        client_credential=client_secret,
    )

    # Primeiro tenta cache silencioso (não deve ter, mas não custa)
    result = app.acquire_token_silent(scopes, account=None)
    if not result:
        result = app.acquire_token_for_client(scopes=scopes)

    if "access_token" not in result:
        print("Falha ao obter token.")
        print("Erro:", result.get("error"))
        print("Descrição:", result.get("error_description"))
        return

    token = result["access_token"]
    print("Token obtido com sucesso (tamanho):", len(token))

    # Monta requisição de sendMail
    url = f"https://graph.microsoft.com/v1.0/users/{send_as_user}/sendMail"
    payload = {
        "message": {
            "subject": "[Teste] Sistema de Chamados - Graph/MSAL",
            "body": {
                "contentType": "HTML",
                "content": "<p>Se você recebeu este e-mail, o envio via Microsoft Graph (MSAL) está funcionando.</p>",
            },
            "toRecipients": [
                {"emailAddress": {"address": send_as_user}},
            ],
        },
        "saveToSentItems": "true",
    }

    print(f"Enviando e-mail de teste para {send_as_user} via Graph/MSAL...")
    resp = requests.post(
        url,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        data=json.dumps(payload),
        timeout=15,
    )

    print("Status HTTP:", resp.status_code)
    if resp.content:
        try:
            print("Resposta JSON:", json.dumps(resp.json(), indent=2, ensure_ascii=False))
        except ValueError:
            print("Resposta texto:", resp.text[:500])

    if resp.status_code in (200, 202):
        print("SUCESSO: o e-mail de teste foi aceito pelo Graph.")
    else:
        print("FALHA: o Graph retornou erro. Verifique permissões (Mail.Send) e consentimento de admin.")


if __name__ == "__main__":
    main()

