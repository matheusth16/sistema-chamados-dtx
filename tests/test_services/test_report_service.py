"""Testes para alertas de prazo e relatório semanal no report_service."""

from unittest.mock import MagicMock, patch

from app.services.report_service import enviar_alertas_prazo_24h

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_chamado_doc(numero="CH-001", status="Aberto", responsavel_id="sup1"):
    """Cria mock de Firestore doc para um chamado."""
    doc = MagicMock()
    doc.id = "doc_id_1"
    doc.to_dict.return_value = {
        "numero_chamado": numero,
        "status": status,
        "categoria": "Projetos",
        "tipo_solicitacao": "Manutenção",
        "area": "Manutenção",
        "responsavel": "Supervisor",
        "responsavel_id": responsavel_id,
        "solicitante_nome": "Solicitante",
        "data_abertura": None,
        "data_conclusao": None,
        "data_cancelamento": None,
        "sla_dias": None,
        "alerta_prazo_24h_enviado_em": None,
    }
    return doc


def _make_usuario(email="sup@test.com", nome="Supervisor", perfil="supervisor"):
    u = MagicMock()
    u.email = email
    u.nome = nome
    u.perfil = perfil
    return u


def test_alerta_24h_nao_reenvia_quando_ja_marcado():
    """Chamado já marcado com alerta enviado deve ser ignorado."""
    chamado_marcado = {
        "id": "c1",
        "numero": "2026-001",
        "sla_label": "Em risco",
        "responsavel_id": "sup1",
        "alerta_prazo_24h_enviado_em": "2026-03-19T10:00:00Z",
    }
    with (
        patch(
            "app.services.report_service.buscar_chamados_abertos",
            return_value=[chamado_marcado],
        ),
        patch("app.services.report_service.notificar_responsavel_prazo_24h") as mock_notificar,
    ):
        resultado = enviar_alertas_prazo_24h()

    assert resultado["elegiveis"] == 0
    assert resultado["enviados"] == 0
    mock_notificar.assert_not_called()


def test_alerta_24h_marca_chamado_apos_envio():
    """Após envio do alerta 24h, deve marcar o chamado para evitar duplicidade."""
    chamado = {
        "id": "c2",
        "numero": "2026-002",
        "categoria": "Projetos",
        "tipo": "Manutencao",
        "area": "Manutencao",
        "solicitante": "Solicitante",
        "sla_label": "Em risco",
        "responsavel_id": "sup2",
        "alerta_prazo_24h_enviado_em": None,
    }
    usuario = MagicMock()
    usuario.email = "sup2@dtx.aero"

    with (
        patch("app.services.report_service.buscar_chamados_abertos", return_value=[chamado]),
        patch("app.services.report_service.Usuario.get_by_id", return_value=usuario),
        patch("app.services.report_service.notificar_responsavel_prazo_24h") as mock_notificar,
        patch("app.services.report_service.db") as mock_db,
    ):
        resultado = enviar_alertas_prazo_24h()

    assert resultado["elegiveis"] == 1
    assert resultado["enviados"] == 1
    mock_notificar.assert_called_once()
    mock_db.collection.assert_called_once_with("chamados")


# ── buscar_chamados_abertos ───────────────────────────────────────────────────


def test_buscar_chamados_abertos_retorna_lista():
    """buscar_chamados_abertos retorna lista de dicts enriquecidos."""
    from app.services.report_service import buscar_chamados_abertos

    doc = _make_chamado_doc()
    mock_db = MagicMock()
    mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = [
        doc
    ]

    with (
        patch("app.services.report_service.db", mock_db),
        patch(
            "app.services.report_service.Chamado.from_dict",
            return_value=MagicMock(
                numero_chamado="CH-001",
                categoria="Projetos",
                tipo_solicitacao="Manutenção",
                area="Manutenção",
                responsavel="Supervisor",
                responsavel_id="sup1",
                solicitante_nome="Solicitante",
                status="Aberto",
                data_abertura=None,
                sla_dias=None,
            ),
        ),
        patch("app.services.report_service.obter_sla_para_exibicao", return_value={"label": "Ok"}),
    ):
        result = buscar_chamados_abertos()

    assert isinstance(result, list)
    assert len(result) >= 1
    assert result[0]["numero"] == "CH-001"


def test_buscar_chamados_abertos_retorna_vazio_sem_docs():
    """buscar_chamados_abertos retorna [] quando não há chamados."""
    from app.services.report_service import buscar_chamados_abertos

    mock_db = MagicMock()
    mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = []

    with patch("app.services.report_service.db", mock_db):
        result = buscar_chamados_abertos()

    assert result == []


def test_buscar_chamados_abertos_tolera_excecao():
    """buscar_chamados_abertos retorna [] parcial se Firestore lançar exceção."""
    from app.services.report_service import buscar_chamados_abertos

    mock_db = MagicMock()
    mock_db.collection.return_value.where.return_value.limit.return_value.stream.side_effect = (
        Exception("Firestore error")
    )

    with patch("app.services.report_service.db", mock_db):
        result = buscar_chamados_abertos()

    assert isinstance(result, list)


# ── enviar_relatorio_semanal ──────────────────────────────────────────────────


def test_enviar_relatorio_semanal_sem_chamados_retorna_zeros(app):
    """Com zero chamados abertos, retorna zeros sem enviar e-mail."""
    from app.services.report_service import enviar_relatorio_semanal

    with (
        app.app_context(),
        patch("app.services.report_service.buscar_chamados_abertos", return_value=[]),
        patch("app.services.report_service.enviar_email") as mock_send,
    ):
        resultado = enviar_relatorio_semanal()

    assert resultado["enviados"] == 0
    assert resultado["total_chamados"] == 0
    mock_send.assert_not_called()


def test_enviar_relatorio_semanal_envia_para_supervisor(app):
    """Com chamados atribuídos, envia e-mail diretamente para o supervisor."""
    from app.services.report_service import enviar_relatorio_semanal

    chamados = [
        {
            "id": "c1",
            "numero": "CH-001",
            "categoria": "Projetos",
            "tipo": "Manutenção",
            "area": "Manutenção",
            "responsavel": "Supervisor",
            "responsavel_id": "sup1",
            "solicitante": "Solicitante",
            "status": "Aberto",
            "data_abertura_fmt": "01/01/2026",
            "dias_aberto": 5,
            "sla_label": "Ok",
            "atrasado": False,
            "sla_dias": 3,
            "alerta_prazo_24h_enviado_em": None,
        }
    ]
    supervisor = _make_usuario("sup@test.com", "Supervisor", "supervisor")

    with (
        app.app_context(),
        patch("app.services.report_service.buscar_chamados_abertos", return_value=chamados),
        patch("app.services.report_service.Usuario.get_by_id", return_value=supervisor),
        patch("app.services.report_service.Usuario.get_all", return_value=[]),
        patch("app.services.report_service.enviar_email", return_value=(True, None)) as mock_send,
    ):
        resultado = enviar_relatorio_semanal()

    assert resultado["enviados"] == 1
    assert resultado["total_chamados"] == 1
    assert mock_send.called
    destinatario = mock_send.call_args[0][0]
    assert destinatario == "sup@test.com"


def test_enviar_relatorio_semanal_ignora_sem_responsavel(app):
    """Chamados sem responsavel_id são ignorados (não geram e-mail)."""
    from app.services.report_service import enviar_relatorio_semanal

    chamados = [
        {
            "id": "c2",
            "numero": "CH-002",
            "categoria": "Projetos",
            "tipo": "Manutenção",
            "area": "Manutenção",
            "responsavel": "",
            "responsavel_id": "",
            "solicitante": "Solicitante",
            "status": "Aberto",
            "data_abertura_fmt": "01/01/2026",
            "dias_aberto": 5,
            "sla_label": "Ok",
            "atrasado": False,
            "sla_dias": None,
            "alerta_prazo_24h_enviado_em": None,
        }
    ]

    with (
        app.app_context(),
        patch("app.services.report_service.buscar_chamados_abertos", return_value=chamados),
        patch("app.services.report_service.Usuario.get_all", return_value=[]),
        patch("app.services.report_service.enviar_email", return_value=(True, None)) as mock_send,
    ):
        resultado = enviar_relatorio_semanal()

    assert resultado["ignorados"] >= 1
    mock_send.assert_not_called()


def test_enviar_relatorio_semanal_envia_para_admin(app):
    """Admins recebem resumo consolidado diretamente via Graph API."""
    from app.services.report_service import enviar_relatorio_semanal

    chamados = [
        {
            "id": "c3",
            "numero": "CH-003",
            "categoria": "TI",
            "tipo": "Suporte",
            "area": "TI",
            "responsavel": "Supervisor",
            "responsavel_id": "sup2",
            "solicitante": "Req",
            "status": "Em Atendimento",
            "data_abertura_fmt": "01/01/2026",
            "dias_aberto": 2,
            "sla_label": "Atrasado",
            "atrasado": True,
            "sla_dias": 3,
            "alerta_prazo_24h_enviado_em": None,
        }
    ]
    supervisor = _make_usuario("sup2@test.com", "Sup2", "supervisor")
    admin = _make_usuario("admin@test.com", "Admin", "admin")

    with (
        app.app_context(),
        patch("app.services.report_service.buscar_chamados_abertos", return_value=chamados),
        patch("app.services.report_service.Usuario.get_by_id", return_value=supervisor),
        patch("app.services.report_service.Usuario.get_all", return_value=[admin]),
        patch("app.services.report_service.enviar_email", return_value=(True, None)) as mock_send,
    ):
        resultado = enviar_relatorio_semanal()

    assert resultado["total_atrasados"] == 1
    assert mock_send.call_count >= 2
    destinos = [call[0][0] for call in mock_send.call_args_list]
    assert "sup2@test.com" in destinos
    assert "admin@test.com" in destinos
