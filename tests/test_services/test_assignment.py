"""Testes do serviço de atribuição automática de chamados."""
import pytest
from unittest.mock import patch, MagicMock


@patch('app.services.assignment.Usuario.get_supervisores_por_area')
def test_atribuir_retorna_falha_quando_nao_ha_supervisores(mock_get_sup):
    """Se não há supervisores na área, retorna sucesso=False e motivo."""
    mock_get_sup.return_value = []
    from app.services.assignment import AtribuidorAutomatico
    atrib = AtribuidorAutomatico()
    r = atrib.atribuir(area='AreaVazia', categoria='Manutencao', prioridade=1)
    assert r['sucesso'] is False
    assert r['supervisor'] is None
    assert 'Nenhum supervisor' in r['motivo'] or 'disponível' in r['motivo']


@patch('app.services.assignment.Usuario.get_supervisores_por_area')
def test_atribuir_retorna_estrutura_correta_quando_falha(mock_get_sup):
    """Resposta de falha contém estrategia_usada."""
    mock_get_sup.return_value = []
    from app.services.assignment import AtribuidorAutomatico
    atrib = AtribuidorAutomatico(estrategia='balanceamento_carga')
    r = atrib.atribuir(area='X')
    assert 'estrategia_usada' in r
    assert r['estrategia_usada'] == 'balanceamento_carga'


def test_atribuidor_aceita_estrategias_validas():
    """AtribuidorAutomatico aceita apenas estratégias conhecidas."""
    from app.services.assignment import AtribuidorAutomatico
    with pytest.raises(ValueError):
        AtribuidorAutomatico(estrategia='inexistente')
