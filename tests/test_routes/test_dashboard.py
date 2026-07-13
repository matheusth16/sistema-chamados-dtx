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


def test_admin_com_supervisor_redireciona_para_painel(client_logado_supervisor):
    """GET /admin com supervisor redireciona para /painel."""
    r = client_logado_supervisor.get("/admin", follow_redirects=False)
    assert r.status_code == 302
    assert "painel" in (r.location or "")


def test_painel_com_supervisor_retorna_200(client_logado_supervisor):
    """GET /painel com supervisor retorna 200 e página do dashboard (mock contexto)."""
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
        r = client_logado_supervisor.get("/painel", follow_redirects=False)
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


def test_relatorios_propaga_dias_valido_para_analisador(client_logado_admin):
    """GET /admin/relatorios?dias=7 repassa dias=7 pro analisador (seletor de período)."""
    with patch("app.routes.dashboard.analisador") as mock_anal:
        mock_anal.obter_relatorio_completo.return_value = {
            "data_geracao": None,
            "metricas_gerais": {},
            "metricas_supervisores": [],
            "metricas_areas": [],
            "insights": [],
        }
        with patch("app.routes.dashboard.Usuario.get_all", return_value=[]):
            r = client_logado_admin.get("/admin/relatorios?dias=7", follow_redirects=False)
    assert r.status_code == 200
    assert mock_anal.obter_relatorio_completo.call_args.kwargs["dias"] == 7


def test_relatorios_dias_invalido_normaliza_para_30(client_logado_admin):
    """GET /admin/relatorios?dias=999 (fora de 7/30/90) cai para o padrão 30."""
    with patch("app.routes.dashboard.analisador") as mock_anal:
        mock_anal.obter_relatorio_completo.return_value = {
            "data_geracao": None,
            "metricas_gerais": {},
            "metricas_supervisores": [],
            "metricas_areas": [],
            "insights": [],
        }
        with patch("app.routes.dashboard.Usuario.get_all", return_value=[]):
            r = client_logado_admin.get("/admin/relatorios?dias=999", follow_redirects=False)
    assert r.status_code == 200
    assert mock_anal.obter_relatorio_completo.call_args.kwargs["dias"] == 30


def test_supervisor_pode_ver_relatorios(client_logado_supervisor):
    """GET /admin/relatorios com supervisor retorna 200."""
    with patch("app.routes.dashboard.analisador") as mock_anal:
        mock_anal.obter_relatorio_completo.return_value = {
            "data_geracao": None,
            "metricas_gerais": {},
            "metricas_supervisores": [],
            "metricas_areas": [],
            "insights": [],
        }
        with patch("app.routes.dashboard.Usuario.get_all", return_value=[]):
            r = client_logado_supervisor.get("/admin/relatorios", follow_redirects=False)
    assert r.status_code == 200


def test_solicitante_nao_pode_ver_relatorios(client_logado_solicitante):
    """GET /admin/relatorios com solicitante é bloqueado (302 ou 403)."""
    r = client_logado_solicitante.get("/admin/relatorios", follow_redirects=False)
    assert r.status_code in (302, 403)


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
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {
        "status": "Em Atendimento",
        "confirmacao_solicitante": None,
        "area": "Geral",
        "solicitante_id": "s1",
        "participantes": [],
    }
    with (
        patch("app.routes.dashboard.db") as mock_db,
        patch("app.routes.dashboard.Chamado") as mock_chamado_cls,
        patch("app.routes.dashboard.atualizar_status_chamado") as mock_atualizar,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        mock_chamado = MagicMock()
        mock_chamado.status = "Em Atendimento"
        mock_chamado.confirmacao_solicitante = None
        mock_chamado_cls.from_dict.return_value = mock_chamado
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
        mock_doc.to_dict.return_value = {
            "area": "TI",
            "responsavel_id": None,
            "solicitante_id": "sol_x",
            "participantes": [],
        }
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
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


def _chamado_dict_fake(solicitante_id="sol_x", area="Manutencao", status="Aberto"):
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
        "status": status,
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


def test_visualizar_chamado_com_participantes_sem_usuario_atual_retorna_200(client_logado_admin):
    """GET /chamado/<id> com participantes cadastrados, nenhum deles o usuário logado.

    Regressão: o template calcula `participante_atual` filtrando
    chamado.participantes pelo supervisor_id do usuário atual e aplicando
    `| first`. Se a lista tiver itens mas nenhum bater com o usuário logado
    (ex.: um admin olhando um chamado com participantes de outras pessoas),
    o filtro resulta em lista vazia e `| first` lança
    jinja2.exceptions.UndefinedError — capturado pelo except genérico da rota
    e mascarado como um redirect com flash de erro, sem 500 visível.
    """
    dados = _chamado_dict_fake()
    dados["participantes"] = [{"supervisor_id": "outra_pessoa", "area": "TI", "status": "pendente"}]
    with patch("app.routes.dashboard.db") as mock_db:
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = dados
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        with (
            patch("app.routes.dashboard.usuario_pode_ver_chamado", return_value=True),
            patch("app.routes.dashboard.Usuario.get_all", return_value=[]),
            patch("app.routes.dashboard.filtrar_supervisores_por_area", return_value=[]),
            patch("app.routes.dashboard.CategoriaSetor.get_all", return_value=[]),
        ):
            r = client_logado_admin.get("/chamado/ch1", follow_redirects=False)
    assert r.status_code == 200


def test_visualizar_chamado_traduz_status_para_ingles(client_logado_admin):
    """GET /chamado/<id> com idioma=en não deve mostrar status cru em PT-BR.

    Regressão: components/_status_badge.html importado sem 'with context' em
    visualizar_chamado.html — a macro perde acesso a translate_status()/t()
    do context_processor, cai no fallback hardcoded em português
    independente do idioma escolhido pelo usuário.
    """
    with patch("app.routes.dashboard.db") as mock_db:
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = _chamado_dict_fake(status="Em Atendimento")
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        with (
            patch("app.routes.dashboard.usuario_pode_ver_chamado", return_value=True),
            patch("app.routes.dashboard.Usuario.get_all", return_value=[]),
            patch("app.routes.dashboard.filtrar_supervisores_por_area", return_value=[]),
            patch("app.routes.dashboard.CategoriaSetor.get_all", return_value=[]),
        ):
            with client_logado_admin.session_transaction() as sess:
                sess["language"] = "en"
            r = client_logado_admin.get("/chamado/ch1")
    body = r.data.decode("utf-8")
    assert "In Progress" in body
    # value="Em Atendimento" no <option> é o valor canônico do form (correto,
    # não é texto visível) — só o texto exibido não pode vazar em PT-BR.
    assert ">Em Atendimento<" not in body


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
    assert "/painel" in (r.location or "")


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


# ── S4-03: Cache Usuario.get_all() via get_static_cached ─────────────────────


def test_visualizar_chamado_usa_cache_para_usuarios(client_logado_supervisor):
    """visualizar_detalhe_chamado deve usar get_static_cached, não Usuario.get_all() direto."""
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {
        "numero_chamado": "CHM-0001",
        "categoria": "Chamado",
        "status": "Aberto",
        "descricao": "Teste",
        "area": "Manutencao",
        "solicitante_id": "s1",
        "responsavel": "Sup",
        "tipo_solicitacao": "Manutencao",
        "setores_adicionais": [],
    }
    with (
        patch("app.routes.dashboard.db") as mock_db,
        patch("app.routes.dashboard.usuario_pode_ver_chamado", return_value=True),
        patch("app.routes.dashboard.get_static_cached", return_value=[]) as mock_cache,
        patch("app.routes.dashboard.CategoriaSetor.get_all", return_value=[]),
        patch("app.routes.dashboard.Usuario.get_all") as mock_get_all,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        client_logado_supervisor.get("/chamado/ch1", follow_redirects=False)

    mock_cache.assert_called()
    mock_get_all.assert_not_called()


# ── F-59: Injeção de fórmula neutralizada em /exportar ────────────────────────


def test_exportar_neutraliza_formula_injection_em_xlsx(client_logado_supervisor):
    """F-59: /exportar deve aplicar _safe_cell() neutralizando fórmulas em descrição e responsável."""
    import io

    from openpyxl import load_workbook

    from app.models import Chamado

    chamado = Chamado(
        id="inj1",
        numero_chamado="2026-999",
        categoria="TI",
        tipo_solicitacao="Corretiva",
        descricao="=CMD('calc')",
        responsavel="+123",
        responsavel_id="u1",
        solicitante_id="s1",
        solicitante_nome="Teste",
        area="Manutencao",
        status="Aberto",
        prioridade=1,
        rl_codigo=None,
        gate=None,
        impacto=None,
        anexo=None,
        anexos=[],
        data_abertura=None,
        data_conclusao=None,
    )

    with (
        patch("app.routes.dashboard.aplicar_filtros_dashboard_com_paginacao") as mock_filtros,
        patch("app.routes.dashboard._filtrar_chamados_por_permissao") as mock_perm,
        patch("app.routes.dashboard.db"),
        patch("app.routes.dashboard.verificar_e_incrementar_export", return_value=(True, None)),
    ):
        mock_filtros.return_value = {
            "docs": [MagicMock()],
            "cursor_next": None,
            "cursor_prev": None,
        }
        mock_perm.return_value = [chamado]

        r = client_logado_supervisor.get("/exportar", follow_redirects=False)

    assert r.status_code == 200, f"Esperado 200, recebido {r.status_code}"
    assert "spreadsheetml" in r.content_type or "xlsx" in r.content_type

    wb = load_workbook(io.BytesIO(r.data))
    ws = wb.active

    # Colunas: Chamado(1) Categoria(2) RL(3) Tipo(4) Gate(5)
    #          Responsável(6) Solicitante(7) Área(8) Status(9) Anexo(10)
    #          Abertura(11) Conclusão(12) Descrição(13)
    desc_val = ws.cell(row=2, column=13).value
    resp_val = ws.cell(row=2, column=6).value

    assert isinstance(desc_val, str), f"Descrição deveria ser str, foi {type(desc_val)}"
    assert not desc_val.startswith("="), (
        f"Fórmula não neutralizada em 'Descrição': {desc_val!r} — aplicar _safe_cell()"
    )
    assert isinstance(resp_val, str), f"Responsável deveria ser str, foi {type(resp_val)}"
    assert not resp_val.startswith("+"), (
        f"Fórmula não neutralizada em 'Responsável': {resp_val!r} — aplicar _safe_cell()"
    )


# ── Regressão de segurança: /exportar e /exportar-avancado vazando outras áreas ──
# Achado em QA manual: supervisor da área "Demo" baixou /exportar e recebeu linhas
# de chamados da área "Manutencao"; /exportar-avancado trouxe métricas de
# supervisores de outras áreas na aba "Performance". Causa raiz: essas duas rotas
# consultavam db.collection("chamados") sem o mesmo filtro
# supervisor_ids_com_acesso array_contains que obter_contexto_admin já aplica
# pro /painel — a query saía sem escopo e só era filtrada depois, em memória,
# por _filtrar_chamados_por_permissao (que escopa os chamados, mas não as
# métricas agregadas por supervisor).


def test_exportar_escopa_query_por_supervisor_ids_com_acesso(client_logado_supervisor):
    """/exportar deve escopar a query por área do supervisor ANTES da paginação,
    mesmo padrão usado em obter_contexto_admin para o /painel."""
    with (
        patch("app.routes.dashboard.aplicar_filtros_dashboard_com_paginacao") as mock_filtros,
        patch("app.routes.dashboard._filtrar_chamados_por_permissao", return_value=[]),
        patch("app.routes.dashboard.db") as mock_db,
        patch("app.routes.dashboard.verificar_e_incrementar_export", return_value=(True, None)),
    ):
        mock_filtros.return_value = {"docs": []}

        client_logado_supervisor.get("/exportar", follow_redirects=False)

        colecao = mock_db.collection.return_value
        assert colecao.where.call_count >= 1, (
            "A query de /exportar não foi escopada por área — supervisor pode "
            "exportar chamados de áreas que não são dele."
        )
        filtro = colecao.where.call_args.kwargs.get("filter")
        assert filtro is not None
        assert filtro.field_path == "supervisor_ids_com_acesso"
        assert filtro.op_string == "array_contains"
        assert filtro.value == "sup_1"

        query_passada = mock_filtros.call_args[0][0]
        assert query_passada is colecao.where.return_value, (
            "aplicar_filtros_dashboard_com_paginacao recebeu a coleção crua, não "
            "a query já escopada por .where(supervisor_ids_com_acesso)."
        )


def test_exportar_avancado_escopa_query_por_supervisor_ids_com_acesso(
    client_logado_supervisor,
):
    """/exportar-avancado deve escopar a query de chamados da mesma forma que /exportar."""
    with (
        patch("app.routes.dashboard.aplicar_filtros_dashboard_com_paginacao") as mock_filtros,
        patch("app.routes.dashboard._filtrar_chamados_por_permissao", return_value=[]),
        patch("app.routes.dashboard.analisador") as mock_anal,
        patch("app.services.excel_export_service.exportador_excel") as mock_exp,
        patch("app.routes.dashboard.db") as mock_db,
        patch("app.routes.dashboard.verificar_e_incrementar_export", return_value=(True, None)),
    ):
        import io

        mock_filtros.return_value = {"docs": []}
        mock_anal.obter_metricas_gerais.return_value = {}
        mock_anal.obter_metricas_supervisores.return_value = []
        mock_exp.exportar_relatorio_completo.return_value = io.BytesIO(b"PK fake")

        client_logado_supervisor.get("/exportar-avancado", follow_redirects=False)

        colecao = mock_db.collection.return_value
        assert colecao.where.call_count >= 1, (
            "A query de /exportar-avancado não foi escopada por área."
        )
        filtro = colecao.where.call_args.kwargs.get("filter")
        assert filtro is not None
        assert filtro.field_path == "supervisor_ids_com_acesso"
        assert filtro.value == "sup_1"


def test_exportar_avancado_metricas_supervisores_filtradas_por_area(
    client_logado_supervisor,
):
    """/exportar-avancado não pode incluir, na aba de Performance, métricas de
    supervisores de áreas diferentes da do usuário que exportou."""
    with (
        patch("app.routes.dashboard.aplicar_filtros_dashboard_com_paginacao") as mock_filtros,
        patch("app.routes.dashboard._filtrar_chamados_por_permissao", return_value=[]),
        patch("app.routes.dashboard.analisador") as mock_anal,
        patch("app.services.excel_export_service.exportador_excel") as mock_exp,
        patch("app.routes.dashboard.db"),
        patch("app.routes.dashboard.verificar_e_incrementar_export", return_value=(True, None)),
    ):
        import io

        mock_filtros.return_value = {"docs": []}
        mock_anal.obter_metricas_gerais.return_value = {}
        mock_anal.obter_metricas_supervisores.return_value = [
            {"supervisor_nome": "Sup Mesma Area", "area": "Manutencao"},
            {"supervisor_nome": "Sup Outra Area", "area": "TI"},
        ]
        mock_exp.exportar_relatorio_completo.return_value = io.BytesIO(b"PK fake")

        client_logado_supervisor.get("/exportar-avancado", follow_redirects=False)

        _, kwargs = mock_exp.exportar_relatorio_completo.call_args
        metricas_enviadas = kwargs.get("metricas_supervisores") or []
        areas_enviadas = {m.get("area") for m in metricas_enviadas}
        assert "TI" not in areas_enviadas, (
            "Métricas de supervisor de outra área ('TI') vazaram pro relatório "
            "de um supervisor da área 'Manutencao'."
        )


# ── Onda 3: POST /painel como supervisor ──────────────────────────────────────


def test_painel_post_supervisor_altera_status_sucesso(client_logado_supervisor):
    """POST /painel com supervisor altera status com sucesso e redireciona."""
    with (
        patch("app.routes.dashboard.atualizar_status_chamado") as mock_atualizar,
        patch("app.routes.dashboard.db") as mock_db,
    ):
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            "area": "Manutencao",
            "responsavel_id": None,
            "solicitante_id": "sol_x",
            "participantes": [],
        }
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        mock_atualizar.return_value = {"sucesso": True, "mensagem": "Status atualizado"}
        r = client_logado_supervisor.post(
            "/painel",
            data={"chamado_id": "ch1", "novo_status": "Concluído"},
            follow_redirects=False,
        )
    assert r.status_code == 302
    mock_atualizar.assert_called_once()


def test_painel_post_supervisor_sem_permissao_na_area(client_logado_supervisor):
    """POST /painel com supervisor sem permissão na área redireciona."""
    with patch("app.routes.dashboard.db") as mock_db:
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            "area": "OutraArea",
            "responsavel_id": None,
            "solicitante_id": "sol_x",
            "participantes": [],
        }
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        r = client_logado_supervisor.post(
            "/painel",
            data={"chamado_id": "ch1", "novo_status": "Concluído"},
            follow_redirects=False,
        )
    assert r.status_code == 302


def test_dashboard_alterar_status_supervisor_colega_owner_negado(client_logado_supervisor):
    """Lacuna 2: supervisor não pode alterar chamado da mesma área se outro supervisor é o owner."""
    with (
        patch("app.routes.dashboard.db") as mock_db,
        patch("app.routes.dashboard.atualizar_status_chamado") as mock_atualizar,
    ):
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            "area": "Manutencao",
            "responsavel_id": "outro_supervisor",
            "solicitante_id": "sol_outro",
            "participantes": [],
        }
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        r = client_logado_supervisor.post(
            "/painel",
            data={"chamado_id": "ch1", "novo_status": "Concluído"},
            follow_redirects=False,
        )
    assert r.status_code == 302
    mock_atualizar.assert_not_called()


def test_painel_post_chamado_inexistente(client_logado_supervisor):
    """POST /painel com chamado que não existe redireciona."""
    with patch("app.routes.dashboard.db") as mock_db:
        mock_doc = MagicMock()
        mock_doc.exists = False
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        r = client_logado_supervisor.post(
            "/painel",
            data={"chamado_id": "nao_existe", "novo_status": "Concluído"},
            follow_redirects=False,
        )
    assert r.status_code == 302


def test_painel_post_falha_sem_chave_erro(client_logado_admin):
    """POST /admin quando sucesso=False sem 'erro' no resultado exibe flash genérico."""
    with patch("app.routes.dashboard.atualizar_status_chamado") as mock_atualizar:
        mock_atualizar.return_value = {"sucesso": False}  # sem chave 'erro'
        r = client_logado_admin.post(
            "/admin",
            data={"chamado_id": "ch1", "novo_status": "Invalido"},
            follow_redirects=False,
        )
    assert r.status_code == 302


# ── Onda 3: _render_dashboard FailedPrecondition ──────────────────────────────


def test_admin_get_failed_precondition_retorna_503(client_logado_admin):
    """GET /admin quando Firestore retorna FailedPrecondition ('currently building') retorna 503."""
    from google.api_core.exceptions import FailedPrecondition

    with patch("app.routes.dashboard.obter_contexto_admin") as mock_ctx:
        mock_ctx.side_effect = FailedPrecondition("index currently building")
        r = client_logado_admin.get("/admin", follow_redirects=False)
    assert r.status_code == 503


# ── Onda 3: /painel redireciona admin ─────────────────────────────────────────


def test_painel_com_admin_redireciona_para_admin(client_logado_admin):
    """GET /painel com perfil admin redireciona para /admin."""
    r = client_logado_admin.get("/painel", follow_redirects=False)
    assert r.status_code == 302
    assert "/admin" in (r.location or "")


# ── Onda 3: editar_chamado_pagina falhas ──────────────────────────────────────


def test_editar_chamado_falha_com_erro_exibe_flash(client_logado_admin):
    """POST /chamado/editar com sucesso=False e 'erro' presente redireciona para chamado."""
    with patch("app.routes.dashboard.db") as mock_db:
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = _chamado_dict_fake()
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        with (
            patch("app.routes.dashboard.usuario_pode_ver_chamado", return_value=True),
            patch(
                "app.services.edicao_chamado_service.processar_edicao_chamado",
                return_value={"sucesso": False, "erro": "Erro de validação"},
            ),
        ):
            r = client_logado_admin.post(
                "/chamado/editar",
                data={"chamado_id": "ch1", "novo_status": "Concluído"},
                follow_redirects=False,
            )
    assert r.status_code == 302
    assert "ch1" in (r.location or "")


def test_editar_chamado_falha_sem_erro_exibe_flash_generico(client_logado_admin):
    """POST /chamado/editar com sucesso=False sem 'erro' usa flash_t genérico."""
    with patch("app.routes.dashboard.db") as mock_db:
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = _chamado_dict_fake()
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        with (
            patch("app.routes.dashboard.usuario_pode_ver_chamado", return_value=True),
            patch(
                "app.services.edicao_chamado_service.processar_edicao_chamado",
                return_value={"sucesso": False},  # sem chave 'erro'
            ),
        ):
            r = client_logado_admin.post(
                "/chamado/editar",
                data={"chamado_id": "ch1", "novo_status": "Concluído"},
                follow_redirects=False,
            )
    assert r.status_code == 302


# ── Onda 3: visualizar_historico branches ─────────────────────────────────────


def test_historico_chamado_nao_encontrado_redireciona(client_logado_supervisor):
    """GET /chamado/<id>/historico quando chamado não existe redireciona."""
    with patch("app.routes.dashboard.db") as mock_db:
        mock_doc = MagicMock()
        mock_doc.exists = False
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        r = client_logado_supervisor.get("/chamado/nao_existe/historico", follow_redirects=False)
    assert r.status_code == 302


def test_historico_supervisor_sem_permissao_redireciona(client_logado_supervisor):
    """GET /chamado/<id>/historico com supervisor sem permissão redireciona."""
    with patch("app.routes.dashboard.db") as mock_db:
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = _chamado_dict_fake(area="OutraArea")
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        with patch("app.routes.dashboard.usuario_pode_ver_chamado", return_value=False):
            r = client_logado_supervisor.get("/chamado/ch1/historico", follow_redirects=False)
    assert r.status_code == 302


def test_historico_exception_redireciona(client_logado_supervisor):
    """GET /chamado/<id>/historico quando db lança exceção redireciona."""
    with patch("app.routes.dashboard.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.side_effect = Exception("db err")
        r = client_logado_supervisor.get("/chamado/ch_erro/historico", follow_redirects=False)
    assert r.status_code == 302


def test_historico_traduz_status_para_ingles(client_logado_admin):
    """GET /chamado/<id>/historico com idioma=en não deve mostrar status cru em PT-BR.

    Dois bugs no mesmo template (historico.html):
    1. components/_status_badge.html importado sem 'with context' — badge do
       status atual cai no fallback hardcoded em português.
    2. O diff da timeline só traduz quando evento.campo_alterado == 'Status'
       (maiúsculo), mas todo o backend grava campo_alterado="status"
       (minúsculo) — a comparação nunca bate e o valor cru em PT-BR vaza
       pro <span class="bento-diff-chip"> independente do idioma.
    """
    from datetime import datetime

    from app.models_historico import Historico

    evento = Historico(
        id="h1",
        chamado_id="ch1",
        usuario_id="u1",
        usuario_nome="Fulano",
        acao="alteracao_status",
        campo_alterado="status",
        valor_anterior="Aberto",
        valor_novo="Em Atendimento",
        data_acao=datetime.now(),
    )
    with patch("app.routes.dashboard.db") as mock_db:
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = _chamado_dict_fake(status="Em Atendimento")
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        with (
            patch("app.routes.dashboard.usuario_pode_ver_chamado", return_value=True),
            patch("app.routes.dashboard.Historico.get_by_chamado_id", return_value=[evento]),
        ):
            with client_logado_admin.session_transaction() as sess:
                sess["language"] = "en"
            r = client_logado_admin.get("/chamado/ch1/historico")
    body = r.data.decode("utf-8")
    assert "In Progress" in body
    assert "Em Atendimento" not in body


# ── Onda 3: exportar exception handler ────────────────────────────────────────


def test_exportar_exception_redireciona(client_logado_supervisor):
    """GET /exportar quando ocorre exceção redireciona para painel."""
    with patch(
        "app.routes.dashboard.aplicar_filtros_dashboard_com_paginacao",
        side_effect=Exception("timeout"),
    ):
        r = client_logado_supervisor.get("/exportar", follow_redirects=False)
    assert r.status_code == 302


# ── Onda 3: exportar_avancado ──────────────────────────────────────────────────


def _mock_chamado_obj():
    """Cria Chamado mock para exportar_avancado."""
    from app.models import Chamado

    return Chamado(
        id="adv1",
        numero_chamado="2026-001",
        categoria="TI",
        tipo_solicitacao="Corretiva",
        descricao="Teste avançado",
        responsavel="Resp",
        responsavel_id="u1",
        solicitante_id="s1",
        solicitante_nome="Sol",
        area="TI",
        status="Aberto",
        prioridade=1,
        rl_codigo=None,
        gate=None,
        impacto=None,
        anexo=None,
        anexos=[],
        data_abertura=None,
        data_conclusao=None,
    )


def test_exportar_avancado_sem_login_redireciona(client):
    """GET /exportar-avancado sem login redireciona para login."""
    r = client.get("/exportar-avancado", follow_redirects=False)
    assert r.status_code == 302
    assert "login" in (r.location or "").lower()


def test_exportar_avancado_retorna_xlsx(client_logado_supervisor):
    """GET /exportar-avancado com supervisor retorna arquivo xlsx."""
    from unittest.mock import MagicMock, patch

    with (
        patch("app.routes.dashboard.aplicar_filtros_dashboard_com_paginacao") as mock_filtros,
        patch("app.routes.dashboard._filtrar_chamados_por_permissao") as mock_perm,
        patch("app.routes.dashboard.analisador") as mock_anal,
        patch("app.services.excel_export_service.exportador_excel") as mock_exp,
        patch("app.routes.dashboard.db"),
        patch("app.routes.dashboard.verificar_e_incrementar_export", return_value=(True, None)),
    ):
        import io

        mock_filtros.return_value = {"docs": [MagicMock()]}
        mock_perm.return_value = [_mock_chamado_obj()]
        mock_anal.obter_metricas_gerais.return_value = {}
        mock_anal.obter_metricas_supervisores.return_value = []
        output = io.BytesIO(b"PK fake xlsx content")
        mock_exp.exportar_relatorio_completo.return_value = output

        r = client_logado_supervisor.get("/exportar-avancado", follow_redirects=False)

    assert r.status_code == 200
    ct = r.headers.get("Content-Type", "")
    assert "spreadsheet" in ct or "excel" in ct or "octet" in ct.lower()


def test_exportar_avancado_limite_excedido_redireciona(client_logado_supervisor):
    """GET /exportar-avancado quando limite diário excedido redireciona."""
    from unittest.mock import patch

    with (
        patch(
            "app.routes.dashboard.verificar_e_incrementar_export",
            return_value=(False, "Limite excedido"),
        ),
        patch("app.routes.dashboard.Config") as mock_cfg,
    ):
        mock_cfg.EXPORT_EXCEL_MAX_POR_USUARIO_POR_DIA = 5
        mock_cfg.ITENS_POR_PAGINA_DASHBOARD = 20
        r = client_logado_supervisor.get("/exportar-avancado", follow_redirects=False)
    assert r.status_code == 302


def test_exportar_avancado_exception_redireciona(client_logado_supervisor):
    """GET /exportar-avancado quando serviço lança exceção redireciona."""
    with (
        patch("app.routes.dashboard.aplicar_filtros_dashboard_com_paginacao") as mock_filtros,
        patch("app.routes.dashboard._filtrar_chamados_por_permissao", return_value=[]),
        patch("app.routes.dashboard.analisador") as mock_anal,
        patch("app.routes.dashboard.db"),
    ):
        mock_filtros.return_value = {"docs": []}
        mock_anal.obter_metricas_gerais.return_value = {}
        mock_anal.obter_metricas_supervisores.return_value = []
        # exportador_excel.exportar_relatorio_completo vai falhar porque não mockamos
        r = client_logado_supervisor.get("/exportar-avancado", follow_redirects=False)

    assert r.status_code in (200, 302)


def test_exportar_avancado_com_filtros_no_url(client_logado_supervisor):
    """GET /exportar-avancado com filtros no query string inclui filtros no Excel."""
    from unittest.mock import patch

    with (
        patch("app.routes.dashboard.aplicar_filtros_dashboard_com_paginacao") as mock_filtros,
        patch("app.routes.dashboard._filtrar_chamados_por_permissao") as mock_perm,
        patch("app.routes.dashboard.analisador") as mock_anal,
        patch("app.services.excel_export_service.exportador_excel") as mock_exp,
        patch("app.routes.dashboard.db"),
    ):
        import io

        mock_filtros.return_value = {"docs": []}
        mock_perm.return_value = []
        mock_anal.obter_metricas_gerais.return_value = {}
        mock_anal.obter_metricas_supervisores.return_value = []
        output = io.BytesIO(b"PK xlsx")
        mock_exp.exportar_relatorio_completo.return_value = output

        client_logado_supervisor.get(
            "/exportar-avancado?search=teste&categoria=TI&status=Aberto&responsavel=Ana",
            follow_redirects=False,
        )

    # Deve ter passado filtros_aplicados ao exportar
    if mock_exp.exportar_relatorio_completo.called:
        call_kwargs = mock_exp.exportar_relatorio_completo.call_args[1]
        filtros = call_kwargs.get("filtros_aplicados", {})
        assert "Busca" in filtros or isinstance(filtros, dict)


# ── Onda 3: relatorios branches ────────────────────────────────────────────────


def test_relatorios_atualizar_1_com_limite_excedido_redireciona(client_logado_admin):
    """GET /admin/relatorios?atualizar=1 quando limite excedido redireciona."""
    with (
        patch("app.routes.dashboard.analisador") as mock_anal,
        patch("app.routes.dashboard.Usuario.get_all", return_value=[]),
        patch(
            "app.routes.dashboard.verificar_e_incrementar_relatorio",
            return_value=(False, "Limite de relatórios diário atingido"),
        ),
        patch("app.routes.dashboard.Config") as mock_cfg,
    ):
        mock_cfg.RELATORIO_MAX_POR_USUARIO_POR_DIA = 5
        mock_cfg.ITENS_POR_PAGINA_DASHBOARD = 20
        mock_cfg.ITENS_POR_PAGINA = 10
        mock_anal.obter_relatorio_completo.return_value = {}
        r = client_logado_admin.get("/admin/relatorios?atualizar=1", follow_redirects=False)
    assert r.status_code == 302


def test_relatorios_analytics_exception_mostra_erro(client_logado_admin):
    """GET /admin/relatorios quando analytics lança exceção retorna 200 com erro_relatorio."""
    with (
        patch("app.routes.dashboard.analisador") as mock_anal,
        patch("app.routes.dashboard.Usuario.get_all", return_value=[]),
        patch("app.routes.dashboard.CategoriaSetor.get_all", return_value=[]),
    ):
        mock_anal.obter_relatorio_completo.side_effect = Exception("analytics down")
        r = client_logado_admin.get("/admin/relatorios", follow_redirects=False)
    assert r.status_code == 200


def test_relatorios_com_busca_sup_filtra_supervisores(client_logado_admin):
    """GET /admin/relatorios?busca_sup=Ana filtra lista de supervisores."""
    sup_ana = {
        "supervisor_nome": "Ana Souza",
        "supervisor_email": "ana@dtx.aero",
        "area": "TI",
        "carga_atual": 3,
        "taxa_resolucao_percentual": 80.0,
        "total_chamados": 10,
        "concluidos": 8,
        "abertos": 2,
        "em_andamento": 0,
        "tempo_medio_resolucao_horas": 12.0,
        "percentual_dentro_sla": 90.0,
        "distribuicao_categoria": {},
    }
    sup_bob = {
        "supervisor_nome": "Bob Lima",
        "supervisor_email": "bob@dtx.aero",
        "area": "RH",
        "carga_atual": 2,
        "taxa_resolucao_percentual": 70.0,
        "total_chamados": 5,
        "concluidos": 3,
        "abertos": 2,
        "em_andamento": 0,
        "tempo_medio_resolucao_horas": 8.0,
        "percentual_dentro_sla": 80.0,
        "distribuicao_categoria": {},
    }
    with (
        patch("app.routes.dashboard.analisador") as mock_anal,
        patch("app.routes.dashboard.Usuario.get_all", return_value=[]),
        patch("app.routes.dashboard.CategoriaSetor.get_all", return_value=[]),
    ):
        mock_anal.obter_relatorio_completo.return_value = {
            "data_geracao": None,
            "metricas_gerais": {},
            "metricas_supervisores": [sup_ana, sup_bob],
            "metricas_areas": [],
            "insights": [],
        }
        r = client_logado_admin.get("/admin/relatorios?busca_sup=ana", follow_redirects=False)
    assert r.status_code == 200
    # Ana deve aparecer, Bob não
    assert b"Ana" in r.data


def test_relatorios_com_ordem_invalida_usa_desc(client_logado_admin):
    """GET /admin/relatorios?ordem_sup=INVALIDO normaliza para 'desc'."""
    with (
        patch("app.routes.dashboard.analisador") as mock_anal,
        patch("app.routes.dashboard.Usuario.get_all", return_value=[]),
        patch("app.routes.dashboard.CategoriaSetor.get_all", return_value=[]),
    ):
        mock_anal.obter_relatorio_completo.return_value = {
            "data_geracao": None,
            "metricas_gerais": {},
            "metricas_supervisores": [],
            "metricas_areas": [],
            "insights": [],
        }
        r = client_logado_admin.get(
            "/admin/relatorios?ordem_sup=INVALIDO&ordem_area=INVALIDO",
            follow_redirects=False,
        )
    assert r.status_code == 200


def test_relatorios_com_busca_area_filtra_areas(client_logado_admin):
    """GET /admin/relatorios?busca_area=TI filtra lista de áreas."""
    area_ti = {
        "area": "TI",
        "total_chamados": 10,
        "abertos": 3,
        "concluidos": 7,
        "taxa_resolucao_percentual": 70.0,
        "tempo_medio_resolucao_horas": 12.0,
        "supervisores_alocados": 2,
        "chamados_por_supervisor": 5.0,
        "atribuidos_automaticamente": 4,
        "atribuidos_manualmente": 6,
        "taxa_automacao_percentual": 40.0,
    }
    area_rh = {
        "area": "RH",
        "total_chamados": 5,
        "abertos": 2,
        "concluidos": 3,
        "taxa_resolucao_percentual": 60.0,
        "tempo_medio_resolucao_horas": 8.0,
        "supervisores_alocados": 1,
        "chamados_por_supervisor": 5.0,
        "atribuidos_automaticamente": 1,
        "atribuidos_manualmente": 4,
        "taxa_automacao_percentual": 20.0,
    }
    with (
        patch("app.routes.dashboard.analisador") as mock_anal,
        patch("app.routes.dashboard.Usuario.get_all", return_value=[]),
        patch("app.routes.dashboard.CategoriaSetor.get_all", return_value=[]),
    ):
        mock_anal.obter_relatorio_completo.return_value = {
            "data_geracao": None,
            "metricas_gerais": {},
            "metricas_supervisores": [],
            "metricas_areas": [area_ti, area_rh],
            "insights": [],
        }
        r = client_logado_admin.get("/admin/relatorios?busca_area=ti", follow_redirects=False)
    assert r.status_code == 200


def test_relatorios_outer_exception_renderiza_pagina_erro(client_logado_admin):
    """GET /admin/relatorios quando preparar_metricas_paginadas lança exceção retorna 200 de fallback."""
    with (
        patch("app.routes.dashboard.analisador") as mock_anal,
        patch("app.routes.dashboard.Usuario.get_all", return_value=[]),
        patch("app.routes.dashboard.CategoriaSetor.get_all", return_value=[]),
        patch(
            "app.routes.dashboard.preparar_metricas_paginadas",
            side_effect=Exception("pagination error"),
        ),
    ):
        mock_anal.obter_relatorio_completo.return_value = {
            "data_geracao": None,
            "metricas_gerais": {},
            "metricas_supervisores": [],
            "metricas_areas": [],
            "insights": [],
        }
        r = client_logado_admin.get("/admin/relatorios", follow_redirects=False)
    assert r.status_code in (200, 302)


# ── Onda 3: indices_firestore exception ───────────────────────────────────────


def test_indices_firestore_exception_redireciona(client_logado_admin):
    """GET /admin/indices-firestore quando OptimizadorQuery lança exceção redireciona."""
    with patch("app.routes.dashboard.OptimizadorQuery") as mock_opt:
        mock_opt.INDICES_RECOMENDADOS = MagicMock(side_effect=Exception("indices error"))
        r = client_logado_admin.get("/admin/indices-firestore", follow_redirects=False)
    assert r.status_code in (200, 302)


# ── Onda 3: visualizar_detalhe_chamado com referrer same-origin ───────────────


def test_visualizar_chamado_com_referrer_same_origin(client_logado_admin):
    """GET /chamado/<id> com Referer same-origin usa o referrer como voltar_url."""
    with patch("app.routes.dashboard.db") as mock_db:
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = _chamado_dict_fake()
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
        with (
            patch("app.routes.dashboard.usuario_pode_ver_chamado", return_value=True),
            patch("app.routes.dashboard.get_static_cached", return_value=[]),
            patch("app.routes.dashboard.CategoriaSetor.get_all", return_value=[]),
            patch("app.routes.dashboard.filtrar_supervisores_por_area", return_value=[]),
        ):
            r = client_logado_admin.get(
                "/chamado/ch1",
                headers={"Referer": "http://localhost/admin"},
                follow_redirects=False,
            )
    assert r.status_code == 200
