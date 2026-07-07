"""
Invariantes visuais do design system DTX Light Enterprise.

Garante que alterações futuras não violem:
  A1 – Somente tokens light (sem dark:, sem #0b1b3d, sem backdrop-blur, sem shadow-xl)
  A2 – Zero emoji Unicode em templates, JS e translations.json
  A3 – CSS carregado no <head> via base.html; dashboard.html não repete o <link>
  A4 – Componentes dashboard e usuarios usam o macro status_badge
"""

import glob as _glob
import os
import re

import pytest

pytestmark = pytest.mark.regression

# ---------------------------------------------------------------------------
# Paths independentes de cwd (resolve a partir deste arquivo)
# ---------------------------------------------------------------------------
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_TEMPLATES = os.path.join(_ROOT, "app", "templates")
_STATIC_CSS = os.path.join(_ROOT, "app", "static", "css")
_STATIC_JS = os.path.join(_ROOT, "app", "static", "js")
_TRANSLATIONS = os.path.join(_ROOT, "app", "translations.json")


def _all_html() -> list[str]:
    return _glob.glob(os.path.join(_TEMPLATES, "**", "*.html"), recursive=True)


def _all_css() -> list[str]:
    return _glob.glob(os.path.join(_STATIC_CSS, "*.css"))


def _all_js() -> list[str]:
    return _glob.glob(os.path.join(_STATIC_JS, "*.js"))


def _rel(path: str) -> str:
    return os.path.relpath(path, _ROOT)


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# ===========================================================================
# A1 – Light-only tokens
# ===========================================================================


def test_no_tailwind_dark_prefix_in_templates():
    """Nenhum template deve usar o prefixo dark: do Tailwind (design light-only)."""
    violations: list[str] = []
    for path in _all_html():
        with open(path, encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                # Ignora ocorrências dentro de comentários Jinja {# ... #}
                stripped = re.sub(r"\{#.*?#\}", "", line)
                if "dark:" in stripped:
                    violations.append(f"{_rel(path)}:{i}")
    assert violations == [], f"Prefixo Tailwind dark: encontrado em templates: {violations[:10]}"


def test_no_dark_navy_hex_in_css():
    """Nenhum CSS deve conter #0b1b3d (hex exclusivo do modo escuro)."""
    violations: list[str] = []
    for path in _all_css():
        with open(path, encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                if "#0b1b3d" in line.lower():
                    violations.append(f"{_rel(path)}:{i}")
    assert violations == [], f"Hex modo escuro em CSS: {violations}"


def test_no_backdrop_blur_in_templates():
    """Templates não devem conter backdrop-blur (viola constraints de perf do design system)."""
    violations: list[str] = []
    for path in _all_html():
        with open(path, encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                stripped = re.sub(r"\{#.*?#\}", "", line)
                if "backdrop-blur" in stripped:
                    violations.append(f"{_rel(path)}:{i}")
    assert violations == [], f"backdrop-blur em templates: {violations}"


def test_no_shadow_xl_in_templates():
    """Templates não devem conter shadow-xl (usar tokens shadow-dtx* do design system)."""
    violations: list[str] = []
    for path in _all_html():
        with open(path, encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                stripped = re.sub(r"\{#.*?#\}", "", line)
                if re.search(r"\bshadow-xl\b", stripped):
                    violations.append(f"{_rel(path)}:{i}")
    assert violations == [], f"shadow-xl em templates: {violations}"


# ===========================================================================
# A2 – Zero emoji
# ===========================================================================

# Ranges de emoji reais usados em UI.
# Exclui deliberadamente:
#   - Box Drawings (U+2500-U+257F) — usados como separadores em comentários JS
#   - Geometric Shapes (U+25A0-U+25FF) — usados em regex de filtros (●○)
# Inclui:
#   - Todos os emoji modernos do Supplementary Multilingual Plane (U+1F300+)
#   - Misc Symbols + Dingbats (U+2600-U+27BF) — ☀⚠✓✔✖ etc. (começa APÓS geom. shapes)
#   - Misc Symbols and Arrows (U+2B00-U+2BFF) — inclui ⭐ (U+2B50)
#   - ℹ (U+2139) do bloco Letterlike Symbols
_EMOJI_RE = re.compile(
    "["
    "\U0001f300-\U0001f9ff"  # Emoticons, pictogramas, transporte
    "\U0001fa00-\U0001faff"  # Chess symbols, novos emoji
    "\U0001f1e0-\U0001f1ff"  # Regional indicators (bandeiras)
    # Misc Symbols (U+2600-U+26FF) + Dingbats (U+2700-U+27BF)
    # Começa em U+2600, APÓS Geometric Shapes (U+25A0-U+25FF) e Box Drawings (U+2500-U+257F)
    # Abrange ☀ ⚠ ⚡ ✓ ✔ ✖ ➡ e outros símbolos usados incorretamente como ícones
    "☀-➿"
    # Misc Symbols and Arrows (U+2B00-U+2BFF) — inclui ⭐ (U+2B50) e ⭕ (U+2B55)
    "⬀-⯿"
    # ℹ (U+2139) do bloco Letterlike Symbols — fora dos ranges acima
    "ℹ"
    "]",
    re.UNICODE,
)


def _emoji_violations(path: str) -> list[str]:
    violations: list[str] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                if _EMOJI_RE.search(line):
                    violations.append(f"{_rel(path)}:{i}: {line.strip()[:80]}")
    except (OSError, UnicodeDecodeError):
        pass
    return violations


def test_no_emoji_in_templates():
    """Nenhum template deve conter emoji Unicode (substituir por SVG inline)."""
    violations = [v for path in _all_html() for v in _emoji_violations(path)]
    assert violations == [], "Emoji encontrado em templates:\n" + "\n".join(violations[:20])


def test_no_emoji_in_js_files():
    """Nenhum arquivo JS em static/js deve conter emoji Unicode."""
    violations = [v for path in _all_js() for v in _emoji_violations(path)]
    assert violations == [], "Emoji encontrado em JS:\n" + "\n".join(violations[:20])


def test_no_emoji_in_translations():
    """translations.json não deve conter emoji Unicode nos valores de tradução."""
    violations = _emoji_violations(_TRANSLATIONS)
    assert violations == [], "Emoji em translations.json:\n" + "\n".join(violations[:20])


# ===========================================================================
# A3 – CSS no <head> via base.html; templates filhos sem <link> redundante
# ===========================================================================


def _head_section(html: str) -> str:
    """Retorna o conteúdo do bloco <head>...</head> de um template."""
    match = re.search(r"<head\b[^>]*>(.*?)</head>", html, re.DOTALL | re.IGNORECASE)
    return match.group(1) if match else ""


def test_base_html_loads_dashboard_css_in_head():
    """base.html deve carregar dashboard.css no <head> (não em block content)."""
    head = _head_section(_read(os.path.join(_TEMPLATES, "base.html")))
    assert "dashboard.css" in head, "dashboard.css ausente no <head> de base.html"


def test_base_html_loads_relatorios_css_in_head():
    """base.html deve carregar relatorios.css no <head>."""
    head = _head_section(_read(os.path.join(_TEMPLATES, "base.html")))
    assert "relatorios.css" in head, "relatorios.css ausente no <head> de base.html"


def test_dashboard_html_has_no_redundant_css_link():
    """dashboard.html não deve ter <link> para dashboard.css (já carregado via base.html)."""
    content = _read(os.path.join(_TEMPLATES, "dashboard.html"))
    links = re.findall(r"<link[^>]+dashboard\.css[^>]*>", content, re.IGNORECASE)
    assert links == [], f"dashboard.html tem <link> redundante para dashboard.css: {links}"


def test_relatorios_html_has_no_redundant_css_link():
    """relatorios.html não deve ter <link> para relatorios.css (já carregado via base.html)."""
    path = os.path.join(_TEMPLATES, "relatorios.html")
    if not os.path.isfile(path):
        pytest.skip("relatorios.html não encontrado")
    content = _read(path)
    links = re.findall(r"<link[^>]+relatorios\.css[^>]*>", content, re.IGNORECASE)
    assert links == [], f"relatorios.html tem <link> redundante para relatorios.css: {links}"


# ===========================================================================
# A4 – Macro status_badge usada nos componentes corretos
# ===========================================================================


def test_ticket_row_dashboard_imports_status_badge():
    """_ticket_row_dashboard.html deve importar o macro status_badge via {% from ... %}."""
    path = os.path.join(_TEMPLATES, "components", "_ticket_row_dashboard.html")
    content = _read(path)
    assert "import status_badge" in content, "_ticket_row_dashboard.html não importa status_badge"


def test_ticket_row_dashboard_calls_status_badge():
    """_ticket_row_dashboard.html deve chamar {{ status_badge(...) }} no lugar de <span> inline."""
    path = os.path.join(_TEMPLATES, "components", "_ticket_row_dashboard.html")
    content = _read(path)
    assert "status_badge(" in content, "_ticket_row_dashboard.html não chama status_badge()"


def test_ticket_row_dashboard_calls_sla_badge():
    """_ticket_row_dashboard.html deve chamar {{ sla_badge(...) }} para exibir SLA."""
    path = os.path.join(_TEMPLATES, "components", "_ticket_row_dashboard.html")
    content = _read(path)
    assert "sla_badge(" in content, "_ticket_row_dashboard.html não chama sla_badge()"


def test_usuarios_html_imports_status_badge():
    """usuarios.html deve importar o macro status_badge."""
    path = os.path.join(_TEMPLATES, "usuarios.html")
    content = _read(path)
    assert "import status_badge" in content, "usuarios.html não importa status_badge"


def test_usuarios_html_calls_status_badge_with_perfil():
    """usuarios.html deve usar status_badge(usuario.perfil) em vez de if/elif manual."""
    path = os.path.join(_TEMPLATES, "usuarios.html")
    content = _read(path)
    assert "status_badge(usuario.perfil)" in content, (
        "usuarios.html não usa status_badge(usuario.perfil)"
    )


# ===========================================================================
# A5 – F-68: Tokens de borda CSS — paridade input.css ↔ tailwind.config.js
# ===========================================================================


def _extract_css_var(css: str, var_name: str) -> str | None:
    """Extrai o valor de uma custom property CSS do :root, ex: '--color-surface-border: #EAEAEA'."""
    import re

    m = re.search(rf"{re.escape(var_name)}\s*:\s*([^;]+);", css)
    return m.group(1).strip().upper() if m else None


def _extract_tailwind_color(js: str, key_path: str) -> str | None:
    """Extrai valor de cor do tailwind.config.js por caminho simples (ex: 'surface.border')."""
    import re

    parts = key_path.split(".")
    pattern = parts[-1] + r"\s*:\s*['\"]([^'\"]+)['\"]"
    m = re.search(pattern, js)
    return m.group(1).strip().upper() if m else None


def test_surface_border_token_paridade_input_css_tailwind():
    """input.css deve definir --color-surface-border; tailwind.config.js deve referenciar var(--color-surface-border).

    Arquitetura de fonte única de verdade: o valor vive em input.css, tailwind apenas
    referencia a custom property — nunca hardcoda o hex diretamente.
    """
    css_path = os.path.join(_STATIC_CSS, "input.css")
    tw_path = os.path.join(_ROOT, "tailwind.config.js")

    if not os.path.isfile(css_path):
        pytest.skip("input.css não encontrado")
    if not os.path.isfile(tw_path):
        pytest.skip("tailwind.config.js não encontrado")

    css_val = _extract_css_var(_read(css_path), "--color-surface-border")
    tw_val = _extract_tailwind_color(_read(tw_path), "surface.border")

    assert css_val is not None, "--color-surface-border não definido em input.css"
    assert tw_val is not None, "surface.border não encontrado em tailwind.config.js"
    assert tw_val == "VAR(--COLOR-SURFACE-BORDER)", (
        f"tailwind.config.js deve referenciar var(--color-surface-border), obtido: {tw_val} — "
        "mantenha fonte única de verdade em input.css"
    )


def test_no_e5e7eb_in_layout_css():
    """#E5E7EB/#e5e7eb não deve aparecer em CSS de layout (usar var(--color-surface-border) = #EAEAEA).

    #E5E7EB é Tailwind gray-200 e não é um token do design system DTX.
    Bordas de containers devem usar var(--color-surface-border) cujo valor é #EAEAEA.
    """
    violations: list[str] = []
    layout_css = ["dashboard.css", "relatorios.css", "table-filters.css"]
    for filename in layout_css:
        path = os.path.join(_STATIC_CSS, filename)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                if re.search(r"#[Ee]5[Ee]7[Ee][Bb]", line):
                    violations.append(f"{filename}:{i}: {line.strip()[:80]}")
    assert violations == [], (
        "Hex hardcoded #E5E7EB encontrado em CSS de layout — "
        "substituir por var(--color-surface-border):\n" + "\n".join(violations)
    )


def test_no_legacy_rgba_comma_syntax_in_layout_css():
    """rgba(r, g, b, a) com vírgula (sintaxe CSS nível 3, depreciada) não deve
    aparecer em CSS de layout — usar color-mix() ou rgb() nível 4 (F-66)."""
    violations: list[str] = []
    layout_css = ["dashboard.css", "relatorios.css", "table-filters.css"]
    for filename in layout_css:
        path = os.path.join(_STATIC_CSS, filename)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                if re.search(r"rgba\(", line):
                    violations.append(f"{filename}:{i}: {line.strip()[:80]}")
    assert violations == [], (
        "rgba() legado (vírgula) encontrado em CSS de layout — "
        "substituir por color-mix():\n" + "\n".join(violations)
    )
