"""Testes de integração: fluxo de atualização de status em lote (bulk)."""

from unittest.mock import MagicMock, patch


def test_bulk_status_sem_login_retorna_401_ou_redirect(client):
    """POST /api/bulk-status sem autenticação deve falhar.
    403 pode ocorrer quando a validação Origin/Referer (CSRF) está ativa e o cliente não envia Origin."""
    r = client.post(
        "/api/bulk-status",
        json={
            "chamado_ids": ["id1", "id2"],
            "novo_status": "Concluído",
        },
        content_type="application/json",
        follow_redirects=False,
    )
    assert r.status_code in (302, 401, 403, 404)


def test_bulk_status_com_login_json_invalido_retorna_400(client_logado_supervisor):
    """POST /api/bulk-status com payload inválido (JSON vazio) retorna 400 ou 403 (403 se Origin/Referer falhar)."""
    r = client_logado_supervisor.post(
        "/api/bulk-status",
        json={},
        content_type="application/json",
    )
    assert r.status_code in (400, 403)
    if r.status_code == 400:
        data = r.get_json()
        assert (
            data is not None
            and (data.get("erro") or "").lower().find("json") >= 0
            or data.get("erro")
        )


def test_bulk_status_lote_100_por_cento_sucesso(client_logado_supervisor):
    """Lote com todos os itens da área do supervisor: atualizados == total_solicitados, erros vazio."""
    doc_a = MagicMock()
    doc_a.exists = True
    doc_a.to_dict.return_value = {
        "area": "Manutencao",
        "status": "Aberto",
        "responsavel_id": None,
        "solicitante_id": "sol_x",
        "participantes": [],
    }
    doc_b = MagicMock()
    doc_b.exists = True
    doc_b.to_dict.return_value = {
        "area": "Manutencao",
        "status": "Aberto",
        "responsavel_id": None,
        "solicitante_id": "sol_y",
        "participantes": [],
    }
    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.atualizar_status_chamado") as mock_atualizar,
    ):
        col = mock_db.collection.return_value

        def doc_side_effect(doc_id):
            m = MagicMock()
            m.get.return_value = doc_a if doc_id == "ch_a" else doc_b
            return m

        col.document.side_effect = doc_side_effect
        mock_atualizar.return_value = {"sucesso": True, "novo_status": "Em Atendimento"}

        r = client_logado_supervisor.post(
            "/api/bulk-status",
            json={"chamado_ids": ["ch_a", "ch_b"], "novo_status": "Em Atendimento"},
            content_type="application/json",
            headers={"Origin": "http://localhost:5000"},
        )
    # Origin já enviado acima — CSRF não deve barrar, então cravamos 200 direto
    # (em vez de aceitar 403 em silêncio) pra uma regressão real falhar alto.
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("sucesso") is True
    assert data.get("atualizados") == 2
    assert data.get("total_solicitados") == 2
    assert data.get("erros") == []


def test_bulk_status_lote_falha_total_ainda_retorna_sucesso_true_no_topo(
    client_logado_supervisor,
):
    """Regressão/documentação de contrato: quando NENHUM item do lote é atualizado
    (ex.: todos de outra área), o campo top-level "sucesso" continua True — só
    "atualizados": 0 e "erros" preenchido denunciam a falha completa.

    Isso é intencional (o request em si foi processado), mas um consumidor que só
    olha `data.sucesso` (como o JS de app/templates/dashboard.html fazia antes desta
    correção) não percebe que 0 de N chamados foram de fato atualizados.
    """
    doc_outra_area = MagicMock()
    doc_outra_area.exists = True
    doc_outra_area.to_dict.return_value = {
        "area": "TI",
        "status": "Aberto",
        "responsavel_id": None,
        "solicitante_id": "sol_x",
        "participantes": [],
    }
    with patch("app.routes.api.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.return_value = doc_outra_area

        r = client_logado_supervisor.post(
            "/api/bulk-status",
            json={"chamado_ids": ["ch_ti_1", "ch_ti_2"], "novo_status": "Em Atendimento"},
            content_type="application/json",
            headers={"Origin": "http://localhost:5000"},
        )
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("sucesso") is True
    assert data.get("atualizados") == 0
    assert data.get("total_solicitados") == 2
    assert len(data.get("erros", [])) == 2
