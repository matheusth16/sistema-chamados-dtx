"""Testes da API de atualização de status (AJAX). Ref: CT-STAT-*."""

from unittest.mock import MagicMock, patch

import pytest


def test_atualizar_status_sem_login_retorna_401_ou_redirect(client):
    """POST /api/atualizar-status sem login deve falhar (401/403/302)."""
    r = client.post(
        "/api/atualizar-status",
        json={"chamado_id": "x", "novo_status": "Em Atendimento"},
        content_type="application/json",
    )
    assert r.status_code in (302, 401, 403)


def test_atualizar_status_json_vazio_retorna_400(client):
    """POST com JSON vazio ou inválido retorna 400 (ou 401/403 se não logado)."""
    r = client.post("/api/atualizar-status", data={})
    assert r.status_code in (400, 302, 401, 403, 415)
    r2 = client.post("/api/atualizar-status", json={}, content_type="application/json")
    assert r2.status_code in (400, 302, 401, 403)


def test_atualizar_status_sem_chamado_id_retorna_400(client_logado_supervisor):
    """CT-STAT-02: POST /api/atualizar-status sem chamado_id retorna 400 (ou 403 por Origin)."""
    r = client_logado_supervisor.post(
        "/api/atualizar-status",
        json={"novo_status": "Aberto"},
        content_type="application/json",
    )
    assert r.status_code in (400, 403)
    if r.status_code == 400:
        data = r.get_json()
        assert data is not None and data.get("sucesso") is False
        assert "chamado_id" in data.get("erro", "").lower()


def test_atualizar_status_status_invalido_retorna_400(client_logado_supervisor):
    """CT-STAT-03: novo_status inválido retorna 400."""
    r = client_logado_supervisor.post(
        "/api/atualizar-status",
        json={"chamado_id": "ch_123", "novo_status": "Fechado"},  # "Fechado" não é status válido
        content_type="application/json",
    )
    assert r.status_code == 400
    data = r.get_json()
    assert data is not None and data.get("sucesso") is False
    assert "inválido" in data.get("erro", "").lower() or "status" in data.get("erro", "").lower()


def test_atualizar_status_com_sucesso_retorna_200(client_logado_supervisor):
    """CT-STAT-01: POST /api/atualizar-status com payload válido retorna 200."""
    from unittest.mock import MagicMock

    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {"area": "Manutencao", "status": "Aberto", "solicitante_id": "s1"}
    chamado_mock = MagicMock()
    chamado_mock.area = "Manutencao"
    chamado_mock.responsavel_id = None  # sem dono → supervisor da área pode ver
    chamado_mock.solicitante_id = "s1"
    chamado_mock.participantes = []
    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Chamado") as mock_chamado_cls,
        patch("app.routes.api.atualizar_status_chamado") as mock_atualizar,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado_cls.from_dict.return_value = chamado_mock
        mock_atualizar.return_value = {
            "sucesso": True,
            "mensagem": "Status alterado para Em Atendimento",
            "novo_status": "Em Atendimento",
        }
        r = client_logado_supervisor.post(
            "/api/atualizar-status",
            json={"chamado_id": "ch_valido_123", "novo_status": "Em Atendimento"},
            content_type="application/json",
        )
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("sucesso") is True
    assert data.get("novo_status") == "Em Atendimento"


def test_atualizar_status_chamado_inexistente_retorna_404(client_logado_supervisor):
    """CT-STAT-04: Chamado não encontrado retorna 404."""
    mock_doc = MagicMock()
    mock_doc.exists = False
    with patch("app.routes.api.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        r = client_logado_supervisor.post(
            "/api/atualizar-status",
            json={"chamado_id": "ch_inexistente", "novo_status": "Em Atendimento"},
            content_type="application/json",
        )
    assert r.status_code == 404
    data = r.get_json()
    assert data.get("sucesso") is False
    assert "não encontrado" in data.get("erro", "").lower()


def test_bulk_status_como_solicitante_retorna_403(client_logado_solicitante):
    """CT-STAT-05: POST /api/bulk-status como solicitante retorna 403 (acesso negado ou origem)."""
    r = client_logado_solicitante.post(
        "/api/bulk-status",
        json={"chamado_ids": ["ch_1"], "novo_status": "Concluído"},
        content_type="application/json",
    )
    assert r.status_code == 403
    data = r.get_json()
    assert data is not None and data.get("sucesso") is False
    erro = (data.get("erro") or "").lower()
    assert (
        "acesso negado" in erro
        or "negado" in erro
        or "origem" in erro
        or "permissão" in erro
        or "permissao" in erro
    )


def test_bulk_status_chamado_ids_nao_lista_retorna_400(client_logado_supervisor):
    """CT-STAT-06: chamado_ids não-lista retorna 400 (ou 403 por Origin)."""
    r = client_logado_supervisor.post(
        "/api/bulk-status",
        json={"chamado_ids": "id_unico", "novo_status": "Concluído"},
        content_type="application/json",
    )
    assert r.status_code in (400, 403)
    if r.status_code == 400:
        data = r.get_json()
        assert data.get("sucesso") is False
        assert (
            "lista" in data.get("erro", "").lower() or "chamado_ids" in data.get("erro", "").lower()
        )


def test_bulk_status_novo_status_invalido_retorna_400(client_logado_supervisor):
    """CT-STAT-07: novo_status inválido retorna 400 (ou 403 por Origin)."""
    r = client_logado_supervisor.post(
        "/api/bulk-status",
        json={"chamado_ids": ["ch_1"], "novo_status": "Fechado"},
        content_type="application/json",
    )
    assert r.status_code in (400, 403)
    if r.status_code == 400:
        data = r.get_json()
        assert data.get("sucesso") is False
        assert (
            "inválido" in data.get("erro", "").lower()
            or "novo_status" in data.get("erro", "").lower()
        )


@pytest.mark.regression
def test_atualizar_status_supervisor_outra_area_retorna_403(client_logado_supervisor):
    """CT-STAT-08 (IDOR): supervisor da área 'Manutencao' não pode alterar chamado da área 'TI'.

    Verifica que verificar_permissao_mudanca_status bloqueia no endpoint,
    não apenas no serviço de permissões.
    """
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {"area": "TI", "status": "Aberto", "solicitante_id": "outro_usuario"}

    chamado_mock = MagicMock()
    chamado_mock.area = "TI"
    chamado_mock.solicitante_id = "outro_usuario"

    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Chamado") as mock_chamado_cls,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado_cls.from_dict.return_value = chamado_mock

        r = client_logado_supervisor.post(
            "/api/atualizar-status",
            json={"chamado_id": "ch_de_ti", "novo_status": "Em Atendimento"},
            content_type="application/json",
        )

    assert r.status_code == 403, (
        f"Supervisor de 'Manutencao' não deveria alterar chamado de 'TI'. "
        f"Recebeu {r.status_code}: {r.get_json()}"
    )
    data = r.get_json()
    assert data is not None and data.get("sucesso") is False


# ── F-63: Transição inválida via API retorna 400 ──────────────────────────────


def test_atualizar_status_transicao_invalida_retorna_400(client_logado_supervisor):
    """CT-STAT-09 (F-63): Transição inválida (Concluído → Aberto) retorna 400."""
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {
        "area": "Manutencao",
        "status": "Concluído",
        "solicitante_id": "s1",
    }
    chamado_mock = MagicMock()
    chamado_mock.area = "Manutencao"
    chamado_mock.responsavel_id = None  # sem dono → supervisor da área pode ver
    chamado_mock.solicitante_id = "s1"
    chamado_mock.participantes = []
    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Chamado") as mock_chamado_cls,
        patch("app.routes.api.atualizar_status_chamado") as mock_atualizar,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado_cls.from_dict.return_value = chamado_mock
        mock_atualizar.return_value = {
            "sucesso": False,
            "erro": "Transição inválida: Concluído → Aberto",
            "codigo": 400,
        }
        r = client_logado_supervisor.post(
            "/api/atualizar-status",
            json={"chamado_id": "ch_conc", "novo_status": "Aberto"},
            content_type="application/json",
        )
    assert r.status_code == 400
    data = r.get_json()
    assert data is not None and data.get("sucesso") is False


# ── Lacuna 4: motivo_reabertura obrigatório ao reabrir de Concluído ───────────


def test_atualizar_status_reabrir_concluido_sem_motivo_retorna_400(client_logado_admin):
    """Lacuna 4: Concluído → Aberto sem motivo_reabertura retorna 400."""
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {
        "area": "Geral",
        "status": "Concluído",
        "confirmacao_solicitante": "pendente",
        "solicitante_id": "s1",
    }
    chamado_mock = MagicMock()
    chamado_mock.status = "Concluído"
    chamado_mock.area = "Geral"
    chamado_mock.responsavel_id = None
    chamado_mock.solicitante_id = "s1"
    chamado_mock.participantes = []
    chamado_mock.confirmacao_solicitante = "pendente"
    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Chamado") as mock_chamado_cls,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado_cls.from_dict.return_value = chamado_mock
        r = client_logado_admin.post(
            "/api/atualizar-status",
            json={"chamado_id": "ch_conc", "novo_status": "Aberto"},
            content_type="application/json",
        )
    assert r.status_code == 400
    data = r.get_json()
    assert data is not None and data.get("sucesso") is False
    assert "motivo" in data.get("erro", "").lower() or "reabrir" in data.get("erro", "").lower()


def test_atualizar_status_reabrir_concluido_motivo_curto_retorna_400(client_logado_admin):
    """Lacuna 4: motivo_reabertura com menos de 3 chars retorna 400."""
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {
        "area": "Geral",
        "status": "Concluído",
        "confirmacao_solicitante": "confirmado",
        "solicitante_id": "s1",
    }
    chamado_mock = MagicMock()
    chamado_mock.status = "Concluído"
    chamado_mock.area = "Geral"
    chamado_mock.responsavel_id = None
    chamado_mock.solicitante_id = "s1"
    chamado_mock.participantes = []
    chamado_mock.confirmacao_solicitante = "confirmado"
    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Chamado") as mock_chamado_cls,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado_cls.from_dict.return_value = chamado_mock
        r = client_logado_admin.post(
            "/api/atualizar-status",
            json={"chamado_id": "ch_conc", "novo_status": "Aberto", "motivo_reabertura": "ok"},
            content_type="application/json",
        )
    assert r.status_code == 400


def test_atualizar_status_reabrir_concluido_com_motivo_valido_passa(client_logado_admin):
    """Lacuna 4: Concluído → Aberto com motivo_reabertura válido passa a validação de motivo."""
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {
        "area": "Geral",
        "status": "Concluído",
        "confirmacao_solicitante": "confirmado",
        "solicitante_id": "s1",
    }
    chamado_mock = MagicMock()
    chamado_mock.status = "Concluído"
    chamado_mock.area = "Geral"
    chamado_mock.responsavel_id = None
    chamado_mock.solicitante_id = "s1"
    chamado_mock.participantes = []
    chamado_mock.confirmacao_solicitante = "confirmado"
    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Chamado") as mock_chamado_cls,
        patch("app.routes.api.atualizar_status_chamado") as mock_atualizar,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado_cls.from_dict.return_value = chamado_mock
        mock_atualizar.return_value = {
            "sucesso": True,
            "mensagem": "Status alterado para Aberto",
            "novo_status": "Aberto",
        }
        r = client_logado_admin.post(
            "/api/atualizar-status",
            json={
                "chamado_id": "ch_conc",
                "novo_status": "Aberto",
                "motivo_reabertura": "Problema recorrente identificado",
            },
            content_type="application/json",
        )
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("sucesso") is True
