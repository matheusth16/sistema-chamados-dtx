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
    assert assunto == "Bem-vindo ao DTX Digital Andon — suas credenciais de acesso"
    assert "Perfil" in corpo_html or "perfil" in corpo_html.lower()
    assert "SenhaTest99" in corpo_html
    assert "123456" not in corpo_html


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
    assert assunto == "Chamado 2026-100: prazo se encerrando em 24h"
    assert "2026-100" in corpo_html
    assert "vencer" in corpo_html.lower() or "prazo" in corpo_html.lower()


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
    assert assunto == "Chamado 2026-101: seu setor foi incluído"
    assert "2026-101" in corpo_html
    assert "Engenharia" in corpo_html


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
    assert assunto == "Novo chamado atribuído: 2026-103"


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
    assert "CH-001" in corpo_html
    assert "Concluído" in corpo_html or "conclu" in corpo_html.lower()


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
            "app.services.notifications._enviar_via_graph", return_value=(True, None)
        ) as mock_graph,
    ):
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
    assert assunto == "Novo chamado atribuído: 2026-102"
    assert "2026-102" in corpo_html
    assert "Ver histórico do chamado" in corpo_html
    assert "Ver chamados do setor" in corpo_html
