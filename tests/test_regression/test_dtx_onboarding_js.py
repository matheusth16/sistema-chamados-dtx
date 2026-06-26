"""
Testes de regressão — F-48 e F-60: onboarding.js

F-48: nenhum handler inline onmouseover/onmouseout no JS (incompatível com CSP strict-dynamic).
F-60: TOURS deve ter exatamente 5/6/7 passos por perfil (solicitante/supervisor/admin) em todos os idiomas.
"""

import re
from pathlib import Path

ONBOARDING_JS = Path(__file__).parent.parent.parent / "app" / "static" / "js" / "onboarding.js"


def _js_source() -> str:
    return ONBOARDING_JS.read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# F-48 — sem handlers inline (CSP)
# ─────────────────────────────────────────────────────────────────────────────


def test_onboarding_js_sem_onmouseover():
    """Nenhum onmouseover= deve existir em onboarding.js (bloqueado por CSP)."""
    src = _js_source()
    assert "onmouseover=" not in src, (
        "onboarding.js contém onmouseover= — remova e use event listeners"
    )


def test_onboarding_js_sem_onmouseout():
    """Nenhum onmouseout= deve existir em onboarding.js (bloqueado por CSP)."""
    src = _js_source()
    assert "onmouseout=" not in src, (
        "onboarding.js contém onmouseout= — remova e use event listeners"
    )


def test_onboarding_js_sem_onclick_inline():
    """Nenhum onclick= deve existir em strings HTML geradas (bloqueado por CSP)."""
    src = _js_source()
    # Permitido: não há onclick inline em strings template
    assert 'onclick="' not in src, "onboarding.js contém onclick= inline — use addEventListener"


# ─────────────────────────────────────────────────────────────────────────────
# F-60 — invariantes de tamanho dos tours (5 / 6 / 7 passos)
# ─────────────────────────────────────────────────────────────────────────────


def _count_steps_for_profile(src: str, profile: str, lang: str) -> int:
    """
    Conta os passos do tour para um perfil/idioma no TOURS object do JS.

    Estratégia: localiza o bloco TOURS[profile][lang] e conta os objetos
    iniciados por '{' alinhados imediatamente dentro do array de steps.
    Usa uma heurística por contagem de 'titulo:' dentro do bloco.
    """
    tours_match = re.search(r"(?:const|var|let)\s+TOURS\s*=\s*(\{)", src)
    if not tours_match:
        return -1

    # Conta 'titulo:' dentro do bloco do profile/lang
    # Heurística: buscar sequência profile → lang → array de steps
    profile_pattern = re.compile(rf"{re.escape(profile)}\s*:\s*\{{", re.DOTALL)
    pm = profile_pattern.search(src, tours_match.start())
    if not pm:
        return -1

    lang_pattern = re.compile(rf"{re.escape(lang)}\s*:\s*\[", re.DOTALL)
    lm = lang_pattern.search(src, pm.start())
    if not lm:
        return -1

    # Extrai conteúdo do array de steps (até o ']' correspondente)
    depth = 0
    start = lm.end()
    for j in range(lm.end(), len(src)):
        ch = src[j]
        if ch == "[":
            depth += 1
        elif ch == "]":
            if depth == 0:
                end = j
                break
            depth -= 1
    else:
        return -1

    block = src[start:end]
    # Cada step tem exatamente um campo 'titulo:'
    return len(re.findall(r"\btitulo\s*:", block))


def test_tour_solicitante_tem_5_passos_pt():
    src = _js_source()
    assert _count_steps_for_profile(src, "solicitante", "pt_BR") == 5


def test_tour_solicitante_tem_5_passos_en():
    src = _js_source()
    assert _count_steps_for_profile(src, "solicitante", "en") == 5


def test_tour_solicitante_tem_5_passos_es():
    src = _js_source()
    assert _count_steps_for_profile(src, "solicitante", "es") == 5


def test_tour_supervisor_tem_6_passos_pt():
    src = _js_source()
    assert _count_steps_for_profile(src, "supervisor", "pt_BR") == 6


def test_tour_supervisor_tem_6_passos_en():
    src = _js_source()
    assert _count_steps_for_profile(src, "supervisor", "en") == 6


def test_tour_supervisor_tem_6_passos_es():
    src = _js_source()
    assert _count_steps_for_profile(src, "supervisor", "es") == 6


def test_tour_admin_tem_7_passos_pt():
    src = _js_source()
    assert _count_steps_for_profile(src, "admin", "pt_BR") == 7


def test_tour_admin_tem_7_passos_en():
    src = _js_source()
    assert _count_steps_for_profile(src, "admin", "en") == 7


def test_tour_admin_tem_7_passos_es():
    src = _js_source()
    assert _count_steps_for_profile(src, "admin", "es") == 7
