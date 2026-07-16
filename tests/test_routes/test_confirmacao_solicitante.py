"""Testes da funcionalidade de confirmação de resolução pelo solicitante."""

from unittest.mock import MagicMock, patch


def _doc_chamado(
    solicitante_id="sol_1", status="Concluído", confirmacao="pendente", reaberturas_count=0
):
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {
        "status": status,
        "confirmacao_solicitante": confirmacao,
        "solicitante_id": solicitante_id,
        "categoria": "Manutenção",
        "numero_chamado": "CH-001",
        "area": "Planejamento",
        "responsavel_id": "sup_1",
        "responsavel": "Supervisor",
        "solicitante_nome": "Solicitante",
        "reaberturas_solicitante_count": reaberturas_count,
    }
    return doc


# ── Confirmar resolução ────────────────────────────────────────────────────────


def test_confirmar_resolucao_sucesso(client_logado_solicitante):
    """Solicitante confirma resolução: campo vira 'confirmado', status permanece 'Concluído'."""
    doc = _doc_chamado()
    with patch("app.routes.api.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_solicitante.post(
            "/api/chamado/ch_123/confirmar-resolucao",
            json={"acao": "confirmar"},
            content_type="application/json",
        )
    assert r.status_code == 200
    data = r.get_json()
    assert data["sucesso"] is True
    # Verifica que gravou confirmacao_solicitante="confirmado" no Firestore
    update_call = mock_db.collection.return_value.document.return_value.update
    update_call.assert_called_once()
    payload = update_call.call_args[0][0]
    assert payload["confirmacao_solicitante"] == "confirmado"


def test_reabrir_chamado_sucesso(client_logado_solicitante):
    """Solicitante rejeita resolução: status volta para 'Aberto', motivo salvo no histórico."""
    doc = _doc_chamado()
    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Historico") as mock_historico,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_solicitante.post(
            "/api/chamado/ch_123/confirmar-resolucao",
            json={"acao": "reabrir", "motivo": "Problema ainda persiste"},
            content_type="application/json",
        )
    assert r.status_code == 200
    data = r.get_json()
    assert data["sucesso"] is True
    update_call = mock_db.collection.return_value.document.return_value.update
    update_call.assert_called_once()
    payload = update_call.call_args[0][0]
    assert payload["status"] == "Aberto"
    assert payload["confirmacao_solicitante"] == "reaberto"
    # Histórico deve ter sido criado com o parâmetro correto (detalhe, não detalhes)
    mock_historico.assert_called_once()
    _, kwargs = mock_historico.call_args
    assert "detalhe" in kwargs, "Historico deve ser criado com 'detalhe=', não 'detalhes='"
    assert "detalhes" not in kwargs, "Typo 'detalhes' não deve ser usado"


def test_reabrir_sem_motivo_retorna_400(client_logado_solicitante):
    """Reabrir sem motivo retorna 400."""
    doc = _doc_chamado()
    with patch("app.routes.api.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_solicitante.post(
            "/api/chamado/ch_123/confirmar-resolucao",
            json={"acao": "reabrir", "motivo": ""},
            content_type="application/json",
        )
    assert r.status_code == 400
    assert r.get_json()["sucesso"] is False


# ── Limite de reaberturas pelo solicitante (3x) ─────────────────────────────────


def test_reabrir_incrementa_contador(client_logado_solicitante):
    """Reabertura bem-sucedida incrementa reaberturas_solicitante_count."""
    doc = _doc_chamado(reaberturas_count=1)
    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Historico"),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_solicitante.post(
            "/api/chamado/ch_123/confirmar-resolucao",
            json={"acao": "reabrir", "motivo": "Ainda com problema"},
            content_type="application/json",
        )
    assert r.status_code == 200
    payload = mock_db.collection.return_value.document.return_value.update.call_args[0][0]
    assert payload.get("reaberturas_solicitante_count") == 2


def test_reabrir_no_limite_ainda_permite_terceira_vez(client_logado_solicitante):
    """Com 2 reaberturas anteriores, a 3ª ainda é permitida (limite = 3)."""
    doc = _doc_chamado(reaberturas_count=2)
    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Historico"),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_solicitante.post(
            "/api/chamado/ch_123/confirmar-resolucao",
            json={"acao": "reabrir", "motivo": "Ainda com problema"},
            content_type="application/json",
        )
    assert r.status_code == 200
    payload = mock_db.collection.return_value.document.return_value.update.call_args[0][0]
    assert payload.get("reaberturas_solicitante_count") == 3


def test_reabrir_apos_limite_atingido_bloqueado(client_logado_solicitante):
    """Após 3 reaberturas, a 4ª tentativa é bloqueada com 403."""
    doc = _doc_chamado(reaberturas_count=3)
    with patch("app.routes.api.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_solicitante.post(
            "/api/chamado/ch_123/confirmar-resolucao",
            json={"acao": "reabrir", "motivo": "Ainda com problema"},
            content_type="application/json",
        )
    assert r.status_code == 403
    assert r.get_json()["sucesso"] is False
    mock_db.collection.return_value.document.return_value.update.assert_not_called()


def test_reabrir_apos_limite_nao_dispara_notificacao(client_logado_solicitante):
    """Bloqueio por limite não deve disparar notificação de reabertura."""
    doc = _doc_chamado(reaberturas_count=3)
    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api._enviar_notificacao_reabrir") as mock_notif,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_solicitante.post(
            "/api/chamado/ch_123/confirmar-resolucao",
            json={"acao": "reabrir", "motivo": "Ainda com problema"},
            content_type="application/json",
        )
    assert r.status_code == 403
    mock_notif.assert_not_called()


# ── Controle de acesso ─────────────────────────────────────────────────────────


def test_supervisor_nao_pode_confirmar_chamado_alheio(client_logado_supervisor):
    """Supervisor não pode confirmar chamado que não abriu (solicitante_id diferente)."""
    doc = _doc_chamado(solicitante_id="sol_1")  # sup_1 != sol_1
    with patch("app.routes.api.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_supervisor.post(
            "/api/chamado/ch_123/confirmar-resolucao",
            json={"acao": "confirmar"},
            content_type="application/json",
        )
    assert r.status_code == 403


def test_supervisor_pode_confirmar_chamado_que_abriu(client_logado_supervisor):
    """Supervisor que é o solicitante do chamado pode confirmar a resolução."""
    doc = _doc_chamado(solicitante_id="sup_1")  # mesmo ID do supervisor logado
    with patch("app.routes.api.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_supervisor.post(
            "/api/chamado/ch_123/confirmar-resolucao",
            json={"acao": "confirmar"},
            content_type="application/json",
        )
    assert r.status_code == 200
    assert r.get_json()["sucesso"] is True


def test_solicitante_nao_confirma_chamado_alheio(client_logado_solicitante):
    """Solicitante não pode confirmar chamado de outro usuário (403)."""
    doc = _doc_chamado(solicitante_id="outro_usuario")
    with patch("app.routes.api.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_solicitante.post(
            "/api/chamado/ch_123/confirmar-resolucao",
            json={"acao": "confirmar"},
            content_type="application/json",
        )
    assert r.status_code == 403


def test_chamado_sem_confirmacao_pendente_retorna_400(client_logado_solicitante):
    """Não é possível confirmar chamado que não está aguardando confirmação."""
    doc = _doc_chamado(confirmacao=None)
    with patch("app.routes.api.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_solicitante.post(
            "/api/chamado/ch_123/confirmar-resolucao",
            json={"acao": "confirmar"},
            content_type="application/json",
        )
    assert r.status_code == 400
    assert r.get_json()["sucesso"] is False


def test_solicitante_nao_confirma_nivel2_confirmado(client_logado_solicitante):
    """Regressão Nível 2: solicitante não pode confirmar chamado já 'confirmado' (400)."""
    doc = _doc_chamado(confirmacao="confirmado")
    with patch("app.routes.api.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_solicitante.post(
            "/api/chamado/ch_123/confirmar-resolucao",
            json={"acao": "confirmar"},
            content_type="application/json",
        )
    assert r.status_code == 400
    assert r.get_json()["sucesso"] is False


def test_acao_invalida_retorna_400(client_logado_solicitante):
    """Ação desconhecida retorna 400."""
    doc = _doc_chamado()
    with patch("app.routes.api.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_solicitante.post(
            "/api/chamado/ch_123/confirmar-resolucao",
            json={"acao": "deletar"},
            content_type="application/json",
        )
    assert r.status_code == 400


# ── E-mails ───────────────────────────────────────────────────────────────────


def test_reabrir_dispara_notificacao_supervisor(client_logado_solicitante):
    """Reabrir chamado chama _enviar_notificacao_reabrir com os dados corretos."""
    doc = _doc_chamado()
    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Historico"),
        patch("app.routes.api._enviar_notificacao_reabrir") as mock_notif,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_solicitante.post(
            "/api/chamado/ch_123/confirmar-resolucao",
            json={"acao": "reabrir", "motivo": "Problema persiste"},
            content_type="application/json",
        )
    assert r.status_code == 200
    mock_notif.assert_called_once()
    _, chamado_id_arg, data_arg, motivo_arg, _ = mock_notif.call_args[0]
    assert chamado_id_arg == "ch_123"
    assert motivo_arg == "Problema persiste"


def test_confirmar_dispara_notificacao_responsavel(client_logado_solicitante):
    """Confirmar resolução notifica o responsável designado do chamado."""
    doc = _doc_chamado()
    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api._enviar_notificacao_confirmar") as mock_notif,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_solicitante.post(
            "/api/chamado/ch_123/confirmar-resolucao",
            json={"acao": "confirmar"},
            content_type="application/json",
        )
    assert r.status_code == 200
    mock_notif.assert_called_once()
    # Verifica que o helper recebeu o chamado_id correto
    _, chamado_id_arg, _data_arg, solicitante_nome_arg = mock_notif.call_args[0]
    assert chamado_id_arg == "ch_123"
    assert solicitante_nome_arg == "Solicitante Teste"


def test_confirmar_nao_dispara_notificacao_reabrir(client_logado_solicitante):
    """Confirmar resolução NÃO chama o helper de reabertura."""
    doc = _doc_chamado()
    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api._enviar_notificacao_reabrir") as mock_reabrir,
        patch("app.routes.api._enviar_notificacao_confirmar"),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_solicitante.post(
            "/api/chamado/ch_123/confirmar-resolucao",
            json={"acao": "confirmar"},
            content_type="application/json",
        )
    assert r.status_code == 200
    mock_reabrir.assert_not_called()


def test_confirmar_nao_notifica_se_confirmacao_nao_persistiu(client_logado_solicitante):
    """Notificação de confirmação é ignorada se o chamado não estiver confirmado no Firestore."""
    doc = _doc_chamado()
    doc_sem_confirmacao = MagicMock()
    doc_sem_confirmacao.exists = False

    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.threading.Thread", side_effect=_thread_executa_sync),
        patch("app.services.notifications.notificar_responsavel_chamado_confirmado") as mock_notif,
    ):
        mock_db.collection.return_value.document.return_value.get.side_effect = [
            doc,
            doc_sem_confirmacao,
        ]
        r = client_logado_solicitante.post(
            "/api/chamado/ch_123/confirmar-resolucao",
            json={"acao": "confirmar"},
            content_type="application/json",
        )
    assert r.status_code == 200
    mock_notif.assert_not_called()


def test_reabrir_reseta_flags_lembrete(client_logado_solicitante):
    """Ao reabrir, flags de lembrete devem ser zeradas para o próximo ciclo de conclusão."""
    doc = _doc_chamado()
    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Historico"),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_solicitante.post(
            "/api/chamado/ch_123/confirmar-resolucao",
            json={"acao": "reabrir", "motivo": "Ainda com problema"},
            content_type="application/json",
        )
    assert r.status_code == 200
    payload = mock_db.collection.return_value.document.return_value.update.call_args[0][0]
    assert payload.get("lembrete_confirmacao_1_enviado") is False
    assert payload.get("lembrete_confirmacao_2_enviado") is False


def test_reabrir_reseta_escalacao_resposta_nivel(client_logado_solicitante):
    """ADR-004: ao reabrir, escalacao_resposta_nivel deve ser zerado para reiniciar Escada A."""
    doc = _doc_chamado()
    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Historico"),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_solicitante.post(
            "/api/chamado/ch_123/confirmar-resolucao",
            json={"acao": "reabrir", "motivo": "Não resolvido"},
            content_type="application/json",
        )
    assert r.status_code == 200
    payload = mock_db.collection.return_value.document.return_value.update.call_args[0][0]
    assert payload.get("escalacao_resposta_nivel") == 0


def test_reabrir_reseta_flags_escada_b(client_logado_solicitante):
    """Fase 7: ao reabrir, campos Escada B devem ser zerados junto com Escada A."""
    doc = _doc_chamado()
    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Historico"),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_solicitante.post(
            "/api/chamado/ch_123/confirmar-resolucao",
            json={"acao": "reabrir", "motivo": "Não resolvido"},
            content_type="application/json",
        )
    assert r.status_code == 200
    payload = mock_db.collection.return_value.document.return_value.update.call_args[0][0]
    assert payload.get("escalacao_resolucao_nivel") == 0
    assert payload.get("alerta_supervisor_50_enviado") is False
    assert payload.get("alerta_supervisor_80_enviado") is False


def test_chamado_nao_concluido_nao_permite_confirmacao(client_logado_solicitante):
    """Regressão: status != 'Concluído' com confirmacao_solicitante='pendente' deve retornar 400.

    Garante que a guarda de status no endpoint impede que um chamado em 'Em Atendimento'
    com flag residual seja confirmado indevidamente.
    """
    doc = _doc_chamado(status="Em Atendimento", confirmacao="pendente")
    with patch("app.routes.api.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_solicitante.post(
            "/api/chamado/ch_123/confirmar-resolucao",
            json={"acao": "confirmar"},
            content_type="application/json",
        )
    assert r.status_code == 400
    assert r.get_json()["sucesso"] is False


def _thread_executa_sync(target, daemon=True):
    """Substituto de threading.Thread que executa o target na hora (para testes)."""

    class _T:
        def start(self):
            target()

    return _T()


def test_reabrir_nao_notifica_se_chamado_removido_antes_do_email(client_logado_solicitante):
    """Notificação de reabertura é ignorada se o chamado não existir mais no Firestore."""
    doc = _doc_chamado()
    doc_removido = MagicMock()
    doc_removido.exists = False

    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Historico"),
        patch("app.routes.api.threading.Thread", side_effect=_thread_executa_sync),
        patch("app.services.notifications.notificar_supervisor_chamado_reaberto") as mock_notif,
    ):
        mock_db.collection.return_value.document.return_value.get.side_effect = [
            doc,
            doc_removido,
        ]
        r = client_logado_solicitante.post(
            "/api/chamado/ch_123/confirmar-resolucao",
            json={"acao": "reabrir", "motivo": "Problema persiste"},
            content_type="application/json",
        )
    assert r.status_code == 200
    mock_notif.assert_not_called()
