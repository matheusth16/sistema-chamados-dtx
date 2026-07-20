"""Fixtures locais para tests/test_routes/.

Patches autouse — prevenção de chamadas reais ao Firestore em testes de rota:
- api.setor_para_area → passthrough (retorna o próprio setor_nome)
"""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _patch_setor_para_area_routes():
    """Evita chamadas ao Firestore via setor_para_area nas rotas."""
    with patch(
        "app.routes.api_chamados.setor_para_area",
        side_effect=lambda setor_nome: setor_nome or "",
    ):
        yield
