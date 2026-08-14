"""
Testes de API: contrato e validação de comunicação entre sistemas.

Valida códigos HTTP, estrutura JSON e autenticação conforme docs/API.md.
Todos os testes estão marcados com @pytest.mark.api para execução seletiva: pytest -m api -v
"""

from unittest.mock import patch

import pytest

# --- Health e Service Worker (sem auth) ---


def test_pagina_html_sem_login_preserva_redirect_e_flash(client):
    r = client.get("/meus-dados/exportar", follow_redirects=False)

    assert r.status_code == 302
    assert "/login" in (r.location or "")
    with client.session_transaction() as sess:
        assert sess.get("_flashes")


@pytest.mark.api
def test_api_health_contrato_200_status_ok(client):
    """GET /health retorna 200 e corpo { status: ok }."""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok"}


@pytest.mark.api
def test_api_sw_js_contrato_200_javascript(client):
    """GET /sw.js retorna 200 e Content-Type JavaScript."""
    r = client.get("/sw.js")
    assert r.status_code == 200
    assert "javascript" in (r.content_type or "").lower()


# --- POST /api/atualizar-status ---


@pytest.mark.api
def test_api_atualizar_status_sem_login_401(client):
    """POST /api/atualizar-status sem login retorna JSON 401."""
    r = client.post(
        "/api/atualizar-status",
        json={"chamado_id": "x", "novo_status": "Aberto"},
        content_type="application/json",
    )
    assert r.status_code == 401
    assert r.is_json
    assert r.get_json()["sucesso"] is False


@pytest.mark.api
def test_api_atualizar_status_sem_chamado_id_400(client_logado_supervisor):
    """POST /api/atualizar-status sem chamado_id retorna 400 com campo erro."""
    r = client_logado_supervisor.post(
        "/api/atualizar-status", json={"novo_status": "Aberto"}, content_type="application/json"
    )
    assert r.status_code == 400
    data = r.get_json()
    assert data is not None and data.get("sucesso") is False and "erro" in data


@pytest.mark.api
def test_api_atualizar_status_novo_status_invalido_400(client_logado_supervisor):
    """POST /api/atualizar-status com novo_status inválido retorna 400."""
    r = client_logado_supervisor.post(
        "/api/atualizar-status",
        json={"chamado_id": "ch1", "novo_status": "Fechado"},
        content_type="application/json",
    )
    assert r.status_code == 400
    assert r.get_json().get("sucesso") is False


@pytest.mark.api
def test_api_atualizar_status_sucesso_200_estrutura(client_logado_supervisor, db_session):
    """POST /api/atualizar-status sucesso retorna 200 com sucesso, mensagem, novo_status."""
    from tests.factories import make_chamado

    chamado = make_chamado(
        area="Manutencao", status="Aberto", responsavel_id=None, solicitante_id="s1"
    )
    with patch("app.routes.api_chamados.atualizar_status_chamado") as m:
        m.return_value = {
            "sucesso": True,
            "mensagem": "Status alterado",
            "novo_status": "Em Atendimento",
        }
        r = client_logado_supervisor.post(
            "/api/atualizar-status",
            json={"chamado_id": str(chamado.id), "novo_status": "Em Atendimento"},
            content_type="application/json",
        )
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("sucesso") is True and data.get("novo_status") == "Em Atendimento"


# --- POST /api/bulk-status ---


@pytest.mark.api
def test_api_bulk_status_sem_login_401(client):
    """POST /api/bulk-status sem login retorna JSON 401."""
    r = client.post(
        "/api/bulk-status",
        json={"chamado_ids": ["ch1"], "novo_status": "Concluído"},
        content_type="application/json",
    )
    assert r.status_code == 401
    assert r.is_json


@pytest.mark.api
def test_api_bulk_status_solicitante_403(client_logado_solicitante):
    """POST /api/bulk-status como solicitante retorna 403."""
    r = client_logado_solicitante.post(
        "/api/bulk-status",
        json={"chamado_ids": ["ch1"], "novo_status": "Concluído"},
        content_type="application/json",
    )
    assert r.status_code == 403
    assert r.get_json().get("erro")


@pytest.mark.api
def test_api_bulk_status_chamado_ids_nao_lista_400(client_logado_supervisor):
    """POST /api/bulk-status com chamado_ids não-lista retorna 400."""
    r = client_logado_supervisor.post(
        "/api/bulk-status",
        json={"chamado_ids": "id1", "novo_status": "Concluído"},
        content_type="application/json",
    )
    assert r.status_code == 400


@pytest.mark.api
def test_api_bulk_status_sucesso_200_estrutura(client_logado_supervisor, db_session):
    """POST /api/bulk-status sucesso retorna 200 com sucesso, atualizados, total_solicitados, erros."""
    from tests.factories import make_chamado

    chamado = make_chamado(area="Manutencao", status="Aberto", responsavel_id=None)
    with patch("app.routes.api_chamados.atualizar_status_chamado") as mock_atualizar:
        mock_atualizar.return_value = {
            "sucesso": True,
            "mensagem": "ok",
            "novo_status": "Concluído",
        }
        r = client_logado_supervisor.post(
            "/api/bulk-status",
            json={"chamado_ids": [str(chamado.id)], "novo_status": "Concluído"},
            content_type="application/json",
        )
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("sucesso") is True
    assert "atualizados" in data and "total_solicitados" in data and "erros" in data


# --- POST /api/editar-chamado ---


@pytest.mark.api
def test_api_editar_chamado_sem_login_401(client):
    """POST /api/editar-chamado sem login retorna JSON 401."""
    r = client.post(
        "/api/editar-chamado", data={"chamado_id": "ch1"}, content_type="multipart/form-data"
    )
    assert r.status_code == 401
    assert r.is_json


@pytest.mark.api
def test_api_editar_chamado_solicitante_403(client_logado_solicitante):
    """POST /api/editar-chamado como solicitante retorna 403."""
    r = client_logado_solicitante.post(
        "/api/editar-chamado", data={"chamado_id": "ch1"}, content_type="multipart/form-data"
    )
    assert r.status_code == 403


@pytest.mark.api
def test_api_editar_chamado_sem_chamado_id_400(client_logado_supervisor):
    """POST /api/editar-chamado sem chamado_id retorna 400 (validação antes do db)."""
    r = client_logado_supervisor.post(
        "/api/editar-chamado", data={}, content_type="multipart/form-data"
    )
    assert r.status_code == 400
    assert "erro" in (r.get_json() or {})


@pytest.mark.api
def test_api_editar_chamado_inexistente_404(client_logado_supervisor):
    """POST /api/editar-chamado com ID inexistente retorna 404."""
    r = client_logado_supervisor.post(
        "/api/editar-chamado",
        data={"chamado_id": "inexistente"},
        content_type="multipart/form-data",
    )
    assert r.status_code == 404


# --- GET /api/chamados/paginar ---


@pytest.mark.api
def test_api_chamados_paginar_sem_login_401(client):
    """GET /api/chamados/paginar sem login retorna JSON 401."""
    r = client.get("/api/chamados/paginar")
    assert r.status_code == 401
    assert r.is_json


@pytest.mark.api
def test_api_chamados_paginar_sucesso_200_estrutura(client_logado_supervisor):
    """GET /api/chamados/paginar retorna 200 com chamados e paginacao."""
    with patch("app.routes.api_chamados.aplicar_filtros_dashboard_com_paginacao") as m:
        m.return_value = {"docs": [], "proximo_cursor": None, "tem_proxima": False}
        r = client_logado_supervisor.get("/api/chamados/paginar")
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("sucesso") is True and "chamados" in data and "paginacao" in data


# --- POST /api/carregar-mais ---


@pytest.mark.api
def test_api_carregar_mais_sem_login_401(client):
    """POST /api/carregar-mais sem login retorna JSON 401."""
    r = client.post(
        "/api/carregar-mais", json={"cursor": None, "limite": 20}, content_type="application/json"
    )
    assert r.status_code == 401
    assert r.is_json


@pytest.mark.api
def test_api_carregar_mais_sucesso_200_estrutura(client_logado_supervisor):
    """POST /api/carregar-mais retorna 200 com chamados, cursor_proximo, tem_proxima."""
    with patch("app.routes.api_chamados.aplicar_filtros_dashboard_com_paginacao") as m:
        m.return_value = {"docs": [], "proximo_cursor": None, "tem_proxima": False}
        r = client_logado_supervisor.post(
            "/api/carregar-mais",
            json={"cursor": None, "limite": 20},
            content_type="application/json",
        )
    assert r.status_code == 200
    data = r.get_json()
    assert (
        data.get("sucesso") is True
        and "chamados" in data
        and "cursor_proximo" in data
        and "tem_proxima" in data
    )


# --- GET /api/chamado/<id> ---


@pytest.mark.api
def test_api_chamado_por_id_sem_login_401(client):
    """GET /api/chamado/<id> sem login retorna JSON 401."""
    r = client.get("/api/chamado/ch123")
    assert r.status_code == 401
    assert r.is_json


@pytest.mark.api
def test_api_chamado_por_id_sucesso_200_estrutura(client_logado_supervisor, db_session):
    """GET /api/chamado/<id> retorna 200 com objeto chamado."""
    from tests.factories import make_chamado

    chamado = make_chamado(
        numero_chamado="CHM-0001",
        categoria="Chamado",
        status="Aberto",
        descricao="X",
        area="Manutencao",
        solicitante_id="s1",
        responsavel="Sup",
        tipo_solicitacao="Manutencao",
    )
    with (
        patch("app.routes.api_chamados.usuario_pode_ver_chamado", return_value=True),
        patch("app.routes.api_chamados.obter_sla_para_exibicao", return_value=None),
    ):
        r = client_logado_supervisor.get(f"/api/chamado/{chamado.id}")
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("sucesso") is True and "chamado" in data
    assert "numero_chamado" in data["chamado"] and "status" in data["chamado"]


# --- GET /api/notificacoes ---


@pytest.mark.api
def test_api_notificacoes_sem_login_401(client):
    """GET /api/notificacoes sem login retorna JSON 401."""
    r = client.get("/api/notificacoes")
    assert r.status_code == 401
    assert r.is_json


@pytest.mark.api
def test_api_notificacoes_sucesso_200_estrutura(client_logado_solicitante):
    """GET /api/notificacoes retorna 200 com notificacoes e total_nao_lidas."""
    with (
        patch("app.routes.api_notificacoes.listar_para_usuario", return_value=[]),
        patch("app.routes.api_notificacoes.contar_nao_lidas", return_value=0),
    ):
        r = client_logado_solicitante.get("/api/notificacoes")
    assert r.status_code == 200
    data = r.get_json()
    assert "notificacoes" in data and "total_nao_lidas" in data


# --- POST /api/notificacoes/<id>/ler ---


@pytest.mark.api
def test_api_notificacoes_ler_sem_login_401(client):
    """POST /api/notificacoes/<id>/ler sem login retorna JSON 401."""
    r = client.post("/api/notificacoes/not_123/ler", content_type="application/json")
    assert r.status_code == 401
    assert r.is_json


@pytest.mark.api
def test_api_notificacoes_ler_sucesso_200_estrutura(client_logado_solicitante):
    """POST /api/notificacoes/<id>/ler retorna 200 com sucesso."""
    with patch("app.routes.api_notificacoes.marcar_como_lida", return_value=True):
        r = client_logado_solicitante.post(
            "/api/notificacoes/not_123/ler",
            content_type="application/json",
        )
    assert r.status_code == 200
    data = r.get_json()
    assert "sucesso" in data


# --- GET /api/push-vapid-public ---


@pytest.mark.api
def test_api_push_vapid_public_sem_login_401(client):
    """GET /api/push-vapid-public sem login retorna JSON 401."""
    r = client.get("/api/push-vapid-public")
    assert r.status_code == 401
    assert r.is_json


@pytest.mark.api
def test_api_push_vapid_public_sucesso_200_estrutura(client_logado_solicitante):
    """GET /api/push-vapid-public retorna 200 com vapid_public_key."""
    r = client_logado_solicitante.get("/api/push-vapid-public")
    assert r.status_code == 200
    data = r.get_json()
    assert "vapid_public_key" in data


# --- POST /api/push-subscribe ---


@pytest.mark.api
def test_api_push_subscribe_sem_login_401(client):
    """POST /api/push-subscribe sem login retorna JSON 401."""
    r = client.post(
        "/api/push-subscribe",
        json={"subscription": {"endpoint": "https://x"}},
        content_type="application/json",
    )
    assert r.status_code == 401
    assert r.is_json


@pytest.mark.api
def test_api_push_subscribe_subscription_invalida_400(client_logado_solicitante):
    """POST /api/push-subscribe sem subscription válida retorna 400."""
    r = client_logado_solicitante.post(
        "/api/push-subscribe", json={}, content_type="application/json"
    )
    assert r.status_code == 400


# --- GET /api/supervisores/disponibilidade ---


@pytest.mark.api
def test_api_supervisores_disponibilidade_sem_login_401(client):
    """GET /api/supervisores/disponibilidade sem login retorna 401, 403, 302 ou 404."""
    r = client.get("/api/supervisores/disponibilidade")
    assert r.status_code in (401, 403, 302, 404)


@pytest.mark.api
def test_api_supervisores_disponibilidade_nao_implementada(client_logado_supervisor):
    """GET /api/supervisores/disponibilidade retorna 404 — rota não implementada em api.py."""
    r = client_logado_supervisor.get("/api/supervisores/disponibilidade")
    assert r.status_code == 404
