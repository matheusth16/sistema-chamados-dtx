"""Regressões do lote WCAG 2.2 AA + i18n de 2026-08-13."""

import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
TEMPLATES = BASE_DIR / "app" / "templates"


def _ler(relativo: str) -> str:
    return (BASE_DIR / relativo).read_text(encoding="utf-8")


def _tag_por_id(html: str, elemento_id: str) -> str:
    match = re.search(rf"<[^>]+\bid=[\"']{re.escape(elemento_id)}[\"'][^>]*>", html)
    assert match, f"Elemento #{elemento_id} não encontrado"
    return match.group(0)


def test_campos_apontados_tem_rotulos_programaticos_e_erros_associados():
    visualizar = _ler("app/templates/visualizar_chamado.html")
    formulario = _ler("app/templates/formulario.html")
    campos = {
        visualizar: (
            "sup-resposta-texto",
            "sol-resposta-texto",
            "sol-anexo-motivo",
            "sol-nova-descricao",
            "previsao-motivo-rejeicao",
            "motivo-reabrir",
            "motivo-reabrir-admin",
            "motivo-cancelar-admin",
            "sol-motivo-cancelar",
        ),
        formulario: ("obs-busca", "input_link_externo"),
    }
    for html, ids in campos.items():
        for elemento_id in ids:
            assert f'for="{elemento_id}"' in html, f"Falta label para #{elemento_id}"

    assert "<fieldset" in formulario and "<legend" in formulario
    assert 'for="modal-descricao"' not in visualizar.split("{% if pode_editar_descricao %}")[0]
    for elemento_id in (
        "sup-resposta-texto",
        "sol-resposta-texto",
        "sol-anexo-motivo",
        "sol-nova-descricao",
        "previsao-motivo-rejeicao",
        "motivo-reabrir-admin",
        "motivo-cancelar-admin",
        "sol-motivo-cancelar",
    ):
        assert "aria-describedby=" in _tag_por_id(visualizar, elemento_id)


def test_fechamentos_de_modal_tem_nome_traduzido_e_svg_decorativo():
    html = _ler("app/templates/visualizar_chamado.html")
    botoes = re.findall(
        r'<button[^>]*class="[^"]*\bbento-modal-close\b[^"]*"[^>]*>.*?</button>',
        html,
        flags=re.DOTALL,
    )
    assert len(botoes) >= 7
    for botao in botoes:
        assert "aria-label=" in botao
        assert "close_modal" in botao
        assert 'aria-hidden="true"' in botao


def test_alvos_criticos_tem_44px_e_foco_visivel():
    css = _ler("app/static/css/bento.css")
    for seletor in (".bento-info-btn", ".bento-modal-close", ".bento-toast-close"):
        regra = re.search(rf"{re.escape(seletor)}\s*\{{([^}}]+)\}}", css)
        assert regra, f"Regra ausente: {seletor}"
        declaracoes = regra.group(1)
        assert ("min-width:44px" in declaracoes or "width:44px" in declaracoes) and (
            "min-height:44px" in declaracoes or "height:44px" in declaracoes
        )
        assert f"{seletor}:focus-visible" in css

    for seletor in (
        ".bento-btn-primary:focus-visible",
        ".bento-btn-outline:focus-visible",
        ".bento-btn-block:focus-visible",
        ".bento-escalation-btn:focus-visible",
        ".bento-row-btn:focus-visible",
    ):
        assert seletor in css


def test_cards_de_informacao_usam_disclosure_completo():
    html = _ler("app/templates/visualizar_chamado.html")
    pares = (
        ("info-transferir-area", "info_transfer_area_aria"),
        ("info-transferir-colega", "info_transfer_colleague_aria"),
        ("info-incluir-participantes", "info_include_participants_aria"),
    )
    for painel_id, chave_label in pares:
        botao = re.search(
            rf'<button[^>]*aria-controls="{painel_id}"[^>]*>.*?</button>',
            html,
            flags=re.DOTALL,
        )
        assert botao, f"Disclosure sem aria-controls para {painel_id}"
        assert 'aria-expanded="false"' in botao.group(0)
        assert chave_label in botao.group(0)
        painel = _tag_por_id(html, painel_id)
        assert 'role="region"' in painel
        assert "aria-labelledby=" in painel
    assert "setAttribute('aria-expanded'" in html
    assert "event.key === 'Escape'" in html or "e.key === 'Escape'" in html


def test_modais_custom_isolam_fundo_e_fazem_cleanup():
    html = _ler("app/templates/visualizar_chamado.html")
    assert "main-content" in html
    assert "setAttribute('inert'" in html or ".inert = true" in html
    assert "setAttribute('aria-hidden', 'true')" in html
    assert "removeAttribute('inert')" in html or ".inert = false" in html
    assert "removeAttribute('aria-hidden')" in html
    assert "removeEventListener('keydown', _trapFocusHandler)" in html
    assert "_ultimoElementoFocado.focus()" in html


def test_erros_dinamicos_sao_alertas_e_atualizam_estado_dos_campos():
    html = _ler("app/templates/visualizar_chamado.html")
    erros = re.findall(r'<div[^>]*id="[^"]*-erro"[^>]*>', html)
    assert erros
    assert all('role="alert"' in erro for erro in erros)
    assert "aria-invalid" in html
    assert "setAttribute('aria-invalid', 'true')" in html
    assert "removeAttribute('aria-invalid')" in html


def test_historico_tem_headings_lista_time_e_icones_decorativos():
    html = _ler("app/templates/historico.html")
    assert '<h2 id="timeline-title"' in html
    assert re.search(r'<ol class="[^"]*\bbento-timeline\b', html)
    assert "<li" in html and "</li>" in html
    assert re.search(r"<time\b[^>]*\bdatetime=\"", html)
    svgs = re.findall(r"<svg\b[^>]*>", html)
    assert svgs and all('aria-hidden="true"' in svg for svg in svgs)
    assert "<h4" not in html


def test_toast_webpush_e_navbar_expoem_semantica_e_escape():
    base = _ler("app/templates/base.html")
    navbar = _ler("app/templates/components/navbar.html")
    trecho_toast = base.split("function mostrarToastSucesso()", 1)[1][:700]
    assert 'toast.setAttribute("role", "status")' in trecho_toast
    assert 'toast.setAttribute("aria-live", "polite")' in trecho_toast

    assert 'aria-controls="nav-menu-dropdown"' in navbar
    assert 'aria-controls="sino-dropdown"' in navbar
    assert "aria-label=\"{{ t('profile_menu_aria') }}\"" in navbar
    assert 'role="region"' in _tag_por_id(navbar, "sino-dropdown")
    assert "btn.focus()" in base


def test_thread_de_conversa_e_mensagens_sao_semanticas():
    html = _ler("app/templates/visualizar_chamado.html")
    assert 'role="log"' in html
    assert "conversation-title" in html
    assert "<ol" in html and "<li" in html
    assert "<article" in html
    assert '<time datetime="' in html


def test_chaves_novas_wcag_estao_completas_nos_tres_idiomas():
    traducoes = json.loads(_ler("app/translations.json"))
    chaves = (
        "close_modal",
        "profile_menu_aria",
        "external_link_label",
        "observer_search_label",
        "info_transfer_area_aria",
        "info_transfer_colleague_aria",
        "info_include_participants_aria",
        "conversation_log_aria",
        "message_sent_at",
    )
    for chave in chaves:
        assert chave in traducoes, f"Chave ausente: {chave}"
        assert set(traducoes[chave]) >= {"pt_BR", "en", "es"}
        assert all(traducoes[chave][idioma].strip() for idioma in ("pt_BR", "en", "es"))
