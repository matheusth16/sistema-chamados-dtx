"""Testes de cobertura para gaps em app/routes/api.py (Onda 2 — Segurança e API)."""

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# /api/download-anexo: 404 e 503
# ---------------------------------------------------------------------------


def test_download_anexo_chamado_nao_encontrado_retorna_404(client_logado_solicitante):
    """GET /api/download-anexo com chamado inexistente retorna 404."""
    doc = MagicMock()
    doc.exists = False
    with patch("app.routes.api_solicitante.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_solicitante.get("/api/download-anexo?chamado_id=ch999&chave=r2:arq.pdf")
    assert r.status_code == 404


def test_download_anexo_presign_falha_retorna_503(client_logado_solicitante):
    """GET /api/download-anexo quando gerar_url_presignada retorna None retorna 503."""
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {"anexos": ["r2:arq.pdf"], "anexo": None, "solicitante_id": "sol_1"}
    with (
        patch("app.routes.api_solicitante.db") as mock_db,
        patch("app.routes.api_solicitante.Chamado.from_dict", return_value=MagicMock()),
        patch("app.routes.api_solicitante.usuario_pode_ver_chamado", return_value=True),
        patch("app.services.upload.gerar_url_presignada", return_value=None),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_solicitante.get("/api/download-anexo?chamado_id=ch1&chave=r2:arq.pdf")
    assert r.status_code == 503


def test_download_anexo_com_campo_legado_anexo_simples(client_logado_solicitante):
    """GET /api/download-anexo: chave no campo legado 'anexo' (não 'anexos') é aceita."""
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {
        "anexos": [],
        "anexo": "r2:legado.pdf",
        "solicitante_id": "sol_1",
    }
    with (
        patch("app.routes.api_solicitante.db") as mock_db,
        patch("app.routes.api_solicitante.Chamado.from_dict", return_value=MagicMock()),
        patch("app.routes.api_solicitante.usuario_pode_ver_chamado", return_value=True),
        patch(
            "app.services.upload.gerar_url_presignada", return_value="https://r2.example.com/l.pdf"
        ),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_solicitante.get("/api/download-anexo?chamado_id=ch1&chave=r2:legado.pdf")
    assert r.status_code == 302
    assert "r2.example.com" in (r.location or "")


# ---------------------------------------------------------------------------
# /api/atualizar-status: branches de validação (logado)
# ---------------------------------------------------------------------------


def test_atualizar_status_json_vazio_logado_retorna_400(client_logado_supervisor):
    """POST /api/atualizar-status com JSON vazio ({}) retorna 400 (usuário logado)."""
    r = client_logado_supervisor.post(
        "/api/atualizar-status",
        json={},
        content_type="application/json",
    )
    assert r.status_code == 400
    data = r.get_json()
    assert data is not None and data.get("sucesso") is False


def test_atualizar_status_sem_novo_status_retorna_400(client_logado_supervisor):
    """POST /api/atualizar-status com chamado_id mas sem novo_status retorna 400."""
    r = client_logado_supervisor.post(
        "/api/atualizar-status",
        json={"chamado_id": "ch_1"},
        content_type="application/json",
    )
    assert r.status_code == 400
    data = r.get_json()
    assert data is not None and data.get("sucesso") is False
    assert "novo_status" in data.get("erro", "").lower()


def test_atualizar_status_cancelado_sem_motivo_retorna_400(client_logado_supervisor):
    """POST /api/atualizar-status com status=Cancelado sem motivo retorna 400."""
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {"area": "Manutencao", "status": "Aberto", "solicitante_id": "s1"}
    chamado_mock = MagicMock()
    chamado_mock.area = "Manutencao"
    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Chamado") as mock_chamado,
        patch("app.routes.api.verificar_permissao_mudanca_status", return_value=(True, None)),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado.from_dict.return_value = chamado_mock
        r = client_logado_supervisor.post(
            "/api/atualizar-status",
            json={"chamado_id": "ch_1", "novo_status": "Cancelado"},
            content_type="application/json",
        )
    assert r.status_code == 400
    data = r.get_json()
    assert data is not None and data.get("sucesso") is False
    assert "reason" in data.get("erro", "").lower()


def test_atualizar_status_excecao_retorna_500(client_logado_supervisor):
    """POST /api/atualizar-status com exceção interna retorna 500 genérico."""
    with patch("app.routes.api.db") as mock_db:
        mock_db.collection.side_effect = Exception("db explodiu")
        r = client_logado_supervisor.post(
            "/api/atualizar-status",
            json={"chamado_id": "ch_1", "novo_status": "Aberto"},
            content_type="application/json",
        )
    assert r.status_code == 500
    data = r.get_json()
    assert data is not None and data.get("sucesso") is False
    assert "internal" in data.get("erro", "").lower() or "Error" in data.get("erro", "")


# ---------------------------------------------------------------------------
# /api/editar-chamado: success + exception
# ---------------------------------------------------------------------------


def test_api_editar_chamado_sucesso_retorna_200(client_logado_supervisor):
    """POST /api/editar-chamado com processamento bem-sucedido retorna 200."""
    with patch("app.services.edicao_chamado_service.processar_edicao_chamado") as mock_proc:
        mock_proc.return_value = {
            "sucesso": True,
            "mensagem": "Chamado atualizado",
            "dados": {"status": "Em Atendimento"},
        }
        r = client_logado_supervisor.post(
            "/api/editar-chamado",
            data={"chamado_id": "ch_ok"},
            content_type="multipart/form-data",
        )
    assert r.status_code == 200
    data = r.get_json()
    assert data is not None and data.get("sucesso") is True


def test_api_editar_chamado_excecao_retorna_500(client_logado_supervisor):
    """POST /api/editar-chamado com exceção inesperada retorna 500 genérico."""
    with patch("app.services.edicao_chamado_service.processar_edicao_chamado") as mock_proc:
        mock_proc.side_effect = Exception("unexpected")
        r = client_logado_supervisor.post(
            "/api/editar-chamado",
            data={"chamado_id": "ch_err"},
            content_type="multipart/form-data",
        )
    assert r.status_code == 500
    data = r.get_json()
    assert data is not None and data.get("sucesso") is False


# ---------------------------------------------------------------------------
# /api/bulk-status: empty ids, chamado not found, Concluído + histórico, exception
# ---------------------------------------------------------------------------


def test_bulk_status_ids_lista_vazia_apos_filtro_retorna_400(client_logado_supervisor):
    """POST /api/bulk-status com lista vazia de IDs retorna 400."""
    r = client_logado_supervisor.post(
        "/api/bulk-status",
        json={"chamado_ids": [], "novo_status": "Aberto"},
        content_type="application/json",
    )
    assert r.status_code == 400
    data = r.get_json()
    assert data is not None and data.get("sucesso") is False
    assert "no ticket" in data.get("erro", "").lower() or "provided" in data.get("erro", "").lower()


def test_bulk_status_chamado_nao_encontrado_vai_para_erros(client_logado_supervisor):
    """POST /api/bulk-status: chamado inexistente vai para lista de erros, não aborta."""
    doc_nao_existe = MagicMock()
    doc_nao_existe.exists = False

    with patch("app.routes.api.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.return_value = doc_nao_existe
        r = client_logado_supervisor.post(
            "/api/bulk-status",
            json={"chamado_ids": ["ch_nao_existe"], "novo_status": "Aberto"},
            content_type="application/json",
        )
    assert r.status_code == 200
    data = r.get_json()
    assert data is not None and data.get("sucesso") is True
    assert data.get("atualizados") == 0
    assert len(data.get("erros", [])) == 1
    assert data["erros"][0]["erro"] == "Not found"


def test_bulk_status_concluido_seta_data_conclusao(client_logado_supervisor):
    """POST /api/bulk-status com status=Concluído delega a atualizar_status_chamado."""
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {
        "status": "Em Atendimento",
        "area": "Manutencao",
        "responsavel_id": "sup_1",
        "solicitante_id": "sol_1",
        "participantes": [],
    }

    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.atualizar_status_chamado") as mock_atualizar,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_atualizar.return_value = {
            "sucesso": True,
            "mensagem": "Status atualizado",
            "novo_status": "Concluído",
        }
        r = client_logado_supervisor.post(
            "/api/bulk-status",
            json={"chamado_ids": ["ch_conc"], "novo_status": "Concluído"},
            content_type="application/json",
        )

    assert r.status_code == 200
    data = r.get_json()
    assert data.get("sucesso") is True
    assert data.get("atualizados") == 1
    mock_atualizar.assert_called_once()
    _, kw = mock_atualizar.call_args
    assert kw.get("novo_status") == "Concluído"
    assert kw.get("chamado_id") == "ch_conc"


def test_bulk_status_inner_exception_vai_para_erros(client_logado_supervisor):
    """POST /api/bulk-status: exceção em atualizar_status_chamado vai para erros sem abortar."""
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {
        "status": "Aberto",
        "area": "Manutencao",
        "responsavel_id": "sup_1",
        "solicitante_id": "sol_1",
        "participantes": [],
    }

    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.atualizar_status_chamado", side_effect=Exception("timeout")),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_supervisor.post(
            "/api/bulk-status",
            json={"chamado_ids": ["ch_err"], "novo_status": "Aberto"},
            content_type="application/json",
        )

    assert r.status_code == 200
    data = r.get_json()
    assert data.get("sucesso") is True
    assert data.get("atualizados") == 0
    assert len(data.get("erros", [])) == 1


def test_bulk_status_outer_exception_retorna_500(client_logado_supervisor):
    """POST /api/bulk-status: exceção em cascata (logger.warning raises) retorna 500."""
    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.logger") as mock_logger,
    ):
        doc = MagicMock()
        doc.exists = True
        doc.to_dict.side_effect = RuntimeError("db explodiu")
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_logger.warning.side_effect = RuntimeError("cascade fail")
        r = client_logado_supervisor.post(
            "/api/bulk-status",
            json={"chamado_ids": ["ch_1"], "novo_status": "Concluído"},
            content_type="application/json",
        )
    assert r.status_code == 500
    data = r.get_json()
    assert data is not None and data.get("sucesso") is False


# Lacuna 1 — novos testes TDD (devem falhar antes da correção em api.py)


def test_bulk_status_supervisor_nao_altera_ticket_de_colega_mesma_area(client_logado_supervisor):
    """Lacuna 1: supervisor não pode alterar chamado com owner diferente, mesmo sendo da sua área."""
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {
        "status": "Aberto",
        "area": "Manutencao",
        "responsavel_id": "outro_supervisor",
        "solicitante_id": "sol_1",
        "participantes": [],
    }
    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.atualizar_status_chamado") as mock_atualizar,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_supervisor.post(
            "/api/bulk-status",
            json={"chamado_ids": ["ch_colega"], "novo_status": "Concluído"},
            content_type="application/json",
        )
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("sucesso") is True
    assert data.get("atualizados") == 0
    erros_ids = [e.get("id") for e in data.get("erros", [])]
    assert "ch_colega" in erros_ids
    mock_atualizar.assert_not_called()


def test_bulk_status_em_atendimento_fila_delega_atualizar_status_chamado(client_logado_supervisor):
    """Lacuna 1: chamado na fila (sem owner) → Em Atendimento delega a atualizar_status_chamado (claim)."""
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {
        "status": "Aberto",
        "area": "Manutencao",
        "responsavel_id": None,
        "solicitante_id": "sol_1",
        "participantes": [],
    }
    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.atualizar_status_chamado") as mock_atualizar,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_atualizar.return_value = {
            "sucesso": True,
            "mensagem": "ok",
            "novo_status": "Em Atendimento",
        }
        r = client_logado_supervisor.post(
            "/api/bulk-status",
            json={"chamado_ids": ["ch_fila"], "novo_status": "Em Atendimento"},
            content_type="application/json",
        )
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("sucesso") is True
    assert data.get("atualizados") == 1
    mock_atualizar.assert_called_once()
    _, kw = mock_atualizar.call_args
    assert kw.get("chamado_id") == "ch_fila"
    assert kw.get("novo_status") == "Em Atendimento"


# ---------------------------------------------------------------------------
# /api/notificacoes: contar e ler-todas (endpoints não testados)
# ---------------------------------------------------------------------------


def test_api_notificacoes_contar_sucesso(client_logado_solicitante):
    """GET /api/notificacoes/contar retorna total_nao_lidas."""
    with patch("app.routes.api_notificacoes.contar_nao_lidas", return_value=3):
        r = client_logado_solicitante.get("/api/notificacoes/contar")
    assert r.status_code == 200
    data = r.get_json()
    assert data is not None
    assert data.get("total_nao_lidas") == 3


def test_api_notificacoes_contar_excecao_retorna_zero(client_logado_solicitante):
    """GET /api/notificacoes/contar com exceção retorna total_nao_lidas=0."""
    with patch("app.routes.api_notificacoes.contar_nao_lidas", side_effect=Exception("redis down")):
        r = client_logado_solicitante.get("/api/notificacoes/contar")
    assert r.status_code == 200
    data = r.get_json()
    assert data is not None
    assert data.get("total_nao_lidas") == 0


def test_api_notificacoes_ler_todas_sucesso(client_logado_solicitante):
    """POST /api/notificacoes/ler-todas marca todas como lidas e retorna count."""
    with patch("app.routes.api_notificacoes.marcar_todas_como_lidas", return_value=5):
        r = client_logado_solicitante.post("/api/notificacoes/ler-todas")
    assert r.status_code == 200
    data = r.get_json()
    assert data is not None
    assert data.get("sucesso") is True
    assert data.get("atualizadas") == 5


def test_api_notificacoes_ler_todas_excecao_retorna_500(client_logado_solicitante):
    """POST /api/notificacoes/ler-todas com exceção retorna 500."""
    with patch("app.routes.api_notificacoes.marcar_todas_como_lidas", side_effect=Exception("err")):
        r = client_logado_solicitante.post("/api/notificacoes/ler-todas")
    assert r.status_code == 500
    data = r.get_json()
    assert data is not None and data.get("sucesso") is False


def test_api_notificacoes_listar_excecao_retorna_500(client_logado_solicitante):
    """GET /api/notificacoes com exceção retorna 500 com estrutura segura."""
    with patch(
        "app.routes.api_notificacoes.listar_para_usuario", side_effect=Exception("redis fail")
    ):
        r = client_logado_solicitante.get("/api/notificacoes")
    assert r.status_code == 500
    data = r.get_json()
    assert data is not None
    assert data.get("sucesso") is False
    assert data.get("notificacoes") == []
    assert data.get("total_nao_lidas") == 0


def test_api_notificacoes_marcar_lida_excecao_retorna_500(client_logado_solicitante):
    """POST /api/notificacoes/<id>/ler com exceção retorna 500."""
    with patch("app.routes.api_notificacoes.marcar_como_lida", side_effect=Exception("err")):
        r = client_logado_solicitante.post("/api/notificacoes/notif_1/ler")
    assert r.status_code == 500
    data = r.get_json()
    assert data is not None and data.get("sucesso") is False


# ---------------------------------------------------------------------------
# /api/push-subscribe: exceção
# ---------------------------------------------------------------------------


def test_api_push_subscribe_excecao_retorna_500(client_logado_solicitante):
    """POST /api/push-subscribe com exceção em salvar_inscricao retorna 500."""
    with patch("app.routes.api_notificacoes.salvar_inscricao", side_effect=Exception("push err")):
        r = client_logado_solicitante.post(
            "/api/push-subscribe",
            json={"subscription": {"endpoint": "https://example.com/push"}},
            content_type="application/json",
        )
    assert r.status_code == 500
    data = r.get_json()
    assert data is not None and data.get("sucesso") is False


# ---------------------------------------------------------------------------
# /api/chamado/<id>: 404, supervisor sem permissão, except
# ---------------------------------------------------------------------------


def test_api_chamado_por_id_nao_encontrado_retorna_404(client_logado_supervisor):
    """GET /api/chamado/<id> com chamado inexistente retorna 404."""
    doc = MagicMock()
    doc.exists = False
    with patch("app.routes.api.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_supervisor.get("/api/chamado/nao_existe")
    assert r.status_code == 404
    data = r.get_json()
    assert data is not None and data.get("sucesso") is False


def test_api_chamado_por_id_supervisor_sem_permissao_retorna_403(client_logado_supervisor):
    """GET /api/chamado/<id> por supervisor sem acesso ao chamado retorna 403."""
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {"area": "TI", "status": "Aberto", "solicitante_id": "s1"}
    chamado_mock = MagicMock()
    chamado_mock.area = "TI"
    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.Chamado.from_dict", return_value=chamado_mock),
        patch("app.routes.api.usuario_pode_ver_chamado", return_value=False),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_supervisor.get("/api/chamado/ch_ti_1")
    assert r.status_code == 403
    data = r.get_json()
    assert data is not None and data.get("sucesso") is False


def test_api_chamado_por_id_excecao_retorna_500(client_logado_supervisor):
    """GET /api/chamado/<id> com exceção inesperada retorna 500 genérico."""
    with patch("app.routes.api.db") as mock_db:
        mock_db.collection.side_effect = Exception("timeout")
        r = client_logado_supervisor.get("/api/chamado/ch_err")
    assert r.status_code == 500
    data = r.get_json()
    assert data is not None and data.get("sucesso") is False


# ---------------------------------------------------------------------------
# _aplicar_filtro_perfil: branch admin (sem restrição)
# ---------------------------------------------------------------------------


def test_aplicar_filtro_perfil_admin_retorna_ref_sem_where(app):
    """_aplicar_filtro_perfil para admin retorna a ref original sem filtro."""
    from app.routes.api import _aplicar_filtro_perfil

    ref = MagicMock()
    user = MagicMock()
    user.perfil = "admin"

    result = _aplicar_filtro_perfil(ref, user)

    assert result is ref
    ref.where.assert_not_called()


def test_aplicar_filtro_perfil_solicitante_filtra_por_id(app):
    """_aplicar_filtro_perfil para solicitante adiciona filtro por solicitante_id."""
    from app.routes.api import _aplicar_filtro_perfil

    ref = MagicMock()
    user = MagicMock()
    user.perfil = "solicitante"
    user.id = "sol_1"

    _aplicar_filtro_perfil(ref, user)

    ref.where.assert_called_once()


# ---------------------------------------------------------------------------
# /api/chamados/paginar: sucesso e exceção
# ---------------------------------------------------------------------------


def test_api_chamados_paginar_retorna_estrutura_esperada(client_logado_admin):
    """GET /api/chamados/paginar retorna sucesso com chamados e paginação."""
    doc = MagicMock()
    doc.id = "ch_pag_1"
    doc.to_dict.return_value = {
        "status": "Aberto",
        "categoria": "Manutenção",
        "tipo_solicitacao": "Corretiva",
        "responsavel": "Fulano",
        "prioridade": "Alta",
        "descricao": "Descrição teste",
        "numero_chamado": "CH-001",
        "rl_codigo": None,
    }
    chamado_mock = MagicMock()
    chamado_mock.numero_chamado = "CH-001"
    chamado_mock.categoria = "Manutenção"
    chamado_mock.rl_codigo = None
    chamado_mock.tipo_solicitacao = "Corretiva"
    chamado_mock.responsavel = "Fulano"
    chamado_mock.status = "Aberto"
    chamado_mock.prioridade = "Alta"
    chamado_mock.descricao = "Descrição teste"
    chamado_mock.data_abertura_formatada.return_value = "01/01/2025"
    chamado_mock.data_conclusao_formatada.return_value = "-"

    with (
        patch("app.routes.api.aplicar_filtros_dashboard_com_paginacao") as mock_filtros,
        patch("app.routes.api.Chamado.from_dict", return_value=chamado_mock),
    ):
        mock_filtros.return_value = {
            "docs": [doc],
            "proximo_cursor": None,
            "tem_proxima": False,
        }
        r = client_logado_admin.get("/api/chamados/paginar?limite=10")

    assert r.status_code == 200
    data = r.get_json()
    assert data is not None and data.get("sucesso") is True
    assert "chamados" in data
    assert "paginacao" in data
    assert len(data["chamados"]) == 1


def test_api_chamados_paginar_excecao_retorna_500(client_logado_admin):
    """GET /api/chamados/paginar com exceção retorna 500 genérico."""
    with patch(
        "app.routes.api.aplicar_filtros_dashboard_com_paginacao", side_effect=Exception("err")
    ):
        r = client_logado_admin.get("/api/chamados/paginar")
    assert r.status_code == 500
    data = r.get_json()
    assert data is not None and data.get("sucesso") is False


# ---------------------------------------------------------------------------
# /api/carregar-mais: sucesso com docs e exceção
# ---------------------------------------------------------------------------


def test_carregar_mais_com_docs_retorna_chamados(client_logado_supervisor):
    """POST /api/carregar-mais com docs retorna lista de chamados."""
    doc = MagicMock()
    doc.id = "ch_scroll_1"
    doc.to_dict.return_value = {"status": "Aberto"}
    chamado_mock = MagicMock()
    chamado_mock.numero_chamado = "CH-002"
    chamado_mock.categoria = "Elétrica"
    chamado_mock.status = "Aberto"
    chamado_mock.responsavel = "Maria"
    chamado_mock.data_abertura_formatada.return_value = "02/01/2025"

    with (
        patch("app.routes.api.aplicar_filtros_dashboard_com_paginacao") as mock_filtros,
        patch("app.routes.api.Chamado.from_dict", return_value=chamado_mock),
    ):
        mock_filtros.return_value = {
            "docs": [doc],
            "proximo_cursor": "cursor_abc",
            "tem_proxima": True,
        }
        r = client_logado_supervisor.post(
            "/api/carregar-mais",
            json={"limite": 20},
            content_type="application/json",
        )

    assert r.status_code == 200
    data = r.get_json()
    assert data is not None and data.get("sucesso") is True
    assert len(data.get("chamados", [])) == 1
    assert data.get("tem_proxima") is True


def test_carregar_mais_excecao_retorna_500(client_logado_supervisor):
    """POST /api/carregar-mais com exceção retorna 500 genérico."""
    with patch(
        "app.routes.api.aplicar_filtros_dashboard_com_paginacao", side_effect=Exception("err")
    ):
        r = client_logado_supervisor.post(
            "/api/carregar-mais",
            json={},
            content_type="application/json",
        )
    assert r.status_code == 500
    data = r.get_json()
    assert data is not None and data.get("sucesso") is False


# ---------------------------------------------------------------------------
# Onboarding: exceções nos endpoints
# ---------------------------------------------------------------------------


def test_onboarding_avancar_excecao_retorna_500(client_logado_solicitante):
    """POST /api/onboarding/avancar com exceção retorna 500 genérico."""
    with patch("app.services.onboarding_service.avancar_passo", side_effect=Exception("err")):
        r = client_logado_solicitante.post(
            "/api/onboarding/avancar",
            json={"passo": 1},
            content_type="application/json",
        )
    assert r.status_code == 500
    data = r.get_json()
    assert data is not None and data.get("sucesso") is False


def test_onboarding_concluir_excecao_retorna_500(client_logado_solicitante):
    """POST /api/onboarding/concluir com exceção retorna 500 genérico."""
    with patch("app.services.onboarding_service.concluir_onboarding", side_effect=Exception("err")):
        r = client_logado_solicitante.post("/api/onboarding/concluir")
    assert r.status_code == 500
    data = r.get_json()
    assert data is not None and data.get("sucesso") is False


def test_onboarding_pular_excecao_retorna_500(client_logado_solicitante):
    """POST /api/onboarding/pular com exceção retorna 500 genérico."""
    with patch("app.services.onboarding_service.concluir_onboarding", side_effect=Exception("err")):
        r = client_logado_solicitante.post("/api/onboarding/pular")
    assert r.status_code == 500
    data = r.get_json()
    assert data is not None and data.get("sucesso") is False


# ---------------------------------------------------------------------------
# /api/chamado/<id>/confirmar-resolucao: chamado não encontrado + except
# ---------------------------------------------------------------------------


def test_confirmar_resolucao_chamado_nao_encontrado_retorna_404(client_logado_solicitante):
    """POST confirmar-resolucao com chamado inexistente retorna 404."""
    doc = MagicMock()
    doc.exists = False
    with patch("app.routes.api.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        r = client_logado_solicitante.post(
            "/api/chamado/ch_nao_existe/confirmar-resolucao",
            json={"acao": "confirmar"},
            content_type="application/json",
        )
    assert r.status_code == 404
    data = r.get_json()
    assert data is not None and data.get("sucesso") is False


def test_confirmar_resolucao_excecao_retorna_500(client_logado_solicitante):
    """POST confirmar-resolucao com exceção inesperada retorna 500 genérico."""
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {
        "status": "Concluído",
        "confirmacao_solicitante": "pendente",
        "solicitante_id": "sol_1",
    }
    with (
        patch("app.routes.api.db") as mock_db,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_db.collection.return_value.document.return_value.update.side_effect = Exception("db")
        r = client_logado_solicitante.post(
            "/api/chamado/ch_exc/confirmar-resolucao",
            json={"acao": "confirmar"},
            content_type="application/json",
        )
    assert r.status_code == 500
    data = r.get_json()
    assert data is not None and data.get("sucesso") is False


# ---------------------------------------------------------------------------
# /api/supervisores/lista: exceção
# ---------------------------------------------------------------------------


def test_api_lista_supervisores_excecao_retorna_200_vazio(client_logado_solicitante):
    """GET /api/supervisores/lista com exceção retorna 200 com lista vazia (degradado)."""
    with patch("app.routes.api.Usuario.get_supervisores_por_area", side_effect=Exception("db")):
        r = client_logado_solicitante.get("/api/supervisores/lista?area=TI")
    assert r.status_code == 200
    data = r.get_json()
    assert data is not None
    assert data.get("sucesso") is False
    assert data.get("supervisores") == []


# ---------------------------------------------------------------------------
# Fase 2 — _aplicar_filtro_perfil: supervisor usa supervisor_ids_com_acesso
# ---------------------------------------------------------------------------


def test_aplicar_filtro_perfil_supervisor_usa_array_contains(app):
    """Supervisor → filtro por supervisor_ids_com_acesso array_contains (não area in)."""

    from app.routes.api import _aplicar_filtro_perfil

    ref = MagicMock()
    user = MagicMock()
    user.perfil = "supervisor"
    user.id = "id_julia"
    user.areas = ["Engenharia"]

    _aplicar_filtro_perfil(ref, user)

    ref.where.assert_called_once()
    call_kwargs = ref.where.call_args
    ff = call_kwargs[1].get("filter") or (call_kwargs[0][0] if call_kwargs[0] else None)
    assert ff is not None
    assert ff.field_path == "supervisor_ids_com_acesso"
    assert ff.op_string in ("ARRAY_CONTAINS", "array_contains", "array-contains")
    assert ff.value == "id_julia"


def test_aplicar_filtro_perfil_supervisor_sem_areas_retorna_none(app):
    """Supervisor sem áreas → retorna None (sem acesso)."""
    from app.routes.api import _aplicar_filtro_perfil

    ref = MagicMock()
    user = MagicMock()
    user.perfil = "supervisor"
    user.areas = []

    result = _aplicar_filtro_perfil(ref, user)

    assert result is None


# ---------------------------------------------------------------------------
# Fase 5 — Lacunas gestor read-only (bypass tests)
# ---------------------------------------------------------------------------


def test_gestor_bulk_status_retorna_403(client_logado_gestor):
    """Lacuna 1: gestor não pode alterar status em lote — 403 antes do loop."""
    resp = client_logado_gestor.post(
        "/api/bulk-status",
        json={"chamado_ids": ["ch_001"], "novo_status": "Em Atendimento"},
    )
    assert resp.status_code == 403
    data = resp.get_json()
    assert data["sucesso"] is False


def test_supervisor_bulk_status_nao_regrediu(client_logado_supervisor):
    """Regressão: supervisor comum continua funcionando após bloqueio de gestor."""
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {
        "status": "Aberto",
        "area": "Manutencao",
        "responsavel_id": None,
        "solicitante_id": "sol_1",
        "participantes": [],
    }
    with (
        patch("app.routes.api.db") as mock_db,
        patch("app.routes.api.atualizar_status_chamado") as mock_atualizar,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_atualizar.return_value = {"sucesso": True, "mensagem": "ok"}
        resp = client_logado_supervisor.post(
            "/api/bulk-status",
            json={"chamado_ids": ["ch_001"], "novo_status": "Em Atendimento"},
        )
    assert resp.status_code == 200
    assert resp.get_json()["atualizados"] == 1


def test_gestor_transferir_area_403(client_logado_gestor):
    """Lacuna 4: gestor não pode transferir área de chamado — 403."""
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {}
    chamado_obj = MagicMock()
    chamado_obj.responsavel_id = "gest_1"

    with (
        patch("app.routes.api_colaboracao.db") as mock_db,
        patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=True),
        patch("app.routes.api_colaboracao.Chamado.from_dict", return_value=chamado_obj),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        resp = client_logado_gestor.post(
            "/api/chamado/ch_001/transferir-area",
            json={"area": "TI", "supervisor_id": "sup_x", "motivo": "Motivo válido"},
        )
    assert resp.status_code == 403
    assert resp.get_json()["sucesso"] is False


def test_gestor_escalonar_colega_403(client_logado_gestor):
    """Lacuna 4: gestor não pode escalonar para colega — 403."""
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {}
    chamado_obj = MagicMock()
    chamado_obj.responsavel_id = "gest_1"

    with (
        patch("app.routes.api_colaboracao.db") as mock_db,
        patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=True),
        patch("app.routes.api_colaboracao.Chamado.from_dict", return_value=chamado_obj),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        resp = client_logado_gestor.post(
            "/api/chamado/ch_001/escalonar-colega",
            json={"supervisor_id": "sup_x", "motivo": "Motivo válido"},
        )
    assert resp.status_code == 403
    assert resp.get_json()["sucesso"] is False


def test_gestor_incluir_participantes_403(client_logado_gestor):
    """Lacuna 4: gestor não pode incluir participantes — 403."""
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {}
    chamado_obj = MagicMock()
    chamado_obj.responsavel_id = "gest_1"

    with (
        patch("app.routes.api_colaboracao.db") as mock_db,
        patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=True),
        patch("app.routes.api_colaboracao.Chamado.from_dict", return_value=chamado_obj),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        resp = client_logado_gestor.post(
            "/api/chamado/ch_001/incluir-participantes",
            json={"participantes": [{"supervisor_id": "sup_x", "area": "TI"}]},
        )
    assert resp.status_code == 403
    assert resp.get_json()["sucesso"] is False


def test_gestor_concluir_minha_parte_403_mesmo_sendo_participante(client_logado_gestor):
    """Lacuna 4 edge case: gestor bloqueado mesmo estando na lista de participantes."""
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {
        "participantes": [{"supervisor_id": "gest_1", "area": "Geral", "status": "em_atendimento"}]
    }
    chamado_obj = MagicMock()
    chamado_obj.participantes = [
        {"supervisor_id": "gest_1", "area": "Geral", "status": "em_atendimento"}
    ]

    with (
        patch("app.routes.api_colaboracao.db") as mock_db,
        patch("app.routes.api_colaboracao.Chamado.from_dict", return_value=chamado_obj),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        resp = client_logado_gestor.post("/api/chamado/ch_001/concluir-minha-parte")
    assert resp.status_code == 403
    assert resp.get_json()["sucesso"] is False


def test_gestor_post_painel_nao_altera_status(client_logado_gestor):
    """Lacuna 2: gestor POST /painel redireciona para /gestor/dashboard sem alterar status."""
    with patch("app.routes.dashboard.atualizar_status_chamado") as mock_update:
        resp = client_logado_gestor.post(
            "/painel",
            data={"chamado_id": "ch_001", "novo_status": "Concluído"},
            follow_redirects=False,
        )
    assert resp.status_code == 302
    assert "gestor/dashboard" in resp.headers.get("Location", "")
    mock_update.assert_not_called()


def test_gestor_get_painel_redireciona_gestor_dashboard(client_logado_gestor):
    """Lacuna 3: gestor GET /painel redireciona para /gestor/dashboard."""
    resp = client_logado_gestor.get("/painel", follow_redirects=False)
    assert resp.status_code == 302
    assert "gestor/dashboard" in resp.headers.get("Location", "")


# ---------------------------------------------------------------------------
# Lacuna 5 — POST /api/editar-chamado sem bloqueio gestor
# ---------------------------------------------------------------------------


def test_gestor_api_editar_chamado_retorna_403(client_logado_gestor):
    """Lacuna 5: gestor não pode editar chamado via POST /api/editar-chamado — 403."""
    resp = client_logado_gestor.post(
        "/api/editar-chamado",
        data={"chamado_id": "ch_001"},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 403
    data = resp.get_json()
    assert data["sucesso"] is False


def test_supervisor_api_editar_chamado_nao_regrediu(client_logado_supervisor):
    """Regressão Lacuna 5: supervisor comum pode editar após bloqueio de gestor."""
    with patch("app.services.edicao_chamado_service.processar_edicao_chamado") as mock_proc:
        mock_proc.return_value = {"sucesso": True, "mensagem": "ok", "dados": {}}
        resp = client_logado_supervisor.post(
            "/api/editar-chamado",
            data={"chamado_id": "ch_001"},
            content_type="multipart/form-data",
        )
    assert resp.status_code == 200
    assert resp.get_json()["sucesso"] is True
