"""Testes das funções utilitárias (utils)."""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

from app.utils import (
    formatar_data_para_excel,
    extrair_numero_chamado,
    gerar_numero_chamado,
)


def test_formatar_data_para_excel_none():
    assert formatar_data_para_excel(None) == '-'


def test_formatar_data_para_excel_string():
    assert formatar_data_para_excel('10/02/2026') == '10/02/2026'


def test_formatar_data_para_excel_datetime():
    dt = datetime(2026, 2, 10, 14, 30)
    assert formatar_data_para_excel(dt) == '10/02/2026 14:30'


def test_extrair_numero_chamado_valido():
    assert extrair_numero_chamado('CHM-0001') == 1
    assert extrair_numero_chamado('CHM-0045') == 45


def test_extrair_numero_chamado_vazio_ou_none():
    assert extrair_numero_chamado(None) == float('inf')
    assert extrair_numero_chamado('') == float('inf')


def test_extrair_numero_chamado_invalido_retorna_inf():
    assert extrair_numero_chamado('CHM-abc') == float('inf')


def test_gerar_numero_chamado_formato(app):
    """gerar_numero_chamado retorna string no formato CHM-XXXX (transação mockada)."""
    class DocContador:
        exists = True
        def get(self, k):
            return 1 if k == 'proximo_numero' else None
    doc_contador = DocContador()
    with patch('app.utils.db') as mock_db:
        mock_transaction = MagicMock()
        mock_transaction.get.return_value = doc_contador
        mock_db.transaction.return_value = mock_transaction
        mock_db.collection.return_value.document.return_value = MagicMock()

        with app.app_context():
            result = gerar_numero_chamado()
    assert result.startswith('CHM-')
    assert len(result) == 8
    assert result[4:].isdigit()
    assert result == 'CHM-0002'
