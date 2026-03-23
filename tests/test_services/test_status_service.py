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


def test_atualizar_status_invalido_retorna_erro():
    """Status inválido retorna sucesso=False com mensagem de erro."""
    resultado = atualizar_status_chamado(
        chamado_id="ch1",
        novo_status="StatusInexistente",
        usuario_id="u1",
        usuario_nome="Test",
        data_chamado={"status": "Aberto"},
    )
    assert resultado["sucesso"] is False
    assert "inválido" in resultado["erro"].lower() or "StatusInexistente" in resultado["erro"]


def test_atualizar_cancelado_sem_motivo_retorna_erro():
    """Cancelado sem motivo retorna sucesso=False."""
    resultado = atualizar_status_chamado(
        chamado_id="ch1",
        novo_status="Cancelado",
        usuario_id="u1",
        usuario_nome="Test",
        data_chamado={"status": "Aberto"},
        motivo_cancelamento="",
    )
    assert resultado["sucesso"] is False
    assert "motivo" in resultado["erro"].lower() or "cancelamento" in resultado["erro"].lower()


def test_atualizar_cancelado_com_motivo_retorna_sucesso():
    """Cancelado com motivo atualiza status e registra histórico do motivo."""
    with (
        patch("app.services.status_service.execute_with_retry"),
        patch("app.services.status_service.Historico") as mock_hist,
        patch("app.services.status_service.GamificationService"),
    ):
        resultado = atualizar_status_chamado(
            chamado_id="ch1",
            novo_status="Cancelado",
            usuario_id="u1",
            usuario_nome="Test",
            data_chamado={"status": "Aberto", "solicitante_id": "s1"},
            motivo_cancelamento="Não é mais necessário",
        )
    assert resultado["sucesso"] is True
    # Deve ter registrado histórico duas vezes: status + motivo
    assert mock_hist.call_count == 2


def test_atualizar_em_atendimento_chama_gamificacao_inicial():
    """Em Atendimento chama GamificationService.avaliar_atendimento_inicial."""
    with (
        patch("app.services.status_service.execute_with_retry"),
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service.notificar_solicitante_status"),
        patch("app.services.status_service.GamificationService") as mock_gamif,
    ):
        resultado = atualizar_status_chamado(
            chamado_id="ch1",
            novo_status="Em Atendimento",
            usuario_id="u1",
            usuario_nome="Test",
            data_chamado={"status": "Aberto", "solicitante_id": "s1"},
        )
    assert resultado["sucesso"] is True
    mock_gamif.avaliar_atendimento_inicial.assert_called_once_with("u1")


def test_atualizar_status_excecao_retorna_falso():
    """Exceção durante execute_with_retry retorna sucesso=False."""
    with patch(
        "app.services.status_service.execute_with_retry", side_effect=Exception("db timeout")
    ):
        resultado = atualizar_status_chamado(
            chamado_id="ch1",
            novo_status="Aberto",
            usuario_id="u1",
            usuario_nome="Test",
            data_chamado={"status": "Em Atendimento"},
        )
    assert resultado["sucesso"] is False
    assert "erro" in resultado
