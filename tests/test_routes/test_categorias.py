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
        patch("app.routes.categorias.CategoriaSetor.get_all", return_value=[]),
        patch("app.routes.categorias.CategoriaGate.get_all", return_value=[]),
        patch("app.routes.categorias.CategoriaImpacto.get_all", return_value=[]),
    ):
        r = client_logado_admin.get("/admin/categorias", follow_redirects=False)
    assert r.status_code == 200
    assert (
        b"categorias" in r.data.lower() or b"setor" in r.data.lower() or b"gate" in r.data.lower()
    )


# ── Setores ────────────────────────────────────────────────────────────────────


def test_criar_setor_sucesso(client_logado_admin):
    """POST criar_setor com nome válido cria setor e redireciona."""
    with (
        patch("app.routes.categorias.CategoriaSetor") as mock_cls,
        patch("app.routes.categorias.cache_delete"),
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
    """POST criar_gate com nome válido cria gate e redireciona."""
    from unittest.mock import MagicMock

    with (
        patch("app.routes.categorias.CategoriaGate") as mock_cls,
        patch("app.routes.categorias.CategoriaGate.get_all", return_value=[]),
        patch("app.routes.categorias.cache_delete"),
        patch("app.routes.categorias.adicionar_traducao_customizada"),
    ):
        mock_gate = MagicMock()
        mock_gate.nome_en = "Gate A"
        mock_gate.nome_es = "Puerta A"
        mock_cls.return_value = mock_gate
        r = client_logado_admin.post(
            "/admin/categorias/gate/nova",
            data={"nome_pt": "Gate A", "descricao_pt": ""},
            follow_redirects=False,
        )
    assert r.status_code == 302


def test_criar_gate_sem_nome_redireciona(client_logado_admin):
    """POST criar_gate sem nome redireciona com erro gate_name_required."""
    r = client_logado_admin.post(
        "/admin/categorias/gate/nova",
        data={"nome_pt": ""},
        follow_redirects=False,
    )
    assert r.status_code == 302


def test_editar_gate_sucesso(client_logado_admin):
    """POST editar_gate com gate existente atualiza e redireciona."""
    from unittest.mock import MagicMock

    mock_gate = MagicMock()
    mock_gate.nome_pt = "Gate 1"
    mock_gate.descricao_pt = ""
    with (
        patch("app.routes.categorias.CategoriaGate.get_by_id", return_value=mock_gate),
        patch("app.routes.categorias.cache_delete"),
    ):
        r = client_logado_admin.post(
            "/admin/categorias/gate/g1/editar",
            data={"nome_pt": "Gate 1 Novo", "descricao_pt": "", "ativo": "on"},
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
    mock_gate.nome_pt = "Gate B"
    with (
        patch("app.routes.categorias.CategoriaGate.get_by_id", return_value=mock_gate),
        patch("app.routes.categorias.cache_delete"),
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
