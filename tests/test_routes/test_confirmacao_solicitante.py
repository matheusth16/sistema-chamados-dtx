"""Testes da funcionalidade de confirmação de resolução pelo solicitante."""

from unittest.mock import MagicMock, patch


def _doc_chamado(solicitante_id="sol_1", status="Concluído", confirmacao="pendente"):
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {
        "status": status,
        "confirmacao_solicitante": confirmacao,
        "solicitante_id": solicitante_id,
        "categoria": "Manutenção",
        "numero_chamado": "CH-001",
        "area": "Planejamento",
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
    # Histórico deve ter sido criado
    mock_historico.assert_called_once()


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


# ── Controle de acesso ─────────────────────────────────────────────────────────


def test_supervisor_nao_pode_confirmar(client_logado_supervisor):
    """Supervisor não tem acesso à rota de confirmação (403)."""
    r = client_logado_supervisor.post(
        "/api/chamado/ch_123/confirmar-resolucao",
        json={"acao": "confirmar"},
        content_type="application/json",
    )
    assert r.status_code == 403


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
