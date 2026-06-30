"""Fixtures locais para tests/test_services/.

Patches autouse — prevenção de chamadas reais ao Firestore em testes unitários:
- chamados_criacao_service.setor_para_area → identidade (retorna o próprio setor_nome)
- assignment.setor_para_area → identidade
- status_service.Usuario → Mock com get_by_id lançando Exception (graceful skip)

Atenção: o patch de Usuario.get_supervisores_por_area é feito no nível do módulo
test_chamados_criacao_service.py (não aqui) para evitar interferir em
test_models_usuario.py, que testa o próprio método.
"""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _patch_firestore_defaults():
    """Evita chamadas ao Firestore em testes unitários de serviço."""
    _passthrough = lambda setor_nome: setor_nome or ""  # noqa: E731
    with (
        patch(
            "app.services.chamados_criacao_service.setor_para_area",
            side_effect=_passthrough,
        ),
        patch(
            "app.services.assignment.setor_para_area",
            side_effect=_passthrough,
        ),
        patch("app.services.status_service.Usuario") as _mock_ss_usuario,
    ):
        # get_by_id lança Exception — status_service captura e ignora graciosamente
        _mock_ss_usuario.get_by_id.side_effect = Exception("no Firestore in unit tests")
        yield
