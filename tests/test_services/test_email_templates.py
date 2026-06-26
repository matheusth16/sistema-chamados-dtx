"""Testes para email_templates.py — helpers de HTML de e-mail."""


# ── _html ─────────────────────────────────────────────────────────────────────


def test_html_escapa_angulares():
    from app.services.email_templates import _html

    assert "&lt;" in _html("<script>")
    assert "&gt;" in _html("<script>")


def test_html_escapa_ampersand():
    from app.services.email_templates import _html

    assert "&amp;" in _html("a & b")


def test_html_none_retorna_string_vazia():
    from app.services.email_templates import _html

    assert _html(None) == ""


def test_html_converte_nao_string():
    from app.services.email_templates import _html

    assert _html(42) == "42"


# ── build_detail_table ────────────────────────────────────────────────────────


def test_build_detail_table_contem_dados():
    from app.services.email_templates import build_detail_table

    html = build_detail_table([("Chamado", "CH-001"), ("Status", "Aberto")])
    assert "CH-001" in html
    assert "Aberto" in html
    assert "<table" in html


def test_build_detail_table_sem_linhas_retorna_vazio():
    from app.services.email_templates import build_detail_table

    assert build_detail_table([]) == ""


def test_build_detail_table_escapa_conteudo_xss():
    from app.services.email_templates import build_detail_table

    html = build_detail_table([("<script>xss</script>", "<img/>")])
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_build_detail_table_chave_e_valor_na_estrutura():
    from app.services.email_templates import build_detail_table

    html = build_detail_table([("Categoria", "TI")])
    assert "<td" in html
    assert "Categoria" in html
    assert "TI" in html


# ── build_cta_button ──────────────────────────────────────────────────────────


def test_build_cta_button_contem_href():
    from app.services.email_templates import build_cta_button

    html = build_cta_button("Ver chamado", "https://example.com/ch1", "#2563eb")
    assert "https://example.com/ch1" in html


def test_build_cta_button_contem_texto():
    from app.services.email_templates import build_cta_button

    html = build_cta_button("Ver chamado", "https://example.com", "#2563eb")
    assert "Ver chamado" in html


def test_build_cta_button_escapa_href():
    from app.services.email_templates import build_cta_button

    html = build_cta_button("Clique", "<script>bad</script>", "#fff")
    assert "<script>" not in html


# ── build_email_shell ─────────────────────────────────────────────────────────


def test_build_email_shell_contem_titulo():
    from app.services.email_templates import build_email_shell

    html = build_email_shell("Chamado Aberto", "#2563eb", "<p>corpo</p>")
    assert "Chamado Aberto" in html


def test_build_email_shell_contem_corpo():
    from app.services.email_templates import build_email_shell

    html = build_email_shell("Título", "#000", "<p>Conteúdo especial</p>")
    assert "Conteúdo especial" in html


def test_build_email_shell_contem_footer_dtx():
    from app.services.email_templates import build_email_shell

    html = build_email_shell("T", "#000", "corpo")
    assert "DTX Service Portal" in html


def test_build_email_shell_escapa_titulo():
    from app.services.email_templates import build_email_shell

    html = build_email_shell("<script>bad</script>", "#000", "corpo")
    assert "<script>bad</script>" not in html


# ── build_two_ctas ────────────────────────────────────────────────────────────


def test_build_two_ctas_lista_vazia_retorna_string_vazia():
    from app.services.email_templates import build_two_ctas

    assert build_two_ctas([]) == ""


def test_build_two_ctas_um_item_retorna_botao():
    from app.services.email_templates import build_two_ctas

    html = build_two_ctas([("Ver", "https://example.com", "#2563eb")])
    assert "Ver" in html
    assert "https://example.com" in html
