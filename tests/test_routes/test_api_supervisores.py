"""
Testes do endpoint GET /api/supervisores/lista.
Cobre filtragem do usuário logado da lista (anti-self-assignment).
"""

from unittest.mock import MagicMock, patch


def _sup_mock(uid, nome, email):
    u = MagicMock()
    u.id = uid
    u.nome = nome
    u.email = email
    return u


def test_supervisores_lista_exclui_usuario_logado(client_logado_supervisor):
    """
    RED: /api/supervisores/lista não deve incluir o próprio usuário logado
    na lista de supervisores disponíveis para atribuição.
    """
    sup_logado = _sup_mock("sup_1", "Supervisor Teste", "sup@test.com")
    sup_outro = _sup_mock("sup_2", "Outro Supervisor", "outro@test.com")

    with patch(
        "app.routes.api.Usuario.get_supervisores_por_area", return_value=[sup_logado, sup_outro]
    ):
        r = client_logado_supervisor.get("/api/supervisores/lista?area=Manutencao")

    assert r.status_code == 200
    data = r.get_json()
    assert data["sucesso"] is True

    ids_retornados = [s["id"] for s in data["supervisores"]]
    assert "sup_1" not in ids_retornados, (
        "O usuário logado (sup_1) não deve aparecer na lista de supervisores disponíveis"
    )
    assert "sup_2" in ids_retornados


def test_supervisores_lista_area_sem_supervisores_retorna_lista_vazia(client_logado_supervisor):
    """Área sem supervisores → lista vazia, sem erro."""
    with patch("app.routes.api.Usuario.get_supervisores_por_area", return_value=[]):
        r = client_logado_supervisor.get("/api/supervisores/lista?area=Inexistente")

    assert r.status_code == 200
    data = r.get_json()
    assert data["sucesso"] is True
    assert data["supervisores"] == []


def test_supervisores_lista_quando_unico_supervisor_e_o_proprio_logado_retorna_vazio(
    client_logado_supervisor,
):
    """
    Se o único supervisor da área for o próprio usuário logado,
    a lista retornada deve ser vazia (não self-assign).
    """
    sup_logado = _sup_mock("sup_1", "Supervisor Teste", "sup@test.com")

    with patch("app.routes.api.Usuario.get_supervisores_por_area", return_value=[sup_logado]):
        r = client_logado_supervisor.get("/api/supervisores/lista?area=Manutencao")

    assert r.status_code == 200
    data = r.get_json()
    assert data["supervisores"] == []


def test_supervisores_lista_sem_login_retorna_redirect(client):
    """Sem autenticação → redirect para login (302)."""
    r = client.get("/api/supervisores/lista?area=Manutencao")
    assert r.status_code in (302, 401)
