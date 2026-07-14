"""
Regressão CSP — F-XX: nenhum handler de evento inline em templates.

CSP de produção usa script-src com nonce (sem 'unsafe-inline'). Nonce cobre
apenas tags <script>, não atributos onclick/onchange/onsubmit/etc — esses
continuam bloqueados pelo browser independente do nonce presente no
documento. Handlers devem ser ligados via addEventListener em bloco
<script nonce="{{ csp_nonce }}">.
"""

import glob as _glob
import os
import re

import pytest

pytestmark = pytest.mark.regression

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_TEMPLATES = os.path.join(_ROOT, "app", "templates")

_INLINE_HANDLER_RE = re.compile(
    r"\bon(click|change|submit|load|keydown|keyup|input|focus|blur|mouseover|mouseout)\s*=",
    re.IGNORECASE,
)


def _all_html() -> list[str]:
    return _glob.glob(os.path.join(_TEMPLATES, "**", "*.html"), recursive=True)


def _rel(path: str) -> str:
    return os.path.relpath(path, _ROOT)


def test_no_inline_event_handlers_in_templates():
    """Nenhum template deve usar onclick=/onchange=/onsubmit=/etc — bloqueado pela CSP em produção."""
    violations: list[str] = []
    for path in _all_html():
        with open(path, encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                stripped = re.sub(r"\{#.*?#\}", "", line)
                if _INLINE_HANDLER_RE.search(stripped):
                    violations.append(f"{_rel(path)}:{i}: {line.strip()[:100]}")
    assert violations == [], (
        "Handler de evento inline encontrado (bloqueado pela CSP script-src em produção, "
        "nonce não cobre atributos on*): usar addEventListener.\n" + "\n".join(violations[:30])
    )
