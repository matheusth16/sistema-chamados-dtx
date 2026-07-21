"""Regressão: correções de acessibilidade (auditoria WCAG 2.1 AA de 2026-07-21).

Cobre os 7 achados da auditoria manual: dropdown hover-only, foco do tour de
onboarding, modais sem role=dialog, contraste de --color-surface-muted,
autocomplete de observadores sem semântica de combobox, cabeçalhos
ordenáveis sem suporte a teclado, e toasts sem aria-live.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

BASE_DIR = Path(__file__).resolve().parents[2]


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


def test_dropdown_idioma_perfil_abre_por_teclado():
    """CSS: dropdowns de idioma/perfil devem abrir também via :focus-within, não só :hover."""
    css = (BASE_DIR / "app/static/css/bento.css").read_text(encoding="utf-8")
    assert ".bento-nav-hover-wrap:focus-within .bento-nav-dropdown" in css


def test_onboarding_move_foco_e_faz_trap_no_card():
    """JS: tour de onboarding deve mover foco pro card ao abrir e prender Tab dentro dele."""
    js = (BASE_DIR / "app/static/js/onboarding.js").read_text(encoding="utf-8")
    assert "card.focus" in js or "primeiro.focus" in js or "focaveis[0].focus" in js
    assert "Tab" in js


def test_modais_reabrir_e_cancelar_admin_tem_role_dialog():
    """modal-reabrir-admin e modal-cancelar-admin devem ter role=dialog + aria-modal, como os
    outros 4 modais da mesma página (modal-transferir-area etc.)."""
    html = (BASE_DIR / "app/templates/visualizar_chamado.html").read_text(encoding="utf-8")
    trecho_reabrir = html.split('id="modal-reabrir-admin"')[1][:200]
    trecho_cancelar = html.split('id="modal-cancelar-admin"')[1][:200]
    assert 'role="dialog"' in trecho_reabrir
    assert 'role="dialog"' in trecho_cancelar


def test_contraste_surface_muted_atende_wcag_aa():
    """--color-surface-muted precisa ter contraste >= 4.5:1 sobre fundo branco (WCAG 1.4.1 AA)."""
    css = (BASE_DIR / "app/static/css/input.css").read_text(encoding="utf-8")
    linha = next(linha for linha in css.splitlines() if "--color-surface-muted:" in linha)
    hex_cor = linha.split(":")[1].strip().split(";")[0].split()[0].lstrip("#")
    r, g, b = (int(hex_cor[i : i + 2], 16) for i in (0, 2, 4))

    def _linear(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    luminancia = 0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b)
    contraste = (1.05) / (luminancia + 0.05)
    assert contraste >= 4.5, f"Contraste atual: {contraste:.2f}:1 (mínimo AA: 4.5:1)"


def test_observadores_autocomplete_tem_semantica_combobox(client_logado_solicitante):
    """Campo de busca de observadores precisa expor role=combobox/listbox para leitor de tela."""
    with (
        patch("app.routes.chamados.get_static_cached", return_value=[]),
        patch("app.routes.chamados.obter_total_por_contagem", return_value=0),
        patch("app.routes.chamados._build_gate_subetapas", return_value={}),
    ):
        r = client_logado_solicitante.get("/")
    html = r.data.decode("utf-8")
    assert r.status_code == 200
    assert 'role="combobox"' in html
    assert 'role="listbox"' in html


def test_cabecalhos_ordenaveis_sao_acessiveis_por_teclado(client_logado_solicitante):
    """th.sortable precisa de tabindex e aria-sort para ser operável só com teclado."""
    chamado_fake = SimpleNamespace(
        grupo_key="x|",
        categoria="TI",
        rl_codigo=None,
        id="ch1",
        numero_chamado="001",
        descricao="Teste",
        tipo_solicitacao="Corretiva",
        responsavel="Resp",
        status="Aberto",
        prioridade="normal",
        em_copia=False,
        data_abertura_formatada=lambda: "01/01/2026",
    )
    with (
        patch("app.routes.chamados.listar_meus_chamados") as mock_listar,
        patch("app.routes.chamados.listar_chamados_como_observador", return_value=[]),
    ):
        mock_listar.return_value = {
            "chamados": [chamado_fake],
            "pagina_atual": 1,
            "total_paginas": 1,
            "total_chamados": 1,
            "status_counts": {"Aberto": 1, "Em Atendimento": 0, "Concluído": 0, "Cancelado": 0},
            "cursor_next": None,
            "cursor_prev": None,
        }
        r = client_logado_solicitante.get("/meus-chamados")
    html = r.data.decode("utf-8")
    assert r.status_code == 200
    trecho = html.split('class="sortable"')[1][:200]
    assert 'tabindex="0"' in trecho
    assert "aria-sort=" in trecho


def test_toasts_flash_tem_aria_live():
    """Container de toasts (#flash-messages) precisa anunciar mudanças a leitores de tela."""
    html = (BASE_DIR / "app/templates/base.html").read_text(encoding="utf-8")
    trecho = html.split('id="flash-messages"')[1][:200]
    assert 'aria-live="polite"' in trecho or 'role="status"' in trecho
