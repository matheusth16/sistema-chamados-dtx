"""
Teste paralelo de envio de e-mail via Microsoft Graph (Application permissions).

Isolado do fluxo atual: nao altera MAIL_* nem notificacoes existentes.

Uso:
  python scripts/teste_email_graph.py --to usuario@empresa.com
  python scripts/teste_email_graph.py --to u1@empresa.com,u2@empresa.com --subject "Teste Graph"
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime

from dotenv import load_dotenv


def _load_env() -> None:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    env_path = os.path.join(root, ".env")
    if not os.path.isfile(env_path):
        print(f"Arquivo .env nao encontrado em: {root}")
        sys.exit(1)
    load_dotenv(env_path)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Teste paralelo de envio via Microsoft Graph.")
    parser.add_argument(
        "--to",
        required=True,
        help="Destinatarios separados por virgula (ex.: a@x.com,b@y.com).",
    )
    parser.add_argument(
        "--subject",
        default="[Teste Paralelo] Sistema de Chamados - Microsoft Graph",
        help="Assunto do e-mail de teste.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout das requisicoes HTTP em segundos (padrao: 30).",
    )
    return parser.parse_args()


def _split_destinatarios(raw: str) -> list[str]:
    destinos = [item.strip() for item in raw.split(",") if item.strip()]
    if not destinos:
        print("Parametro --to vazio. Informe ao menos um e-mail.")
        sys.exit(1)
    return destinos


def _required_env(key: str) -> str:
    value = os.getenv(key, "").strip()
    if not value:
        raise ValueError(f"Variavel obrigatoria ausente no .env: {key}")
    return value


def _get_access_token(
    tenant_id: str,
    client_id: str,
    client_secret: str,
    timeout: int,
    events: list[dict],
) -> str:
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    payload = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        token_url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
            events.append(
                {
                    "step": "token",
                    "method": "POST",
                    "url": token_url,
                    "http_status": response.getcode(),
                    "ok": True,
                }
            )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        events.append(
            {
                "step": "token",
                "method": "POST",
                "url": token_url,
                "http_status": exc.code,
                "ok": False,
                "error_code": "HTTPError",
                "error_message": str(exc),
                "raw_error": detail,
            }
        )
        raise RuntimeError("Falha ao obter token") from exc
    except Exception as exc:  # noqa: BLE001
        events.append(
            {
                "step": "token",
                "method": "POST",
                "url": token_url,
                "http_status": None,
                "ok": False,
                "error_code": type(exc).__name__,
                "error_message": str(exc),
                "raw_error": "",
            }
        )
        raise RuntimeError("Falha ao obter token") from exc

    token = data.get("access_token", "").strip()
    if not token:
        events.append(
            {
                "step": "token",
                "method": "POST",
                "url": token_url,
                "http_status": 200,
                "ok": False,
                "error_code": "MissingAccessToken",
                "error_message": "Resposta sem access_token",
                "raw_error": json.dumps(data, ensure_ascii=True),
            }
        )
        raise RuntimeError("Resposta de token sem access_token")
    return token


def _decode_jwt_claims(token: str) -> dict:
    """Decodifica payload JWT sem verificar assinatura (somente diagnostico local)."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        payload_b64 = parts[1]
        padding = "=" * (-len(payload_b64) % 4)
        decoded = base64.urlsafe_b64decode(payload_b64 + padding).decode("utf-8")
        payload = json.loads(decoded)
        if isinstance(payload, dict):
            return payload
        return {}
    except Exception:  # noqa: BLE001
        return {}


def _token_diagnostics(token: str, events: list[dict]) -> dict:
    claims = _decode_jwt_claims(token)
    roles = claims.get("roles", [])
    appid = claims.get("appid", "")
    tid = claims.get("tid", "")
    aud = claims.get("aud", "")
    diag = {
        "appid": appid or "N/A",
        "tid": tid or "N/A",
        "aud": aud or "N/A",
        "roles": roles if roles else [],
        "mail_send_present": "Mail.Send" in roles,
    }
    events.append({"step": "token_claims", "ok": True, "diagnostics": diag})
    return diag


def _graph_get_sender_check(sender: str, token: str, timeout: int, events: list[dict]) -> None:
    """Valida acesso de leitura ao user/mailbox alvo antes do sendMail."""
    url = (
        "https://graph.microsoft.com/v1.0/users/"
        f"{urllib.parse.quote(sender)}?$select=id,mail,userPrincipalName"
    )
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
            events.append(
                {
                    "step": "precheck",
                    "method": "GET",
                    "url": url,
                    "http_status": response.getcode(),
                    "ok": True,
                    "userPrincipalName": data.get("userPrincipalName") or "N/A",
                    "mail": data.get("mail") or "N/A",
                }
            )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        events.append(
            {
                "step": "precheck",
                "method": "GET",
                "url": url,
                "http_status": exc.code,
                "ok": False,
                "error_code": "HTTPError",
                "error_message": str(exc),
                "raw_error": detail,
            }
        )
    except Exception as exc:  # noqa: BLE001
        events.append(
            {
                "step": "precheck",
                "method": "GET",
                "url": url,
                "http_status": None,
                "ok": False,
                "error_code": type(exc).__name__,
                "error_message": str(exc),
                "raw_error": "",
            }
        )


def _send_mail_graph(
    sender: str,
    token: str,
    destinatarios: list[str],
    subject: str,
    timeout: int,
    events: list[dict],
) -> None:
    url = f"https://graph.microsoft.com/v1.0/users/{urllib.parse.quote(sender)}/sendMail"
    body_html = (
        "<p><strong>Teste paralelo de Microsoft Graph</strong> do Sistema de Chamados.</p>"
        "<p>Este envio <strong>nao usa</strong> o fluxo principal (Gmail/relay).</p>"
    )
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": body_html},
            "toRecipients": [{"emailAddress": {"address": email}} for email in destinatarios],
        },
        "saveToSentItems": True,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = response.getcode()
            # Graph normalmente retorna 202 Accepted.
            if status not in (202, 200):
                events.append(
                    {
                        "step": "sendmail",
                        "method": "POST",
                        "url": url,
                        "http_status": status,
                        "ok": False,
                        "error_code": "UnexpectedStatus",
                        "error_message": f"HTTP {status}",
                        "raw_error": "",
                    }
                )
                raise RuntimeError(f"Resposta inesperada do Graph: HTTP {status}")
            events.append(
                {
                    "step": "sendmail",
                    "method": "POST",
                    "url": url,
                    "http_status": status,
                    "ok": True,
                }
            )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        events.append(
            {
                "step": "sendmail",
                "method": "POST",
                "url": url,
                "http_status": exc.code,
                "ok": False,
                "error_code": "HTTPError",
                "error_message": str(exc),
                "raw_error": detail,
            }
        )
        raise RuntimeError("Falha ao enviar e-mail via Graph") from exc
    except Exception as exc:  # noqa: BLE001
        events.append(
            {
                "step": "sendmail",
                "method": "POST",
                "url": url,
                "http_status": None,
                "ok": False,
                "error_code": type(exc).__name__,
                "error_message": str(exc),
                "raw_error": "",
            }
        )
        raise RuntimeError("Falha ao enviar e-mail via Graph") from exc


def _infer_likely_cause(events: list[dict]) -> str:
    claims_event = next((e for e in events if e.get("step") == "token_claims"), None)
    if claims_event:
        roles = claims_event.get("diagnostics", {}).get("roles", [])
        if "Mail.Send" not in roles:
            return "Mail.Send ausente no token (Application permissions/admin consent)."

    last_error = next((e for e in reversed(events) if not e.get("ok", False)), None)
    if not last_error:
        return "Sem erros."

    status = last_error.get("http_status")
    raw = (last_error.get("raw_error") or "").lower()
    if status == 403 and "insufficient privileges" in raw:
        return "Permissao insuficiente no Graph (consent/policy Exchange)."
    if status == 403 and "access is denied" in raw:
        return "Acesso negado no sendMail (policy Exchange ou app sem escopo efetivo)."
    if status == 401:
        return "Token invalido/expirado ou credencial incorreta."
    return "Verifique detalhes em events[].raw_error."


def _print_structured_log(context: dict, events: list[dict]) -> None:
    failed_event = next(
        (e for e in reversed(events) if (not e.get("ok", False)) and e.get("step") != "runtime"),
        None,
    )
    if failed_event is None:
        failed_event = next((e for e in reversed(events) if not e.get("ok", False)), None)
    run_summary = {
        "success": failed_event is None,
        "failed_step": failed_event.get("step") if failed_event else None,
        "likely_cause": _infer_likely_cause(events),
    }
    output = {"context": context, "run_summary": run_summary, "events": events}
    print(json.dumps(output, ensure_ascii=True, indent=2))


def main() -> None:
    _load_env()
    events: list[dict] = []

    try:
        args = _parse_args()
        tenant_id = _required_env("GRAPH_TENANT_ID")
        client_id = _required_env("GRAPH_CLIENT_ID")
        client_secret = _required_env("GRAPH_CLIENT_SECRET")
        sender = _required_env("GRAPH_SENDER_EMAIL")
        destinatarios = _split_destinatarios(args.to)
        context = {
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "tenant_id": tenant_id,
            "client_id": client_id,
            "sender": sender,
            "destinatarios": destinatarios,
            "subject": args.subject,
            "timeout_seconds": args.timeout,
        }

        token = _get_access_token(tenant_id, client_id, client_secret, args.timeout, events)
        _token_diagnostics(token, events)
        _graph_get_sender_check(sender, token, args.timeout, events)
        _send_mail_graph(sender, token, destinatarios, args.subject, args.timeout, events)
    except Exception as exc:  # noqa: BLE001
        if not any(not e.get("ok", False) for e in events):
            events.append(
                {
                    "step": "runtime",
                    "ok": False,
                    "error_code": type(exc).__name__,
                    "error_message": str(exc),
                    "raw_error": "",
                }
            )
        if "context" not in locals():
            context = {
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "tenant_id": os.getenv("GRAPH_TENANT_ID", "").strip(),
                "client_id": os.getenv("GRAPH_CLIENT_ID", "").strip(),
                "sender": os.getenv("GRAPH_SENDER_EMAIL", "").strip(),
                "destinatarios": [],
                "subject": "",
                "timeout_seconds": None,
            }
    finally:
        _print_structured_log(context, events)
        has_error = any(not e.get("ok", False) for e in events)
        if has_error:
            sys.exit(1)


if __name__ == "__main__":
    main()
