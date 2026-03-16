"""
Teste isolado de envio de e-mail via SMTP (variáveis MAIL_* do .env).
Use para diagnosticar erros de autenticação ou conexão ao Gmail/Outlook.

Uso:
  python scripts/testar_email_smtp.py
  python scripts/testar_email_smtp.py destino@exemplo.com

Se não informar destinatário, envia para o próprio MAIL_USERNAME.
"""

import os
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Carrega .env da raiz do projeto
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_env = os.path.join(_root, ".env")
if os.path.isfile(_env):
    from dotenv import load_dotenv

    load_dotenv(_env)
else:
    print("Arquivo .env não encontrado em:", _root)
    sys.exit(1)

MAIL_SERVER = os.getenv("MAIL_SERVER", "").strip()
MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "true").lower() in ("true", "1", "yes")
MAIL_USERNAME = os.getenv("MAIL_USERNAME", "").strip()
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "").strip()
MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "").strip() or MAIL_USERNAME


def main():
    if not MAIL_SERVER or not MAIL_USERNAME:
        print("Configure MAIL_SERVER e MAIL_USERNAME no .env")
        sys.exit(1)

    destinatario = (sys.argv[1] if len(sys.argv) > 1 else MAIL_USERNAME).strip()
    if not destinatario:
        print("Informe o destinatário: python scripts/testar_email_smtp.py email@exemplo.com")
        sys.exit(1)

    assunto = "[Teste] Sistema de Chamados - SMTP"
    corpo = "Se você recebeu este e-mail, o SMTP está configurado corretamente."

    msg = MIMEMultipart("alternative")
    msg["Subject"] = assunto
    msg["From"] = MAIL_DEFAULT_SENDER or MAIL_USERNAME
    msg["To"] = destinatario
    msg.attach(MIMEText(corpo, "plain", "utf-8"))
    msg.attach(MIMEText(f"<p>{corpo}</p>", "html", "utf-8"))

    print(f"Enviando para: {destinatario}")
    print(f"Servidor: {MAIL_SERVER}:{MAIL_PORT} (TLS={MAIL_USE_TLS})")
    print(f"Remetente: {msg['From']}")
    if not MAIL_PASSWORD:
        print("AVISO: MAIL_PASSWORD está vazio no .env")
    print("-" * 50)

    try:
        with smtplib.SMTP(MAIL_SERVER, MAIL_PORT) as s:
            if MAIL_USE_TLS:
                s.starttls()
            if MAIL_USERNAME and MAIL_PASSWORD:
                s.login(MAIL_USERNAME, MAIL_PASSWORD)
            s.sendmail(msg["From"], destinatario, msg.as_string())
        print("Sucesso: e-mail enviado.")
    except Exception as e:
        print("Falha ao enviar e-mail:")
        print(type(e).__name__ + ":", e)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
