"""Testes do serviço de filtros e paginação do dashboard."""

from unittest.mock import MagicMock

from app.services.filters import (
    _aplicar_filtros_em_memoria,
    _construir_query_base,
    aplicar_filtros_dashboard,
    aplicar_filtros_dashboard_com_paginacao,
    construir_query_para_contagem,
)


def test_construir_query_base_sem_filtros_retorna_query_original():
    """Sem status/gate/responsavel, query_ref é retornada sem alteração lógica (mock chainable)."""
    query_ref = MagicMock()
    query_ref.where.return_value = query_ref
    args = {}
    query_filtrada, cat_filtrada, cat, status, gate = _construir_query_base(query_ref, args)
    assert query_filtrada is query_ref
    # categoria_filtrada = categoria and categoria not in ['','Todas'] -> None quando categoria é None
    assert not cat_filtrada
    assert status is None
    assert gate is None


def test_construir_query_base_com_status_aplica_where():
    """Com status nos args, where(filter=FieldFilter('status', '==', valor)) é chamado."""
    from google.cloud.firestore_v1.base_query import FieldFilter

    query_ref = MagicMock()
    query_ref.where.return_value = query_ref
    args = {"status": "Aberto"}
    query_filtrada, _, _, status, _ = _construir_query_base(query_ref, args)
    query_ref.where.assert_called_once()
    ff = query_ref.where.call_args.kwargs.get("filter")
    assert isinstance(ff, FieldFilter)
    assert ff.field_path == "status"
    assert ff.value == "Aberto"
    assert status == "Aberto"


def test_construir_query_base_ignora_status_todos():
    """Status 'Todos' ou vazio não aplica filtro de status."""
    query_ref = MagicMock()
    query_ref.where.return_value = query_ref
    for args in [{"status": "Todos"}, {"status": ""}]:
        _construir_query_base(query_ref, args)
    query_ref.where.assert_not_called()


def test_construir_query_para_contagem_retorna_mesma_query_base():
    """construir_query_para_contagem retorna a mesma query que _construir_query_base (para agregação)."""
    from google.cloud.firestore_v1.base_query import FieldFilter

    query_ref = MagicMock()
    query_ref.where.return_value = query_ref
    args = {"status": "Aberto"}
    q_contagem = construir_query_para_contagem(query_ref, args)
    query_filtrada, _, _, _, _ = _construir_query_base(query_ref, args)
    assert q_contagem is query_filtrada
    ff = query_ref.where.call_args.kwargs.get("filter")
    assert isinstance(ff, FieldFilter)
    assert ff.field_path == "status"


def test_aplicar_filtros_em_memoria_categoria_nao_filtra_em_memoria():
    """categoria é filtrada pelo Firestore; _aplicar_filtros_em_memoria não refiltra por ela."""
    doc_a = MagicMock()
    doc_a.to_dict.return_value = {"categoria": "Projetos", "descricao": "x"}
    doc_a.id = "a"
    doc_b = MagicMock()
    doc_b.to_dict.return_value = {"categoria": "Manutencao", "descricao": "y"}
    doc_b.id = "b"
    docs = [doc_a, doc_b]
    # O Firestore já filtrou por categoria antes de chamar esta função;
    # o parâmetro categoria é ignorado em memória — todos os docs passam.
    resultado = _aplicar_filtros_em_memoria(docs, None, None, "Projetos", None)
    assert len(resultado) == 2


def test_aplicar_filtros_em_memoria_busca_por_texto():
    """Busca por texto (case-insensitive) filtra por descrição, rl_codigo, responsavel, numero_chamado, id."""
    doc_ok = MagicMock()
    doc_ok.to_dict.return_value = {
        "descricao": "Falha no equipamento",
        "rl_codigo": "",
        "responsavel": "",
        "numero_chamado": "CHM-0001",
    }
    doc_ok.id = "doc1"
    doc_no = MagicMock()
    doc_no.to_dict.return_value = {
        "descricao": "Outro tema",
        "rl_codigo": "",
        "responsavel": "",
        "numero_chamado": "CHM-0002",
    }
    doc_no.id = "doc2"
    resultado = _aplicar_filtros_em_memoria([doc_ok, doc_no], None, None, None, "equipamento")
    assert len(resultado) == 1
    assert "equipamento" in resultado[0].to_dict().get("descricao", "").lower()


def test_aplicar_filtros_dashboard_com_paginacao_retorna_estrutura():
    """aplicar_filtros_dashboard_com_paginacao retorna dict com docs, proximo_cursor, tem_proxima, cursor_anterior, tem_anterior."""
    query_ref = MagicMock()
    query_ref.where.return_value = query_ref
    query_ref.order_by.return_value = query_ref
    query_ref.limit.return_value = query_ref
    query_ref.stream.return_value = []
    resultado = aplicar_filtros_dashboard_com_paginacao(query_ref, {}, limite=50, cursor=None)
    assert "docs" in resultado
    assert "proximo_cursor" in resultado
    assert "tem_proxima" in resultado
    assert "cursor_anterior" in resultado
    assert "tem_anterior" in resultado
    assert resultado["docs"] == []
    assert resultado["tem_proxima"] is False
    assert resultado["proximo_cursor"] is None


def test_aplicar_filtros_dashboard_com_paginacao_tem_proxima():
    """Quando stream retorna mais que limite, tem_proxima True e proximo_cursor do último doc da página."""
    doc1 = MagicMock()
    doc1.id = "id1"
    doc1.to_dict.return_value = {"categoria": "Geral", "status": "Aberto", "gate": None}
    doc2 = MagicMock()
    doc2.id = "id2"
    doc2.to_dict.return_value = {"categoria": "Geral", "status": "Aberto", "gate": None}
    doc3 = MagicMock()
    doc3.id = "id3"
    doc3.to_dict.return_value = {"categoria": "Geral", "status": "Aberto", "gate": None}
    query_ref = MagicMock()
    query_ref.where.return_value = query_ref
    query_ref.order_by.return_value = query_ref
    query_ref.limit.return_value = query_ref
    # limite=2 -> limit(3).stream(); 3 docs = tem_proxima True, página fica com doc1, doc2
    query_ref.stream.return_value = [doc1, doc2, doc3]
    resultado = aplicar_filtros_dashboard_com_paginacao(query_ref, {}, limite=2, cursor=None)
    assert len(resultado["docs"]) == 2
    assert resultado["proximo_cursor"] == "id2"
    assert resultado["tem_proxima"] is True


def test_construir_query_base_com_categoria_aplica_where_firestore():
    """categoria deve ser aplicada via .where() no Firestore, não só em memória após .limit()."""

    query_ref = MagicMock()
    query_ref.where.return_value = query_ref
    args = {"categoria": "Projetos"}
    _construir_query_base(query_ref, args)

    ff_calls = [c.kwargs.get("filter") for c in query_ref.where.call_args_list]
    categoria_ff = next(
        (ff for ff in ff_calls if getattr(ff, "field_path", None) == "categoria"), None
    )
    assert categoria_ff is not None, (
        "categoria deve ser aplicada na query Firestore para evitar filtro pós-limit"
    )
    assert categoria_ff.value == "Projetos"


def test_construir_query_base_ignora_categoria_todas():
    """categoria 'Todas' ou vazia não aplica filtro de categoria na query."""
    query_ref = MagicMock()
    query_ref.where.return_value = query_ref
    for args in [{"categoria": "Todas"}, {"categoria": ""}]:
        query_ref.where.reset_mock()
        _construir_query_base(query_ref, args)
        ff_calls = [c.kwargs.get("filter") for c in query_ref.where.call_args_list]
        categoria_ff = next(
            (ff for ff in ff_calls if getattr(ff, "field_path", None) == "categoria"), None
        )
        assert categoria_ff is None, (
            f"'{args['categoria']}' não deve filtrar categoria no Firestore"
        )


def test_aplicar_filtros_dashboard_retorna_lista():
    """aplicar_filtros_dashboard (legado) retorna lista de docs."""
    query_ref = MagicMock()
    query_ref.where.return_value = query_ref
    query_ref.order_by.return_value = query_ref
    query_ref.limit.return_value = query_ref
    query_ref.stream.return_value = []
    docs = aplicar_filtros_dashboard(query_ref, {})
    assert isinstance(docs, list)
    assert docs == []


def test_aplicar_filtros_com_cursor_start_after():
    """Paginação avançada com cursor deve chamar start_after no doc cursor."""
    doc1 = MagicMock()
    doc1.id = "id_cursor"
    doc1.to_dict.return_value = {"categoria": "TI", "status": "Aberto", "gate": None}

    cursor_doc = MagicMock()
    cursor_doc.exists = True

    query_ref = MagicMock()
    query_ref.where.return_value = query_ref
    query_ref.order_by.return_value = query_ref
    query_ref.start_after.return_value = query_ref
    query_ref.limit.return_value = query_ref
    query_ref.stream.return_value = [doc1]
    query_ref.parent = query_ref
    query_ref.document.return_value.get.return_value = cursor_doc

    resultado = aplicar_filtros_dashboard_com_paginacao(
        query_ref, {}, limite=10, cursor="id_cursor"
    )
    assert "docs" in resultado
    query_ref.start_after.assert_called_once_with(cursor_doc)


def test_aplicar_filtros_cursor_anterior_tem_anterior_true():
    """cursor_anterior com mais docs que limite define tem_anterior=True e trunca a lista."""
    doc1 = MagicMock()
    doc1.id = "id1"
    doc1.to_dict.return_value = {"categoria": "TI", "status": "Aberto", "gate": None}
    doc2 = MagicMock()
    doc2.id = "id2"
    doc2.to_dict.return_value = {"categoria": "TI", "status": "Aberto", "gate": None}

    cursor_doc = MagicMock()
    cursor_doc.exists = True

    query_ref = MagicMock()
    query_ref.where.return_value = query_ref
    query_ref.order_by.return_value = query_ref
    query_ref.end_before.return_value = query_ref
    query_ref.limit.return_value = query_ref
    # Stream retorna 2 docs; limite=1 → tem_anterior=True, trunca para 1
    query_ref.stream.return_value = [doc1, doc2]
    query_ref.parent = query_ref
    query_ref.document.return_value.get.return_value = cursor_doc

    resultado = aplicar_filtros_dashboard_com_paginacao(
        query_ref, {}, limite=1, cursor_anterior="id1"
    )
    assert resultado["tem_anterior"] is True
    assert len(resultado["docs"]) == 1


def test_construir_query_base_com_gate_aplica_where():
    """Com gate nos args, where(filter=FieldFilter('gate', ...)) é chamado."""

    query_ref = MagicMock()
    query_ref.where.return_value = query_ref
    args = {"gate": "G1"}
    _construir_query_base(query_ref, args)
    ff_calls = [c.kwargs.get("filter") for c in query_ref.where.call_args_list]
    gate_ff = next((ff for ff in ff_calls if getattr(ff, "field_path", None) == "gate"), None)
    assert gate_ff is not None
    assert gate_ff.value == "G1"


def test_construir_query_base_com_responsavel_aplica_where():
    """Com responsavel nos args, where(filter=FieldFilter('responsavel', ...)) é chamado."""

    query_ref = MagicMock()
    query_ref.where.return_value = query_ref
    args = {"responsavel": "Ana"}
    _construir_query_base(query_ref, args)
    ff_calls = [c.kwargs.get("filter") for c in query_ref.where.call_args_list]
    resp_ff = next(
        (ff for ff in ff_calls if getattr(ff, "field_path", None) == "responsavel"), None
    )
    assert resp_ff is not None
    assert resp_ff.value == "Ana"


def test_construir_query_base_com_rl_codigo_aplica_where():
    """Com rl_codigo nos args, where(filter=FieldFilter('rl_codigo', ...)) é chamado."""

    query_ref = MagicMock()
    query_ref.where.return_value = query_ref
    args = {"rl_codigo": "RL-001"}
    _construir_query_base(query_ref, args)
    ff_calls = [c.kwargs.get("filter") for c in query_ref.where.call_args_list]
    rl_ff = next((ff for ff in ff_calls if getattr(ff, "field_path", None) == "rl_codigo"), None)
    assert rl_ff is not None
    assert rl_ff.value == "RL-001"


def test_aplicar_filtros_dashboard_com_paginacao_cursor_anterior():
    """cursor_anterior faz paginação reversa (end_before) e reverte a ordem."""
    doc1 = MagicMock()
    doc1.id = "id_first"
    doc1.to_dict.return_value = {"categoria": "TI", "status": "Aberto", "gate": None}
    doc2 = MagicMock()
    doc2.id = "id_second"
    doc2.to_dict.return_value = {"categoria": "TI", "status": "Aberto", "gate": None}

    cursor_doc = MagicMock()
    cursor_doc.exists = True

    query_ref = MagicMock()
    query_ref.where.return_value = query_ref
    query_ref.order_by.return_value = query_ref
    query_ref.end_before.return_value = query_ref
    query_ref.limit.return_value = query_ref
    query_ref.stream.return_value = [doc1, doc2]
    query_ref.parent = query_ref
    query_ref.document.return_value.get.return_value = cursor_doc

    resultado = aplicar_filtros_dashboard_com_paginacao(
        query_ref, {}, limite=10, cursor_anterior="id_first"
    )
    assert "docs" in resultado
    assert "tem_anterior" in resultado


# ── F-23: to_dict() chamado exatamente 1x por doc na busca textual ─────────────


def test_aplicar_filtros_em_memoria_to_dict_chamado_uma_vez_por_doc():
    """F-23: _aplicar_filtros_em_memoria deve chamar to_dict() apenas 1x por doc,
    independente de quantos campos são testados na busca textual."""
    doc_a = MagicMock()
    doc_a.to_dict.return_value = {
        "descricao": "Falha no equipamento",
        "rl_codigo": "RL-001",
        "responsavel": "Ana",
        "numero_chamado": "CHM-0001",
    }
    doc_a.id = "doc_a"

    doc_b = MagicMock()
    doc_b.to_dict.return_value = {
        "descricao": "Outro assunto",
        "rl_codigo": "RL-002",
        "responsavel": "Bruno",
        "numero_chamado": "CHM-0002",
    }
    doc_b.id = "doc_b"

    _aplicar_filtros_em_memoria([doc_a, doc_b], None, None, None, "equipamento")

    assert doc_a.to_dict.call_count == 1, (
        f"to_dict() deve ser chamado exatamente 1x para doc_a, chamado {doc_a.to_dict.call_count}x"
    )
    assert doc_b.to_dict.call_count == 1, (
        f"to_dict() deve ser chamado exatamente 1x para doc_b, chamado {doc_b.to_dict.call_count}x"
    )
