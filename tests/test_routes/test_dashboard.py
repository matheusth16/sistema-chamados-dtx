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


# ── POST /admin (alteração de status) ─────────────────────────────────────────


def test_admin_post_status_change_admin_sucesso(client_logado_admin):
    """POST /admin com admin altera status com sucesso e redireciona."""
    with patch("app.routes.dashboard.atualizar_status_chamado") as mock_atualizar:
        mock_atualizar.return_value = {"sucesso": True, "mensagem": "Status atualizado"}
        r = client_logado_admin.post(
            "/admin",
            data={"chamado_id": "ch1", "novo_status": "Concluído"},
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert "/admin" in (r.location or "")
    mock_atualizar.assert_called_once()


def test_admin_post_status_change_falha_exibe_erro(client_logado_admin):
    """POST /admin quando atualizar_status_chamado retorna sucesso=False redireciona."""
    with patch("app.routes.dashboard.atualizar_status_chamado") as mock_atualizar:
        mock_atualizar.return_value = {"sucesso": False, "erro": "Status inválido"}
        r = client_logado_admin.post(
            "/admin",
            data={"chamado_id": "ch1", "novo_status": "Invalido"},
            follow_redirects=False,
        )
    assert r.status_code == 302


def test_admin_post_status_change_supervisor_chamado_nao_encontrado(client_logado_supervisor):
    """POST /admin com supervisor quando chamado não existe redireciona."""
    with patch("app.routes.dashboard.db") as mock_db:
        mock_doc = MagicMock()
        mock_doc.exists = False
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        r = client_logado_supervisor.post(
            "/admin",
            data={"chamado_id": "ch_nao_existe", "novo_status": "Concluído"},
            follow_redirects=False,
        )
    assert r.status_code == 302


def test_admin_post_status_change_supervisor_sem_permissao_redireciona(client_logado_supervisor):
    """POST /admin com supervisor sem permissão na área redireciona."""
    with patch("app.routes.dashboard.db") as mock_db:
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {"area": "TI"}
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        with patch("app.routes.dashboard.supervisor_pode_alterar_chamado", return_value=False):
            r = client_logado_supervisor.post(
                "/admin",
                data={"chamado_id": "ch1", "novo_status": "Concluído"},
                follow_redirects=False,
            )
    assert r.status_code == 302


def test_admin_post_exception_redireciona(client_logado_admin):
    """POST /admin quando atualizar_status_chamado lança exceção redireciona."""
    with patch("app.routes.dashboard.atualizar_status_chamado", side_effect=Exception("timeout")):
        r = client_logado_admin.post(
            "/admin",
            data={"chamado_id": "ch1", "novo_status": "Concluído"},
            follow_redirects=False,
        )
    assert r.status_code == 302


# ── GET /chamado/<chamado_id> ─────────────────────────────────────────────────


def _chamado_dict_fake(solicitante_id="sol_x", area="Manutencao"):
    return {
        "numero_chamado": "001",
        "categoria": "TI",
        "tipo_solicitacao": "Corretiva",
        "descricao": "Teste",
        "responsavel": "Resp",
        "area": area,
        "solicitante_id": solicitante_id,
        "solicitante_nome": "Fulano",
        "responsavel_id": None,
        "status": "Aberto",
        "gate": None,
        "rl_codigo": None,
        "data_abertura": None,
        "data_conclusao": None,
        "sla_dias": None,
        "anexo": None,
    }


def test_visualizar_chamado_nao_encontrado_redireciona_admin(client_logado_admin):
    """GET /chamado/<id> quando chamado não existe redireciona para /admin."""
    with patch("app.routes.dashboard.db") as mock_db:
        mock_doc = MagicMock()
        mock_doc.exists = False
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        r = client_logado_admin.get("/chamado/naoexiste", follow_redirects=False)
    assert r.status_code == 302
    assert "/admin" in (r.location or "")


def test_visualizar_chamado_admin_com_permissao_retorna_200(client_logado_admin):
    """GET /chamado/<id> com admin que pode ver retorna 200."""
    with patch("app.routes.dashboard.db") as mock_db:
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = _chamado_dict_fake()
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        with (
            patch("app.routes.dashboard.usuario_pode_ver_chamado", return_value=True),
            patch("app.routes.dashboard.Usuario.get_all", return_value=[]),
            patch("app.routes.dashboard.filtrar_supervisores_por_area", return_value=[]),
            patch("app.routes.dashboard.CategoriaSetor.get_all", return_value=[]),
        ):
            r = client_logado_admin.get("/chamado/ch1", follow_redirects=False)
    assert r.status_code == 200


def test_visualizar_chamado_supervisor_sem_permissao_redireciona(client_logado_supervisor):
    """GET /chamado/<id> com supervisor sem permissão na área redireciona."""
    with patch("app.routes.dashboard.db") as mock_db:
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = _chamado_dict_fake(area="TI")
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        with patch("app.routes.dashboard.usuario_pode_ver_chamado", return_value=False):
            r = client_logado_supervisor.get("/chamado/ch1", follow_redirects=False)
    assert r.status_code == 302
    assert "/admin" in (r.location or "")


def test_visualizar_chamado_solicitante_proprio_retorna_200(client_logado_solicitante):
    """GET /chamado/<id> com solicitante visualizando o próprio chamado retorna 200."""
    with patch("app.routes.dashboard.db") as mock_db:
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = _chamado_dict_fake(solicitante_id="sol_1")
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        with patch("app.routes.dashboard.CategoriaSetor.get_all", return_value=[]):
            r = client_logado_solicitante.get("/chamado/ch1", follow_redirects=False)
    assert r.status_code == 200


def test_visualizar_chamado_solicitante_outro_redireciona(client_logado_solicitante):
    """GET /chamado/<id> com solicitante tentando ver chamado alheio redireciona."""
    with patch("app.routes.dashboard.db") as mock_db:
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = _chamado_dict_fake(solicitante_id="outro_id")
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        r = client_logado_solicitante.get("/chamado/ch1", follow_redirects=False)
    assert r.status_code == 302


def test_visualizar_chamado_exception_redireciona(client_logado_admin):
    """GET /chamado/<id> quando db lança exceção redireciona."""
    with patch("app.routes.dashboard.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.side_effect = Exception("db err")
        r = client_logado_admin.get("/chamado/ch_erro", follow_redirects=False)
    assert r.status_code == 302


# ── POST /chamado/editar ──────────────────────────────────────────────────────


def test_editar_chamado_solicitante_redireciona(client_logado_solicitante):
    """POST /chamado/editar com solicitante redireciona (sem permissão)."""
    r = client_logado_solicitante.post(
        "/chamado/editar",
        data={"chamado_id": "ch1", "novo_status": "Concluído"},
        follow_redirects=False,
    )
    assert r.status_code == 302


def test_editar_chamado_sem_id_redireciona(client_logado_admin):
    """POST /chamado/editar sem chamado_id redireciona para /admin."""
    r = client_logado_admin.post(
        "/chamado/editar",
        data={"novo_status": "Concluído"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert "/admin" in (r.location or "")


def test_editar_chamado_nao_encontrado_redireciona(client_logado_admin):
    """POST /chamado/editar quando chamado não existe redireciona para /admin."""
    with patch("app.routes.dashboard.db") as mock_db:
        mock_doc = MagicMock()
        mock_doc.exists = False
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        r = client_logado_admin.post(
            "/chamado/editar",
            data={"chamado_id": "naoexiste", "novo_status": "Concluído"},
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert "/admin" in (r.location or "")


def test_editar_chamado_sem_permissao_redireciona(client_logado_admin):
    """POST /chamado/editar quando usuario_pode_ver_chamado=False redireciona."""
    with patch("app.routes.dashboard.db") as mock_db:
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = _chamado_dict_fake()
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        with patch("app.routes.dashboard.usuario_pode_ver_chamado", return_value=False):
            r = client_logado_admin.post(
                "/chamado/editar",
                data={"chamado_id": "ch1", "novo_status": "Concluído"},
                follow_redirects=False,
            )
    assert r.status_code == 302
    assert "/admin" in (r.location or "")


def test_editar_chamado_sucesso_redireciona_para_detalhe(client_logado_admin):
    """POST /chamado/editar com dados válidos chama serviço e redireciona para o chamado."""
    with patch("app.routes.dashboard.db") as mock_db:
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = _chamado_dict_fake()
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        with (
            patch("app.routes.dashboard.usuario_pode_ver_chamado", return_value=True),
            patch(
                "app.services.edicao_chamado_service.processar_edicao_chamado",
                return_value={"sucesso": True, "mensagem": "Salvo"},
            ),
        ):
            r = client_logado_admin.post(
                "/chamado/editar",
                data={"chamado_id": "ch1", "novo_status": "Concluído"},
                follow_redirects=False,
            )
    assert r.status_code == 302
    assert "ch1" in (r.location or "")
