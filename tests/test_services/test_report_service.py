"""Testes para alertas de prazo no report_service."""

from unittest.mock import MagicMock, patch

from app.services.report_service import enviar_alertas_prazo_24h


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
