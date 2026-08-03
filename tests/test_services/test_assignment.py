"""Testes do serviço de atribuição automática de chamados.

Fase 2 (Marco 7): _contar_chamados_abertos roda contra Postgres real
(fixture db_session) via GROUP BY agregado — substitui o antigo mock de
db.collection("chamados").where(filter=FieldFilter(...)).stream(). Como o
banco de teste começa vazio, os testes que só precisam de "sem chamados
existentes" (contagem 0) não precisam mockar nada — é o estado natural.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.models import Chamado

pytestmark = pytest.mark.usefixtures("db_session")


def _criar_chamado(responsavel: str, status: str = "Aberto") -> int:
    chamado = Chamado(
        categoria="TI",
        tipo_solicitacao="Suporte",
        descricao="Descrição de teste",
        responsavel=responsavel,
        status=status,
    )
    chamado_id = chamado.salvar()
    assert chamado_id is not None
    return chamado_id


@patch("app.services.assignment.Usuario.get_supervisores_por_area")
def test_atribuir_retorna_falha_quando_nao_ha_supervisores(mock_get_sup):
    """Se não há supervisores na área, retorna sucesso=False e motivo."""
    mock_get_sup.return_value = []
    from app.services.assignment import AtribuidorAutomatico

    atrib = AtribuidorAutomatico()
    r = atrib.atribuir(area="AreaVazia", categoria="Manutencao", prioridade=1)
    assert r["sucesso"] is False
    assert r["supervisor"] is None
    assert "No supervisor" in r["motivo"] or "available" in r["motivo"]


@patch("app.services.assignment.Usuario.get_supervisores_por_area")
def test_atribuir_retorna_estrutura_correta_quando_falha(mock_get_sup):
    """Resposta de falha contém estrategia_usada."""
    mock_get_sup.return_value = []
    from app.services.assignment import AtribuidorAutomatico

    atrib = AtribuidorAutomatico(estrategia="balanceamento_carga")
    r = atrib.atribuir(area="X")
    assert "estrategia_usada" in r
    assert r["estrategia_usada"] == "balanceamento_carga"


def test_atribuidor_aceita_estrategias_validas():
    """AtribuidorAutomatico aceita apenas estratégias conhecidas."""
    from app.services.assignment import AtribuidorAutomatico

    with pytest.raises(ValueError):
        AtribuidorAutomatico(estrategia="inexistente")


def test_contar_chamados_abertos_conta_por_responsavel():
    """_contar_chamados_abertos agrega corretamente por responsavel (nome)."""
    from app.services.assignment import AtribuidorAutomatico

    sup_a = MagicMock()
    sup_a.nome = "Ana"
    sup_b = MagicMock()
    sup_b.nome = "Bruno"

    # Dois chamados abertos para Ana, um para Bruno, um concluído (não conta)
    _criar_chamado("Ana", "Aberto")
    _criar_chamado("Ana", "Em Atendimento")
    _criar_chamado("Bruno", "Aberto")
    _criar_chamado("Ana", "Concluído")  # não deve contar

    atrib = AtribuidorAutomatico()
    result = atrib._contar_chamados_abertos([sup_a, sup_b])

    por_nome = {r["usuario"].nome: r["chamados_abertos"] for r in result}
    assert por_nome["Ana"] == 2
    assert por_nome["Bruno"] == 1


def test_contar_chamados_abertos_exclui_cancelado():
    """_contar_chamados_abertos deve excluir chamados Cancelado (além de Concluído) da contagem."""
    from app.services.assignment import AtribuidorAutomatico

    sup = MagicMock()
    sup.nome = "Carlos"

    _criar_chamado("Carlos", "Aberto")
    _criar_chamado("Carlos", "Cancelado")  # não deve contar
    _criar_chamado("Carlos", "Concluído")  # não deve contar
    _criar_chamado("Carlos", "Em Atendimento")

    atrib = AtribuidorAutomatico()
    result = atrib._contar_chamados_abertos([sup])

    por_nome = {r["usuario"].nome: r["chamados_abertos"] for r in result}
    assert por_nome["Carlos"] == 2, (
        "Cancelado e Concluído não devem ser contados como chamados abertos"
    )


def test_contar_chamados_abertos_lista_vazia_retorna_vazia():
    """_contar_chamados_abertos com lista vazia retorna []."""
    from app.services.assignment import AtribuidorAutomatico

    atrib = AtribuidorAutomatico()
    assert atrib._contar_chamados_abertos([]) == []


def test_contar_chamados_abertos_excecao_nao_propaga():
    """Exceção no banco não derruba a contagem — retorna zeros."""
    from app.services.assignment import AtribuidorAutomatico

    sup = MagicMock()
    sup.nome = "Erro"

    with patch("app.services.assignment.db_module") as mock_db_module:
        mock_db_module.SessionLocal.side_effect = Exception("timeout")
        atrib = AtribuidorAutomatico()
        result = atrib._contar_chamados_abertos([sup])

    assert result[0]["chamados_abertos"] == 0


# ── _atribuir_balanceamento ───────────────────────────────────────────────────


def test_atribuir_balanceamento_escolhe_supervisor_com_menos_carga():
    from app.services.assignment import AtribuidorAutomatico

    sup_a = MagicMock()
    sup_a.nome = "Ana"
    sup_b = MagicMock()
    sup_b.nome = "Bruno"
    carga = [
        {"usuario": sup_a, "chamados_abertos": 5},
        {"usuario": sup_b, "chamados_abertos": 2},
    ]

    atrib = AtribuidorAutomatico(estrategia="balanceamento_carga")
    escolhido = atrib._atribuir_balanceamento(carga, "TI")
    assert escolhido["usuario"].nome == "Bruno"


def test_atribuir_balanceamento_lista_vazia_retorna_none():
    from app.services.assignment import AtribuidorAutomatico

    atrib = AtribuidorAutomatico(estrategia="balanceamento_carga")
    assert atrib._atribuir_balanceamento([], "TI") is None


# ── _atribuir_round_robin ─────────────────────────────────────────────────────


def test_atribuir_round_robin_rotaciona_supervisores():
    from app.services.assignment import AtribuidorAutomatico

    sup_a = MagicMock()
    sup_a.nome = "Ana"
    sup_b = MagicMock()
    sup_b.nome = "Bruno"
    carga = [{"usuario": sup_a, "chamados_abertos": 0}, {"usuario": sup_b, "chamados_abertos": 0}]

    atrib = AtribuidorAutomatico(estrategia="round_robin")
    primeiro = atrib._atribuir_round_robin(carga, "TI")
    segundo = atrib._atribuir_round_robin(carga, "TI")
    assert primeiro["usuario"].nome != segundo["usuario"].nome


def test_atribuir_round_robin_lista_vazia_retorna_none():
    from app.services.assignment import AtribuidorAutomatico

    atrib = AtribuidorAutomatico(estrategia="round_robin")
    assert atrib._atribuir_round_robin([], "TI") is None


# ── atribuir() success path ───────────────────────────────────────────────────


@patch("app.services.assignment.Usuario.get_supervisores_por_area")
def test_atribuir_sucesso_com_balanceamento(mock_get_sup):
    """atribuir() com supervisores disponíveis retorna sucesso=True."""
    from app.services.assignment import AtribuidorAutomatico

    sup = MagicMock()
    sup.id = "sup_1"
    sup.nome = "Ana"
    sup.email = "ana@test.com"
    sup.area = "TI"
    mock_get_sup.return_value = [sup]

    atrib = AtribuidorAutomatico(estrategia="balanceamento_carga")
    r = atrib.atribuir(area="TI", categoria="Suporte")
    assert r["sucesso"] is True
    assert r["supervisor"]["nome"] == "Ana"


@patch("app.services.assignment.Usuario.get_supervisores_por_area")
def test_atribuir_excecao_retorna_falha(mock_get_sup):
    """Exceção interna em atribuir() retorna sucesso=False sem explodir."""
    from app.services.assignment import AtribuidorAutomatico

    mock_get_sup.side_effect = Exception("Postgres error")
    atrib = AtribuidorAutomatico()
    r = atrib.atribuir(area="TI")
    assert r["sucesso"] is False
    assert "Error assigning" in r["motivo"]


# ── obter_disponibilidade ─────────────────────────────────────────────────────


@patch("app.services.assignment.Usuario.get_supervisores_por_area")
def test_obter_disponibilidade_retorna_estrutura(mock_get_sup):
    """obter_disponibilidade retorna dict com area, supervisores e carga."""
    from app.services.assignment import AtribuidorAutomatico

    sup = MagicMock()
    sup.id = "s1"
    sup.nome = "Ana"
    sup.email = "ana@test.com"
    mock_get_sup.return_value = [sup]

    atrib = AtribuidorAutomatico()
    d = atrib.obter_disponibilidade("TI")
    assert "area" in d
    assert "supervisores" in d
    assert "carga_total" in d
    assert d["total_supervisores"] == 1


@patch("app.services.assignment.Usuario.get_supervisores_por_area")
def test_obter_disponibilidade_excecao_retorna_estrutura_vazia(mock_get_sup):
    """Exceção em obter_disponibilidade retorna estrutura com zeros."""
    from app.services.assignment import AtribuidorAutomatico

    mock_get_sup.side_effect = Exception("Postgres error")
    atrib = AtribuidorAutomatico()
    d = atrib.obter_disponibilidade("TI")
    assert d["total_supervisores"] == 0
    assert d["supervisores"] == []


# ── strategy branches via atribuir() ─────────────────────────────────────────


@patch("app.services.assignment.Usuario.get_supervisores_por_area")
def test_atribuir_round_robin_via_atribuir_sucesso(mock_get_sup):
    """atribuir() com estrategia=round_robin retorna sucesso=True."""
    from app.services.assignment import AtribuidorAutomatico

    sup = MagicMock()
    sup.id = "sup_rr"
    sup.nome = "Ana RR"
    sup.email = "ana_rr@test.com"
    sup.area = "TI"
    mock_get_sup.return_value = [sup]

    atrib = AtribuidorAutomatico(estrategia="round_robin")
    r = atrib.atribuir(area="TI", categoria="Suporte")
    assert r["sucesso"] is True
    assert r["supervisor"]["nome"] == "Ana RR"


@patch("app.services.assignment.Usuario.get_supervisores_por_area")
def test_atribuir_aleatorio_via_atribuir_sucesso(mock_get_sup):
    """atribuir() com estrategia=aleatorio retorna sucesso=True."""
    from app.services.assignment import AtribuidorAutomatico

    sup = MagicMock()
    sup.id = "sup_al"
    sup.nome = "Bruno Aleatório"
    sup.email = "bruno@test.com"
    sup.area = "TI"
    mock_get_sup.return_value = [sup]

    atrib = AtribuidorAutomatico(estrategia="aleatorio")
    r = atrib.atribuir(area="TI", categoria="Suporte")
    assert r["sucesso"] is True


@patch("app.services.assignment.Usuario.get_supervisores_por_area")
def test_atribuir_retorna_falha_quando_escolhido_none(mock_get_sup):
    """atribuir() retorna sucesso=False quando _atribuir_balanceamento devolve None."""
    from app.services.assignment import AtribuidorAutomatico

    sup = MagicMock()
    sup.nome = "Ana"
    mock_get_sup.return_value = [sup]

    atrib = AtribuidorAutomatico(estrategia="balanceamento_carga")
    with patch.object(atrib, "_atribuir_balanceamento", return_value=None):
        r = atrib.atribuir(area="TI")
    assert r["sucesso"] is False
    assert "Could not select" in r["motivo"]


# ── S4-08: Validação de área inválida em atribuir() ──────────────────────────


def test_atribuir_area_vazia_retorna_falha():
    """atribuir() com area='' retorna sucesso=False sem consultar supervisores."""
    from app.services.assignment import AtribuidorAutomatico

    atrib = AtribuidorAutomatico()
    r = atrib.atribuir(area="")
    assert r["sucesso"] is False
    assert "invalid" in r["motivo"].lower() or "missing" in r["motivo"].lower()
    assert "estrategia_usada" in r


def test_atribuir_area_apenas_whitespace_retorna_falha():
    """atribuir() com area somente de espaços retorna sucesso=False."""
    from app.services.assignment import AtribuidorAutomatico

    atrib = AtribuidorAutomatico()
    r = atrib.atribuir(area="   ")
    assert r["sucesso"] is False


def test_atribuir_area_valida_nao_afetada():
    """atribuir() com área válida segue o fluxo normal (sem regressão)."""
    from app.services.assignment import AtribuidorAutomatico

    with patch("app.services.assignment.Usuario.get_supervisores_por_area", return_value=[]):
        atrib = AtribuidorAutomatico()
        r = atrib.atribuir(area="Manutencao")
    assert r["sucesso"] is False
    assert "No supervisor" in r["motivo"]


# ── F-20: estratégia aleatorio usa random.choice ──────────────────────────────


@patch("app.services.assignment.Usuario.get_supervisores_por_area")
def test_atribuir_aleatorio_usa_random_choice(mock_get_sup):
    """Estratégia aleatorio deve usar random.choice, não sempre pegar o primeiro supervisor."""

    from app.services.assignment import AtribuidorAutomatico

    sup_a = MagicMock()
    sup_a.id = "a"
    sup_a.nome = "Ana"
    sup_a.email = "ana@test.com"
    sup_a.area = "TI"
    sup_b = MagicMock()
    sup_b.id = "b"
    sup_b.nome = "Bruno"
    sup_b.email = "bruno@test.com"
    sup_b.area = "TI"

    mock_get_sup.return_value = [sup_a, sup_b]

    atrib = AtribuidorAutomatico(estrategia="aleatorio")

    with patch("app.services.assignment.random.choice") as mock_choice:
        mock_choice.return_value = {"usuario": sup_b, "chamados_abertos": 0}
        r = atrib.atribuir(area="TI")

    mock_choice.assert_called_once()
    assert r["sucesso"] is True


# ── F-21: round-robin atômico com Redis INCR ──────────────────────────────────


def test_round_robin_usa_redis_incr_quando_disponivel():
    """F-21: com REDIS_URL, _atribuir_round_robin usa Redis INCR para contador atômico cross-worker."""
    from app.services.assignment import AtribuidorAutomatico

    sup_a = MagicMock()
    sup_a.nome = "Ana"
    sup_b = MagicMock()
    sup_b.nome = "Bruno"
    carga = [{"usuario": sup_a, "chamados_abertos": 0}, {"usuario": sup_b, "chamados_abertos": 0}]

    mock_redis = MagicMock()
    mock_redis.incr.return_value = 1  # 1 % 2 = índice 1 → "Bruno"

    with (
        patch.dict("os.environ", {"REDIS_URL": "redis://localhost:6379"}),
        patch("redis.from_url", return_value=mock_redis),
    ):
        atrib = AtribuidorAutomatico(estrategia="round_robin")
        escolhido = atrib._atribuir_round_robin(carga, "TI")

    mock_redis.incr.assert_called_once()
    assert escolhido["usuario"].nome == "Bruno"


def test_round_robin_fallback_em_memoria_quando_redis_indisponivel():
    """F-21: sem REDIS_URL, _atribuir_round_robin usa contador em memória e ainda rotaciona."""
    from app.services.assignment import AtribuidorAutomatico

    sup_a = MagicMock()
    sup_a.nome = "Ana"
    sup_b = MagicMock()
    sup_b.nome = "Bruno"
    carga = [{"usuario": sup_a, "chamados_abertos": 0}, {"usuario": sup_b, "chamados_abertos": 0}]

    with patch.dict("os.environ", {}, clear=True):
        atrib = AtribuidorAutomatico(estrategia="round_robin")
        primeiro = atrib._atribuir_round_robin(carga, "TI")
        segundo = atrib._atribuir_round_robin(carga, "TI")

    assert primeiro["usuario"].nome != segundo["usuario"].nome
