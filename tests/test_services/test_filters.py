"""Testes do serviço de filtros e paginação do dashboard."""
import pytest
from unittest.mock import MagicMock

from app.services.filters import (
    _construir_query_base,
    construir_query_para_contagem,
    _aplicar_filtros_em_memoria,
    aplicar_filtros_dashboard_com_paginacao,
    aplicar_filtros_dashboard,
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
    """Com status nos args, where('status', '==', valor) é chamado."""
    query_ref = MagicMock()
    query_ref.where.return_value = query_ref
    args = {'status': 'Aberto'}
    query_filtrada, _, _, status, _ = _construir_query_base(query_ref, args)
    query_ref.where.assert_called_with('status', '==', 'Aberto')
    assert status == 'Aberto'


def test_construir_query_base_ignora_status_todos():
    """Status 'Todos' ou vazio não aplica filtro de status."""
    query_ref = MagicMock()
    query_ref.where.return_value = query_ref
    for args in [{'status': 'Todos'}, {'status': ''}]:
        _construir_query_base(query_ref, args)
    query_ref.where.assert_not_called()


def test_construir_query_para_contagem_retorna_mesma_query_base():
    """construir_query_para_contagem retorna a mesma query que _construir_query_base (para agregação)."""
    query_ref = MagicMock()
    query_ref.where.return_value = query_ref
    args = {'status': 'Aberto'}
    q_contagem = construir_query_para_contagem(query_ref, args)
    query_filtrada, _, _, _, _ = _construir_query_base(query_ref, args)
    assert q_contagem is query_filtrada
    query_ref.where.assert_called_with('status', '==', 'Aberto')


def test_aplicar_filtros_em_memoria_filtra_por_categoria():
    """Filtro em memória por categoria retorna apenas docs da categoria."""
    doc_a = MagicMock()
    doc_a.to_dict.return_value = {'categoria': 'Projetos', 'descricao': 'x'}
    doc_a.id = 'a'
    doc_b = MagicMock()
    doc_b.to_dict.return_value = {'categoria': 'Manutencao', 'descricao': 'y'}
    doc_b.id = 'b'
    docs = [doc_a, doc_b]
    resultado = _aplicar_filtros_em_memoria(docs, None, None, 'Projetos', None)
    assert len(resultado) == 1
    assert resultado[0].to_dict().get('categoria') == 'Projetos'


def test_aplicar_filtros_em_memoria_busca_por_texto():
    """Busca por texto (case-insensitive) filtra por descrição, rl_codigo, responsavel, numero_chamado, id."""
    doc_ok = MagicMock()
    doc_ok.to_dict.return_value = {'descricao': 'Falha no equipamento', 'rl_codigo': '', 'responsavel': '', 'numero_chamado': 'CHM-0001'}
    doc_ok.id = 'doc1'
    doc_no = MagicMock()
    doc_no.to_dict.return_value = {'descricao': 'Outro tema', 'rl_codigo': '', 'responsavel': '', 'numero_chamado': 'CHM-0002'}
    doc_no.id = 'doc2'
    resultado = _aplicar_filtros_em_memoria([doc_ok, doc_no], None, None, None, 'equipamento')
    assert len(resultado) == 1
    assert 'equipamento' in resultado[0].to_dict().get('descricao', '').lower()


def test_aplicar_filtros_dashboard_com_paginacao_retorna_estrutura():
    """aplicar_filtros_dashboard_com_paginacao retorna dict com docs, proximo_cursor, tem_proxima."""
    query_ref = MagicMock()
    query_ref.where.return_value = query_ref
    query_ref.limit.return_value = query_ref
    query_ref.stream.return_value = []
    resultado = aplicar_filtros_dashboard_com_paginacao(query_ref, {}, limite=50, cursor=None)
    assert 'docs' in resultado
    assert 'proximo_cursor' in resultado
    assert 'tem_proxima' in resultado
    assert resultado['docs'] == []
    assert resultado['tem_proxima'] is False
    assert resultado['proximo_cursor'] is None


def test_aplicar_filtros_dashboard_com_paginacao_tem_proxima():
    """Quando stream retorna mais que limite, tem_proxima True e proximo_cursor do último doc da página."""
    doc1 = MagicMock()
    doc1.id = 'id1'
    doc1.to_dict.return_value = {'categoria': 'Geral', 'status': 'Aberto', 'gate': None}
    doc2 = MagicMock()
    doc2.id = 'id2'
    doc2.to_dict.return_value = {'categoria': 'Geral', 'status': 'Aberto', 'gate': None}
    doc3 = MagicMock()
    doc3.id = 'id3'
    doc3.to_dict.return_value = {'categoria': 'Geral', 'status': 'Aberto', 'gate': None}
    query_ref = MagicMock()
    query_ref.where.return_value = query_ref
    query_ref.limit.return_value = query_ref
    # limite=2 -> limit(3).stream(); 3 docs = tem_proxima True, página fica com doc1, doc2
    query_ref.stream.return_value = [doc1, doc2, doc3]
    resultado = aplicar_filtros_dashboard_com_paginacao(query_ref, {}, limite=2, cursor=None)
    assert len(resultado['docs']) == 2
    assert resultado['proximo_cursor'] == 'id2'
    assert resultado['tem_proxima'] is True


def test_aplicar_filtros_dashboard_retorna_lista():
    """aplicar_filtros_dashboard (legado) retorna lista de docs."""
    query_ref = MagicMock()
    query_ref.where.return_value = query_ref
    query_ref.limit.return_value = query_ref
    query_ref.stream.return_value = []
    docs = aplicar_filtros_dashboard(query_ref, {})
    assert isinstance(docs, list)
    assert docs == []
