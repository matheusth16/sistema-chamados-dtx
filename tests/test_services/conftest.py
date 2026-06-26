"""Fixtures locais para tests/test_services/.

Patches autouse — prevenção de chamadas reais ao Firestore em testes unitários:
- chamados_criacao_service.setor_para_area → identidade (retorna o próprio setor_nome)

Atenção: o patch de Usuario.get_supervisores_por_area é feito no nível do módulo
test_chamados_criacao_service.py (não aqui) para evitar interferir em
test_models_usuario.py, que testa o próprio método.
"""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _patch_setor_para_area_default():
    """Evita chamadas ao Firestore via setor_para_area nos testes de serviço."""
    with patch(
        "app.services.chamados_criacao_service.setor_para_area",
        side_effect=lambda setor_nome: setor_nome or "",
    ):
        yield
