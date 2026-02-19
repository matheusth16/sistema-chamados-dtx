"""Testes do serviço de analytics/relatórios."""
import pytest
from unittest.mock import patch, MagicMock


def test_obter_metricas_gerais_retorna_dict_com_chaves_esperadas():
    """obter_metricas_gerais retorna dict com periodo_dias, total_chamados, etc."""
    from app.services.analytics import AnalisadorChamados
    mock_where = MagicMock()
    mock_where.stream.return_value = []  # lista vazia = nenhum chamado
    mock_collection = MagicMock()
    mock_collection.where.return_value = mock_where
    mock_db = MagicMock()
    mock_db.collection.return_value = mock_collection
    with patch.object(AnalisadorChamados, 'get_db', return_value=mock_db):
        a = AnalisadorChamados()
        r = a.obter_metricas_gerais(dias=30)
    assert isinstance(r, dict)
    assert 'periodo_dias' in r
    assert 'total_chamados' in r
    assert 'abertos' in r
    assert 'concluidos' in r
    assert 'taxa_resolucao_percentual' in r
    assert r['periodo_dias'] == 30


def test_obter_relatorio_completo_retorna_dict_com_secoes():
    """obter_relatorio_completo retorna dict com metricas_gerais, insights, etc."""
    from app.services.analytics import AnalisadorChamados
    with patch.object(AnalisadorChamados, 'obter_metricas_gerais', return_value={}):
        with patch.object(AnalisadorChamados, 'obter_metricas_supervisores', return_value=[]):
            with patch.object(AnalisadorChamados, 'obter_metricas_areas', return_value=[]):
                with patch.object(AnalisadorChamados, 'obter_analise_atribuicao', return_value={}):
                    with patch.object(AnalisadorChamados, 'obter_insights', return_value=[]):
                        a = AnalisadorChamados()
                        r = a.obter_relatorio_completo(usar_cache=False)
    assert 'metricas_gerais' in r
    assert 'metricas_supervisores' in r
    assert 'metricas_areas' in r
    assert 'analise_atribuicao' in r
    assert 'insights' in r
    assert 'data_geracao' in r
