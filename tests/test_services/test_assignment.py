"""Testes do serviço de atribuição automática de chamados."""
import pytest
from unittest.mock import patch, MagicMock, call


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


@patch('app.services.assignment.db')
def test_contar_chamados_abertos_usa_query_in_unica(mock_db):
    """_contar_chamados_abertos deve fazer UMA query IN, não uma por supervisor."""
    from app.services.assignment import AtribuidorAutomatico

    sup_a = MagicMock()
    sup_a.nome = 'Ana'
    sup_b = MagicMock()
    sup_b.nome = 'Bruno'

    # Dois chamados abertos para Ana, um para Bruno, um concluído (não conta)
    def make_doc(responsavel, status):
        d = MagicMock()
        d.to_dict.return_value = {'responsavel': responsavel, 'status': status}
        return d

    mock_stream = [
        make_doc('Ana', 'Aberto'),
        make_doc('Ana', 'Em Atendimento'),
        make_doc('Bruno', 'Aberto'),
        make_doc('Ana', 'Concluído'),  # não deve contar
    ]

    mock_db.collection.return_value\
        .where.return_value\
        .stream.return_value = iter(mock_stream)

    atrib = AtribuidorAutomatico()
    result = atrib._contar_chamados_abertos([sup_a, sup_b])

    # Deve ter chamado .where('responsavel', 'in', ...) apenas uma vez
    assert mock_db.collection.return_value.where.call_count == 1
    where_call = mock_db.collection.return_value.where.call_args
    assert where_call[0][0] == 'responsavel'
    assert where_call[0][1] == 'in'
    assert set(where_call[0][2]) == {'Ana', 'Bruno'}

    # Contagens corretas
    por_nome = {r['usuario'].nome: r['chamados_abertos'] for r in result}
    assert por_nome['Ana'] == 2
    assert por_nome['Bruno'] == 1
