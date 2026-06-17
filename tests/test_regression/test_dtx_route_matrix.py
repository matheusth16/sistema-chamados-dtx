"""
Matriz de rotas × perfil — controle de acesso e integridade do navbar.

12 testes de acesso (4 rotas × 3 perfis) + 6 assertivas de HTML do navbar.
Nenhuma chamada real ao Firestore; todos os serviços são mockados.

Mapa de acesso:
  GET /                  → @requer_solicitante  → todos os perfis: 200
  GET /meus-chamados     → @requer_solicitante  → todos os perfis: 200
  GET /admin             → @requer_supervisor_area → supervisor+admin: 200 / solicitante: 302→/
  GET /admin/usuarios    → @requer_perfil('admin') → admin: 200 / outros: 302
"""

from contextlib import contextmanager
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.regression

# ---------------------------------------------------------------------------
# Contextos de mock reutilizáveis
# ---------------------------------------------------------------------------

_DASHBOARD_CTX = {
    "chamados": [],
    "gates": [],
    "responsaveis": [],
    "sla_map": {},
    "tem_proxima": False,
    "tem_anterior": False,
    "proximo_cursor": None,
    "cursor_anterior": None,
}

_MEUS_CHAMADOS_CTX = {
    "chamados": [],
    "pagina_atual": 1,
    "total_paginas": 1,
    "total_chamados": 0,
    "status_counts": {"Aberto": 0, "Em Atendimento": 0, "Concluído": 0, "Cancelado": 0},
    "cursor_next": None,
    "cursor_prev": None,
}


@contextmanager
def _mock_dashboard():
    with patch("app.routes.dashboard.obter_contexto_admin", return_value=_DASHBOARD_CTX):
        yield


@contextmanager
def _mock_meus_chamados():
    with patch("app.routes.chamados.listar_meus_chamados", return_value=_MEUS_CHAMADOS_CTX):
        yield


@contextmanager
def _mock_formulario():
    with (
        patch("app.routes.chamados.get_static_cached", return_value=[]),
        patch("app.routes.chamados.obter_total_por_contagem", return_value=0),
    ):
        yield


# ===========================================================================
# GET /  (@requer_solicitante → todos os perfis têm acesso)
# ===========================================================================


def test_formulario_solicitante_200(client_logado_solicitante):
    """GET / como solicitante retorna 200."""
    with _mock_formulario():
        r = client_logado_solicitante.get("/", follow_redirects=False)
    assert r.status_code == 200


def test_formulario_supervisor_200(client_logado_supervisor):
    """GET / como supervisor retorna 200 (@requer_solicitante permite supervisor e admin)."""
    with _mock_formulario():
        r = client_logado_supervisor.get("/", follow_redirects=False)
    assert r.status_code == 200


def test_formulario_admin_200(client_logado_admin):
    """GET / como admin retorna 200."""
    with _mock_formulario():
        r = client_logado_admin.get("/", follow_redirects=False)
    assert r.status_code == 200


# ===========================================================================
# GET /meus-chamados  (@requer_solicitante → todos os perfis têm acesso)
# ===========================================================================


def test_meus_chamados_solicitante_200(client_logado_solicitante):
    """GET /meus-chamados como solicitante retorna 200."""
    with _mock_meus_chamados():
        r = client_logado_solicitante.get("/meus-chamados", follow_redirects=False)
    assert r.status_code == 200


def test_meus_chamados_supervisor_200(client_logado_supervisor):
    """GET /meus-chamados como supervisor retorna 200."""
    with _mock_meus_chamados():
        r = client_logado_supervisor.get("/meus-chamados", follow_redirects=False)
    assert r.status_code == 200


def test_meus_chamados_admin_200(client_logado_admin):
    """GET /meus-chamados como admin retorna 200."""
    with _mock_meus_chamados():
        r = client_logado_admin.get("/meus-chamados", follow_redirects=False)
    assert r.status_code == 200


# ===========================================================================
# GET /admin  (@requer_supervisor_area → supervisor+admin: 200 / solicitante: 302)
# ===========================================================================


def test_dashboard_solicitante_bloqueado(client_logado_solicitante):
    """GET /admin como solicitante deve redirecionar (302) — acesso negado."""
    r = client_logado_solicitante.get("/admin", follow_redirects=False)
    assert r.status_code == 302
    # Redireciona para / (não para /admin), conforme @requer_supervisor_area
    assert "/admin" not in (r.location or "")


def test_dashboard_supervisor_200(client_logado_supervisor):
    """GET /painel como supervisor retorna 200."""
    with _mock_dashboard():
        r = client_logado_supervisor.get("/painel", follow_redirects=False)
    assert r.status_code == 200


def test_dashboard_supervisor_admin_url_redireciona(client_logado_supervisor):
    """GET /admin como supervisor redireciona para /painel (302)."""
    r = client_logado_supervisor.get("/admin", follow_redirects=False)
    assert r.status_code == 302
    assert "painel" in (r.location or "")


def test_dashboard_admin_200(client_logado_admin):
    """GET /admin como admin retorna 200."""
    with _mock_dashboard():
        r = client_logado_admin.get("/admin", follow_redirects=False)
    assert r.status_code == 200


# ===========================================================================
# GET /admin/usuarios  (@requer_perfil('admin') → admin: 200 / outros: 302)
# ===========================================================================


def test_usuarios_solicitante_bloqueado(client_logado_solicitante):
    """GET /admin/usuarios como solicitante deve redirecionar (302)."""
    r = client_logado_solicitante.get("/admin/usuarios", follow_redirects=False)
    assert r.status_code == 302


def test_usuarios_supervisor_bloqueado(client_logado_supervisor):
    """GET /admin/usuarios como supervisor deve redirecionar (302) — não é admin."""
    r = client_logado_supervisor.get("/admin/usuarios", follow_redirects=False)
    assert r.status_code == 302


def test_usuarios_admin_200(client_logado_admin):
    """GET /admin/usuarios como admin retorna 200."""
    with patch("app.routes.usuarios.Usuario.get_all", return_value=[]):
        r = client_logado_admin.get("/admin/usuarios", follow_redirects=False)
    assert r.status_code == 200


# ===========================================================================
# Navbar HTML — presença e ausência de links por perfil
# ===========================================================================


def test_navbar_solicitante_nao_tem_link_admin(client_logado_solicitante):
    """Navbar do solicitante não deve conter href="/admin" (sem link de Gestão)."""
    with _mock_meus_chamados():
        r = client_logado_solicitante.get("/meus-chamados", follow_redirects=False)
    assert r.status_code == 200
    html = r.data.decode("utf-8", errors="replace")
    # O navbar do solicitante não inclui link para /admin em nenhuma seção
    # (o dropdown de notificações usa /meus-chamados para solicitante)
    assert 'href="/admin"' not in html


def test_navbar_solicitante_tem_link_novo_chamado(client_logado_solicitante):
    """Navbar do solicitante deve conter link para / (Novo Chamado) com lang=pt_BR."""
    with _mock_meus_chamados():
        r = client_logado_solicitante.get("/meus-chamados?lang=pt_BR", follow_redirects=False)
    html = r.data.decode("utf-8", errors="replace")
    # href="/" aparece no nav link de Novo Chamado e na logo; verifica o texto PT-BR
    assert "Novo Chamado" in html


def test_navbar_supervisor_tem_gestao(client_logado_supervisor):
    """Navbar do supervisor deve conter href="/painel" (link de Gestão)."""
    with _mock_dashboard():
        r = client_logado_supervisor.get("/painel?lang=pt_BR", follow_redirects=False)
    assert r.status_code == 200
    html = r.data.decode("utf-8", errors="replace")
    assert 'href="/painel"' in html


def test_navbar_supervisor_tem_relatorios(client_logado_supervisor):
    """Navbar do supervisor deve conter link para /admin/relatorios."""
    with _mock_dashboard():
        r = client_logado_supervisor.get("/painel?lang=pt_BR", follow_redirects=False)
    html = r.data.decode("utf-8", errors="replace")
    assert "/admin/relatorios" in html


def test_navbar_admin_tem_gestao(client_logado_admin):
    """Navbar do admin deve conter href="/admin" (link de Gestão)."""
    with _mock_dashboard():
        r = client_logado_admin.get("/admin?lang=pt_BR", follow_redirects=False)
    assert r.status_code == 200
    html = r.data.decode("utf-8", errors="replace")
    assert 'href="/admin"' in html


def test_navbar_admin_tem_usuarios(client_logado_admin):
    """Navbar do admin deve conter link para /admin/usuarios (gestão de usuários)."""
    with _mock_dashboard():
        r = client_logado_admin.get("/admin?lang=pt_BR", follow_redirects=False)
    html = r.data.decode("utf-8", errors="replace")
    assert "/admin/usuarios" in html


# ===========================================================================
# Active state — aria-current="page" na rota ativa
# ===========================================================================


def test_active_state_solicitante_meus_chamados(client_logado_solicitante):
    """Em /meus-chamados o link Meus Chamados deve ter aria-current='page'."""
    with _mock_meus_chamados():
        r = client_logado_solicitante.get("/meus-chamados", follow_redirects=False)
    assert r.status_code == 200
    html = r.data.decode("utf-8", errors="replace")
    assert 'aria-current="page"' in html


def test_active_state_solicitante_novo_chamado_nao_ativo_em_meus(client_logado_solicitante):
    """Em /meus-chamados o link Novo Chamado NÃO deve ter aria-current='page'."""
    with _mock_meus_chamados():
        r = client_logado_solicitante.get("/meus-chamados", follow_redirects=False)
    html = r.data.decode("utf-8", errors="replace")
    # aria-current existe só uma vez (Meus Chamados), não no link /
    # Confirma que bg-dtx-50 aparece só no link ativo (Meus Chamados)
    # e que Novo Chamado não tem destaque fixo
    assert html.count('aria-current="page"') == 1


def test_active_state_admin_dashboard(client_logado_admin):
    """Em /admin o link Gestão deve ter aria-current='page'."""
    with _mock_dashboard():
        r = client_logado_admin.get("/admin", follow_redirects=False)
    assert r.status_code == 200
    html = r.data.decode("utf-8", errors="replace")
    assert 'aria-current="page"' in html


# ===========================================================================
# Hamburger — ausência para solicitante e ausência de "Navegação Rápida"
# ===========================================================================


def test_solicitante_sem_hamburger(client_logado_solicitante):
    """Navbar do solicitante não deve conter o botão hamburger."""
    with _mock_formulario():
        r = client_logado_solicitante.get("/", follow_redirects=False)
    assert r.status_code == 200
    html = r.data.decode("utf-8", errors="replace")
    assert 'id="btn-hamburger"' not in html


def test_sem_quick_navigation_solicitante(client_logado_solicitante):
    """Navbar do solicitante não deve conter a seção 'Navegação Rápida'."""
    with _mock_meus_chamados():
        r = client_logado_solicitante.get("/meus-chamados", follow_redirects=False)
    html = r.data.decode("utf-8", errors="replace")
    assert "quick_navigation" not in html
    assert "Navegação Rápida" not in html


def test_sem_quick_navigation_supervisor(client_logado_supervisor):
    """Navbar do supervisor não deve conter a seção 'Navegação Rápida'."""
    with _mock_dashboard():
        r = client_logado_supervisor.get("/admin", follow_redirects=False)
    html = r.data.decode("utf-8", errors="replace")
    assert "quick_navigation" not in html
    assert "Navegação Rápida" not in html


def test_sem_quick_navigation_admin(client_logado_admin):
    """Navbar do admin não deve conter a seção 'Navegação Rápida'."""
    with _mock_dashboard():
        r = client_logado_admin.get("/admin", follow_redirects=False)
    html = r.data.decode("utf-8", errors="replace")
    assert "quick_navigation" not in html
    assert "Navegação Rápida" not in html


def test_admin_tem_administration_section(client_logado_admin):
    """Navbar do admin deve conter links de Categorias e Usuários no dropdown (seção Administração)."""
    with _mock_dashboard():
        r = client_logado_admin.get("/admin?lang=pt_BR", follow_redirects=False)
    html = r.data.decode("utf-8", errors="replace")
    # A seção Administração expõe esses dois links no hamburger do admin
    assert "/admin/categorias" in html
    assert "/admin/usuarios" in html


def test_supervisor_tem_hamburger(client_logado_supervisor):
    """Navbar do supervisor deve conter o botão hamburger (tem links mobile)."""
    with _mock_dashboard():
        r = client_logado_supervisor.get("/painel", follow_redirects=False)
    html = r.data.decode("utf-8", errors="replace")
    assert 'id="btn-hamburger"' in html
