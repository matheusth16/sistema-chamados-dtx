"""Testes das funções utilitárias (utils)."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.utils import (
    extrair_numero_chamado,
    formatar_data_para_excel,
    gerar_numero_chamado,
)


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        (None, "-"),
        ("10/02/2026", "10/02/2026"),
        (datetime(2026, 2, 10, 14, 30), "10/02/2026 14:30"),
    ],
    ids=["none", "string", "datetime"],
)
def test_formatar_data_para_excel(entrada, esperado):
    assert formatar_data_para_excel(entrada) == esperado


@pytest.mark.parametrize(
    "numero,esperado",
    [
        ("CHM-0001", 1),
        ("CHM-0045", 45),
        (None, float("inf")),
        ("", float("inf")),
        ("CHM-abc", float("inf")),
    ],
    ids=["um_digito", "dois_digitos", "none", "vazio", "invalido"],
)
def test_extrair_numero_chamado(numero, esperado):
    assert extrair_numero_chamado(numero) == esperado


def test_gerar_numero_chamado_formato(app):
    """gerar_numero_chamado retorna string no formato CHM-XXXX (transação mockada)."""

    class DocContador:
        exists = True

        def get(self, k):
            return 1 if k == "proximo_numero" else None

    with patch("app.utils.db") as mock_db:
        mock_transaction = MagicMock()
        mock_transaction.get.return_value = DocContador()
        mock_db.transaction.return_value = mock_transaction
        mock_db.collection.return_value.document.return_value = MagicMock()

        with app.app_context():
            result = gerar_numero_chamado()

    assert result.startswith("CHM-")
    assert len(result) == 8
    assert result[4:].isdigit()
    assert result == "CHM-0002"
