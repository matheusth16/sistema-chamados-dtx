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
    assert 'resumo_sla' in r
    assert 'distribuicao_categoria' in r
    assert r['periodo_dias'] == 30
    assert set(r['resumo_sla'].keys()) == {'no_prazo', 'atrasado', 'em_risco'}


def test_obter_relatorio_completo_retorna_dict_com_secoes():
    """obter_relatorio_completo retorna dict com metricas_gerais, insights, metricas_delta, etc."""
    from app.services.analytics import AnalisadorChamados
    with patch.object(AnalisadorChamados, 'obter_metricas_gerais', return_value={}):
        with patch.object(AnalisadorChamados, 'obter_metricas_periodo_anterior', return_value={}):
            with patch.object(AnalisadorChamados, 'obter_metricas_supervisores', return_value=[]):
                with patch.object(AnalisadorChamados, 'obter_metricas_areas', return_value=[]):
                    with patch.object(AnalisadorChamados, 'obter_insights', return_value=[]):
                        a = AnalisadorChamados()
                        r = a.obter_relatorio_completo(usar_cache=False)
    assert 'metricas_gerais' in r
    assert 'metricas_delta' in r
    assert 'metricas_supervisores' in r
    assert 'metricas_areas' in r
    assert 'insights' in r
    assert 'data_geracao' in r


def test_calcular_deltas_retorna_valores_corretos():
    """_calcular_deltas calcula diferenças entre período atual e anterior."""
    from app.services.analytics import AnalisadorChamados
    atual = {
        'total_chamados': 50,
        'taxa_resolucao_percentual': 75.0,
        'percentual_dentro_sla': 80.0,
        'tempo_medio_resolucao_horas': 12.0,
    }
    anterior = {
        'total_chamados': 40,
        'taxa_resolucao_percentual': 70.0,
        'percentual_dentro_sla': None,
        'tempo_medio_resolucao_horas': 15.0,
    }
    deltas = AnalisadorChamados._calcular_deltas(atual, anterior)
    assert deltas['total_chamados_delta'] == 10
    assert deltas['taxa_resolucao_percentual_delta'] == 5.0
    assert deltas['percentual_dentro_sla_delta'] is None
    assert deltas['tempo_medio_resolucao_horas_delta'] == -3.0
