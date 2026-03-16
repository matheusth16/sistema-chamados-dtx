"""Testes do serviço de dashboard (obter_contexto_admin, _filtrar_chamados_por_permissao)."""

from unittest.mock import MagicMock, patch


def test_obter_contexto_admin_retorna_dict_com_chaves_esperadas():
    """obter_contexto_admin retorna dicionário com chamados, gates, responsaveis, sla_map, paginação."""
    from app.services.dashboard_service import obter_contexto_admin

    user = MagicMock()
    user.perfil = "admin"
    user.areas = ["Geral"]
    user.id = "admin1"

    with patch("app.services.dashboard_service.get_static_cached") as mock_cache:
        mock_cache.return_value = []
        with patch("app.services.dashboard_service.db") as mock_db:
            mock_ref = MagicMock()
            mock_db.collection.return_value = mock_ref
            with patch(
                "app.services.dashboard_service.aplicar_filtros_dashboard_com_paginacao"
            ) as mock_filtros:
                mock_filtros.return_value = {
                    "docs": [],
                    "proximo_cursor": None,
                    "tem_proxima": False,
                    "cursor_anterior": None,
                    "tem_anterior": False,
                }
                with patch(
                    "app.services.dashboard_service.obter_sla_para_exibicao", return_value=None
                ):
                    ctx = obter_contexto_admin(user, {}, itens_por_pagina=25)

    assert "chamados" in ctx
    assert "lista_responsaveis" in ctx
    assert "lista_gates" in ctx
    assert "proximo_cursor" in ctx
    assert "tem_proxima" in ctx
    assert "tem_anterior" in ctx
    assert isinstance(ctx["chamados"], list)
    assert isinstance(ctx["lista_responsaveis"], list)
    assert isinstance(ctx["lista_gates"], list)


def test_filtrar_chamados_por_permissao_admin_retorna_todos():
    """_filtrar_chamados_por_permissao com usuário admin retorna todos os chamados convertidos."""
    from app.models import Chamado
    from app.services.dashboard_service import _filtrar_chamados_por_permissao

    user = MagicMock()
    user.perfil = "admin"

    doc1 = MagicMock()
    doc1.id = "d1"
    doc1.to_dict.return_value = {
        "categoria": "Manutencao",
        "tipo_solicitacao": "Corretiva",
        "descricao": "D1",
        "responsavel": "",
        "numero_chamado": "001",
        "area": "Manutencao",
    }
    doc2 = MagicMock()
    doc2.id = "d2"
    doc2.to_dict.return_value = {
        "categoria": "Manutencao",
        "tipo_solicitacao": "Preventiva",
        "descricao": "D2",
        "responsavel": "",
        "numero_chamado": "002",
        "area": "Manutencao",
    }
    docs = [doc1, doc2]

    result = _filtrar_chamados_por_permissao(docs, user)
    assert len(result) == 2
    assert all(isinstance(c, Chamado) for c in result)
    assert result[0].numero_chamado == "001"
    assert result[1].numero_chamado == "002"


def test_filtrar_chamados_por_permissao_supervisor_filtra_por_area():
    """_filtrar_chamados_por_permissao com supervisor usa usuario_pode_ver_chamado_otimizado."""
    from app.services.dashboard_service import _filtrar_chamados_por_permissao

    user = MagicMock()
    user.perfil = "supervisor"
    user.areas = ["Manutencao"]

    doc1 = MagicMock()
    doc1.id = "d1"
    doc1.to_dict.return_value = {
        "categoria": "Manutencao",
        "tipo_solicitacao": "Corretiva",
        "descricao": "D1",
        "responsavel": "",
        "numero_chamado": "001",
        "area": "Manutencao",
        "responsavel_id": None,
    }
    docs = [doc1]

    with (
        patch("app.services.dashboard_service.Usuario.get_by_id", return_value=None),
        patch("app.services.dashboard_service.usuario_pode_ver_chamado_otimizado") as mock_perm,
    ):
        mock_perm.return_value = True
        result = _filtrar_chamados_por_permissao(docs, user)
    assert len(result) == 1
    mock_perm.assert_called()
