"""
Teste paralelo de envio SMTP Microsoft 365 (isolado do fluxo atual).

Nao usa MAIL_* para evitar impacto no pipeline principal.
Usa apenas variaveis TEST_SMTP_* no .env.

Uso:
  python scripts/teste_email_smtp_m365.py --to usuario@empresa.com
  python scripts/teste_email_smtp_m365.py --to u1@empresa.com,u2@empresa.com --subject "Teste M365"

Variaveis esperadas no .env:
  TEST_SMTP_SERVER=smtp.office365.com
  TEST_SMTP_PORT=587
  TEST_SMTP_USE_TLS=true
  TEST_SMTP_USERNAME=conta@empresa.com
  TEST_SMTP_PASSWORD=senha-ou-app-password
  TEST_SMTP_FROM=conta@empresa.com
"""

from __future__ import annotations

import argparse
import os
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv


def _to_bool(raw: str | None, default: bool = True) -> bool:
    if raw is None:
        return default
    return str(raw).strip().lower() in ("true", "1", "yes")


def _carregar_env() -> None:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    env_path = os.path.join(root, ".env")
    if not os.path.isfile(env_path):
        print(f"Arquivo .env nao encontrado em: {root}")
        sys.exit(1)
    load_dotenv(env_path)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Teste paralelo de envio SMTP M365 (isolado do fluxo atual)."
    )
    parser.add_argument(
        "--to",
        required=True,
        help="Destinatarios separados por virgula (ex.: a@x.com,b@y.com).",
    )
    parser.add_argument(
        "--subject",
        default="[Teste Paralelo] Sistema de Chamados - SMTP M365",
        help="Assunto do e-mail de teste.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout de conexao em segundos (padrao: 30).",
    )
    return parser.parse_args()


def _split_destinatarios(raw: str) -> list[str]:
    destinos = [item.strip() for item in raw.split(",") if item.strip()]
    if not destinos:
        print("Parametro --to vazio. Informe ao menos um e-mail.")
        sys.exit(1)
    return destinos


def main() -> None:
    _carregar_env()
    args = _parse_args()

    server = os.getenv("TEST_SMTP_SERVER", "").strip()
    port_raw = os.getenv("TEST_SMTP_PORT", "587").strip()
    use_tls = _to_bool(os.getenv("TEST_SMTP_USE_TLS"), default=True)
    username = os.getenv("TEST_SMTP_USERNAME", "").strip()
    password = os.getenv("TEST_SMTP_PASSWORD", "").strip()
    from_addr = (os.getenv("TEST_SMTP_FROM", "").strip() or username).strip()

    try:
        port = int(port_raw)
    except ValueError:
        print(f"TEST_SMTP_PORT invalido: {port_raw}")
        sys.exit(1)

    obrigatorios = {
        "TEST_SMTP_SERVER": server,
        "TEST_SMTP_USERNAME": username,
        "TEST_SMTP_PASSWORD": password,
        "TEST_SMTP_FROM (ou TEST_SMTP_USERNAME)": from_addr,
    }
    faltantes = [chave for chave, valor in obrigatorios.items() if not valor]
    if faltantes:
        print("Variaveis obrigatorias ausentes no .env:")
        for item in faltantes:
            print(f"- {item}")
        sys.exit(1)

    destinatarios = _split_destinatarios(args.to)
    assunto = args.subject
    corpo_texto = (
        "Teste paralelo SMTP M365 do Sistema de Chamados.\n"
        "Este envio nao usa o fluxo principal (Power Automate/relay)."
    )
    corpo_html = (
        "<p><strong>Teste paralelo SMTP M365</strong> do Sistema de Chamados.</p>"
        "<p>Este envio <strong>nao usa</strong> o fluxo principal "
        "(Power Automate/relay).</p>"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = assunto
    msg["From"] = from_addr
    msg["To"] = ", ".join(destinatarios)
    msg.attach(MIMEText(corpo_texto, "plain", "utf-8"))
    msg.attach(MIMEText(corpo_html, "html", "utf-8"))

    print("Iniciando teste paralelo SMTP M365...")
    print(f"Servidor: {server}:{port} (TLS={use_tls})")
    print(f"Remetente: {from_addr}")
    print(f"Destinatarios: {msg['To']}")
    print("-" * 60)

    try:
        with smtplib.SMTP(server, port, timeout=args.timeout) as smtp:
            if use_tls:
                smtp.starttls()
            smtp.login(username, password)
            smtp.sendmail(from_addr, destinatarios, msg.as_string())
        print("Sucesso: e-mail de teste enviado.")
    except smtplib.SMTPAuthenticationError as exc:
        print("Falha de autenticacao SMTP.")
        print("Possiveis causas:")
        print("- SMTP AUTH desabilitado na conta/tenant Microsoft 365")
        print("- MFA exige app password ou politica especifica")
        print("- Usuario/senha incorretos")
        print(f"Detalhe tecnico: {exc}")
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print("Falha ao enviar e-mail de teste.")
        print(f"{type(exc).__name__}: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
