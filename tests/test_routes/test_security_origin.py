"""Testes de segurança: validação Origin/Referer em POST sensíveis (CSRF por origem)."""

import pytest

POSTS_API_PROTEGIDOS = [
    "/api/atualizar-status",
    "/api/chamado/ch1/transferir-area",
    "/api/chamado/ch1/previsao-atendimento",
    "/api/chamado/ch1/escalonar-colega",
    "/api/chamado/ch1/incluir-participantes",
    "/api/chamado/ch1/editar-solicitante",
    "/api/chamado/ch1/cancelar-solicitante",
    "/api/chamado/ch1/responder-solicitante",
]


def test_post_atualizar_status_sem_origin_com_app_base_url_retorna_403(app, client):
    """
    Quando APP_BASE_URL está definida, POST em /api/atualizar-status sem header Origin/Referer
    deve retornar 403 (origem não informada). A validação ocorre em before_request, antes do login.
    """
    app.config["APP_BASE_URL"] = "https://app.example.com"
    r = client.post(
        "/api/atualizar-status",
        json={"chamado_id": "ch1", "novo_status": "Em Atendimento"},
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 403
    data = r.get_json()
    assert data is not None and data.get("erro") == "Origem não informada"


def test_post_atualizar_status_origin_invalida_retorna_403(app, client):
    """
    Quando APP_BASE_URL está definida, POST com Origin de outro domínio retorna 403.
    """
    app.config["APP_BASE_URL"] = "https://app.example.com"
    r = client.post(
        "/api/atualizar-status",
        json={"chamado_id": "ch1", "novo_status": "Em Atendimento"},
        headers={
            "Content-Type": "application/json",
            "Origin": "https://evil.com",
        },
    )
    assert r.status_code == 403
    data = r.get_json()
    assert data is not None and data.get("erro") == "Origem não autorizada"


@pytest.mark.parametrize("rota", POSTS_API_PROTEGIDOS)
def test_todo_post_api_rejeita_origin_invalida(app, client, rota):
    app.config["APP_BASE_URL"] = "https://app.example.com"

    r = client.post(rota, json={}, headers={"Origin": "https://evil.example"})

    assert r.status_code == 403
    assert r.get_json()["erro"] == "Origem não autorizada"


@pytest.mark.parametrize("rota", POSTS_API_PROTEGIDOS)
def test_todo_post_api_aceita_origin_configurada(app, client, rota):
    app.config["APP_BASE_URL"] = "https://app.example.com"

    r = client.post(rota, json={}, headers={"Origin": "https://app.example.com"})

    assert r.status_code != 403 or r.get_json().get("erro") != "Origem não autorizada"


def test_csp_report_permanece_isento_da_validacao_de_origin(app, client):
    app.config["APP_BASE_URL"] = "https://app.example.com"

    r = client.post(
        "/api/csp-report",
        json={"csp-report": {"blocked-uri": "eval"}},
        headers={"Origin": "https://evil.example"},
    )

    assert r.status_code == 204


def test_post_api_preserva_comportamento_quando_app_base_url_vazia(app, client):
    app.config["APP_BASE_URL"] = ""

    r = client.post(
        "/api/chamado/ch1/transferir-area",
        json={},
        headers={"Origin": "https://evil.example"},
    )

    assert r.status_code == 401
