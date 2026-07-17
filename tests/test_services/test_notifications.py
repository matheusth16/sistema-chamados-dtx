"""Testes dos serviços de notificação (e-mail, in-app)."""

from unittest.mock import MagicMock, patch


def test_enviar_email_retorna_false_sem_destinatario(app):
    """enviar_email retorna (False, None) quando destinatário está vazio."""
    from app.services.notifications import enviar_email

    with app.app_context():
        ok, err = enviar_email("", "Assunto", "<p>Teste</p>")
    assert ok is False
    assert err is None


def test_enviar_email_suprimido_quando_desabilitado(app):
    """enviar_email não chama Graph quando NOTIFY_EMAIL_ENABLED=false."""
    from app.services.notifications import enviar_email

    with (
        app.app_context(),
        patch("app.services.notifications._enviar_via_graph") as mock_graph,
    ):
        app.config["NOTIFY_EMAIL_ENABLED"] = False
        app.config["TESTING"] = False
        ok, err = enviar_email("dest@test.com", "Assunto", "<p>Teste</p>")
    assert ok is True
    assert err is None
    mock_graph.assert_not_called()


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


def test_notificar_novo_usuario_cadastrado_envia_direto(app):
    """notificar_novo_usuario_cadastrado envia direto ao usuário via Graph API."""
    from app.services.notifications import notificar_novo_usuario_cadastrado

    with (
        app.app_context(),
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
    assert destinatario == "novo.usuario@dtx.aero"
    assert assunto == "Welcome to Andon — your access credentials"
    assert "Role" in corpo_html or "Initial password" in corpo_html
    assert "SenhaTest99" in corpo_html
    assert "123456" not in corpo_html


def test_notificar_novo_usuario_sso_envia_email_sem_senha(app):
    """notificar_novo_usuario_sso avisa o novo usuário sem mencionar senha."""
    from app.services.notifications import notificar_novo_usuario_sso

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email") as mock_enviar,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        mock_enviar.return_value = (True, None)
        notificar_novo_usuario_sso(
            usuario_id="user_sso_1",
            usuario_email="novo.sso@dtx.aero",
            usuario_nome="Novo SSO",
        )

    assert mock_enviar.called
    destinatario, assunto, corpo_html, corpo_texto = mock_enviar.call_args[0]
    assert destinatario == "novo.sso@dtx.aero"
    assert "Microsoft" in corpo_html
    assert "Initial password" not in corpo_html
    assert "Initial password" not in corpo_texto
    assert assunto


def test_notificar_admins_novo_usuario_sso_envia_para_cada_admin(app):
    """notificar_admins_novo_usuario_sso envia um e-mail por admin da lista."""
    from app.services.notifications import notificar_admins_novo_usuario_sso

    admins = ["admin1@dtx.aero", "admin2@dtx.aero"]
    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email") as mock_enviar,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        mock_enviar.return_value = (True, None)
        notificar_admins_novo_usuario_sso(
            admin_emails=admins,
            usuario_email="novo.sso@dtx.aero",
            usuario_nome="Novo SSO",
        )

    assert mock_enviar.call_count == 2
    destinatarios = {call.args[0] for call in mock_enviar.call_args_list}
    assert destinatarios == set(admins)


def test_notificar_admins_novo_usuario_sso_lista_vazia_nao_envia(app):
    """notificar_admins_novo_usuario_sso não chama enviar_email com lista vazia."""
    from app.services.notifications import notificar_admins_novo_usuario_sso

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email") as mock_enviar,
    ):
        notificar_admins_novo_usuario_sso(
            admin_emails=[], usuario_email="novo.sso@dtx.aero", usuario_nome="Novo SSO"
        )

    mock_enviar.assert_not_called()


def test_notificar_mudanca_perfil_envia_email_com_novo_perfil(app):
    """notificar_mudanca_perfil avisa o usuário sobre o novo perfil."""
    from app.services.notifications import notificar_mudanca_perfil

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email") as mock_enviar,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        mock_enviar.return_value = (True, None)
        notificar_mudanca_perfil(
            usuario_email="promovido@dtx.aero",
            usuario_nome="Promovido",
            novo_perfil="supervisor",
        )

    assert mock_enviar.called
    destinatario, assunto, corpo_html, _corpo_texto = mock_enviar.call_args[0]
    assert destinatario == "promovido@dtx.aero"
    assert assunto
    assert "Supervisor" in corpo_html or "supervisor" in corpo_html.lower()


def test_notificar_mudanca_perfil_sem_email_nao_envia(app):
    """notificar_mudanca_perfil não chama enviar_email quando e-mail é vazio."""
    from app.services.notifications import notificar_mudanca_perfil

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email") as mock_enviar,
    ):
        notificar_mudanca_perfil(usuario_email="", usuario_nome="X", novo_perfil="admin")

    mock_enviar.assert_not_called()


def test_notificar_responsavel_prazo_24h_envia_direto(app):
    """notificar_responsavel_prazo_24h envia direto ao responsável via Graph API."""
    from app.services.notifications import notificar_responsavel_prazo_24h

    with (
        app.app_context(),
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
    assert destinatario == "resp@dtx.aero"
    assert assunto == "Ticket 2026-100: deadline in 24h"
    assert "2026-100" in corpo_html
    assert "deadline" in corpo_html.lower() or "24h" in corpo_html.lower()


def test_notificar_responsavel_setor_adicional_envia_direto(app):
    """notificar_responsavel_setor_adicional envia direto ao responsável via Graph API."""
    from app.services.notifications import notificar_responsavel_setor_adicional

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email") as mock_enviar,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        mock_enviar.return_value = (True, None)
        notificar_responsavel_setor_adicional(
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
    assert "2026-101" in corpo_html
    assert "Engineering" in corpo_html  # "Engenharia" translated to English in emails


def test_notificar_responsavel_chamado_confirmado_envia_email(app):
    """notificar_responsavel_chamado_confirmado envia e-mail ao responsável com assunto e corpo corretos."""
    from app.services.notifications import notificar_responsavel_chamado_confirmado

    responsavel = MagicMock()
    responsavel.email = "responsavel@dtx.aero"
    responsavel.nome = "João Responsável"

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email") as mock_enviar,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        mock_enviar.return_value = (True, None)
        notificar_responsavel_chamado_confirmado(
            chamado_id="ch_abc",
            numero_chamado="2026-200",
            categoria="Manutenção",
            solicitante_nome="Maria Solicitante",
            responsavel_usuario=responsavel,
        )

    assert mock_enviar.called
    destinatario, assunto, corpo_html, _corpo_texto = mock_enviar.call_args[0]
    assert destinatario == "responsavel@dtx.aero"
    assert assunto == "Ticket 2026-200: requester confirmed resolution"
    assert "2026-200" in corpo_html
    assert "confirmed" in corpo_html.lower()
    assert "Maria Solicitante" in corpo_html


def test_notificar_responsavel_chamado_confirmado_skip_sem_responsavel(app):
    """notificar_responsavel_chamado_confirmado não envia quando responsável é None."""
    from app.services.notifications import notificar_responsavel_chamado_confirmado

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email") as mock_enviar,
    ):
        notificar_responsavel_chamado_confirmado(
            chamado_id="ch_abc",
            numero_chamado="2026-200",
            categoria="Manutenção",
            solicitante_nome="Maria",
            responsavel_usuario=None,
        )

    mock_enviar.assert_not_called()


def test_notificar_responsavel_chamado_confirmado_skip_sem_email(app):
    """notificar_responsavel_chamado_confirmado não envia quando responsável não tem e-mail."""
    from app.services.notifications import notificar_responsavel_chamado_confirmado

    responsavel_sem_email = MagicMock()
    responsavel_sem_email.email = ""

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email") as mock_enviar,
    ):
        notificar_responsavel_chamado_confirmado(
            chamado_id="ch_abc",
            numero_chamado="2026-200",
            categoria="Manutenção",
            solicitante_nome="Maria",
            responsavel_usuario=responsavel_sem_email,
        )

    mock_enviar.assert_not_called()


def test_notificar_aprovador_envia_direto_ao_responsavel(app):
    """notificar_aprovador_novo_chamado envia diretamente ao e-mail do responsável."""
    from app.services.notifications import notificar_aprovador_novo_chamado

    responsavel = type("Resp", (), {"email": "resp@dtx.aero"})()

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email") as mock_enviar,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        mock_enviar.return_value = (True, None)
        notificar_aprovador_novo_chamado(
            chamado_id="chamado_x",
            numero_chamado="2026-103",
            categoria="Projetos",
            tipo_solicitacao="Manutencao",
            descricao_resumo="Resumo",
            area="Manutencao",
            solicitante_nome="Solicitante",
            responsavel_usuario=responsavel,
        )

    destinatario, assunto, _html, _txt = mock_enviar.call_args[0]
    assert destinatario == "resp@dtx.aero"
    # categoria=Projetos → prefixo "Action required: "
    assert assunto == "Action required: New ticket assigned: 2026-103"


# ── notificar_solicitante_status (C1) ─────────────────────────────────────────


def test_notificar_solicitante_status_sempre_envia_sem_gate(app):
    """notificar_solicitante_status envia independentemente de config — gate removido."""
    from unittest.mock import MagicMock

    from app.services.notifications import notificar_solicitante_status

    solicitante = MagicMock()
    solicitante.email = "user@test.com"
    solicitante.nome = "Usuário Teste"
    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", return_value=(True, None)) as mock_send,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        notificar_solicitante_status("ch1", "CH-001", "Concluído", "TI", solicitante)
    mock_send.assert_called_once()


def test_notificar_solicitante_status_sem_usuario_nao_envia(app):
    """Com usuario=None, nenhum e-mail é enviado."""
    from app.services.notifications import notificar_solicitante_status

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email") as mock_send,
    ):
        app.config["NOTIFY_SOLICITANTE_EMAIL"] = True
        notificar_solicitante_status("ch1", "CH-001", "Concluído", "TI", None)
    mock_send.assert_not_called()


def test_notificar_solicitante_status_sem_email_nao_envia(app):
    """Com email vazio no usuário, nenhum e-mail é enviado."""
    from unittest.mock import MagicMock

    from app.services.notifications import notificar_solicitante_status

    solicitante = MagicMock()
    solicitante.email = ""
    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email") as mock_send,
    ):
        app.config["NOTIFY_SOLICITANTE_EMAIL"] = True
        notificar_solicitante_status("ch1", "CH-001", "Concluído", "TI", solicitante)
    mock_send.assert_not_called()


def test_notificar_solicitante_status_concluido_envia_email(app):
    """Com flag ativa e usuário com e-mail, envia e-mail para status Concluído."""
    from unittest.mock import MagicMock

    from app.services.notifications import notificar_solicitante_status

    solicitante = MagicMock()
    solicitante.email = "sol@test.com"
    solicitante.nome = "Solicitante Teste"
    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", return_value=(True, None)) as mock_send,
    ):
        app.config["NOTIFY_SOLICITANTE_EMAIL"] = True
        app.config["APP_BASE_URL"] = "https://example.test"
        notificar_solicitante_status("ch1", "CH-001", "Concluído", "Manutenção", solicitante)
    mock_send.assert_called_once()
    dest, assunto, corpo_html, _txt = mock_send.call_args[0]
    assert dest == "sol@test.com"
    assert "CH-001" in assunto
    assert "completed" in assunto.lower()
    assert "CH-001" in corpo_html
    assert "completed" in corpo_html.lower()


def test_notificar_solicitante_status_em_atendimento_envia_email(app):
    """Com flag ativa, envia e-mail para status Em Atendimento."""
    from unittest.mock import MagicMock

    from app.services.notifications import notificar_solicitante_status

    solicitante = MagicMock()
    solicitante.email = "sol2@test.com"
    solicitante.nome = "Outro Solicitante"
    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", return_value=(True, None)) as mock_send,
    ):
        app.config["NOTIFY_SOLICITANTE_EMAIL"] = True
        app.config["APP_BASE_URL"] = "https://example.test"
        notificar_solicitante_status("ch2", "CH-002", "Em Atendimento", "Projetos", solicitante)
    mock_send.assert_called_once()
    dest, assunto, _html, _txt = mock_send.call_args[0]
    assert dest == "sol2@test.com"
    assert "CH-002" in assunto


# ── Graph API (TDD RED → GREEN) ───────────────────────────────────────────────


def _make_urlopen_graph(token="tok_abc", send_status=202):
    """
    Cria um mock de urllib.request.urlopen que retorna:
    - 1ª chamada (token): JSON com access_token
    - 2ª chamada (sendMail): resposta com status send_status
    """
    import json
    from unittest.mock import MagicMock

    token_body = json.dumps({"access_token": token}).encode()
    token_resp = MagicMock()
    token_resp.__enter__ = lambda s: s
    token_resp.__exit__ = MagicMock(return_value=False)
    token_resp.read.return_value = token_body
    token_resp.status = 200

    send_resp = MagicMock()
    send_resp.__enter__ = lambda s: s
    send_resp.__exit__ = MagicMock(return_value=False)
    send_resp.read.return_value = b""
    send_resp.status = send_status

    mock_urlopen = MagicMock(side_effect=[token_resp, send_resp])
    return mock_urlopen


def test_enviar_via_graph_sucesso():
    """
    RED: _enviar_via_graph com config completa e Graph retornando 202 → (True, None).
    """
    from app.services.notifications import _enviar_via_graph

    env = {
        "GRAPH_TENANT_ID": "tenant-id",
        "GRAPH_CLIENT_ID": "client-id",
        "GRAPH_CLIENT_SECRET": "secret-value",
        "GRAPH_SENDER_EMAIL": "noreply@dtx.aero",
    }
    mock_urlopen = _make_urlopen_graph(send_status=202)
    with (
        patch.dict("os.environ", env),
        patch("urllib.request.urlopen", mock_urlopen),
    ):
        from app.services.notifications import _enviar_via_graph

        ok, err = _enviar_via_graph(
            "dest@test.com", "Assunto", "<p>HTML</p>", "Texto", "noreply@dtx.aero"
        )
    assert ok is True
    assert err is None
    assert mock_urlopen.call_count == 2  # token + sendMail


def test_enviar_via_graph_sem_config_retorna_false():
    """
    RED: _enviar_via_graph sem GRAPH_* vars → (False, mensagem de erro).
    """

    # Garantir que não há vars de Graph no ambiente
    env_limpo = {
        k: ""
        for k in ["GRAPH_TENANT_ID", "GRAPH_CLIENT_ID", "GRAPH_CLIENT_SECRET", "GRAPH_SENDER_EMAIL"]
    }
    with patch.dict("os.environ", env_limpo):
        from app.services.notifications import _enviar_via_graph

        ok, err = _enviar_via_graph("dest@test.com", "Assunto", "<p>H</p>", None, "x@y.com")
    assert ok is False
    assert err is not None


def test_enviar_via_graph_falha_token_retorna_false():
    """
    RED: quando a chamada de token falha (exceção), _enviar_via_graph retorna (False, err).
    """
    import urllib.error

    env = {
        "GRAPH_TENANT_ID": "tid",
        "GRAPH_CLIENT_ID": "cid",
        "GRAPH_CLIENT_SECRET": "sec",
        "GRAPH_SENDER_EMAIL": "x@dtx.aero",
    }
    with (
        patch.dict("os.environ", env),
        patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")),
    ):
        from app.services.notifications import _enviar_via_graph

        ok, err = _enviar_via_graph("dest@test.com", "Assunto", "<p>H</p>", None, "x@dtx.aero")
    assert ok is False
    assert err is not None


def test_enviar_via_graph_falha_send_retorna_false():
    """
    RED: token obtido mas sendMail falha (HTTP 403) → (False, err com código HTTP).
    """
    import io
    import json
    import urllib.error
    from unittest.mock import MagicMock

    token_body = json.dumps({"access_token": "tok"}).encode()
    token_resp = MagicMock()
    token_resp.__enter__ = lambda s: s
    token_resp.__exit__ = MagicMock(return_value=False)
    token_resp.read.return_value = token_body
    token_resp.status = 200

    env = {
        "GRAPH_TENANT_ID": "tid",
        "GRAPH_CLIENT_ID": "cid",
        "GRAPH_CLIENT_SECRET": "sec",
        "GRAPH_SENDER_EMAIL": "x@dtx.aero",
    }
    http_err = urllib.error.HTTPError(
        url="https://graph...", code=403, msg="Forbidden", hdrs={}, fp=io.BytesIO(b"Forbidden")
    )
    with (
        patch.dict("os.environ", env),
        patch("urllib.request.urlopen", side_effect=[token_resp, http_err]),
    ):
        from app.services.notifications import _enviar_via_graph

        ok, err = _enviar_via_graph("dest@test.com", "Assunto", "<p>H</p>", None, "x@dtx.aero")
    assert ok is False
    assert "403" in str(err)


def test_enviar_email_usa_graph_quando_configurado(app):
    """
    RED: enviar_email() deve chamar _enviar_via_graph quando GRAPH_* vars presentes,
    sem tentar Brevo nem SMTP.
    """
    from app.services.notifications import enviar_email

    env = {
        "GRAPH_TENANT_ID": "tid",
        "GRAPH_CLIENT_ID": "cid",
        "GRAPH_CLIENT_SECRET": "sec",
        "GRAPH_SENDER_EMAIL": "noreply@dtx.aero",
        "BREVO_API_KEY": "",
        "MAIL_SERVER": "",
    }
    with (
        app.app_context(),
        patch.dict("os.environ", env),
        patch(
            "app.services.notifications_core._enviar_via_graph", return_value=(True, None)
        ) as mock_graph,
    ):
        app.config["NOTIFY_EMAIL_ENABLED"] = True
        app.config["TESTING"] = False
        ok, err = enviar_email("dest@test.com", "Assunto", "<p>HTML</p>", "Texto")

    assert ok is True
    mock_graph.assert_called_once()
    args = mock_graph.call_args[0]
    assert args[0] == "dest@test.com"
    assert args[1] == "Assunto"


def test_notificar_aprovador_novo_chamado_html_com_ctas(app):
    """notificar_aprovador_novo_chamado gera HTML com título e botões CTA."""
    from app.services.notifications import notificar_aprovador_novo_chamado

    responsavel = type("Resp", (), {"email": "resp@dtx.aero"})()

    with (
        app.app_context(),
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
    assert destinatario == "resp@dtx.aero"
    # categoria=Projetos → prefixo "Action required: "
    assert assunto == "Action required: New ticket assigned: 2026-102"
    assert "2026-102" in corpo_html
    assert "View ticket history" in corpo_html
    assert "View sector tickets" in corpo_html


# ── _config fora de contexto ───────────────────────────────────────────────────


def test_config_fora_de_contexto_retorna_default():
    """_config fora do contexto Flask retorna o valor default."""
    from app.services.notifications import _config

    result = _config("QUALQUER_CHAVE", default="fallback_value")
    assert result == "fallback_value"


# ── _enviar_via_graph — caminhos de falha ────────────────────────────────────


def test_enviar_via_graph_sem_access_token_na_resposta():
    """_enviar_via_graph retorna (False, err) quando resposta do token não tem access_token."""
    import json

    from app.services.notifications import _enviar_via_graph

    env = {
        "GRAPH_TENANT_ID": "tid",
        "GRAPH_CLIENT_ID": "cid",
        "GRAPH_CLIENT_SECRET": "sec",
        "GRAPH_SENDER_EMAIL": "x@dtx.aero",
    }
    token_body = json.dumps({"error": "invalid_client"}).encode()
    token_resp = MagicMock()
    token_resp.__enter__ = lambda s: s
    token_resp.__exit__ = MagicMock(return_value=False)
    token_resp.read.return_value = token_body

    with (
        patch.dict("os.environ", env),
        patch("urllib.request.urlopen", return_value=token_resp),
    ):
        ok, err = _enviar_via_graph("dest@test.com", "Subj", "<p>H</p>", None, "x@dtx.aero")
    assert ok is False
    assert err is not None


def test_enviar_via_graph_http_error_no_token():
    """_enviar_via_graph retorna (False, err) em HTTPError ao obter token."""
    import io
    import urllib.error

    from app.services.notifications import _enviar_via_graph

    env = {
        "GRAPH_TENANT_ID": "tid",
        "GRAPH_CLIENT_ID": "cid",
        "GRAPH_CLIENT_SECRET": "sec",
        "GRAPH_SENDER_EMAIL": "x@dtx.aero",
    }
    http_err = urllib.error.HTTPError(
        url="https://login...",
        code=401,
        msg="Unauthorized",
        hdrs={},
        fp=io.BytesIO(b"Unauthorized"),
    )
    with (
        patch.dict("os.environ", env),
        patch("urllib.request.urlopen", side_effect=http_err),
    ):
        ok, err = _enviar_via_graph("dest@test.com", "Subj", "<p>H</p>", None, "x@dtx.aero")
    assert ok is False
    assert "401" in str(err)


def test_enviar_via_graph_sendmail_status_nao_202():
    """_enviar_via_graph retorna (False, err) quando sendMail retorna status != 202."""
    import json

    from app.services.notifications import _enviar_via_graph

    env = {
        "GRAPH_TENANT_ID": "tid",
        "GRAPH_CLIENT_ID": "cid",
        "GRAPH_CLIENT_SECRET": "sec",
        "GRAPH_SENDER_EMAIL": "x@dtx.aero",
    }
    token_body = json.dumps({"access_token": "tok_abc"}).encode()
    token_resp = MagicMock()
    token_resp.__enter__ = lambda s: s
    token_resp.__exit__ = MagicMock(return_value=False)
    token_resp.read.return_value = token_body

    send_resp = MagicMock()
    send_resp.__enter__ = lambda s: s
    send_resp.__exit__ = MagicMock(return_value=False)
    send_resp.read.return_value = b""
    send_resp.status = 200  # not 202

    with (
        patch.dict("os.environ", env),
        patch("urllib.request.urlopen", MagicMock(side_effect=[token_resp, send_resp])),
    ):
        ok, err = _enviar_via_graph("dest@test.com", "Subj", "<p>H</p>", None, "x@dtx.aero")
    assert ok is False
    assert err is not None


def test_enviar_via_graph_excecao_generica_no_sendmail():
    """_enviar_via_graph retorna (False, str(e)) em exceção genérica ao enviar e-mail."""
    import json

    from app.services.notifications import _enviar_via_graph

    env = {
        "GRAPH_TENANT_ID": "tid",
        "GRAPH_CLIENT_ID": "cid",
        "GRAPH_CLIENT_SECRET": "sec",
        "GRAPH_SENDER_EMAIL": "x@dtx.aero",
    }
    token_body = json.dumps({"access_token": "tok_abc"}).encode()
    token_resp = MagicMock()
    token_resp.__enter__ = lambda s: s
    token_resp.__exit__ = MagicMock(return_value=False)
    token_resp.read.return_value = token_body

    with (
        patch.dict("os.environ", env),
        patch(
            "urllib.request.urlopen",
            MagicMock(side_effect=[token_resp, Exception("network error")]),
        ),
    ):
        ok, err = _enviar_via_graph("dest@test.com", "Subj", "<p>H</p>", None, "x@dtx.aero")
    assert ok is False
    assert "network error" in str(err)


# ── Ramos de falha das funções de notificação ────────────────────────────────


def test_notificar_aprovador_email_falha_loga_warning(app):
    """notificar_aprovador_novo_chamado com envio falho não levanta exceção."""
    from app.services.notifications import notificar_aprovador_novo_chamado

    responsavel = type("Resp", (), {"email": "resp@dtx.aero"})()
    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", return_value=(False, "SMTP error")),
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        notificar_aprovador_novo_chamado(
            chamado_id="ch_x",
            numero_chamado="2026-200",
            categoria="TI",
            tipo_solicitacao="Corretiva",
            descricao_resumo="Resumo",
            area="TI",
            solicitante_nome="Sol",
            responsavel_usuario=responsavel,
        )


def test_notificar_prazo_24h_email_vazio_nao_envia(app):
    """notificar_responsavel_prazo_24h com e-mail vazio não envia nada."""
    from app.services.notifications import notificar_responsavel_prazo_24h

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email") as mock_send,
    ):
        notificar_responsavel_prazo_24h(
            chamado_id="ch1",
            numero_chamado="2026-201",
            responsavel_email="",
        )
    mock_send.assert_not_called()


def test_notificar_prazo_24h_email_falha_nao_levanta(app):
    """notificar_responsavel_prazo_24h com envio falho não levanta exceção."""
    from app.services.notifications import notificar_responsavel_prazo_24h

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", return_value=(False, "err")),
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        notificar_responsavel_prazo_24h(
            chamado_id="ch1",
            numero_chamado="2026-202",
            responsavel_email="resp@dtx.aero",
            categoria="TI",
        )


def test_notificar_novo_usuario_email_vazio_nao_envia(app):
    """notificar_novo_usuario_cadastrado com e-mail vazio não envia nada."""
    from app.services.notifications import notificar_novo_usuario_cadastrado

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email") as mock_send,
    ):
        notificar_novo_usuario_cadastrado(
            usuario_id="u1",
            usuario_email="",
            usuario_nome="Fulano",
        )
    mock_send.assert_not_called()


def test_notificar_novo_usuario_email_falha_nao_levanta(app):
    """notificar_novo_usuario_cadastrado com envio falho não levanta exceção."""
    from app.services.notifications import notificar_novo_usuario_cadastrado

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", return_value=(False, "err")),
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        notificar_novo_usuario_cadastrado(
            usuario_id="u1",
            usuario_email="user@dtx.aero",
            usuario_nome="Fulano",
            perfil="solicitante",
            senha_inicial="abc123",
        )


def test_notificar_setor_adicional_email_vazio_nao_envia(app):
    """notificar_responsavel_setor_adicional com e-mail vazio não envia nada."""
    from app.services.notifications import notificar_responsavel_setor_adicional

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email") as mock_send,
    ):
        notificar_responsavel_setor_adicional(
            chamado_id="ch1",
            numero_chamado="2026-203",
            email_responsavel_setor="",
            setor_adicional="TI",
        )
    mock_send.assert_not_called()


def test_notificar_setor_adicional_email_falha_nao_levanta(app):
    """notificar_responsavel_setor_adicional com envio falho não levanta exceção."""
    from app.services.notifications import notificar_responsavel_setor_adicional

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", return_value=(False, "err")),
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        notificar_responsavel_setor_adicional(
            chamado_id="ch1",
            numero_chamado="2026-204",
            email_responsavel_setor="setor@dtx.aero",
            setor_adicional="TI",
            categoria="Projetos",
        )


def test_notificar_solicitante_status_email_falha_nao_levanta(app):
    """notificar_solicitante_status com envio falho não levanta exceção."""
    from app.services.notifications import notificar_solicitante_status

    solicitante = MagicMock()
    solicitante.email = "sol@dtx.aero"
    solicitante.nome = "Sol"
    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", return_value=(False, "err")),
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        notificar_solicitante_status("ch1", "CH-001", "Concluído", "TI", solicitante)


# ── notificar_solicitante_confirmacao_pendente ────────────────────────────────


def test_notificar_solicitante_confirmacao_pendente_envia_email(app):
    """notificar_solicitante_confirmacao_pendente envia e-mail pedindo confirmação."""
    from app.services.notifications import notificar_solicitante_confirmacao_pendente

    solicitante = MagicMock()
    solicitante.email = "sol@dtx.aero"
    solicitante.nome = "Sol"
    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", return_value=(True, None)) as mock_send,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        notificar_solicitante_confirmacao_pendente("ch1", "CH-001", "TI", solicitante)

    mock_send.assert_called_once()


def test_notificar_solicitante_confirmacao_pendente_sem_usuario_nao_envia(app):
    """Com solicitante_usuario=None, nenhum e-mail é enviado."""
    from app.services.notifications import notificar_solicitante_confirmacao_pendente

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email") as mock_send,
    ):
        notificar_solicitante_confirmacao_pendente("ch1", "CH-001", "TI", None)

    mock_send.assert_not_called()


def test_notificar_solicitante_confirmacao_pendente_sem_email_nao_envia(app):
    """Com email vazio no usuário, nenhum e-mail é enviado."""
    from app.services.notifications import notificar_solicitante_confirmacao_pendente

    solicitante = MagicMock()
    solicitante.email = ""
    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email") as mock_send,
    ):
        notificar_solicitante_confirmacao_pendente("ch1", "CH-001", "TI", solicitante)

    mock_send.assert_not_called()


def test_notificar_solicitante_confirmacao_pendente_falha_nao_levanta(app):
    """Envio falho não levanta exceção."""
    from app.services.notifications import notificar_solicitante_confirmacao_pendente

    solicitante = MagicMock()
    solicitante.email = "sol@dtx.aero"
    solicitante.nome = "Sol"
    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", return_value=(False, "err")),
    ):
        notificar_solicitante_confirmacao_pendente("ch1", "CH-001", "TI", solicitante)


def test_notificar_solicitante_confirmacao_pendente_sem_base_url(app):
    """Sem APP_BASE_URL configurada, ainda envia (sem link no corpo)."""
    from app.services.notifications import notificar_solicitante_confirmacao_pendente

    solicitante = MagicMock()
    solicitante.email = "sol@dtx.aero"
    solicitante.nome = "Sol"
    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", return_value=(True, None)) as mock_send,
    ):
        app.config["APP_BASE_URL"] = ""
        notificar_solicitante_confirmacao_pendente("ch1", "CH-001", "TI", solicitante)

    mock_send.assert_called_once()


# ── notificar_setores_adicionais_chamado ──────────────────────────────────────


def test_notificar_setores_adicionais_lista_vazia_retorna_imediatamente(app):
    """notificar_setores_adicionais_chamado com lista vazia não faz nada."""
    from app.services.notifications import notificar_setores_adicionais_chamado

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email") as mock_send,
    ):
        notificar_setores_adicionais_chamado(
            chamado_id="ch1",
            numero_chamado="2026-300",
            setores_novos=[],
            categoria="TI",
            tipo_solicitacao="Corretiva",
            descricao_resumo="Resumo",
            solicitante_nome="Sol",
            quem_adicionou_nome="Sup",
        )
    mock_send.assert_not_called()


def test_notificar_setores_adicionais_com_supervisor_envia_email(app):
    """notificar_setores_adicionais_chamado com supervisores encontrados envia e-mails."""
    from app.services.notifications import notificar_setores_adicionais_chamado

    sup = MagicMock()
    sup.id = "sup_1"
    sup.email = "sup@dtx.aero"

    with (
        app.app_context(),
        patch("app.models_usuario.Usuario.get_supervisores_por_area", return_value=[sup]),
        patch("app.utils_areas.setor_para_area", return_value="Manutencao"),
        patch("app.services.notifications.enviar_email", return_value=(True, None)) as mock_send,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        notificar_setores_adicionais_chamado(
            chamado_id="ch1",
            numero_chamado="2026-301",
            setores_novos=["Manutencao"],
            categoria="Projetos",
            tipo_solicitacao="Corretiva",
            descricao_resumo="Resumo do chamado",
            solicitante_nome="Solicitante",
            quem_adicionou_nome="Supervisor",
        )
    mock_send.assert_called_once()
    dest = mock_send.call_args[0][0]
    assert dest == "sup@dtx.aero"


def test_notificar_setores_adicionais_supervisor_sem_email_ignorado(app):
    """notificar_setores_adicionais_chamado ignora supervisores sem e-mail."""
    from app.services.notifications import notificar_setores_adicionais_chamado

    sup = MagicMock()
    sup.id = "sup_2"
    sup.email = ""

    with (
        app.app_context(),
        patch("app.models_usuario.Usuario.get_supervisores_por_area", return_value=[sup]),
        patch("app.utils_areas.setor_para_area", return_value=None),
        patch("app.services.notifications.enviar_email") as mock_send,
    ):
        notificar_setores_adicionais_chamado(
            chamado_id="ch2",
            numero_chamado="2026-302",
            setores_novos=["TI"],
            categoria="TI",
            tipo_solicitacao="Corretiva",
            descricao_resumo="",
            solicitante_nome="Sol",
            quem_adicionou_nome="Sup",
        )
    mock_send.assert_not_called()


# ── Fase 3: notificar_supervisor_transferencia_area / escalonamento_colega ────


def test_notificar_transferencia_area_chama_enviar_email_com_area_correta(app):
    """L3: notificar_supervisor_transferencia_area envia e-mail com assunto correto e área destino."""
    from app.services.notifications import notificar_supervisor_transferencia_area

    responsavel = MagicMock()
    responsavel.email = "novo.resp@dtx.aero"
    responsavel.nome = "Matheus Costa"

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", return_value=(True, None)) as mock_send,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        notificar_supervisor_transferencia_area(
            chamado_id="ch_fase3",
            numero_chamado="2026-999",
            area="Planejamento",
            categoria="Projetos",
            motivo="Precisa de PPCP",
            responsavel_usuario=responsavel,
        )

    mock_send.assert_called_once()
    dest, assunto, corpo_html, _txt = mock_send.call_args[0]
    assert dest == "novo.resp@dtx.aero"
    assert "2026-999" in assunto
    assert "transferred" in assunto.lower()
    assert "Planning" in corpo_html  # "Planejamento" is translated to English in emails


def test_notificar_escalonamento_colega_chama_enviar_email(app):
    """L3: notificar_supervisor_escalonamento_colega envia e-mail ao colega destino."""
    from app.services.notifications import notificar_supervisor_escalonamento_colega

    colega = MagicMock()
    colega.email = "colega@dtx.aero"
    colega.nome = "Julia Silva"

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", return_value=(True, None)) as mock_send,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        notificar_supervisor_escalonamento_colega(
            chamado_id="ch_fase3b",
            numero_chamado="2026-998",
            area="Engenharia",
            categoria="Corretiva",
            motivo="Especialidade Julia",
            responsavel_usuario=colega,
        )

    mock_send.assert_called_once()
    dest, assunto, corpo_html, _txt = mock_send.call_args[0]
    assert dest == "colega@dtx.aero"
    assert "2026-998" in assunto
    assert "escalated" in assunto.lower()
    assert "Engineering" in corpo_html  # "Engenharia" is translated to English in emails


def test_notificar_transferencia_sem_email_destino_nao_dispara(app):
    """L3: fail-safe — sem e-mail no usuário destino, nenhum envio ocorre."""
    from app.services.notifications import notificar_supervisor_transferencia_area

    responsavel_sem_email = MagicMock()
    responsavel_sem_email.email = ""

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email") as mock_send,
    ):
        notificar_supervisor_transferencia_area(
            chamado_id="ch_fase3c",
            numero_chamado="2026-997",
            area="TI",
            categoria="TI",
            motivo="motivo",
            responsavel_usuario=responsavel_sem_email,
        )

    mock_send.assert_not_called()


def test_notificar_setores_adicionais_envio_falho_nao_levanta(app):
    """notificar_setores_adicionais_chamado com envio falho não levanta exceção."""
    from app.services.notifications import notificar_setores_adicionais_chamado

    sup = MagicMock()
    sup.id = "sup_3"
    sup.email = "sup3@dtx.aero"

    with (
        app.app_context(),
        patch("app.models_usuario.Usuario.get_supervisores_por_area", return_value=[sup]),
        patch("app.utils_areas.setor_para_area", return_value=None),
        patch("app.services.notifications.enviar_email", return_value=(False, "err")),
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        notificar_setores_adicionais_chamado(
            chamado_id="ch3",
            numero_chamado="2026-303",
            setores_novos=["Engenharia"],
            categoria="Projetos",
            tipo_solicitacao="Nova",
            descricao_resumo="Resumo",
            solicitante_nome="Sol",
            quem_adicionou_nome="Admin",
        )


# ── notificar_escalada_resposta_gerencial (Fase 6 — Escada A) ──────────────


def test_notificar_escalada_resposta_gerencial_assunto_contem_numero(app):
    """Smoke: assunto do e-mail contém o número do chamado e o nível."""
    from app.services.notifications import notificar_escalada_resposta_gerencial

    chamado_data = {
        "numero_chamado": "CHM-0099",
        "categoria": "Manutenção",
        "area": "Engenharia",
        "tipo_solicitacao": "Planejamento",
        "descricao": "Máquina parada.",
    }

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", return_value=(True, None)) as mock_send,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        notificar_escalada_resposta_gerencial(
            chamado_data=chamado_data,
            chamado_id="ch_99",
            nivel=1,
            email_dest="gestor@dtx.aero",
        )

    mock_send.assert_called_once()
    _dest, assunto, _html, _txt = mock_send.call_args[0]
    assert "CHM-0099" in assunto
    assert "1" in assunto
    assert _dest == "gestor@dtx.aero"


def test_notificar_escalada_resposta_gerencial_falha_nao_levanta(app):
    """enviar_email falho não deve propagar exceção (apenas log warning)."""
    from app.services.notifications import notificar_escalada_resposta_gerencial

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", return_value=(False, "timeout")),
    ):
        notificar_escalada_resposta_gerencial(
            chamado_data={"numero_chamado": "CHM-0001"},
            chamado_id="ch_1",
            nivel=2,
            email_dest="gerente@dtx.aero",
        )  # não deve levantar


# ── AOG — notificar_abertura_aog_todos_gestores ────────────────────────────────────────────────


def test_notificar_abertura_aog_todos_gestores_envia_para_os_4_niveis(app):
    """Abertura de AOG dispara e-mail simultâneo pros 4 níveis de gestor, não sequencial."""
    from app.services.notifications import notificar_abertura_aog_todos_gestores

    chamado_data = {
        "numero_chamado": "CHM-AOG-01",
        "categoria": "AOG",
        "area": "Manutenção",
        "tipo_solicitacao": "Corretiva",
        "descricao": "Aeronave PR-XYZ em solo, hidráulica falhou.",
    }

    emails_por_nivel = {
        "gestor_setor": "setor@dtx.aero",
        "gerente_producao": "producao@dtx.aero",
        "assistente_gm": "assistente@dtx.aero",
        "gm": "gm@dtx.aero",
    }

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", return_value=(True, None)) as mock_send,
        patch(
            "app.services.gestor_escalonamento_service.construir_mapa_gestor_setor",
            return_value={"AOG": "setor@dtx.aero"},
        ),
        patch(
            "app.services.gestor_escalonamento_service.construir_mapa_niveis_superiores",
            return_value={
                "gerente_producao": "producao@dtx.aero",
                "assistente_gm": "assistente@dtx.aero",
                "gm": "gm@dtx.aero",
            },
        ),
    ):
        notificar_abertura_aog_todos_gestores(chamado_data=chamado_data, chamado_id="ch_aog_1")

    assert mock_send.call_count == 4
    destinatarios = {call.args[0] for call in mock_send.call_args_list}
    assert destinatarios == set(emails_por_nivel.values())
    # Todos de alta importância (emergência) e mencionam o número do chamado
    for call in mock_send.call_args_list:
        _dest, assunto, _html, _txt = call.args
        assert "CHM-AOG-01" in assunto
        assert call.kwargs.get("importance") == "high"


def test_notificar_abertura_aog_cascateia_para_nivel_acima_quando_ausente(app):
    """gestor_setor sem ninguém cadastrado pra área → cascateia pro gerente_producao
    (emergência: nunca fica sem notificar por lacuna de cadastro)."""
    from app.services.notifications import notificar_abertura_aog_todos_gestores

    chamado_data = {"numero_chamado": "CHM-AOG-02", "categoria": "AOG"}

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", return_value=(True, None)) as mock_send,
        patch(
            "app.services.gestor_escalonamento_service.construir_mapa_gestor_setor",
            return_value={},  # nenhum gestor_setor cadastrado pra área "AOG"
        ),
        patch(
            "app.services.gestor_escalonamento_service.construir_mapa_niveis_superiores",
            return_value={
                "gerente_producao": "producao@dtx.aero",
                "assistente_gm": "assistente@dtx.aero",
                "gm": "gm@dtx.aero",
            },
        ),
    ):
        notificar_abertura_aog_todos_gestores(chamado_data=chamado_data, chamado_id="ch_aog_2")

    # gestor_setor cascateia pra producao@dtx.aero (mesmo destinatário do nível
    # gerente_producao) — deduplicado, não duplica o e-mail: 3 envios no total
    # (producao, assistente, gm), não 4.
    assert mock_send.call_count == 3
    destinatarios = [call.args[0] for call in mock_send.call_args_list]
    assert destinatarios == ["producao@dtx.aero", "assistente@dtx.aero", "gm@dtx.aero"]


def test_notificar_abertura_aog_sem_ninguem_cadastrado_em_nenhum_nivel_nao_envia(app):
    """Nenhum nível (nem acima, via cascata) tem alguém cadastrado → nenhum e-mail
    enviado, sem exception (só log warning)."""
    from app.services.notifications import notificar_abertura_aog_todos_gestores

    chamado_data = {"numero_chamado": "CHM-AOG-02B", "categoria": "AOG"}

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", return_value=(True, None)) as mock_send,
        patch(
            "app.services.gestor_escalonamento_service.construir_mapa_gestor_setor",
            return_value={},
        ),
        patch(
            "app.services.gestor_escalonamento_service.construir_mapa_niveis_superiores",
            return_value={},
        ),
    ):
        notificar_abertura_aog_todos_gestores(chamado_data=chamado_data, chamado_id="ch_aog_2b")

    mock_send.assert_not_called()


def test_notificar_abertura_aog_falha_de_envio_nao_levanta(app):
    """Falha no envio de um nível não deve impedir a tentativa dos outros nem propagar exceção."""
    from app.services.notifications import notificar_abertura_aog_todos_gestores

    chamado_data = {"numero_chamado": "CHM-AOG-03", "categoria": "AOG"}

    with (
        app.app_context(),
        patch(
            "app.services.notifications.enviar_email", return_value=(False, "timeout")
        ) as mock_send,
        patch(
            "app.services.gestor_escalonamento_service.construir_mapa_gestor_setor",
            return_value={"AOG": "setor@dtx.aero"},
        ),
        patch(
            "app.services.gestor_escalonamento_service.construir_mapa_niveis_superiores",
            return_value={
                "gerente_producao": "producao@dtx.aero",
                "assistente_gm": "assistente@dtx.aero",
                "gm": "gm@dtx.aero",
            },
        ),
    ):
        notificar_abertura_aog_todos_gestores(
            chamado_data=chamado_data, chamado_id="ch_aog_3"
        )  # não deve levantar

    assert mock_send.call_count == 4


# ── Fase 7 — notificar_aviso_resolucao_supervisor / notificar_escalada_resolucao_gerencial ────


def test_notificar_aviso_resolucao_supervisor_envia_email(app):
    """notificar_aviso_resolucao_supervisor envia in-app + webpush + e-mail quando email_dest informado."""
    from app.services.notifications import notificar_aviso_resolucao_supervisor

    chamado_data = {
        "numero_chamado": "CHM-0150",
        "categoria": "Manutenção",
        "area": "Engenharia",
        "tipo_solicitacao": "Corretiva",
        "descricao": "Máquina parada.",
    }

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", return_value=(True, None)) as mock_email,
        patch("app.services.notifications_inapp.criar_notificacao") as mock_criar,
        patch("app.services.webpush_service.enviar_webpush_usuario") as mock_webpush,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        notificar_aviso_resolucao_supervisor(
            chamado_data=chamado_data,
            chamado_id="ch_150",
            marco=50,
            responsavel_id="sup_1",
            email_dest="sup@dtx.aero",
        )

    mock_criar.assert_called_once()
    assert mock_criar.call_args.kwargs.get("usuario_id") == "sup_1"
    assert mock_criar.call_args.kwargs.get("tipo") == "sla_resolucao"
    mock_webpush.assert_called_once()
    assert mock_webpush.call_args.kwargs.get("usuario_id") == "sup_1"
    mock_email.assert_called_once()
    _dest, assunto, _html, _txt = mock_email.call_args[0]
    assert "CHM-0150" in assunto
    assert "50" in assunto
    assert _dest == "sup@dtx.aero"


def test_notificar_aviso_resolucao_supervisor_sem_email_dispara_inapp_e_webpush(app):
    """email_dest=None → criar_notificacao e enviar_webpush_usuario chamados; enviar_email NÃO."""
    from app.services.notifications import notificar_aviso_resolucao_supervisor

    chamado_data = {
        "numero_chamado": "CHM-0151",
        "categoria": "Manutenção",
        "area": "Engenharia",
        "tipo_solicitacao": "Corretiva",
        "descricao": "Teste sem email.",
    }

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email") as mock_email,
        patch("app.services.notifications_inapp.criar_notificacao") as mock_criar,
        patch("app.services.webpush_service.enviar_webpush_usuario") as mock_webpush,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        notificar_aviso_resolucao_supervisor(
            chamado_data=chamado_data,
            chamado_id="ch_151",
            marco=50,
            responsavel_id="sup_1",
            email_dest=None,
        )

    mock_criar.assert_called_once()
    mock_webpush.assert_called_once()
    mock_email.assert_not_called()


def test_notificar_escalada_resolucao_gerencial_envia_email(app):
    """notificar_escalada_resolucao_gerencial envia e-mail com assunto contendo numero_chamado e nivel."""
    from app.services.notifications import notificar_escalada_resolucao_gerencial

    chamado_data = {
        "numero_chamado": "CHM-0200",
        "categoria": "Projetos",
        "area": "Planejamento",
        "tipo_solicitacao": "Nova",
        "descricao": "Projeto urgente.",
    }

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", return_value=(True, None)) as mock_email,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        notificar_escalada_resolucao_gerencial(
            chamado_data=chamado_data,
            chamado_id="ch_200",
            nivel=2,
            email_dest="gerente@dtx.aero",
        )

    mock_email.assert_called_once()
    _dest, assunto, _html, _txt = mock_email.call_args[0]
    assert "CHM-0200" in assunto
    assert "2" in assunto
    assert _dest == "gerente@dtx.aero"


# ── Cobertura: _email_envio_permitido linha 223 ───────────────────────────────


def test_email_suprimido_quando_testing_true(app):
    """_email_envio_permitido retorna False (linha 223) quando TESTING=True.

    A conftest seta TESTING=True; não sobrescrever aqui para bater exatamente
    nessa branch não coberta pelos outros testes (que explicitamente setam False).
    """
    from app.services.notifications import enviar_email

    with app.app_context():
        ok, err = enviar_email("dest@test.com", "Assunto", "<p>Teste</p>")
    assert ok is True
    assert err is None
