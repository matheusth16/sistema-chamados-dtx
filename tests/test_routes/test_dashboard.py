"""Testes das rotas do dashboard: /admin, /exportar, /admin/relatorios, /chamado/<id>/historico, /admin/indices-firestore."""

from unittest.mock import MagicMock, patch


def test_admin_sem_login_redireciona(client):
    """GET /admin sem login redireciona para /login."""
    r = client.get("/admin", follow_redirects=False)
    assert r.status_code == 302
    assert "login" in (r.location or "").lower()


def test_admin_com_solicitante_nao_acessa(client_logado_solicitante):
    """GET /admin com perfil solicitante não acessa: 403 ou redirect."""
    r = client_logado_solicitante.get("/admin", follow_redirects=False)
    assert r.status_code in (302, 403)
    if r.status_code == 302:
        assert "/admin" not in (r.location or "")


def test_admin_com_supervisor_retorna_200(client_logado_supervisor):
    """GET /admin com supervisor retorna 200 e página do dashboard (mock contexto)."""
    with patch("app.routes.dashboard.obter_contexto_admin") as mock_ctx:
        mock_ctx.return_value = {
            "chamados": [],
            "gates": [],
            "responsaveis": [],
            "sla_map": {},
            "tem_proxima": False,
            "tem_anterior": False,
            "proximo_cursor": None,
            "cursor_anterior": None,
        }
        r = client_logado_supervisor.get("/admin", follow_redirects=False)
    assert r.status_code == 200
    mock_ctx.assert_called_once()


def test_admin_com_admin_retorna_200(client_logado_admin):
    """GET /admin com admin retorna 200."""
    with patch("app.routes.dashboard.obter_contexto_admin") as mock_ctx:
        mock_ctx.return_value = {
            "chamados": [],
            "gates": [],
            "responsaveis": [],
            "sla_map": {},
            "tem_proxima": False,
            "tem_anterior": False,
            "proximo_cursor": None,
            "cursor_anterior": None,
        }
        r = client_logado_admin.get("/admin", follow_redirects=False)
    assert r.status_code == 200


def test_exportar_sem_login_redireciona(client):
    """GET /exportar sem login redireciona para login."""
    r = client.get("/exportar", follow_redirects=False)
    assert r.status_code == 302
    assert "login" in (r.location or "").lower()


def test_exportar_com_supervisor_retorna_200_ou_redirect(client_logado_supervisor):
    """GET /exportar com supervisor retorna 200 (arquivo) ou redirect em caso de erro (mock)."""
    with patch("app.routes.dashboard.aplicar_filtros_dashboard_com_paginacao") as mock_filtros:
        mock_doc = MagicMock()
        mock_doc.to_dict.return_value = {}
        mock_doc.id = "doc1"
        mock_filtros.return_value = {"docs": [mock_doc]}
        with patch("app.routes.dashboard._filtrar_chamados_por_permissao") as mock_filtrar:
            mock_filtrar.return_value = []
            r = client_logado_supervisor.get("/exportar", follow_redirects=False)
    assert r.status_code in (200, 302)
    if r.status_code == 200:
        ct = r.headers.get("Content-Type", "")
        assert "spreadsheet" in ct or "excel" in ct or "octet" in ct.lower()


def test_relatorios_sem_login_redireciona(client):
    """GET /admin/relatorios sem login redireciona para login."""
    r = client.get("/admin/relatorios", follow_redirects=False)
    assert r.status_code == 302
    assert "login" in (r.location or "").lower()


def test_relatorios_com_admin_retorna_200(client_logado_admin):
    """GET /admin/relatorios com admin retorna 200 (mock analytics)."""
    with patch("app.routes.dashboard.analisador") as mock_anal:
        mock_anal.obter_relatorio_completo.return_value = {
            "data_geracao": None,
            "metricas_gerais": {},
            "metricas_supervisores": [],
            "metricas_areas": [],
            "insights": [],
        }
        with patch("app.routes.dashboard.Usuario.get_all", return_value=[]):
            r = client_logado_admin.get("/admin/relatorios", follow_redirects=False)
    assert r.status_code == 200
    assert b"relat" in r.data.lower() or b"report" in r.data.lower() or b"anal" in r.data.lower()


def test_historico_sem_login_redireciona(client):
    """GET /chamado/<id>/historico sem login redireciona para login."""
    r = client.get("/chamado/abc123/historico", follow_redirects=False)
    assert r.status_code == 302
    assert "login" in (r.location or "").lower()


def test_historico_com_supervisor_permissao_retorna_200(client_logado_supervisor):
    """GET /chamado/<id>/historico com supervisor que pode ver o chamado retorna 200 (mock)."""
    with patch("app.routes.dashboard.db") as mock_db:
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            "numero_chamado": "001",
            "categoria": "Manutencao",
            "tipo_solicitacao": "Corretiva",
            "descricao": "Teste",
            "responsavel": "",
            "area": "Manutencao",
            "solicitante_id": "sol1",
            "responsavel_id": None,
        }
        mock_doc.id = "ch1"
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        with (
            patch("app.routes.dashboard.usuario_pode_ver_chamado", return_value=True),
            patch("app.routes.dashboard.Historico.get_by_chamado_id", return_value=[]),
        ):
            r = client_logado_supervisor.get("/chamado/ch1/historico", follow_redirects=False)
    assert r.status_code == 200


def test_indices_firestore_sem_login_redireciona(client):
    """GET /admin/indices-firestore sem login redireciona para login."""
    r = client.get("/admin/indices-firestore", follow_redirects=False)
    assert r.status_code == 302
    assert "login" in (r.location or "").lower()


def test_indices_firestore_com_admin_retorna_200(client_logado_admin):
    """GET /admin/indices-firestore com admin retorna 200."""
    r = client_logado_admin.get("/admin/indices-firestore", follow_redirects=False)
    assert r.status_code == 200
    assert (
        b"indice" in r.data.lower() or b"firestore" in r.data.lower() or b"index" in r.data.lower()
    )


def test_indices_firestore_com_solicitante_redireciona(client_logado_solicitante):
    """GET /admin/indices-firestore com solicitante redireciona (rota requer perfil admin)."""
    r = client_logado_solicitante.get("/admin/indices-firestore", follow_redirects=False)
    assert r.status_code == 302
    # Solicitante é redirecionado para main.index (/), não para a página de índices
    assert r.location and "/admin/indices-firestore" not in (r.location or "")
