"""
Smoke tests de internacionalização — PT-BR, EN e ES.

Verifica que a mudança de idioma via ?lang= altera o texto renderizado
de forma determinística para os três idiomas suportados.

Pipeline testado:
  ?lang=<code> → session["language"] → t(key) → Jinja2 → HTML

9 cenários: 3 perfis × 3 idiomas, usando nav labels como sinal observável
porque são estritamente controlados por translations.json e variam por idioma.
Nenhum acesso real ao Firestore.
"""

from unittest.mock import patch

import pytest

pytestmark = pytest.mark.regression

# ---------------------------------------------------------------------------
# Contextos de mock reutilizáveis
# ---------------------------------------------------------------------------

_MEUS_CHAMADOS_CTX = {
    "chamados": [],
    "pagina_atual": 1,
    "total_paginas": 1,
    "total_chamados": 0,
    "status_counts": {"Aberto": 0, "Em Atendimento": 0, "Concluído": 0, "Cancelado": 0},
    "cursor_next": None,
    "cursor_prev": None,
}

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


def _meus_chamados(client, lang: str):
    with (
        patch("app.routes.chamados.listar_meus_chamados", return_value=_MEUS_CHAMADOS_CTX),
        patch("app.routes.chamados.listar_chamados_como_observador", return_value=[]),
    ):
        return client.get(f"/meus-chamados?lang={lang}", follow_redirects=False)


def _admin(client, lang: str):
    with (
        patch("app.routes.dashboard.obter_contexto_admin", return_value=_DASHBOARD_CTX),
        patch("app.routes.dashboard.get_static_cached", return_value=[]),
    ):
        return client.get(f"/admin?lang={lang}", follow_redirects=False)


def _painel(client, lang: str):
    with (
        patch("app.routes.dashboard.obter_contexto_admin", return_value=_DASHBOARD_CTX),
        patch("app.routes.dashboard.get_static_cached", return_value=[]),
    ):
        return client.get(f"/painel?lang={lang}", follow_redirects=False)


def _html(r) -> str:
    return r.data.decode("utf-8", errors="replace")


# ===========================================================================
# Solicitante — nav_new_ticket muda com idioma
# ===========================================================================
# translations.json: nav_new_ticket → pt_BR: "Novo Chamado" / en: "New Ticket" / es: "Nuevo Ticket"


def test_i18n_solicitante_ptbr_novo_chamado(client_logado_solicitante):
    """PT-BR: navbar do solicitante exibe 'Novo Chamado'."""
    r = _meus_chamados(client_logado_solicitante, "pt_BR")
    assert r.status_code == 200
    assert "Novo Chamado" in _html(r), "PT-BR: 'Novo Chamado' não encontrado na navbar"


def test_i18n_solicitante_en_new_ticket(client_logado_solicitante):
    """EN: navbar do solicitante exibe 'New Ticket'."""
    r = _meus_chamados(client_logado_solicitante, "en")
    assert r.status_code == 200
    assert "New Ticket" in _html(r), "EN: 'New Ticket' não encontrado na navbar"


def test_i18n_solicitante_es_nuevo_ticket(client_logado_solicitante):
    """ES: navbar do solicitante exibe 'Nuevo Ticket'."""
    r = _meus_chamados(client_logado_solicitante, "es")
    assert r.status_code == 200
    assert "Nuevo Ticket" in _html(r), "ES: 'Nuevo Ticket' não encontrado na navbar"


# ===========================================================================
# Supervisor — nav_management muda com idioma
# ===========================================================================
# translations.json: nav_management → pt_BR: "Gestão" / en: "Management" / es: "Gestión"


def test_i18n_supervisor_ptbr_gestao(client_logado_supervisor):
    """PT-BR: navbar do supervisor exibe 'Gestão' (em /painel)."""
    r = _painel(client_logado_supervisor, "pt_BR")
    assert r.status_code == 200
    assert "Gestão" in _html(r), "PT-BR: 'Gestão' não encontrado na navbar do supervisor"


def test_i18n_supervisor_en_management(client_logado_supervisor):
    """EN: navbar do supervisor exibe 'Management' (em /painel)."""
    r = _painel(client_logado_supervisor, "en")
    assert r.status_code == 200
    assert "Management" in _html(r), "EN: 'Management' não encontrado na navbar do supervisor"


def test_i18n_supervisor_es_gestion(client_logado_supervisor):
    """ES: navbar do supervisor exibe 'Gestión' (em /painel)."""
    r = _painel(client_logado_supervisor, "es")
    assert r.status_code == 200
    assert "Gestión" in _html(r), "ES: 'Gestión' não encontrado na navbar do supervisor"


# ===========================================================================
# Admin — nav_my_reports muda com idioma
# ===========================================================================
# translations.json: nav_my_reports → pt_BR: "Meus Relatórios" / en: "My Reports" / es: "Mis Informes"


def test_i18n_admin_ptbr_meus_relatorios(client_logado_admin):
    """PT-BR: navbar do admin exibe 'Meus Relatórios'."""
    r = _admin(client_logado_admin, "pt_BR")
    assert r.status_code == 200
    assert "Meus Relatórios" in _html(r), "PT-BR: 'Meus Relatórios' não encontrado"


def test_i18n_admin_en_my_reports(client_logado_admin):
    """EN: navbar do admin exibe 'My Reports'."""
    r = _admin(client_logado_admin, "en")
    assert r.status_code == 200
    assert "My Reports" in _html(r), "EN: 'My Reports' não encontrado"


def test_i18n_admin_es_mis_informes(client_logado_admin):
    """ES: navbar do admin exibe 'Mis Informes'."""
    r = _admin(client_logado_admin, "es")
    assert r.status_code == 200
    assert "Mis Informes" in _html(r), "ES: 'Mis Informes' não encontrado"
