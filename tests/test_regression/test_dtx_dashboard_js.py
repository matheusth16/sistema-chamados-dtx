"""
Testes de regressão — F-41: dedup de CSS injetado em dashboard_otimizacoes.js

Garante que o bloco @keyframes fadeIn nunca seja appendado múltiplas vezes
ao DOM pela injeção dinâmica de <style>.
"""

from pathlib import Path

DASHBOARD_JS = (
    Path(__file__).parent.parent.parent / "app" / "static" / "js" / "dashboard_otimizacoes.js"
)


def _js_source() -> str:
    return DASHBOARD_JS.read_text(encoding="utf-8")


def test_fade_keyframes_usa_guard_getelementbyid():
    """O bloco de injeção de @keyframes fadeIn deve checar getElementById antes de appendar."""
    src = _js_source()
    assert "getElementById('dtx-dashboard-fade-keyframes')" in src, (
        "dashboard_otimizacoes.js não tem guard getElementById para o bloco fadeIn — "
        "o <style> seria appendado múltiplas vezes"
    )


def test_fade_style_tem_id_dtx_dashboard():
    """O <style> injetado deve receber id='dtx-dashboard-fade-keyframes' para o guard funcionar."""
    src = _js_source()
    assert "'dtx-dashboard-fade-keyframes'" in src, (
        "dashboard_otimizacoes.js não atribui style.id = 'dtx-dashboard-fade-keyframes'"
    )


def test_fade_keyframes_nao_appenda_incondicionalmente():
    """document.head.appendChild(style) não deve aparecer fora de um bloco condicional.

    Usa janela de 15 linhas para acomodar template literals multi-linha.
    """
    src = _js_source()
    lines = src.splitlines()
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if "document.head.appendChild(style)" in stripped:
            # 15 linhas de contexto para acomodar o template literal @keyframes
            context = "\n".join(lines[max(0, i - 15) : i])
            assert "getElementById" in context, (
                f"Linha {i}: document.head.appendChild(style) sem guard getElementById nas "
                f"15 linhas anteriores — possível injeção duplicada"
            )
