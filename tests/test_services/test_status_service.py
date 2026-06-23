"""Testes do serviço centralizado de atualização de status (status_service)."""

from unittest.mock import MagicMock, patch

from app.services.status_service import _notificar_solicitante, atualizar_status_chamado


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
        patch("app.services.status_service._notificar_solicitante"),
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
        patch("app.services.status_service._notificar_solicitante"),
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
        patch("app.services.status_service._notificar_solicitante"),
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
        patch("app.services.status_service._notificar_solicitante"),
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


def test_saindo_de_concluido_reseta_confirmacao_solicitante():
    """Regressão: transição de 'Concluído' para outro status limpa confirmacao_solicitante=None.

    Evita que flag residual 'pendente' mostre bloco de confirmação ao solicitante
    mesmo após o supervisor ter reaberto o chamado manualmente.
    """
    with (
        patch("app.services.status_service.execute_with_retry") as mock_retry,
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
    ):
        atualizar_status_chamado(
            chamado_id="ch1",
            novo_status="Em Atendimento",
            usuario_id="u1",
            usuario_nome="Test",
            data_chamado={
                "status": "Concluído",
                "confirmacao_solicitante": "pendente",
                "solicitante_id": "s1",
            },
        )

    update_payload = mock_retry.call_args[0][1]
    assert update_payload.get("confirmacao_solicitante") is None


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


def test_busca_chamado_no_firestore_quando_data_nao_fornecida():
    """Quando data_chamado=None e doc.exists=True, chama doc.to_dict() para obter os dados."""
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {
        "status": "Aberto",
        "solicitante_id": "s1",
        "numero_chamado": "CHM-001",
        "categoria": "TI",
    }
    with (
        patch("app.services.status_service.db") as mock_db,
        patch("app.services.status_service.execute_with_retry"),
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        resultado = atualizar_status_chamado(
            chamado_id="ch1",
            novo_status="Concluído",
            usuario_id="u1",
            usuario_nome="Test",
        )
    assert resultado["sucesso"] is True
    mock_doc.to_dict.assert_called_once()


def test_threading_notificacao_lanca_thread_com_app_context(app):
    """Dentro de app_context, a notificação inicia um Thread daemon e executa o closure."""
    notif_closure_calls = []

    def fake_thread(target, daemon=True):
        notif_closure_calls.append(target)
        mock = MagicMock()
        mock.start = lambda: None
        return mock

    with (
        patch("app.services.status_service.execute_with_retry"),
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service.GamificationService"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.threading.Thread", side_effect=fake_thread),
        app.app_context(),
    ):
        atualizar_status_chamado(
            chamado_id="ch1",
            novo_status="Em Atendimento",
            usuario_id="u1",
            usuario_nome="Test",
            data_chamado={"status": "Aberto", "solicitante_id": "s1"},
        )

    assert len(notif_closure_calls) == 1
    # Execute the closure to cover lines inside _notif()
    with patch("app.services.status_service._notificar_solicitante"):
        notif_closure_calls[0]()


def test_notificar_solicitante_com_sid_envia_notificacao_e_webpush(app):
    """_notificar_solicitante com solicitante_id chama notificar_solicitante_status e webpush."""
    with (
        app.app_context(),
        patch("app.services.status_service.Usuario.get_by_id", return_value=MagicMock()),
        patch("app.services.status_service.notificar_solicitante_status") as mock_notif,
        patch("app.services.webpush_service.enviar_webpush_usuario") as mock_webpush,
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        _notificar_solicitante(
            "ch1",
            {"solicitante_id": "s1", "numero_chamado": "CHM-001", "categoria": "TI"},
            "Concluído",
        )
    mock_notif.assert_called_once()
    mock_webpush.assert_called_once()


def test_notificar_solicitante_sem_sid_nao_envia_webpush(app):
    """_notificar_solicitante sem solicitante_id chama notificar_solicitante_status mas não webpush."""
    with (
        app.app_context(),
        patch("app.services.status_service.notificar_solicitante_status") as mock_notif,
        patch("app.services.webpush_service.enviar_webpush_usuario") as mock_webpush,
    ):
        _notificar_solicitante(
            "ch1",
            {"solicitante_id": None, "numero_chamado": "CHM-001", "categoria": "TI"},
            "Concluído",
        )
    mock_notif.assert_called_once()
    mock_webpush.assert_not_called()


def test_notificar_solicitante_excecao_nao_propaga(app):
    """_notificar_solicitante captura exceções internas sem propagar."""
    with (
        app.app_context(),
        patch("app.services.status_service.Usuario.get_by_id", return_value=MagicMock()),
        patch(
            "app.services.status_service.notificar_solicitante_status",
            side_effect=Exception("smtp error"),
        ),
    ):
        _notificar_solicitante("ch1", {"solicitante_id": "s1"}, "Concluído")


# ── F-63: Validação de transição de status ─────────────────────────────────────


def test_atualizar_status_transicao_invalida_concluido_para_aberto():
    """F-63: Concluído → Aberto é transição inválida — retorna sucesso=False."""
    resultado = atualizar_status_chamado(
        chamado_id="ch1",
        novo_status="Aberto",
        usuario_id="u1",
        usuario_nome="Test",
        data_chamado={"status": "Concluído"},
    )
    assert resultado["sucesso"] is False
    assert (
        "transição" in resultado.get("erro", "").lower()
        or "inválid" in resultado.get("erro", "").lower()
    )


def test_atualizar_status_mesmo_status_nao_rejeita_transicao():
    """F-63: Transição de um status para ele mesmo deve ser permitida."""
    with (
        patch("app.services.status_service.execute_with_retry"),
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
    ):
        resultado = atualizar_status_chamado(
            chamado_id="ch1",
            novo_status="Concluído",
            usuario_id="u1",
            usuario_nome="Test",
            data_chamado={"status": "Concluído", "solicitante_id": "s1"},
        )
    assert resultado["sucesso"] is True


def test_atualizar_status_sem_status_anterior_nao_rejeita():
    """F-63: Sem status_anterior (campo ausente), transição não é bloqueada."""
    with (
        patch("app.services.status_service.execute_with_retry"),
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
    ):
        resultado = atualizar_status_chamado(
            chamado_id="ch1",
            novo_status="Em Atendimento",
            usuario_id="u1",
            usuario_nome="Test",
            data_chamado={"solicitante_id": "s1"},
        )
    assert resultado["sucesso"] is True


def test_transicoes_validas_permite_fluxo_normal():
    """F-63: Aberto → Em Atendimento → Concluído deve ser permitido."""
    for status_ant, status_novo in [
        ("Aberto", "Em Atendimento"),
        ("Em Atendimento", "Concluído"),
        ("Concluído", "Em Atendimento"),
        ("Aberto", "Cancelado"),
    ]:
        with (
            patch("app.services.status_service.execute_with_retry"),
            patch("app.services.status_service.Historico"),
            patch("app.services.status_service._notificar_solicitante"),
            patch("app.services.status_service.GamificationService"),
        ):
            r = atualizar_status_chamado(
                chamado_id="ch1",
                novo_status=status_novo,
                usuario_id="u1",
                usuario_nome="Test",
                data_chamado={"status": status_ant, "solicitante_id": "s1"},
                motivo_cancelamento="motivo" if status_novo == "Cancelado" else None,
            )
        assert r["sucesso"] is True, f"Transição {status_ant} → {status_novo} deveria ser permitida"
