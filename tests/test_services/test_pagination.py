"""Testes do serviço de paginação (cursor-based e agregação count)."""
import pytest
from unittest.mock import MagicMock

from app.services.pagination import (
    PaginadorFirestore,
    obter_total_por_contagem,
)


def test_obter_total_por_contagem_retorna_none_se_query_sem_count():
    """Se a query não tiver método count(), retorna None (evita OOM)."""
    query_ref = MagicMock(spec=[])  # sem .count
    assert obter_total_por_contagem(query_ref) is None


def test_obter_total_por_contagem_extrai_value_de_result_0_0():
    """Formato Firestore SDK: result[0][0].value."""
    cell = MagicMock()
    cell.value = 42
    row = [cell]
    result = [row]
    query_ref = MagicMock()
    query_ref.count.return_value.get.return_value = result
    assert obter_total_por_contagem(query_ref) == 42


def test_obter_total_por_contagem_extrai_value_de_result_0():
    """Fallback: result[0].value."""
    row = MagicMock()
    row.value = 100
    result = [row]
    query_ref = MagicMock()
    query_ref.count.return_value.get.return_value = result
    assert obter_total_por_contagem(query_ref) == 100


def test_obter_total_por_contagem_extrai_value_de_result_direto():
    """Fallback: result.value."""
    result = MagicMock()
    result.value = 7
    query_ref = MagicMock()
    query_ref.count.return_value.get.return_value = result
    assert obter_total_por_contagem(query_ref) == 7


def test_obter_total_por_contagem_retorna_none_em_excecao():
    """Em caso de exceção (ex.: rede), retorna None."""
    query_ref = MagicMock()
    query_ref.count.return_value.get.side_effect = Exception("timeout")
    assert obter_total_por_contagem(query_ref) is None


def test_paginar_nao_inclui_total_global():
    """paginar() não retorna total_global (evita OOM ao não depender de len(docs))."""
    p = PaginadorFirestore(limite_padrao=2)
    doc1 = MagicMock()
    doc1.id = "id1"
    doc2 = MagicMock()
    doc2.id = "id2"
    docs = [doc1, doc2]
    resultado = p.paginar(docs, pagina=1)
    assert "total_global" not in resultado
    assert resultado["total_pagina"] == 2
    assert resultado["limite"] == 2
