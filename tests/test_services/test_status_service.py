"""Testes do serviço centralizado de atualização de status (status_service)."""

from unittest.mock import MagicMock, patch

from app.services.status_service import atualizar_status_chamado


def test_atualizar_status_chamado_nao_encontrado_retorna_erro():
    """Quando o chamado não existe no Firestore, retorna sucesso=False e erro 'Chamado não encontrado'."""
    mock_db = MagicMock()
    mock_doc = MagicMock()
    mock_doc.exists = False
    mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

    with patch("app.services.status_service.db", mock_db):
        resultado = atualizar_status_chamado(
            chamado_id="inexistente",
            novo_status="Em Atendimento",
            usuario_id="u1",
            usuario_nome="Test",
        )
    assert resultado["sucesso"] is False
    assert resultado["erro"] == "Chamado não encontrado"


def test_atualizar_status_chamado_com_data_chamado_atualiza_e_retorna_sucesso():
    """Com data_chamado informado, não busca no Firestore; atualiza e retorna sucesso."""
    mock_db = MagicMock()
    with (
        patch("app.services.status_service.db", mock_db),
        patch("app.services.status_service.execute_with_retry") as mock_retry,
        patch("app.services.status_service.Historico") as mock_hist,
        patch("app.services.status_service.notificar_solicitante_status"),
        patch("app.services.status_service.GamificationService") as mock_gamif,
    ):
        resultado = atualizar_status_chamado(
            chamado_id="ch1",
            novo_status="Concluído",
            usuario_id="u1",
            usuario_nome="Test",
            data_chamado={
                "status": "Em Atendimento",
                "solicitante_id": "sol1",
                "numero_chamado": "CHM-001",
                "categoria": "Manutenção",
            },
        )
    assert resultado["sucesso"] is True
    assert resultado["novo_status"] == "Concluído"
    assert "mensagem" in resultado
    mock_retry.assert_called_once()
    mock_hist.assert_called_once()
    mock_gamif.avaliar_resolucao_chamado.assert_called_once_with(
        "u1",
        {
            "status": "Em Atendimento",
            "solicitante_id": "sol1",
            "numero_chamado": "CHM-001",
            "categoria": "Manutenção",
        },
    )


def test_atualizar_status_chamado_mesmo_status_nao_chama_gamificacao():
    """Quando o status não muda (ex.: já era Concluído), não chama gamificação."""
    with (
        patch("app.services.status_service.execute_with_retry"),
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service.notificar_solicitante_status"),
        patch("app.services.status_service.GamificationService") as mock_gamif,
    ):
        resultado = atualizar_status_chamado(
            chamado_id="ch1",
            novo_status="Concluído",
            usuario_id="u1",
            usuario_nome="Test",
            data_chamado={
                "status": "Concluído",
                "solicitante_id": "sol1",
                "numero_chamado": "CHM-001",
                "categoria": "Manutenção",
            },
        )
    assert resultado["sucesso"] is True
    mock_gamif.avaliar_resolucao_chamado.assert_not_called()
    mock_gamif.avaliar_atendimento_inicial.assert_not_called()
