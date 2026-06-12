"""Testes do serviço de paginação (cursor-based e agregação count)."""

from unittest.mock import MagicMock

from app.services.pagination import (
    OptimizadorQuery,
    PaginadorFirestore,
    obter_total_por_contagem,
)


def _make_doc(doc_id):
    d = MagicMock()
    d.id = doc_id
    return d


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


def test_paginar_lista_vazia_retorna_pagina_vazia():
    """paginar([]) retorna estrutura vazia via _pagina_vazia()."""
    p = PaginadorFirestore(limite_padrao=10)
    resultado = p.paginar([])
    assert resultado["docs"] == []
    assert resultado["tem_anterior"] is False
    assert resultado["tem_proximo"] is False
    assert resultado["total_pagina"] == 0
    assert "cursor_atual" in resultado


def test_paginar_com_cursor_anterior_avanca_indice():
    """paginar() com cursor_anterior começa após o documento referenciado."""
    docs = [_make_doc("a"), _make_doc("b"), _make_doc("c"), _make_doc("d")]
    p = PaginadorFirestore(limite_padrao=2)
    resultado = p.paginar(docs, cursor_anterior="b")
    assert resultado["docs"][0].id == "c"


def test_paginar_cursor_invalido_começa_do_inicio():
    """cursor_anterior inválido não encontrado: começa do índice 0."""
    docs = [_make_doc("x"), _make_doc("y")]
    p = PaginadorFirestore(limite_padrao=5)
    resultado = p.paginar(docs, cursor_anterior="nao_existe")
    assert resultado["docs"][0].id == "x"


def test_paginar_com_numero_pagina_offset():
    """paginar() com pagina=2 usa offset por número de página."""
    docs = [_make_doc(f"doc{i}") for i in range(6)]
    p = PaginadorFirestore(limite_padrao=2)
    resultado = p.paginar(docs, pagina=2)
    assert resultado["docs"][0].id == "doc2"
    assert resultado["docs"][1].id == "doc3"


def test_encontrar_indice_cursor_retorna_indice_correto():
    """_encontrar_indice_cursor retorna o índice quando cursor existe."""
    docs = [_make_doc("a"), _make_doc("b"), _make_doc("c")]
    p = PaginadorFirestore()
    assert p._encontrar_indice_cursor(docs, "b") == 1


def test_encontrar_indice_cursor_retorna_menos_um_quando_nao_existe():
    """_encontrar_indice_cursor retorna -1 quando cursor não está na lista."""
    docs = [_make_doc("x"), _make_doc("y")]
    p = PaginadorFirestore()
    assert p._encontrar_indice_cursor(docs, "z") == -1


def test_resposta_json_retorna_estrutura_com_paginacao():
    """resposta_json retorna dict com sucesso=True, chamados e paginacao."""
    p = PaginadorFirestore(limite_padrao=10)
    docs = [_make_doc("d1"), _make_doc("d2")]
    resultado = p.paginar(docs)
    chamados_dict = [{"id": "d1"}, {"id": "d2"}]
    resp = p.resposta_json(resultado, chamados_dict)
    assert resp["sucesso"] is True
    assert resp["chamados"] == chamados_dict
    assert "paginacao" in resp
    assert "cursor_proximo" in resp["paginacao"]


def test_validar_filtros_categoria_e_status():
    """validar_filtros com categoria+status retorna True com mensagem de índice."""
    ok, msg = OptimizadorQuery.validar_filtros({"categoria": "TI", "status": "Aberto"})
    assert ok is True
    assert "categoria" in msg or "índice" in msg.lower()


def test_validar_filtros_gate_e_status():
    """validar_filtros com gate+status retorna True."""
    ok, msg = OptimizadorQuery.validar_filtros({"gate": "G1", "status": "Aberto"})
    assert ok is True
    assert "gate" in msg or "índice" in msg.lower()


def test_validar_filtros_sem_combinacao_conhecida():
    """validar_filtros com filtros arbitrários retorna True."""
    ok, msg = OptimizadorQuery.validar_filtros({"responsavel": "Ana"})
    assert ok is True


def test_obter_total_por_contagem_result_none_retorna_none():
    """obter_total_por_contagem retorna None quando agg.get() retorna None."""
    query_ref = MagicMock()
    query_ref.count.return_value.get.return_value = None
    assert obter_total_por_contagem(query_ref) is None


def test_obter_total_por_contagem_lista_vazia_retorna_none():
    """obter_total_por_contagem retorna None quando result é lista vazia."""
    query_ref = MagicMock()
    query_ref.count.return_value.get.return_value = []
    assert obter_total_por_contagem(query_ref) is None
