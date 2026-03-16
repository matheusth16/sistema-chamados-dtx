"""Testes de integração: fluxo de criação de chamado (POST /)."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def usuario_solicitante():
    u = MagicMock()
    u.id = "sol_1"
    u.email = "sol@test.com"
    u.nome = "Solicitante Teste"
    u.perfil = "solicitante"
    u.area = "Planejamento"
    u.is_authenticated = True
    return u


def test_criar_chamado_sem_login_redireciona(client):
    """POST / (criar chamado) sem login redireciona para login."""
    r = client.post(
        "/",
        data={
            "csrf_token": "ignored",
            "categoria": "Nao Aplicavel",
            "tipo": "Planejamento",
            "gate": "N/A",
            "impacto": "Prazo",
            "descricao": "Teste integração",
        },
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert "login" in r.location


def test_criar_chamado_com_login_e_dados_validos_redireciona(client_logado_solicitante):
    """POST / com usuário logado e dados válidos processa e redireciona (mock criar_chamado)."""
    with patch("app.routes.chamados.criar_chamado") as mock_criar:
        mock_criar.return_value = ("doc_id_123", "CHM-9999", None, None)
        r = client_logado_solicitante.post(
            "/",
            data={
                "categoria": "Nao Aplicavel",
                "tipo": "Planejamento",
                "gate": "N/A",
                "impacto": "Prazo",
                "descricao": "Teste integração",
            },
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert r.location and ("/" in r.location or "admin" in r.location or "chamado" in r.location)


def test_criar_chamado_com_supervisor_redireciona_e_salva_com_solicitante_id_do_supervisor(
    client_logado_supervisor,
):
    """POST / com supervisor logado chama criar_chamado com solicitante_id do supervisor."""
    with patch("app.routes.chamados.criar_chamado") as mock_criar:
        mock_criar.return_value = ("doc_id_456", "CHM-8888", None, None)
        r = client_logado_supervisor.post(
            "/",
            data={
                "categoria": "Nao Aplicavel",
                "tipo": "Planejamento",
                "gate": "N/A",
                "impacto": "Prazo",
                "descricao": "Chamado criado por supervisor",
            },
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert r.location
    mock_criar.assert_called_once()
    call_kw = mock_criar.call_args[1]
    assert call_kw.get("solicitante_id") == "sup_1"
    assert call_kw.get("solicitante_nome") == "Supervisor Teste"
