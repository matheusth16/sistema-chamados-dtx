"""Testes das rotas de administração de categorias (/admin/categorias). Requer perfil admin."""

from unittest.mock import patch


def test_admin_categorias_sem_login_redireciona(client):
    """GET /admin/categorias sem login redireciona para /login."""
    r = client.get("/admin/categorias", follow_redirects=False)
    assert r.status_code == 302
    assert "login" in r.location


def test_admin_categorias_com_solicitante_nao_acessa(client_logado_solicitante):
    """GET /admin/categorias com perfil solicitante não acessa: 403 ou 302 (ex.: redirect troca de senha)."""
    r = client_logado_solicitante.get("/admin/categorias", follow_redirects=False)
    assert r.status_code in (403, 302)
    if r.status_code == 302:
        assert "/admin/categorias" not in (r.location or "")


def test_admin_categorias_com_admin_retorna_200(client_logado_admin):
    """GET /admin/categorias com admin retorna 200 e página de categorias."""
    with (
        patch("app.routes.categorias.CategoriaSetor.get_all_incluindo_inativos", return_value=[]),
        patch("app.routes.categorias.CategoriaGate.get_all", return_value=[]),
        patch("app.routes.categorias.CategoriaImpacto.get_all_incluindo_inativos", return_value=[]),
    ):
        r = client_logado_admin.get("/admin/categorias", follow_redirects=False)
    assert r.status_code == 200
    assert (
        b"categorias" in r.data.lower() or b"setor" in r.data.lower() or b"gate" in r.data.lower()
    )


def test_admin_categorias_passa_gate_pai_opcoes(client_logado_admin):
    """GET /admin/categorias passa gate_pai_opcoes ao template."""
    with (
        patch("app.routes.categorias.CategoriaSetor.get_all_incluindo_inativos", return_value=[]),
        patch("app.routes.categorias.CategoriaGate.get_all", return_value=[]),
        patch("app.routes.categorias.CategoriaImpacto.get_all_incluindo_inativos", return_value=[]),
    ):
        r = client_logado_admin.get("/admin/categorias", follow_redirects=False)
    assert r.status_code == 200
    assert b"Gate 1" in r.data


# ── Setores ────────────────────────────────────────────────────────────────────


def test_criar_setor_sucesso(client_logado_admin):
    """POST criar_setor com nome válido cria setor e redireciona."""
    with (
        patch("app.routes.categorias.CategoriaSetor") as mock_cls,
        patch("app.routes.categorias.cache_delete"),
        patch("app.routes.categorias.static_cache_delete"),
        patch("app.routes.categorias.adicionar_traducao_customizada"),
    ):
        mock_setor = mock_cls.return_value
        mock_setor.nome_pt = "Qualidade"
        mock_setor.nome_en = "Quality"
        mock_setor.nome_es = "Calidad"
        r = client_logado_admin.post(
            "/admin/categorias/setor/nova",
            data={"nome_pt": "Qualidade", "descricao_pt": "Setor de qualidade"},
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert "/admin/categorias" in (r.location or "")


def test_criar_setor_sem_nome_redireciona_com_erro(client_logado_admin):
    """POST criar_setor sem nome redireciona com erro sector_name_required."""
    r = client_logado_admin.post(
        "/admin/categorias/setor/nova",
        data={"nome_pt": "", "descricao_pt": ""},
        follow_redirects=False,
    )
    assert r.status_code == 302


def test_editar_setor_sucesso(client_logado_admin):
    """POST editar_setor com setor existente atualiza e redireciona."""
    from unittest.mock import MagicMock

    mock_setor = MagicMock()
    mock_setor.nome_pt = "TI"
    mock_setor.descricao_pt = ""
    with (
        patch("app.routes.categorias.CategoriaSetor.get_by_id", return_value=mock_setor),
        patch("app.routes.categorias.cache_delete"),
    ):
        r = client_logado_admin.post(
            "/admin/categorias/setor/s1/editar",
            data={"nome_pt": "TI Atualizado", "descricao_pt": "Desc", "ativo": "on"},
            follow_redirects=False,
        )
    assert r.status_code == 302


def test_editar_setor_nao_encontrado_redireciona(client_logado_admin):
    """POST editar_setor com ID inexistente redireciona com erro sector_not_found."""
    with patch("app.routes.categorias.CategoriaSetor.get_by_id", return_value=None):
        r = client_logado_admin.post(
            "/admin/categorias/setor/nao/editar",
            data={"nome_pt": "X"},
            follow_redirects=False,
        )
    assert r.status_code == 302


def test_excluir_setor_sucesso(client_logado_admin):
    """POST excluir_setor com setor existente deleta e redireciona."""
    from unittest.mock import MagicMock

    mock_setor = MagicMock()
    mock_setor.nome_pt = "Almoxarifado"
    with (
        patch("app.routes.categorias.CategoriaSetor.get_by_id", return_value=mock_setor),
        patch("app.routes.categorias.cache_delete"),
        patch("app.routes.categorias.static_cache_delete"),
    ):
        r = client_logado_admin.post(
            "/admin/categorias/setor/s2/excluir",
            follow_redirects=False,
        )
    assert r.status_code == 302
    mock_setor.delete.assert_called_once()


def test_excluir_setor_nao_encontrado_redireciona(client_logado_admin):
    """POST excluir_setor com ID inexistente redireciona com erro."""
    with patch("app.routes.categorias.CategoriaSetor.get_by_id", return_value=None):
        r = client_logado_admin.post("/admin/categorias/setor/nao/excluir", follow_redirects=False)
    assert r.status_code == 302


# ── Gates ──────────────────────────────────────────────────────────────────────


def test_criar_gate_sucesso(client_logado_admin):
    """POST criar_gate com gate_pai + etapa válidos cria gate e redireciona."""
    from unittest.mock import MagicMock

    with (
        patch("app.routes.categorias.CategoriaGate") as mock_cls,
        patch("app.routes.categorias.CategoriaGate.get_all", return_value=[]),
        patch("app.routes.categorias.cache_delete"),
        patch("app.routes.categorias.static_cache_delete"),
        patch("app.routes.categorias.adicionar_traducao_customizada"),
    ):
        mock_gate = MagicMock()
        mock_gate.nome_en = "Gate 1 - Disassembly"
        mock_gate.nome_es = "Gate 1 - Desmontaje"
        mock_gate.nome_pt = "Gate 1 - Desmontagem"
        mock_cls.return_value = mock_gate
        r = client_logado_admin.post(
            "/admin/categorias/gate/nova",
            data={"gate_pai": "Gate 1", "etapa": "Desmontagem", "descricao_pt": ""},
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert "/admin/categorias" in (r.location or "")


def test_criar_gate_sem_etapa_redireciona(client_logado_admin):
    """POST criar_gate sem etapa redireciona com erro gate_name_required."""
    r = client_logado_admin.post(
        "/admin/categorias/gate/nova",
        data={"gate_pai": "Gate 1", "etapa": ""},
        follow_redirects=False,
    )
    assert r.status_code == 302


def test_criar_gate_sem_nome_redireciona(client_logado_admin):
    """POST criar_gate sem gate_pai nem etapa redireciona com erro."""
    r = client_logado_admin.post(
        "/admin/categorias/gate/nova",
        data={"gate_pai": "", "etapa": ""},
        follow_redirects=False,
    )
    assert r.status_code == 302


def test_criar_gate_gate_pai_invalido_redireciona(client_logado_admin):
    """POST criar_gate com gate_pai fora da allowlist redireciona com erro."""
    r = client_logado_admin.post(
        "/admin/categorias/gate/nova",
        data={"gate_pai": "Gate 99", "etapa": "Teste"},
        follow_redirects=False,
    )
    assert r.status_code == 302


def test_editar_gate_sucesso(client_logado_admin):
    """POST editar_gate com gate_pai + etapa válidos atualiza e redireciona."""
    from unittest.mock import MagicMock

    mock_gate = MagicMock()
    mock_gate.nome_pt = "Gate 1 - Desmontagem"
    mock_gate.descricao_pt = ""
    mock_gate.gate_pai = "Gate 1"
    mock_gate.etapa = "Desmontagem"
    with (
        patch("app.routes.categorias.CategoriaGate.get_by_id", return_value=mock_gate),
        patch("app.routes.categorias.cache_delete"),
        patch("app.routes.categorias.static_cache_delete"),
    ):
        r = client_logado_admin.post(
            "/admin/categorias/gate/g1/editar",
            data={"gate_pai": "Gate 1", "etapa": "Limpeza", "descricao_pt": "", "ativo": "on"},
            follow_redirects=False,
        )
    assert r.status_code == 302


def test_editar_gate_nao_encontrado(client_logado_admin):
    """POST editar_gate com ID inexistente redireciona com erro."""
    with patch("app.routes.categorias.CategoriaGate.get_by_id", return_value=None):
        r = client_logado_admin.post(
            "/admin/categorias/gate/nao/editar",
            data={"nome_pt": "X"},
            follow_redirects=False,
        )
    assert r.status_code == 302


def test_excluir_gate_sucesso(client_logado_admin):
    """POST excluir_gate com gate existente deleta e redireciona."""
    from unittest.mock import MagicMock

    mock_gate = MagicMock()
    mock_gate.nome_pt = "Gate 1 - Desmontagem"
    with (
        patch("app.routes.categorias.CategoriaGate.get_by_id", return_value=mock_gate),
        patch("app.routes.categorias.cache_delete"),
        patch("app.routes.categorias.static_cache_delete"),
    ):
        r = client_logado_admin.post("/admin/categorias/gate/g2/excluir", follow_redirects=False)
    assert r.status_code == 302
    mock_gate.delete.assert_called_once()


def test_excluir_gate_nao_encontrado(client_logado_admin):
    """POST excluir_gate com ID inexistente redireciona com erro."""
    with patch("app.routes.categorias.CategoriaGate.get_by_id", return_value=None):
        r = client_logado_admin.post("/admin/categorias/gate/nao/excluir", follow_redirects=False)
    assert r.status_code == 302


# ── Impactos ───────────────────────────────────────────────────────────────────


def test_criar_impacto_sucesso(client_logado_admin):
    """POST criar_impacto com nome válido cria impacto e redireciona."""
    with (
        patch("app.routes.categorias.CategoriaImpacto") as mock_cls,
        patch("app.routes.categorias.cache_delete"),
        patch("app.routes.categorias.static_cache_delete"),
        patch("app.routes.categorias.adicionar_traducao_customizada"),
    ):
        from unittest.mock import MagicMock

        mock_imp = MagicMock()
        mock_imp.nome_en = "High"
        mock_imp.nome_es = "Alto"
        mock_cls.return_value = mock_imp
        r = client_logado_admin.post(
            "/admin/categorias/impacto/nova",
            data={"nome_pt": "Alto", "descricao_pt": ""},
            follow_redirects=False,
        )
    assert r.status_code == 302


def test_criar_impacto_sem_nome_redireciona(client_logado_admin):
    """POST criar_impacto sem nome redireciona com erro impact_name_required."""
    r = client_logado_admin.post(
        "/admin/categorias/impacto/nova",
        data={"nome_pt": ""},
        follow_redirects=False,
    )
    assert r.status_code == 302


def test_editar_impacto_sucesso(client_logado_admin):
    """POST editar_impacto com impacto existente atualiza e redireciona."""
    from unittest.mock import MagicMock

    mock_imp = MagicMock()
    mock_imp.nome_pt = "Baixo"
    mock_imp.descricao_pt = ""
    with (
        patch("app.routes.categorias.CategoriaImpacto.get_by_id", return_value=mock_imp),
        patch("app.routes.categorias.cache_delete"),
    ):
        r = client_logado_admin.post(
            "/admin/categorias/impacto/i1/editar",
            data={"nome_pt": "Baixo Novo", "descricao_pt": "", "ativo": "on"},
            follow_redirects=False,
        )
    assert r.status_code == 302


def test_editar_impacto_nao_encontrado(client_logado_admin):
    """POST editar_impacto com ID inexistente redireciona com erro."""
    with patch("app.routes.categorias.CategoriaImpacto.get_by_id", return_value=None):
        r = client_logado_admin.post(
            "/admin/categorias/impacto/nao/editar",
            data={"nome_pt": "X"},
            follow_redirects=False,
        )
    assert r.status_code == 302


def test_excluir_impacto_sucesso(client_logado_admin):
    """POST excluir_impacto com impacto existente deleta e redireciona."""
    from unittest.mock import MagicMock

    mock_imp = MagicMock()
    mock_imp.nome_pt = "Crítico"
    with (
        patch("app.routes.categorias.CategoriaImpacto.get_by_id", return_value=mock_imp),
        patch("app.routes.categorias.cache_delete"),
        patch("app.routes.categorias.static_cache_delete"),
    ):
        r = client_logado_admin.post("/admin/categorias/impacto/i2/excluir", follow_redirects=False)
    assert r.status_code == 302
    mock_imp.delete.assert_called_once()


def test_excluir_impacto_nao_encontrado(client_logado_admin):
    """POST excluir_impacto com ID inexistente redireciona com erro."""
    with patch("app.routes.categorias.CategoriaImpacto.get_by_id", return_value=None):
        r = client_logado_admin.post(
            "/admin/categorias/impacto/nao/excluir", follow_redirects=False
        )
    assert r.status_code == 302


# ── Handlers de exceção (except Exception) ────────────────────────────────────


def test_criar_setor_excecao_redireciona_com_erro(client_logado_admin):
    """POST criar_setor com exceção no .save() redireciona para /admin/categorias."""
    from unittest.mock import MagicMock

    mock_setor = MagicMock()
    mock_setor.save.side_effect = Exception("firestore error")
    mock_setor.nome_en = "Quality"
    mock_setor.nome_es = "Calidad"
    with patch("app.routes.categorias.CategoriaSetor", return_value=mock_setor):
        r = client_logado_admin.post(
            "/admin/categorias/setor/nova",
            data={"nome_pt": "Qualidade", "descricao_pt": ""},
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert "/admin/categorias" in (r.location or "")


def test_criar_gate_excecao_redireciona_com_erro(client_logado_admin):
    """POST criar_gate com exceção em CategoriaGate.get_all() redireciona."""
    with patch(
        "app.routes.categorias.CategoriaGate.get_all",
        side_effect=Exception("firestore error"),
    ):
        r = client_logado_admin.post(
            "/admin/categorias/gate/nova",
            data={"gate_pai": "Gate 1", "etapa": "Desmontagem", "descricao_pt": ""},
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert "/admin/categorias" in (r.location or "")


def test_criar_impacto_excecao_redireciona_com_erro(client_logado_admin):
    """POST criar_impacto com exceção no .save() redireciona para /admin/categorias."""
    from unittest.mock import MagicMock

    mock_imp = MagicMock()
    mock_imp.save.side_effect = Exception("firestore error")
    mock_imp.nome_en = "High"
    mock_imp.nome_es = "Alto"
    with patch("app.routes.categorias.CategoriaImpacto", return_value=mock_imp):
        r = client_logado_admin.post(
            "/admin/categorias/impacto/nova",
            data={"nome_pt": "Alto", "descricao_pt": ""},
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert "/admin/categorias" in (r.location or "")


def test_excluir_setor_excecao_redireciona_com_erro(client_logado_admin):
    """POST excluir_setor com exceção no .delete() redireciona com erro."""
    from unittest.mock import MagicMock

    mock_setor = MagicMock()
    mock_setor.nome_pt = "Almoxarifado"
    mock_setor.delete.side_effect = Exception("firestore error")
    with patch("app.routes.categorias.CategoriaSetor.get_by_id", return_value=mock_setor):
        r = client_logado_admin.post(
            "/admin/categorias/setor/s_err/excluir",
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert "/admin/categorias" in (r.location or "")


def test_excluir_gate_excecao_redireciona_com_erro(client_logado_admin):
    """POST excluir_gate com exceção no .delete() redireciona com erro."""
    from unittest.mock import MagicMock

    mock_gate = MagicMock()
    mock_gate.nome_pt = "Gate 1 - Desmontagem"
    mock_gate.delete.side_effect = Exception("firestore error")
    with patch("app.routes.categorias.CategoriaGate.get_by_id", return_value=mock_gate):
        r = client_logado_admin.post(
            "/admin/categorias/gate/g_err/excluir",
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert "/admin/categorias" in (r.location or "")


# ── Ações em lote ─────────────────────────────────────────────────────────────


def test_lote_setores_sem_ids_redireciona(client_logado_admin):
    """POST acao_lote_setores sem ids redireciona com aviso."""
    r = client_logado_admin.post(
        "/admin/categorias/setor/lote",
        data={"acao": "excluir"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert "/admin/categorias" in (r.location or "")


def test_lote_setores_excluir_sucesso(client_logado_admin):
    """POST acao_lote_setores acao=excluir com IDs válidos deleta e redireciona."""
    from unittest.mock import MagicMock

    mock_setor = MagicMock()
    mock_setor.nome_pt = "TI"
    with (
        patch("app.routes.categorias.CategoriaSetor.get_by_id", return_value=mock_setor),
        patch("app.routes.categorias.cache_delete"),
        patch("app.routes.categorias.static_cache_delete"),
    ):
        r = client_logado_admin.post(
            "/admin/categorias/setor/lote",
            data={"acao": "excluir", "ids": ["s1", "s2"]},
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert mock_setor.delete.call_count == 2


def test_lote_setores_ativar_sucesso(client_logado_admin):
    """POST acao_lote_setores acao=ativar com IDs válidos ativa e redireciona."""
    from unittest.mock import MagicMock

    mock_setor = MagicMock()
    mock_setor.ativo = False
    with (
        patch("app.routes.categorias.CategoriaSetor.get_by_id", return_value=mock_setor),
        patch("app.routes.categorias.cache_delete"),
        patch("app.routes.categorias.static_cache_delete"),
    ):
        r = client_logado_admin.post(
            "/admin/categorias/setor/lote",
            data={"acao": "ativar", "ids": ["s1"]},
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert mock_setor.ativo is True
    mock_setor.save.assert_called_once()


def test_lote_setores_desativar_sucesso(client_logado_admin):
    """POST acao_lote_setores acao=desativar com IDs válidos desativa e redireciona."""
    from unittest.mock import MagicMock

    mock_setor = MagicMock()
    mock_setor.ativo = True
    with (
        patch("app.routes.categorias.CategoriaSetor.get_by_id", return_value=mock_setor),
        patch("app.routes.categorias.cache_delete"),
        patch("app.routes.categorias.static_cache_delete"),
    ):
        r = client_logado_admin.post(
            "/admin/categorias/setor/lote",
            data={"acao": "desativar", "ids": ["s1"]},
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert mock_setor.ativo is False
    mock_setor.save.assert_called_once()


def test_lote_setores_excecao_redireciona_com_erro(client_logado_admin):
    """POST acao_lote_setores com exceção redireciona com erro."""
    with patch(
        "app.routes.categorias.CategoriaSetor.get_by_id",
        side_effect=Exception("firestore error"),
    ):
        r = client_logado_admin.post(
            "/admin/categorias/setor/lote",
            data={"acao": "excluir", "ids": ["s_err"]},
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert "/admin/categorias" in (r.location or "")


def test_lote_gates_sem_ids_redireciona(client_logado_admin):
    """POST acao_lote_gates sem ids redireciona com aviso."""
    r = client_logado_admin.post(
        "/admin/categorias/gate/lote",
        data={"acao": "excluir"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert "/admin/categorias" in (r.location or "")


def test_lote_gates_excluir_sucesso(client_logado_admin):
    """POST acao_lote_gates acao=excluir com IDs válidos deleta e redireciona."""
    from unittest.mock import MagicMock

    mock_gate = MagicMock()
    mock_gate.nome_pt = "Gate 1 - Desmontagem"
    with (
        patch("app.routes.categorias.CategoriaGate.get_by_id", return_value=mock_gate),
        patch("app.routes.categorias.cache_delete"),
        patch("app.routes.categorias.static_cache_delete"),
    ):
        r = client_logado_admin.post(
            "/admin/categorias/gate/lote",
            data={"acao": "excluir", "ids": ["g1"]},
            follow_redirects=False,
        )
    assert r.status_code == 302
    mock_gate.delete.assert_called_once()


def test_lote_gates_ativar_sucesso(client_logado_admin):
    """POST acao_lote_gates acao=ativar ativa e redireciona."""
    from unittest.mock import MagicMock

    mock_gate = MagicMock()
    mock_gate.ativo = False
    with (
        patch("app.routes.categorias.CategoriaGate.get_by_id", return_value=mock_gate),
        patch("app.routes.categorias.cache_delete"),
        patch("app.routes.categorias.static_cache_delete"),
    ):
        r = client_logado_admin.post(
            "/admin/categorias/gate/lote",
            data={"acao": "ativar", "ids": ["g1"]},
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert mock_gate.ativo is True


def test_lote_gates_excecao_redireciona_com_erro(client_logado_admin):
    """POST acao_lote_gates com exceção redireciona com erro."""
    with patch(
        "app.routes.categorias.CategoriaGate.get_by_id",
        side_effect=Exception("firestore error"),
    ):
        r = client_logado_admin.post(
            "/admin/categorias/gate/lote",
            data={"acao": "excluir", "ids": ["g_err"]},
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert "/admin/categorias" in (r.location or "")


def test_lote_impactos_sem_ids_redireciona(client_logado_admin):
    """POST acao_lote_impactos sem ids redireciona com aviso."""
    r = client_logado_admin.post(
        "/admin/categorias/impacto/lote",
        data={"acao": "excluir"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert "/admin/categorias" in (r.location or "")


def test_lote_impactos_excluir_sucesso(client_logado_admin):
    """POST acao_lote_impactos acao=excluir com IDs válidos deleta e redireciona."""
    from unittest.mock import MagicMock

    mock_imp = MagicMock()
    mock_imp.nome_pt = "Alto"
    with (
        patch("app.routes.categorias.CategoriaImpacto.get_by_id", return_value=mock_imp),
        patch("app.routes.categorias.cache_delete"),
        patch("app.routes.categorias.static_cache_delete"),
    ):
        r = client_logado_admin.post(
            "/admin/categorias/impacto/lote",
            data={"acao": "excluir", "ids": ["i1", "i2"]},
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert mock_imp.delete.call_count == 2


def test_lote_impactos_desativar_sucesso(client_logado_admin):
    """POST acao_lote_impactos acao=desativar desativa e redireciona."""
    from unittest.mock import MagicMock

    mock_imp = MagicMock()
    mock_imp.ativo = True
    with (
        patch("app.routes.categorias.CategoriaImpacto.get_by_id", return_value=mock_imp),
        patch("app.routes.categorias.cache_delete"),
        patch("app.routes.categorias.static_cache_delete"),
    ):
        r = client_logado_admin.post(
            "/admin/categorias/impacto/lote",
            data={"acao": "desativar", "ids": ["i1"]},
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert mock_imp.ativo is False
    mock_imp.save.assert_called_once()


def test_lote_impactos_excecao_redireciona_com_erro(client_logado_admin):
    """POST acao_lote_impactos com exceção redireciona com erro."""
    with patch(
        "app.routes.categorias.CategoriaImpacto.get_by_id",
        side_effect=Exception("firestore error"),
    ):
        r = client_logado_admin.post(
            "/admin/categorias/impacto/lote",
            data={"acao": "excluir", "ids": ["i_err"]},
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert "/admin/categorias" in (r.location or "")
