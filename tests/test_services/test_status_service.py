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


def test_conclusao_reseta_flags_lembrete():
    """Ao ir para Concluído, flags de lembrete devem ser zeradas para novo ciclo de envio."""
    with (
        patch("app.services.status_service.execute_with_retry") as mock_retry,
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
    ):
        resultado = atualizar_status_chamado(
            chamado_id="ch1",
            novo_status="Concluído",
            usuario_id="u1",
            usuario_nome="Test",
            data_chamado={
                "status": "Em Atendimento",
                "lembrete_confirmacao_1_enviado": True,
                "lembrete_confirmacao_2_enviado": True,
                "solicitante_id": "sol1",
                "participantes": [],
            },
        )
    assert resultado["sucesso"] is True
    update_data = mock_retry.call_args[0][1]
    assert update_data.get("lembrete_confirmacao_1_enviado") is False
    assert update_data.get("lembrete_confirmacao_2_enviado") is False


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


def test_saindo_de_concluido_para_aberto_reseta_confirmacao_solicitante():
    """Regressão: Concluído → Aberto (reabertura) limpa confirmacao_solicitante=None."""
    with (
        patch("app.services.status_service.execute_with_retry") as mock_retry,
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
    ):
        resultado = atualizar_status_chamado(
            chamado_id="ch1",
            novo_status="Aberto",
            usuario_id="u1",
            usuario_nome="Test",
            data_chamado={
                "status": "Concluído",
                "confirmacao_solicitante": "pendente",
                "solicitante_id": "s1",
            },
        )

    assert resultado["sucesso"] is True
    update_payload = mock_retry.call_args[0][1]
    assert update_payload.get("confirmacao_solicitante") is None


def test_concluido_para_em_atendimento_transicao_invalida():
    """Concluído → Em Atendimento deve ser transição inválida (TRANSICOES_VALIDAS)."""
    resultado = atualizar_status_chamado(
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
    assert resultado["sucesso"] is False
    assert "inválida" in resultado.get("erro", "").lower() or "Concluído" in resultado.get(
        "erro", ""
    )


def test_reabertura_admin_grava_historico_com_motivo():
    """Concluído → Aberto com motivo_reabertura grava entrada de reabertura no histórico."""
    with (
        patch("app.services.status_service.execute_with_retry"),
        patch("app.services.status_service.Historico") as mock_hist,
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
    ):
        resultado = atualizar_status_chamado(
            chamado_id="ch1",
            novo_status="Aberto",
            usuario_id="admin1",
            usuario_nome="Admin",
            data_chamado={
                "status": "Concluído",
                "confirmacao_solicitante": "confirmado",
                "solicitante_id": "s1",
            },
            motivo_reabertura="Problema recorrente identificado",
        )
    assert resultado["sucesso"] is True
    # histórico: alteracao_status + reabertura (2 chamadas)
    assert mock_hist.call_count >= 2
    acoes = [call.kwargs.get("acao") for call in mock_hist.call_args_list]
    assert "reabertura" in acoes


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
            "Em Atendimento",
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
            "Em Atendimento",
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
        patch("app.services.status_service.notificar_solicitante_confirmacao_pendente"),
        patch("app.services.webpush_service.enviar_webpush_usuario"),
        patch("app.services.notifications_inapp.criar_notificacao_solicitante"),
    ):
        _notificar_solicitante("ch1", {"solicitante_id": "s1"}, "Concluído")


# ── F-63: Validação de transição de status ─────────────────────────────────────


def test_atualizar_status_transicao_concluido_para_aberto_valida():
    """Concluído → Aberto é transição válida (reabertura administrativa)."""
    with (
        patch("app.services.status_service.execute_with_retry"),
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
    ):
        resultado = atualizar_status_chamado(
            chamado_id="ch1",
            novo_status="Aberto",
            usuario_id="u1",
            usuario_nome="Test",
            data_chamado={"status": "Concluído", "solicitante_id": "s1"},
        )
    assert resultado["sucesso"] is True


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
    """F-63: fluxo principal deve ser permitido; Concluído → Em Atendimento é inválido."""
    for status_ant, status_novo in [
        ("Aberto", "Em Atendimento"),
        ("Em Atendimento", "Concluído"),
        ("Concluído", "Aberto"),
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


# ---------------------------------------------------------------------------
# Fase 2 — Claim ao Em Atendimento + data_em_atendimento
# ---------------------------------------------------------------------------


def _patch_status_service(**extras):
    """Context manager helper: patches comuns ao status_service para testes de claim."""
    from contextlib import ExitStack
    from unittest.mock import patch

    stack = ExitStack()
    patches = {
        "execute_with_retry": stack.enter_context(
            patch("app.services.status_service.execute_with_retry")
        ),
        "Historico": stack.enter_context(patch("app.services.status_service.Historico")),
        "notif": stack.enter_context(patch("app.services.status_service._notificar_solicitante")),
        "gamif": stack.enter_context(patch("app.services.status_service.GamificationService")),
        "calc_ids": stack.enter_context(
            patch(
                "app.services.status_service.calcular_supervisor_ids_com_acesso",
                return_value=["id_julia"],
            )
        ),
    }
    patches.update(extras)
    return stack, patches


def test_claim_atribui_owner_ao_em_atendimento():
    """Aberto sem owner → Em Atendimento atribui responsavel_id ao usuário logado."""
    with (
        patch("app.services.status_service.execute_with_retry") as mock_retry,
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
        patch(
            "app.services.status_service.calcular_supervisor_ids_com_acesso",
            return_value=["id_julia"],
        ),
    ):
        resultado = atualizar_status_chamado(
            chamado_id="id_chamado",
            novo_status="Em Atendimento",
            usuario_id="id_julia",
            usuario_nome="Júlia",
            data_chamado={
                "status": "Aberto",
                "responsavel_id": None,
                "area": "Engenharia",
                "participantes": [],
                "solicitante_id": "sol1",
                "numero_chamado": "CHM-001",
                "categoria": "Manutenção",
                "escalacao_resposta_nivel": 0,
            },
        )
    assert resultado["sucesso"] is True
    update_data = mock_retry.call_args[0][1]
    assert update_data["responsavel_id"] == "id_julia"
    assert update_data["data_em_atendimento"] is not None


def test_claim_nao_sobrescreve_owner_existente():
    """Aberto já com owner → Em Atendimento NÃO muda responsavel_id."""
    with (
        patch("app.services.status_service.execute_with_retry") as mock_retry,
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
        patch(
            "app.services.status_service.calcular_supervisor_ids_com_acesso",
            return_value=["id_julia"],
        ),
    ):
        atualizar_status_chamado(
            chamado_id="id_chamado",
            novo_status="Em Atendimento",
            usuario_id="id_matheus",
            usuario_nome="Matheus",
            data_chamado={
                "status": "Aberto",
                "responsavel_id": "id_julia",
                "area": "Engenharia",
                "participantes": [],
                "solicitante_id": "sol1",
                "numero_chamado": "CHM-001",
                "categoria": "Manutenção",
                "escalacao_resposta_nivel": 0,
            },
        )
    update_data = mock_retry.call_args[0][1]
    # responsavel_id não deve ser sobrescrito — não deve aparecer no update como id_matheus
    assert update_data.get("responsavel_id") != "id_matheus"


def test_escada_a_congelada_ao_virar_em_atendimento():
    """Nível de escalação Escada A não deve ser incrementado ao virar Em Atendimento."""
    with (
        patch("app.services.status_service.execute_with_retry") as mock_retry,
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
        patch(
            "app.services.status_service.calcular_supervisor_ids_com_acesso",
            return_value=["id_julia"],
        ),
    ):
        atualizar_status_chamado(
            chamado_id="id_chamado",
            novo_status="Em Atendimento",
            usuario_id="id_julia",
            usuario_nome="Júlia",
            data_chamado={
                "status": "Aberto",
                "responsavel_id": None,
                "area": "Engenharia",
                "participantes": [],
                "solicitante_id": "sol1",
                "numero_chamado": "CHM-001",
                "categoria": "Manutenção",
                "escalacao_resposta_nivel": 2,
            },
        )
    update_data = mock_retry.call_args[0][1]
    # O nível não deve ter sido incrementado — Escada A congela em Em Atendimento
    assert update_data.get("escalacao_resposta_nivel", 2) == 2


def test_claim_atualiza_responsavel_nome():
    """Lacuna 5: claim (Aberto→Em Atendimento sem owner) deve incluir 'responsavel' no update_data."""
    with (
        patch("app.services.status_service.execute_with_retry") as mock_retry,
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
        patch(
            "app.services.status_service.calcular_supervisor_ids_com_acesso",
            return_value=["id_julia"],
        ),
    ):
        atualizar_status_chamado(
            chamado_id="id_chamado",
            novo_status="Em Atendimento",
            usuario_id="id_julia",
            usuario_nome="Júlia Ferreira",
            data_chamado={
                "status": "Aberto",
                "responsavel_id": None,
                "area": "Engenharia",
                "participantes": [],
                "solicitante_id": "sol1",
                "numero_chamado": "CHM-001",
                "categoria": "Manutenção",
                "escalacao_resposta_nivel": 0,
            },
        )
    update_data = mock_retry.call_args[0][1]
    assert update_data.get("responsavel") == "Júlia Ferreira"


# ── Fase 4: bloqueio de conclusão com participantes pendentes ─────────────────


def test_owner_nao_conclui_com_participantes_pendentes():
    """Fase 4: atualizar_status Concluído falha quando há participantes pendentes."""
    resultado = atualizar_status_chamado(
        chamado_id="ch1",
        novo_status="Concluído",
        usuario_id="id_julia",
        usuario_nome="Julia",
        data_chamado={
            "status": "Em Atendimento",
            "solicitante_id": "sol1",
            "participantes": [
                {
                    "supervisor_id": "id_pedro",
                    "area": "Logistica",
                    "status": "pendente",
                    "concluido_em": None,
                }
            ],
        },
    )
    assert resultado["sucesso"] is False
    assert "participante" in resultado["erro"].lower()


def test_owner_nao_conclui_com_participante_em_atendimento():
    """Fase 4: participante em_atendimento também bloqueia conclusão global."""
    resultado = atualizar_status_chamado(
        chamado_id="ch1",
        novo_status="Concluído",
        usuario_id="id_julia",
        usuario_nome="Julia",
        data_chamado={
            "status": "Em Atendimento",
            "solicitante_id": "sol1",
            "participantes": [
                {
                    "supervisor_id": "id_pedro",
                    "area": "Logistica",
                    "status": "em_atendimento",
                    "concluido_em": None,
                }
            ],
        },
    )
    assert resultado["sucesso"] is False


def test_owner_conclui_quando_todos_participantes_concluidos():
    """Fase 4: permite Concluído quando todos participantes têm status='concluido'."""
    with (
        patch("app.services.status_service.execute_with_retry"),
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
    ):
        resultado = atualizar_status_chamado(
            chamado_id="ch1",
            novo_status="Concluído",
            usuario_id="id_julia",
            usuario_nome="Julia",
            data_chamado={
                "status": "Em Atendimento",
                "solicitante_id": "sol1",
                "participantes": [
                    {
                        "supervisor_id": "id_pedro",
                        "area": "L",
                        "status": "concluido",
                        "concluido_em": "x",
                    }
                ],
            },
        )
    assert resultado["sucesso"] is True


def test_concluir_global_sem_participantes_continua_funcionando():
    """Fase 4 regressão: lista vazia de participantes não bloqueia conclusão."""
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
            data_chamado={
                "status": "Em Atendimento",
                "solicitante_id": "sol1",
                "participantes": [],
            },
        )
    assert resultado["sucesso"] is True


def test_concluido_grava_confirmacao_solicitante_pendente():
    """Fase 4 regressão: ao Concluído (sem participantes pendentes), grava confirmacao_solicitante='pendente'."""
    with (
        patch("app.services.status_service.execute_with_retry") as mock_retry,
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
    ):
        atualizar_status_chamado(
            chamado_id="ch1",
            novo_status="Concluído",
            usuario_id="u1",
            usuario_nome="Test",
            data_chamado={
                "status": "Em Atendimento",
                "solicitante_id": "sol1",
                "participantes": [],
            },
        )
    update_payload = mock_retry.call_args[0][1]
    assert update_payload.get("confirmacao_solicitante") == "pendente"


def test_claim_reseta_flags_escada_b():
    """Fase 7 — Escada B: ao Aberto → Em Atendimento (claim), resetar os 3 campos Escada B."""
    with (
        patch("app.services.status_service.execute_with_retry") as mock_retry,
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
        patch(
            "app.services.status_service.calcular_supervisor_ids_com_acesso",
            return_value=["id_julia"],
        ),
    ):
        atualizar_status_chamado(
            chamado_id="id_chamado",
            novo_status="Em Atendimento",
            usuario_id="id_julia",
            usuario_nome="Júlia",
            data_chamado={
                "status": "Aberto",
                "responsavel_id": None,
                "area": "Engenharia",
                "participantes": [],
                "solicitante_id": "sol1",
                "numero_chamado": "CHM-001",
                "categoria": "Manutenção",
                # Simula chamado que tinha escalada prévia
                "escalacao_resolucao_nivel": 2,
                "alerta_supervisor_50_enviado": True,
                "alerta_supervisor_80_enviado": True,
            },
        )
    update_data = mock_retry.call_args[0][1]
    assert update_data.get("escalacao_resolucao_nivel") == 0
    assert update_data.get("alerta_supervisor_50_enviado") is False
    assert update_data.get("alerta_supervisor_80_enviado") is False


def test_claim_data_em_atendimento_usa_config_sla_timezone():
    """Lacuna 6: claim deve usar Config.SLA_TIMEZONE, não timezone hardcoded."""
    with (
        patch("app.services.status_service.Config") as mock_config,
        patch("app.services.status_service.execute_with_retry") as mock_retry,
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
        patch(
            "app.services.status_service.calcular_supervisor_ids_com_acesso",
            return_value=[],
        ),
    ):
        mock_config.SLA_TIMEZONE = "UTC"
        atualizar_status_chamado(
            chamado_id="id_chamado",
            novo_status="Em Atendimento",
            usuario_id="id_user",
            usuario_nome="User",
            data_chamado={
                "status": "Aberto",
                "responsavel_id": None,
                "area": "Engenharia",
                "participantes": [],
                "solicitante_id": "sol1",
                "numero_chamado": "CHM-001",
                "categoria": "Manutenção",
            },
        )
    update_data = mock_retry.call_args[0][1]
    dt = update_data.get("data_em_atendimento")
    assert dt is not None
    assert dt.tzname() == "UTC"


# ── Notificação in-app ao solicitante ─────────────────────────────────────────


def test_notificar_solicitante_em_atendimento_cria_notificacao_inapp(app):
    """_notificar_solicitante para 'Em Atendimento' chama criar_notificacao_solicitante com tipo correto."""
    with (
        app.app_context(),
        patch("app.services.status_service.Usuario.get_by_id", return_value=MagicMock()),
        patch("app.services.status_service.notificar_solicitante_status"),
        patch("app.services.webpush_service.enviar_webpush_usuario"),
        patch("app.services.notifications_inapp.criar_notificacao_solicitante") as mock_inapp,
    ):
        from app.services.status_service import _notificar_solicitante

        _notificar_solicitante(
            "ch1",
            {
                "solicitante_id": "sol1",
                "numero_chamado": "CHM-001",
                "categoria": "TI",
            },
            "Em Atendimento",
        )

    mock_inapp.assert_called_once()
    call_kwargs = mock_inapp.call_args.kwargs
    assert call_kwargs["tipo"] == "status_em_atendimento"
    assert call_kwargs["solicitante_id"] == "sol1"


def test_notificar_solicitante_concluido_cria_notificacao_inapp(app):
    """_notificar_solicitante para 'Concluído' chama criar_notificacao_solicitante com tipo correto."""
    with (
        app.app_context(),
        patch("app.services.status_service.Usuario.get_by_id", return_value=MagicMock()),
        patch("app.services.status_service.notificar_solicitante_confirmacao_pendente"),
        patch("app.services.webpush_service.enviar_webpush_usuario"),
        patch("app.services.notifications_inapp.criar_notificacao_solicitante") as mock_inapp,
    ):
        from app.services.status_service import _notificar_solicitante

        _notificar_solicitante(
            "ch1",
            {
                "solicitante_id": "sol1",
                "numero_chamado": "CHM-001",
                "categoria": "TI",
            },
            "Concluído",
        )

    mock_inapp.assert_called_once()
    call_kwargs = mock_inapp.call_args.kwargs
    assert call_kwargs["tipo"] == "status_concluido_confirmar"
    assert call_kwargs["solicitante_id"] == "sol1"


def test_notificar_solicitante_inapp_falha_nao_propaga(app):
    """Falha ao criar notificação in-app não propaga exceção (log warning apenas)."""
    with (
        app.app_context(),
        patch("app.services.status_service.Usuario.get_by_id", return_value=MagicMock()),
        patch("app.services.status_service.notificar_solicitante_status"),
        patch("app.services.webpush_service.enviar_webpush_usuario"),
        patch(
            "app.services.notifications_inapp.criar_notificacao_solicitante",
            side_effect=Exception("Firestore down"),
        ),
    ):
        from app.services.status_service import _notificar_solicitante

        # Não deve lançar exceção
        _notificar_solicitante(
            "ch1",
            {
                "solicitante_id": "sol1",
                "numero_chamado": "CHM-001",
                "categoria": "TI",
            },
            "Em Atendimento",
        )


def test_notificar_solicitante_sem_sid_nao_cria_inapp(app):
    """_notificar_solicitante sem solicitante_id NÃO chama criar_notificacao_solicitante."""
    with (
        app.app_context(),
        patch("app.services.status_service.notificar_solicitante_status"),
        patch("app.services.webpush_service.enviar_webpush_usuario"),
        patch("app.services.notifications_inapp.criar_notificacao_solicitante") as mock_inapp,
    ):
        from app.services.status_service import _notificar_solicitante

        _notificar_solicitante(
            "ch1",
            {
                "solicitante_id": None,
                "numero_chamado": "CHM-001",
                "categoria": "TI",
            },
            "Em Atendimento",
        )

    mock_inapp.assert_not_called()
