"""
Dispara os e-mails de UAT visual para o seu destino real.

Objetivo:
- Permitir que você veja no cliente de e-mail (Outlook/Gmail) os 4 tipos:
  1) CHAMADO_NOVO
  2) CHAMADO_PRAZO_24H
  3) USUARIO_CADASTRADO
  4) CHAMADO_SETOR_ADICIONAL (opção B: SMTP direto)

Como funciona:
- CHAMADO_NOVO / CHAMADO_PRAZO_24H / USUARIO_CADASTRADO -> são roteados via Power Automate
  usando assunto estruturado e/ou POWER_AUTOMATE_TEST_DEST_EMAIL.
- CHAMADO_SETOR_ADICIONAL -> SMTP direto para o e-mail do responsável do setor adicional.

IMPORTANTE:
- Requer configuração SMTP válida no `.env` (MAIL_SERVER, MAIL_USERNAME, MAIL_PASSWORD, etc.).
- Requer que o Power Automate esteja ouvindo o relay do sistema.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    # Garante que a raiz do projeto esteja no sys.path (para importar `app`).
    root = Path(__file__).resolve().parent.parent
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    from app import create_app
    from app.services.notifications import (
        notificar_aprovador_novo_chamado,
        notificar_novo_usuario_cadastrado,
        notificar_responsavel_prazo_24h,
        notificar_responsavel_setor_adicional_power_automate,
    )

    destino = os.getenv("UAT_VISUAL_DEST_EMAIL", "matheus00237@gmail.com").strip()

    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SECRET_KEY"] = app.config.get("SECRET_KEY") or "test-secret"

    # Garante links nos botões.
    app.config["APP_BASE_URL"] = os.getenv("APP_BASE_URL", "").strip() or "https://example.test"
    app.config["POWER_AUTOMATE_TEST_DEST_EMAIL"] = destino

    # Mock simples de usuário com email.
    responsavel = type("Responsavel", (), {"email": destino})()

    with app.app_context():
        # 1) CHAMADO_NOVO
        notificar_aprovador_novo_chamado(
            chamado_id="chamado_uat_1",
            numero_chamado="UAT-CHAMADO-NOVO-001",
            categoria="Projetos",
            tipo_solicitacao="Manutencao",
            descricao_resumo="Summary for visual UAT: ticket novo.",
            area="Manutencao",
            solicitante_nome="Solicitante UAT",
            solicitante_email="sol.uat@example.com",
            responsavel_usuario=responsavel,
        )

        # 2) CHAMADO_PRAZO_24H
        notificar_responsavel_prazo_24h(
            chamado_id="chamado_uat_1",
            numero_chamado="UAT-CHAMADO-PRAZO-24H-002",
            responsavel_email=destino,
            categoria="Projetos",
            tipo_solicitacao="Manutencao",
            area="Manutencao",
            solicitante_nome="Solicitante UAT",
            descricao_resumo="Summary for visual UAT: prazo 24h.",
        )

        # 3) USUARIO_CADASTRADO
        # destino final será forçado por POWER_AUTOMATE_TEST_DEST_EMAIL
        notificar_novo_usuario_cadastrado(
            usuario_id="user_uat_003",
            usuario_email="novo.usuario.uat@example.com",
            usuario_nome="Novo Usuario UAT",
            perfil="supervisor",
            areas=["Manutencao", "Engenharia"],
        )

        # 4) CHAMADO_SETOR_ADICIONAL (opção B: SMTP direto)
        notificar_responsavel_setor_adicional_power_automate(
            chamado_id="chamado_uat_4",
            numero_chamado="UAT-SETOR-ADICIONAL-004",
            email_responsavel_setor=destino,
            setor_adicional="Engenharia",
            categoria="Projetos",
            tipo_solicitacao="Manutencao",
            solicitante_nome="Solicitante UAT",
            quem_adicionou_nome="Supervisor UAT",
            descricao_resumo="Summary for visual UAT: setor adicional.",
        )

    print("Disparo UAT visual finalizado (ver logs acima para confirmar o envio).")
    print(f"Destino: {destino}")


if __name__ == "__main__":
    main()
