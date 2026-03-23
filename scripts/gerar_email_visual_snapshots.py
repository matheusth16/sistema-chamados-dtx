"""
Gera snapshots HTML dos e-mails de notificação (sem enviar).

Isso ajuda a "ver visualmente" os botões/layout no seu navegador/email client
sem depender do Power Automate ou de SMTP externo.

Uso:
  python scripts/gerar_email_visual_snapshots.py
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch


def _wrap_for_browser(title: str, body_html: str) -> str:
    # body_html já vem com estilos inline; só adicionamos o "outer shell" do documento.
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{title}</title>
    <style>
      body {{ margin: 0; background: #eef2f7; }}
    </style>
  </head>
  <body>
    <div style="max-width: 920px; margin: 24px auto; padding: 0 16px;">
      <h3 style="font-family: Segoe UI, Arial, sans-serif; color:#111827; margin: 0 0 16px;">
        {title}
      </h3>
      {body_html}
    </div>
  </body>
</html>
"""


def main() -> None:
    # Garante que a raiz do projeto esteja no sys.path (para importar `app`).
    root = Path(__file__).resolve().parent.parent
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    # Import local para manter o script simples.
    from app import create_app
    from app.services.notifications import (
        notificar_aprovador_novo_chamado,
        notificar_novo_usuario_cadastrado,
        notificar_responsavel_prazo_24h,
        notificar_responsavel_setor_adicional_power_automate,
    )

    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SECRET_KEY"] = "test-secret"
    app.config["APP_BASE_URL"] = "https://example.test"

    out_dir = Path(__file__).resolve().parent.parent / "tmp" / "email_visual_snapshots"
    out_dir.mkdir(parents=True, exist_ok=True)

    captured: dict[str, dict[str, Any]] = {}

    def _capture(destinatario: str, assunto: str, corpo_html: str, corpo_texto=None):
        # Chamamos funções em sequência; a gente mapeia pelo assunto (prefixo).
        key = assunto.split("|")[0].split(" ")[0].strip() or "UNKNOWN"
        # Ajuste heuristico para manter nomes curtos.
        if assunto.startswith("CHAMADO_NOVO|"):
            key = "CHAMADO_NOVO"
        elif assunto.startswith("CHAMADO_PRAZO_24H|"):
            key = "CHAMADO_PRAZO_24H"
        elif assunto.startswith("USUARIO_CADASTRADO|"):
            key = "USUARIO_CADASTRADO"
        elif assunto.startswith("Ticket "):
            key = "CHAMADO_SETOR_ADICIONAL"

        captured[key] = {
            "destinatario": destinatario,
            "assunto": assunto,
            "corpo_html": corpo_html,
            "corpo_texto": corpo_texto,
        }
        return (True, None)

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", side_effect=_capture) as _mock_enviar,
    ):
        # 1) CHAMADO_NOVO
        responsavel = type("Responsavel", (), {"email": "resp@dtx.aero"})()
        notificar_aprovador_novo_chamado(
            chamado_id="chamado_1",
            numero_chamado="2026-100",
            categoria="Projetos",
            tipo_solicitacao="Manutencao",
            descricao_resumo="Resumo do chamado (preview visual)",
            area="Manutencao",
            solicitante_nome="Solicitante",
            solicitante_email="sol@test.local",
            responsavel_usuario=responsavel,
        )

        # 2) CHAMADO_PRAZO_24H
        notificar_responsavel_prazo_24h(
            chamado_id="chamado_1",
            numero_chamado="2026-100",
            responsavel_email="resp@dtx.aero",
            categoria="Projetos",
            tipo_solicitacao="Manutencao",
            area="Manutencao",
            solicitante_nome="Solicitante",
            descricao_resumo="Resumo do chamado (preview visual)",
        )

        # 3) USUARIO_CADASTRADO
        notificar_novo_usuario_cadastrado(
            usuario_id="user_123",
            usuario_email="novo.usuario@dtx.aero",
            usuario_nome="Novo Usuario",
            perfil="supervisor",
            areas=["Manutencao"],
        )

        # 4) CHAMADO_SETOR_ADICIONAL (opção B: SMTP direto)
        notificar_responsavel_setor_adicional_power_automate(
            chamado_id="chamado_2",
            numero_chamado="2026-101",
            email_responsavel_setor="setor@dtx.aero",
            setor_adicional="Engenharia",
            categoria="Projetos",
            tipo_solicitacao="Manutencao",
            solicitante_nome="Solicitante",
            quem_adicionou_nome="Supervisor",
            descricao_resumo="Resumo do chamado (preview visual)",
        )

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    mapping = [
        ("USUARIO_CADASTRADO", "02_USUARIO_CADASTRADO.html"),
        ("CHAMADO_NOVO", "01_CHAMADO_NOVO.html"),
        ("CHAMADO_PRAZO_24H", "03_CHAMADO_PRAZO_24H.html"),
        ("CHAMADO_SETOR_ADICIONAL", "04_CHAMADO_SETOR_ADICIONAL.html"),
    ]

    # Garante que todos os snapshots saem, mesmo se algum key não cair no heurístico.
    created = []
    for key, fname in mapping:
        item = captured.get(key)
        if not item:
            continue
        title = f"{key} - subject: {item['assunto']}"
        html = _wrap_for_browser(title=title, body_html=item["corpo_html"])
        path = out_dir / f"{ts}_{fname}"
        path.write_text(html, encoding="utf-8")
        created.append(str(path))

    print("Snapshots gerados (HTML) em:")
    for p in created:
        print("-", p)
    missing = [k for k, _ in mapping if k not in captured]
    if missing:
        print("Atenção: não foi possível capturar algum snapshot:", ", ".join(missing))


if __name__ == "__main__":
    main()
