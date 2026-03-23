"""Testes dos serviços de notificação (e-mail, in-app)."""

from unittest.mock import patch


def test_enviar_email_retorna_false_sem_destinatario(app):
    """enviar_email retorna (False, None) quando destinatário está vazio."""
    from app.services.notifications import enviar_email

    with app.app_context():
        ok, err = enviar_email("", "Assunto", "<p>Teste</p>")
        assert ok is False
        assert err is None


def test_criar_notificacao_retorna_none_sem_usuario_id():
    """criar_notificacao retorna None quando usuario_id é vazio."""
    from app.services.notifications_inapp import criar_notificacao

    with patch("app.services.notifications_inapp.db"):
        r = criar_notificacao("", "ch1", "CHM-0001", "Título", "Msg")
    assert r is None


def test_listar_para_usuario_retorna_lista_vazia_sem_usuario_id():
    """listar_para_usuario retorna [] quando usuario_id é vazio."""
    from app.services.notifications_inapp import listar_para_usuario

    assert listar_para_usuario("") == []
    assert listar_para_usuario(None) == []


def test_contar_nao_lidas_retorna_zero_sem_usuario_id():
    """contar_nao_lidas retorna 0 quando usuario_id é vazio."""
    from app.services.notifications_inapp import contar_nao_lidas

    assert contar_nao_lidas("") == 0


def test_notificar_novo_usuario_cadastrado_usa_prefixo_power_automate(app):
    """notificar_novo_usuario_cadastrado envia via relay com prefixo USUARIO_CADASTRADO."""
    from app.services.notifications import notificar_novo_usuario_cadastrado

    with (
        app.app_context(),
        patch("app.services.notifications._relay_email", return_value="relay@test.local"),
        patch("app.services.notifications.enviar_email") as mock_enviar,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        mock_enviar.return_value = (True, None)
        notificar_novo_usuario_cadastrado(
            usuario_id="user_123",
            usuario_email="novo.usuario@dtx.aero",
            usuario_nome="Novo Usuario",
            perfil="solicitante",
            areas=["Manutencao"],
            senha_inicial="SenhaTest99",
        )

    assert mock_enviar.called
    destinatario, assunto, corpo_html, _corpo_texto = mock_enviar.call_args[0]
    assert destinatario == "relay@test.local"
    assert assunto == "USUARIO_CADASTRADO|user_123|novo.usuario@dtx.aero"
    assert "New user registration" in corpo_html
    assert "Open system" in corpo_html
    assert "Profile" in corpo_html
    assert "Areas" in corpo_html
    assert "E-mail" in corpo_html
    assert "Initial password" in corpo_html
    assert "SenhaTest99" in corpo_html
    assert "123456" not in corpo_html


def test_notificar_responsavel_prazo_24h_usa_prefixo_power_automate(app):
    """notificar_responsavel_prazo_24h envia via relay com prefixo CHAMADO_PRAZO_24H."""
    from app.services.notifications import notificar_responsavel_prazo_24h

    with (
        app.app_context(),
        patch("app.services.notifications._relay_email", return_value="relay@test.local"),
        patch("app.services.notifications.enviar_email") as mock_enviar,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        mock_enviar.return_value = (True, None)
        notificar_responsavel_prazo_24h(
            chamado_id="chamado_1",
            numero_chamado="2026-100",
            responsavel_email="resp@dtx.aero",
            categoria="Projetos",
            tipo_solicitacao="Manutencao",
            area="Manutencao",
            solicitante_nome="Solicitante",
            descricao_resumo="Resumo",
        )

    assert mock_enviar.called
    destinatario, assunto, corpo_html, _corpo_texto = mock_enviar.call_args[0]
    assert destinatario == "relay@test.local"
    assert assunto == "CHAMADO_PRAZO_24H|2026-100|resp@dtx.aero"
    assert "Ticket nearing deadline (24h)" in corpo_html
    assert "View ticket history" in corpo_html
    assert "View your sector tickets" in corpo_html


def test_notificar_setor_adicional_envia_email_smtp(app):
    """notificar_responsavel_setor_adicional_power_automate envia via SMTP (opção B)."""
    from app.services.notifications import notificar_responsavel_setor_adicional_power_automate

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email") as mock_enviar,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        mock_enviar.return_value = (True, None)
        notificar_responsavel_setor_adicional_power_automate(
            chamado_id="chamado_2",
            numero_chamado="2026-101",
            email_responsavel_setor="setor@dtx.aero",
            setor_adicional="Engenharia",
            categoria="Projetos",
            tipo_solicitacao="Manutencao",
            solicitante_nome="Solicitante",
            quem_adicionou_nome="Supervisor",
            descricao_resumo="Resumo",
        )

    assert mock_enviar.called
    destinatario, assunto, corpo_html, _corpo_texto = mock_enviar.call_args[0]
    assert destinatario == "setor@dtx.aero"
    assert assunto == "Ticket 2026-101: your department has been included"
    assert "Additional department included" in corpo_html
    assert "View ticket history" in corpo_html
    assert "View your sector tickets" in corpo_html


def test_sanitize_pa_field_remove_pipe():
    """_sanitize_pa_field substitui '|' por '-' para não quebrar parsing do Power Automate."""
    from app.services.notifications import _sanitize_pa_field

    assert _sanitize_pa_field("2026-100") == "2026-100"
    assert _sanitize_pa_field("2026|100") == "2026-100"
    assert _sanitize_pa_field("evil|addr@evil.com|extra") == "evil-addr@evil.com-extra"
    assert _sanitize_pa_field("") == ""
    assert _sanitize_pa_field(None) == ""


def test_notificar_aprovador_assunto_sem_pipe_injection(app):
    """notificar_aprovador_novo_chamado garante que número do chamado não injeta '|' no assunto."""
    from app.services.notifications import notificar_aprovador_novo_chamado

    responsavel = type("Resp", (), {"email": "resp@dtx.aero"})()

    with (
        app.app_context(),
        patch("app.services.notifications._relay_email", return_value="relay@test.local"),
        patch("app.services.notifications.enviar_email") as mock_enviar,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        mock_enviar.return_value = (True, None)
        notificar_aprovador_novo_chamado(
            chamado_id="chamado_x",
            numero_chamado="2026|INJETADO|evil@hack.com",
            categoria="Projetos",
            tipo_solicitacao="Manutencao",
            descricao_resumo="Resumo",
            area="Manutencao",
            solicitante_nome="Solicitante",
            responsavel_usuario=responsavel,
        )

    _dest, assunto, _html, _txt = mock_enviar.call_args[0]
    # O assunto deve ter exatamente 2 separadores '|'
    assert assunto.count("|") == 2
    assert "INJETADO" not in assunto.split("|")[2]


def test_notificar_aprovador_novo_chamado_html_em_ingles(app):
    """notificar_aprovador_novo_chamado gera HTML em inglês com botões CTA."""
    from app.services.notifications import notificar_aprovador_novo_chamado

    responsavel = type("Resp", (), {"email": "resp@dtx.aero"})()

    with (
        app.app_context(),
        patch("app.services.notifications._relay_email", return_value="relay@test.local"),
        patch("app.services.notifications.enviar_email") as mock_enviar,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        mock_enviar.return_value = (True, None)
        notificar_aprovador_novo_chamado(
            chamado_id="chamado_3",
            numero_chamado="2026-102",
            categoria="Projetos",
            tipo_solicitacao="Manutencao",
            descricao_resumo="Resumo do chamado",
            area="Manutencao",
            solicitante_nome="Solicitante",
            solicitante_email="sol@test.local",
            responsavel_usuario=responsavel,
        )

    assert mock_enviar.called
    destinatario, assunto, corpo_html, _corpo_texto = mock_enviar.call_args[0]
    assert assunto == "CHAMADO_NOVO|2026-102|resp@dtx.aero"
    assert "New ticket assigned" in corpo_html
    assert "View ticket history" in corpo_html
    assert "View your sector tickets" in corpo_html
