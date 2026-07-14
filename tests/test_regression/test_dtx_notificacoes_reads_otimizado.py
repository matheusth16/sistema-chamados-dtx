"""
Testes de regressão — otimização de leituras Firestore no sino de notificações.

carregarNotificacoes() busca até 30 documentos (lista completa); atualizarSóBadge()
faz apenas uma leitura agregada de contagem. Como base.html é o layout compartilhado
por todo o site, chamar a versão cara no carregamento inicial de página multiplica
o custo de leitura por navegação — o contador deve carregar com a versão barata,
e a lista completa só deve ser buscada sob demanda (clique no sino).
"""

from pathlib import Path

BASE_HTML = Path(__file__).parent.parent.parent / "app" / "templates" / "base.html"


def _base_html_source() -> str:
    return BASE_HTML.read_text(encoding="utf-8")


def test_carregamento_inicial_de_pagina_usa_badge_barato_nao_lista_completa():
    """A chamada inicial (fora de listeners de clique) deve ser atualizarSóBadge(),
    não carregarNotificacoes() — evita até 30 leituras Firestore em toda navegação."""
    src = _base_html_source()
    idx_poll = src.index("var _POLL_MS")
    trecho_antes = src[:idx_poll]
    # A última chamada de carregamento antes de configurar o poll deve ser a barata
    ultima_carregar = trecho_antes.rfind("carregarNotificacoes();")
    ultima_badge = trecho_antes.rfind("atualizarSóBadge();")
    assert ultima_badge != -1, "atualizarSóBadge() não é chamada no carregamento inicial"
    assert ultima_badge > ultima_carregar, (
        "carregarNotificacoes() (busca até 30 docs) ainda é chamada no carregamento "
        "inicial da página — deveria ser atualizarSóBadge() (1 leitura agregada)"
    )


def test_clique_no_sino_ainda_busca_lista_completa():
    """Abrir o dropdown do sino deve continuar chamando carregarNotificacoes() —
    a lista completa só é cara quando efetivamente exibida."""
    src = _base_html_source()
    assert "carregarNotificacoes();\n            abrirDropdown();" in src, (
        "Clique no sino não está mais chamando carregarNotificacoes() ao abrir o dropdown"
    )
