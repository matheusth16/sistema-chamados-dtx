"""Testes TDD para importance de e-mail (Microsoft Graph).

Cobre: resolver_importance, _prefixar_assunto_high,
payload JSON do Graph, propagação via enviar_email e notificadores específicos.
"""

import json
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers compartilhados
# ---------------------------------------------------------------------------


def _make_urlopen_capture():
    """Mock de urllib.request.urlopen que captura a requisição sendMail.

    Retorna (fake_urlopen, captured_requests) onde captured_requests é uma lista
    preenchida com os objetos Request passados ao urlopen.
    """
    token_body = json.dumps({"access_token": "tok_abc"}).encode()
    captured_requests: list = []

    def fake_urlopen(req, timeout=None):
        captured_requests.append(req)
        if len(captured_requests) == 1:  # requisição de token
            resp = MagicMock()
            resp.__enter__ = lambda s: s
            resp.__exit__ = MagicMock(return_value=False)
            resp.read.return_value = token_body
            resp.status = 200
            return resp
        # requisição sendMail
        resp = MagicMock()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        resp.read.return_value = b""
        resp.status = 202
        return resp

    return fake_urlopen, captured_requests


# ---------------------------------------------------------------------------
# resolver_importance — casos "high"
# ---------------------------------------------------------------------------


def test_resolver_importance_projetos_retorna_high():
    """categoria=Projetos → 'high' para responsavel."""
    from app.services.notifications import resolver_importance

    result = resolver_importance(
        "novo_chamado_aprovador",
        chamado_data={"categoria": "Projetos", "prioridade": 1},
        destinatario_perfil="responsavel",
    )
    assert result == "high"


def test_resolver_importance_prioridade_zero_retorna_high():
    """prioridade=0 (categoria ≠ Projetos) → 'high' para responsavel."""
    from app.services.notifications import resolver_importance

    result = resolver_importance(
        "novo_chamado_aprovador",
        chamado_data={"categoria": "Manutenção", "prioridade": 0},
        destinatario_perfil="responsavel",
    )
    assert result == "high"


def test_resolver_importance_aog_retorna_high():
    """categoria=AOG (prioridade=-1) → 'high' para responsavel, igual Projetos."""
    from app.services.notifications import resolver_importance

    result = resolver_importance(
        "novo_chamado_aprovador",
        chamado_data={"categoria": "AOG", "prioridade": -1},
        destinatario_perfil="responsavel",
    )
    assert result == "high"


def test_resolver_importance_prazo_24h_high():
    """tipo=prazo_24h → 'high'."""
    from app.services.notifications import resolver_importance

    assert resolver_importance("prazo_24h") == "high"


def test_resolver_importance_marco_80_retorna_high():
    """aviso_resolucao_supervisor marco=80 → 'high'."""
    from app.services.notifications import resolver_importance

    assert resolver_importance("aviso_resolucao_supervisor", marco_sla=80) == "high"


def test_resolver_importance_lembrete_2_high():
    """lembrete_confirmacao #2 (48 h sem confirmação) → 'high'."""
    from app.services.notifications import resolver_importance

    assert resolver_importance("lembrete_confirmacao", numero_lembrete=2) == "high"


def test_resolver_importance_escalada_resposta_high():
    """escalada_resposta_gerencial → 'high'."""
    from app.services.notifications import resolver_importance

    assert resolver_importance("escalada_resposta_gerencial") == "high"


def test_resolver_importance_escalada_resolucao_high():
    """escalada_resolucao_gerencial → 'high'."""
    from app.services.notifications import resolver_importance

    assert resolver_importance("escalada_resolucao_gerencial") == "high"


def test_resolver_importance_transferencia_high():
    """transferencia_area → 'high'."""
    from app.services.notifications import resolver_importance

    assert resolver_importance("transferencia_area") == "high"


def test_resolver_importance_escalonamento_colega_high():
    """escalonamento_colega → 'high'."""
    from app.services.notifications import resolver_importance

    assert resolver_importance("escalonamento_colega") == "high"


def test_resolver_importance_chamado_reaberto_high():
    """chamado_reaberto → 'high'."""
    from app.services.notifications import resolver_importance

    assert resolver_importance("chamado_reaberto") == "high"


# ---------------------------------------------------------------------------
# resolver_importance — casos "normal"
# ---------------------------------------------------------------------------


def test_resolver_importance_chamado_padrao_retorna_normal():
    """chamado padrão (prioridade 1, categoria ≠ Projetos) → 'normal'."""
    from app.services.notifications import resolver_importance

    result = resolver_importance(
        "novo_chamado_aprovador",
        chamado_data={"categoria": "Manutenção", "prioridade": 1},
        destinatario_perfil="responsavel",
    )
    assert result == "normal"


def test_resolver_importance_solicitante_sempre_normal():
    """destinatario_perfil='solicitante' → sempre 'normal', mesmo com Projetos/prioridade 0."""
    from app.services.notifications import resolver_importance

    result = resolver_importance(
        "novo_chamado_aprovador",
        chamado_data={"categoria": "Projetos", "prioridade": 0},
        destinatario_perfil="solicitante",
    )
    assert result == "normal"


def test_resolver_importance_marco_50_retorna_normal():
    """aviso_resolucao_supervisor marco=50 → 'normal'."""
    from app.services.notifications import resolver_importance

    assert resolver_importance("aviso_resolucao_supervisor", marco_sla=50) == "normal"


def test_resolver_importance_lembrete_1_normal():
    """lembrete_confirmacao #1 → 'normal'."""
    from app.services.notifications import resolver_importance

    assert resolver_importance("lembrete_confirmacao", numero_lembrete=1) == "normal"


def test_resolver_importance_default_retorna_normal():
    """tipo desconhecido → 'normal'."""
    from app.services.notifications import resolver_importance

    assert resolver_importance("tipo_desconhecido") == "normal"


# ---------------------------------------------------------------------------
# resolver_importance — caso "low"
# ---------------------------------------------------------------------------


def test_resolver_importance_relatorio_retorna_low():
    """tipo=relatorio → 'low'."""
    from app.services.notifications import resolver_importance

    assert resolver_importance("relatorio") == "low"


# ---------------------------------------------------------------------------
# _prefixar_assunto_high
# ---------------------------------------------------------------------------


def test_prefixar_assunto_high_novo_chamado_projetos():
    """contexto=novo_chamado_projetos adiciona 'Action required: ' ao assunto."""
    from app.services.notifications import _prefixar_assunto_high

    result = _prefixar_assunto_high("New ticket assigned: 2026-100", "novo_chamado_projetos")
    assert result == "Action required: New ticket assigned: 2026-100"


def test_prefixar_assunto_high_sla_sem_prefixo_adicional():
    """contexto SLA não adiciona prefixo (assunto já tem [SLA Alert])."""
    from app.services.notifications import _prefixar_assunto_high

    assunto = "[SLA Alert] Ticket CHM-001 — no response"
    assert _prefixar_assunto_high(assunto, "escalada_resposta_gerencial") == assunto


def test_prefixar_assunto_high_outros_sem_prefixo():
    """contexto genérico não modifica o assunto."""
    from app.services.notifications import _prefixar_assunto_high

    assunto = "Ticket CHM-001: reopened by requester"
    assert _prefixar_assunto_high(assunto, "chamado_reaberto") == assunto


def test_prefixar_assunto_high_contexto_vazio_sem_prefixo():
    """contexto vazio não modifica o assunto."""
    from app.services.notifications import _prefixar_assunto_high

    assunto = "Ticket CHM-001: deadline in 24h"
    assert _prefixar_assunto_high(assunto, "") == assunto


# ---------------------------------------------------------------------------
# _enviar_via_graph — importance no payload JSON
# ---------------------------------------------------------------------------


_GRAPH_ENV = {
    "GRAPH_TENANT_ID": "tid",
    "GRAPH_CLIENT_ID": "cid",
    "GRAPH_CLIENT_SECRET": "sec",
    "GRAPH_SENDER_EMAIL": "noreply@dtx.aero",
}


def test_enviar_via_graph_inclui_importance_high_no_payload():
    """_enviar_via_graph com importance='high' inclui o campo no payload JSON."""
    from app.services.notifications import _enviar_via_graph

    fake_urlopen, captured = _make_urlopen_capture()
    with (
        patch.dict("os.environ", _GRAPH_ENV),
        patch("urllib.request.urlopen", fake_urlopen),
    ):
        ok, err = _enviar_via_graph(
            "dest@test.com",
            "Assunto",
            "<p>HTML</p>",
            "Texto",
            "noreply@dtx.aero",
            importance="high",
        )

    assert ok is True, err
    assert len(captured) == 2
    payload = json.loads(captured[1].data.decode("utf-8"))
    assert payload["message"]["importance"] == "high"


def test_enviar_via_graph_inclui_importance_low_no_payload():
    """_enviar_via_graph com importance='low' inclui campo correto no payload."""
    from app.services.notifications import _enviar_via_graph

    fake_urlopen, captured = _make_urlopen_capture()
    with (
        patch.dict("os.environ", _GRAPH_ENV),
        patch("urllib.request.urlopen", fake_urlopen),
    ):
        ok, err = _enviar_via_graph(
            "dest@test.com",
            "Assunto",
            "<p>HTML</p>",
            None,
            "noreply@dtx.aero",
            importance="low",
        )

    assert ok is True, err
    payload = json.loads(captured[1].data.decode("utf-8"))
    assert payload["message"]["importance"] == "low"


def test_enviar_via_graph_default_importance_normal():
    """_enviar_via_graph sem importance → 'normal' no payload."""
    from app.services.notifications import _enviar_via_graph

    fake_urlopen, captured = _make_urlopen_capture()
    with (
        patch.dict("os.environ", _GRAPH_ENV),
        patch("urllib.request.urlopen", fake_urlopen),
    ):
        ok, err = _enviar_via_graph(
            "dest@test.com", "Assunto", "<p>HTML</p>", None, "noreply@dtx.aero"
        )

    assert ok is True, err
    payload = json.loads(captured[1].data.decode("utf-8"))
    assert payload["message"]["importance"] == "normal"


# ---------------------------------------------------------------------------
# enviar_email — propagação de importance para _enviar_via_graph
# ---------------------------------------------------------------------------


def test_enviar_email_passa_importance_high_para_graph(app):
    """enviar_email com importance='high' propaga o valor para _enviar_via_graph."""
    from app.services.notifications import enviar_email

    with (
        app.app_context(),
        patch(
            "app.services.notifications_core._enviar_via_graph", return_value=(True, None)
        ) as mock_graph,
    ):
        app.config["NOTIFY_EMAIL_ENABLED"] = True
        app.config["TESTING"] = False
        enviar_email("dest@test.com", "Assunto", "<p>HTML</p>", importance="high")

    mock_graph.assert_called_once()
    assert mock_graph.call_args.kwargs.get("importance") == "high"


def test_enviar_email_default_importance_normal(app):
    """enviar_email sem importance → propaga 'normal' para _enviar_via_graph."""
    from app.services.notifications import enviar_email

    with (
        app.app_context(),
        patch(
            "app.services.notifications_core._enviar_via_graph", return_value=(True, None)
        ) as mock_graph,
    ):
        app.config["NOTIFY_EMAIL_ENABLED"] = True
        app.config["TESTING"] = False
        enviar_email("dest@test.com", "Assunto", "<p>HTML</p>")

    mock_graph.assert_called_once()
    assert mock_graph.call_args.kwargs.get("importance") == "normal"


def test_enviar_email_importance_invalida_usa_normal(app):
    """enviar_email com importance inválida → fallback para 'normal'."""
    from app.services.notifications import enviar_email

    with (
        app.app_context(),
        patch(
            "app.services.notifications_core._enviar_via_graph", return_value=(True, None)
        ) as mock_graph,
    ):
        app.config["NOTIFY_EMAIL_ENABLED"] = True
        app.config["TESTING"] = False
        enviar_email("dest@test.com", "Assunto", "<p>HTML</p>", importance="urgent")

    mock_graph.assert_called_once()
    assert mock_graph.call_args.kwargs.get("importance") == "normal"


# ---------------------------------------------------------------------------
# Notificadores específicos — importance passada corretamente
# ---------------------------------------------------------------------------


def test_notificar_prazo_24h_importance_high(app):
    """notificar_responsavel_prazo_24h passa importance='high' para enviar_email."""
    from app.services.notifications import notificar_responsavel_prazo_24h

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", return_value=(True, None)) as mock_send,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        notificar_responsavel_prazo_24h(
            chamado_id="ch1",
            numero_chamado="2026-100",
            responsavel_email="resp@dtx.aero",
        )

    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs.get("importance") == "high"


def test_notificar_aprovador_projetos_importance_high(app):
    """notificar_aprovador_novo_chamado com Projetos passa importance='high'."""
    from app.services.notifications import notificar_aprovador_novo_chamado

    responsavel = type("Resp", (), {"email": "resp@dtx.aero"})()

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", return_value=(True, None)) as mock_send,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        notificar_aprovador_novo_chamado(
            chamado_id="ch1",
            numero_chamado="2026-100",
            categoria="Projetos",
            tipo_solicitacao="Nova",
            descricao_resumo="Resumo",
            area="Planejamento",
            solicitante_nome="Sol",
            responsavel_usuario=responsavel,
            prioridade=1,
        )

    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs.get("importance") == "high"


def test_notificar_aprovador_prioridade_zero_importance_high(app):
    """notificar_aprovador_novo_chamado com prioridade=0 passa importance='high'."""
    from app.services.notifications import notificar_aprovador_novo_chamado

    responsavel = type("Resp", (), {"email": "resp@dtx.aero"})()

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", return_value=(True, None)) as mock_send,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        notificar_aprovador_novo_chamado(
            chamado_id="ch1",
            numero_chamado="2026-100",
            categoria="Manutenção",
            tipo_solicitacao="Corretiva",
            descricao_resumo="Resumo",
            area="Manutencao",
            solicitante_nome="Sol",
            responsavel_usuario=responsavel,
            prioridade=0,
        )

    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs.get("importance") == "high"


def test_notificar_aprovador_padrao_importance_normal(app):
    """notificar_aprovador_novo_chamado chamado padrão passa importance='normal'."""
    from app.services.notifications import notificar_aprovador_novo_chamado

    responsavel = type("Resp", (), {"email": "resp@dtx.aero"})()

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", return_value=(True, None)) as mock_send,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        notificar_aprovador_novo_chamado(
            chamado_id="ch2",
            numero_chamado="2026-101",
            categoria="Manutenção",
            tipo_solicitacao="Corretiva",
            descricao_resumo="Resumo",
            area="Manutencao",
            solicitante_nome="Sol",
            responsavel_usuario=responsavel,
            prioridade=1,
        )

    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs.get("importance") == "normal"


def test_notificar_solicitante_status_importance_normal(app):
    """notificar_solicitante_status sempre passa importance='normal' (destinatário é solicitante)."""
    from app.services.notifications import notificar_solicitante_status

    solicitante = MagicMock()
    solicitante.email = "sol@test.com"
    solicitante.nome = "Sol"

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", return_value=(True, None)) as mock_send,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        notificar_solicitante_status("ch1", "CH-001", "Concluído", "Projetos", solicitante)

    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs.get("importance") == "normal"


def test_notificar_aviso_resolucao_marco_80_importance_high(app):
    """notificar_aviso_resolucao_supervisor marco=80 passa importance='high'."""
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
        patch(
            "app.services.notifications_escalonamento.enviar_email", return_value=(True, None)
        ) as mock_email,
        patch("app.services.notifications_inapp.criar_notificacao"),
        patch("app.services.webpush_service.enviar_webpush_usuario"),
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        notificar_aviso_resolucao_supervisor(
            chamado_data=chamado_data,
            chamado_id="ch_150",
            marco=80,
            responsavel_id="sup_1",
            email_dest="sup@dtx.aero",
        )

    mock_email.assert_called_once()
    assert mock_email.call_args.kwargs.get("importance") == "high"


def test_notificar_aviso_resolucao_marco_50_importance_normal(app):
    """notificar_aviso_resolucao_supervisor marco=50 passa importance='normal'."""
    from app.services.notifications import notificar_aviso_resolucao_supervisor

    chamado_data = {
        "numero_chamado": "CHM-0151",
        "categoria": "Manutenção",
        "area": "Engenharia",
        "tipo_solicitacao": "Corretiva",
        "descricao": "Teste.",
    }

    with (
        app.app_context(),
        patch(
            "app.services.notifications_escalonamento.enviar_email", return_value=(True, None)
        ) as mock_email,
        patch("app.services.notifications_inapp.criar_notificacao"),
        patch("app.services.webpush_service.enviar_webpush_usuario"),
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        notificar_aviso_resolucao_supervisor(
            chamado_data=chamado_data,
            chamado_id="ch_151",
            marco=50,
            responsavel_id="sup_1",
            email_dest="sup@dtx.aero",
        )

    mock_email.assert_called_once()
    assert mock_email.call_args.kwargs.get("importance") == "normal"


def test_notificar_lembrete_confirmacao_1_importance_normal(app):
    """notificar_solicitante_lembrete_confirmacao lembrete #1 → importance='normal'."""
    from app.services.notifications import notificar_solicitante_lembrete_confirmacao

    solicitante = MagicMock()
    solicitante.email = "sol@test.com"
    solicitante.nome = "Sol"

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", return_value=(True, None)) as mock_send,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        notificar_solicitante_lembrete_confirmacao(
            "ch1", "CH-001", "TI", solicitante, numero_lembrete=1
        )

    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs.get("importance") == "normal"


def test_notificar_lembrete_confirmacao_2_importance_high(app):
    """notificar_solicitante_lembrete_confirmacao lembrete #2 (48 h) → importance='high'."""
    from app.services.notifications import notificar_solicitante_lembrete_confirmacao

    solicitante = MagicMock()
    solicitante.email = "sol@test.com"
    solicitante.nome = "Sol"

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", return_value=(True, None)) as mock_send,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        notificar_solicitante_lembrete_confirmacao(
            "ch1", "CH-001", "TI", solicitante, numero_lembrete=2
        )

    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs.get("importance") == "high"


def test_notificar_escalada_resposta_importance_high(app):
    """notificar_escalada_resposta_gerencial passa importance='high'."""
    from app.services.notifications import notificar_escalada_resposta_gerencial

    with (
        app.app_context(),
        patch(
            "app.services.notifications_escalonamento.enviar_email", return_value=(True, None)
        ) as mock_send,
    ):
        notificar_escalada_resposta_gerencial(
            chamado_data={"numero_chamado": "CHM-001"},
            chamado_id="ch1",
            nivel=1,
            email_dest="gestor@dtx.aero",
        )

    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs.get("importance") == "high"


def test_notificar_escalada_resolucao_importance_high(app):
    """notificar_escalada_resolucao_gerencial passa importance='high'."""
    from app.services.notifications import notificar_escalada_resolucao_gerencial

    with (
        app.app_context(),
        patch(
            "app.services.notifications_escalonamento.enviar_email", return_value=(True, None)
        ) as mock_send,
    ):
        notificar_escalada_resolucao_gerencial(
            chamado_data={"numero_chamado": "CHM-001"},
            chamado_id="ch1",
            nivel=1,
            email_dest="gestor@dtx.aero",
        )

    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs.get("importance") == "high"


def test_notificar_chamado_reaberto_importance_high(app):
    """notificar_supervisor_chamado_reaberto passa importance='high'."""
    from app.services.notifications import notificar_supervisor_chamado_reaberto

    responsavel = MagicMock()
    responsavel.email = "resp@dtx.aero"
    responsavel.nome = "Resp"

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", return_value=(True, None)) as mock_send,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        notificar_supervisor_chamado_reaberto(
            chamado_id="ch1",
            numero_chamado="CH-001",
            categoria="TI",
            motivo="Não resolveu",
            solicitante_nome="Sol",
            responsavel_usuario=responsavel,
        )

    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs.get("importance") == "high"


def test_notificar_transferencia_area_importance_high(app):
    """notificar_supervisor_transferencia_area passa importance='high'."""
    from app.services.notifications import notificar_supervisor_transferencia_area

    responsavel = MagicMock()
    responsavel.email = "resp@dtx.aero"

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", return_value=(True, None)) as mock_send,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        notificar_supervisor_transferencia_area(
            chamado_id="ch1",
            numero_chamado="CH-001",
            area="TI",
            categoria="Projetos",
            motivo="Motivo",
            responsavel_usuario=responsavel,
        )

    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs.get("importance") == "high"


def test_notificar_escalonamento_colega_importance_high(app):
    """notificar_supervisor_escalonamento_colega passa importance='high'."""
    from app.services.notifications import notificar_supervisor_escalonamento_colega

    responsavel = MagicMock()
    responsavel.email = "colega@dtx.aero"

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", return_value=(True, None)) as mock_send,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        notificar_supervisor_escalonamento_colega(
            chamado_id="ch1",
            numero_chamado="CH-001",
            area="TI",
            categoria="TI",
            motivo="Motivo",
            responsavel_usuario=responsavel,
        )

    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs.get("importance") == "high"


# ---------------------------------------------------------------------------
# Prefixo no assunto para Projetos/prioridade 0
# ---------------------------------------------------------------------------


def test_notificar_aprovador_projetos_assunto_tem_prefixo(app):
    """notificar_aprovador_novo_chamado com Projetos → assunto começa com 'Action required: '."""
    from app.services.notifications import notificar_aprovador_novo_chamado

    responsavel = type("Resp", (), {"email": "resp@dtx.aero"})()

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", return_value=(True, None)) as mock_send,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        notificar_aprovador_novo_chamado(
            chamado_id="ch1",
            numero_chamado="2026-100",
            categoria="Projetos",
            tipo_solicitacao="Nova",
            descricao_resumo="Resumo",
            area="Planejamento",
            solicitante_nome="Sol",
            responsavel_usuario=responsavel,
        )

    _, assunto, _, _ = mock_send.call_args[0]
    assert assunto.startswith("Action required: ")
    assert "2026-100" in assunto


def test_notificar_aprovador_padrao_assunto_sem_prefixo(app):
    """notificar_aprovador_novo_chamado chamado padrão → assunto sem 'Action required'."""
    from app.services.notifications import notificar_aprovador_novo_chamado

    responsavel = type("Resp", (), {"email": "resp@dtx.aero"})()

    with (
        app.app_context(),
        patch("app.services.notifications.enviar_email", return_value=(True, None)) as mock_send,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        notificar_aprovador_novo_chamado(
            chamado_id="ch2",
            numero_chamado="2026-101",
            categoria="Manutenção",
            tipo_solicitacao="Corretiva",
            descricao_resumo="Resumo",
            area="Manutencao",
            solicitante_nome="Sol",
            responsavel_usuario=responsavel,
        )

    _, assunto, _, _ = mock_send.call_args[0]
    assert not assunto.startswith("Action required: ")
    assert assunto == "New ticket assigned: 2026-101"
