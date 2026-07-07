"""Testes do serviço de atribuição automática de chamados."""

from unittest.mock import MagicMock, patch

import pytest


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


@patch("app.services.assignment.db")
def test_contar_chamados_abertos_usa_query_in_unica(mock_db):
    """_contar_chamados_abertos deve fazer UMA query IN, não uma por supervisor."""
    from app.services.assignment import AtribuidorAutomatico

    sup_a = MagicMock()
    sup_a.nome = "Ana"
    sup_b = MagicMock()
    sup_b.nome = "Bruno"

    # Dois chamados abertos para Ana, um para Bruno, um concluído (não conta)
    def make_doc(responsavel, status):
        d = MagicMock()
        d.to_dict.return_value = {"responsavel": responsavel, "status": status}
        return d

    mock_stream = [
        make_doc("Ana", "Aberto"),
        make_doc("Ana", "Em Atendimento"),
        make_doc("Bruno", "Aberto"),
        make_doc("Ana", "Concluído"),  # não deve contar
    ]

    # Mock chainable: .where().limit().stream()
    mock_col = MagicMock()
    mock_col.where.return_value = mock_col
    mock_col.limit.return_value = mock_col
    mock_col.stream.return_value = iter(mock_stream)
    mock_db.collection.return_value = mock_col

    atrib = AtribuidorAutomatico()
    result = atrib._contar_chamados_abertos([sup_a, sup_b])

    # Deve ter chamado .where(filter=FieldFilter('responsavel', 'in', ...)) apenas uma vez
    from google.cloud.firestore_v1.base_query import FieldFilter

    assert mock_col.where.call_count == 1
    ff = mock_col.where.call_args.kwargs.get("filter")
    assert isinstance(ff, FieldFilter)
    assert ff.field_path == "responsavel"
    assert ff.op_string == "in"
    assert set(ff.value) == {"Ana", "Bruno"}

    # Contagens corretas
    por_nome = {r["usuario"].nome: r["chamados_abertos"] for r in result}
    assert por_nome["Ana"] == 2
    assert por_nome["Bruno"] == 1


@patch("app.services.assignment.db")
def test_contar_chamados_abertos_aplica_limite_maximo(mock_db):
    """_contar_chamados_abertos deve chamar .limit(MAX_CHAMADOS_ATRIB) para evitar scan ilimitado."""
    from app.services.assignment import MAX_CHAMADOS_ATRIB, AtribuidorAutomatico

    sup = MagicMock()
    sup.nome = "Ana"

    mock_col = MagicMock()
    mock_col.where.return_value = mock_col
    mock_col.limit.return_value = mock_col
    mock_col.stream.return_value = iter([])
    mock_db.collection.return_value = mock_col

    atrib = AtribuidorAutomatico()
    atrib._contar_chamados_abertos([sup])

    mock_col.limit.assert_called_once_with(MAX_CHAMADOS_ATRIB)


@patch("app.services.assignment.db")
def test_contar_chamados_abertos_exclui_cancelado(mock_db):
    """_contar_chamados_abertos deve excluir chamados Cancelado (além de Concluído) da contagem."""
    from app.services.assignment import AtribuidorAutomatico

    sup = MagicMock()
    sup.nome = "Carlos"

    def make_doc(responsavel, status):
        d = MagicMock()
        d.to_dict.return_value = {"responsavel": responsavel, "status": status}
        return d

    mock_stream = [
        make_doc("Carlos", "Aberto"),
        make_doc("Carlos", "Cancelado"),  # não deve contar
        make_doc("Carlos", "Concluído"),  # não deve contar
        make_doc("Carlos", "Em Atendimento"),
    ]

    mock_col = MagicMock()
    mock_col.where.return_value = mock_col
    mock_col.limit.return_value = mock_col
    mock_col.stream.return_value = iter(mock_stream)
    mock_db.collection.return_value = mock_col

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


@patch("app.services.assignment.db")
def test_contar_chamados_abertos_excecao_nao_propaga(mock_db):
    """Exceção no Firestore não derruba a contagem — retorna zeros."""
    from app.services.assignment import AtribuidorAutomatico

    sup = MagicMock()
    sup.nome = "Erro"
    mock_db.collection.return_value.where.return_value.stream.side_effect = Exception("timeout")

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


@patch("app.services.assignment.db")
@patch("app.services.assignment.Usuario.get_supervisores_por_area")
def test_atribuir_sucesso_com_balanceamento(mock_get_sup, mock_db):
    """atribuir() com supervisores disponíveis retorna sucesso=True."""
    from app.services.assignment import AtribuidorAutomatico

    sup = MagicMock()
    sup.id = "sup_1"
    sup.nome = "Ana"
    sup.email = "ana@test.com"
    sup.area = "TI"
    mock_get_sup.return_value = [sup]
    mock_col = MagicMock()
    mock_col.where.return_value = mock_col
    mock_col.limit.return_value = mock_col
    mock_col.stream.return_value = iter([])
    mock_db.collection.return_value = mock_col

    atrib = AtribuidorAutomatico(estrategia="balanceamento_carga")
    r = atrib.atribuir(area="TI", categoria="Suporte")
    assert r["sucesso"] is True
    assert r["supervisor"]["nome"] == "Ana"


@patch("app.services.assignment.Usuario.get_supervisores_por_area")
def test_atribuir_excecao_retorna_falha(mock_get_sup):
    """Exceção interna em atribuir() retorna sucesso=False sem explodir."""
    from app.services.assignment import AtribuidorAutomatico

    mock_get_sup.side_effect = Exception("Firestore error")
    atrib = AtribuidorAutomatico()
    r = atrib.atribuir(area="TI")
    assert r["sucesso"] is False
    assert "Error assigning" in r["motivo"]


# ── obter_disponibilidade ─────────────────────────────────────────────────────


@patch("app.services.assignment.db")
@patch("app.services.assignment.Usuario.get_supervisores_por_area")
def test_obter_disponibilidade_retorna_estrutura(mock_get_sup, mock_db):
    """obter_disponibilidade retorna dict com area, supervisores e carga."""
    from app.services.assignment import AtribuidorAutomatico

    sup = MagicMock()
    sup.id = "s1"
    sup.nome = "Ana"
    sup.email = "ana@test.com"
    mock_get_sup.return_value = [sup]
    mock_col = MagicMock()
    mock_col.where.return_value = mock_col
    mock_col.limit.return_value = mock_col
    mock_col.stream.return_value = iter([])
    mock_db.collection.return_value = mock_col

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

    mock_get_sup.side_effect = Exception("Firestore error")
    atrib = AtribuidorAutomatico()
    d = atrib.obter_disponibilidade("TI")
    assert d["total_supervisores"] == 0
    assert d["supervisores"] == []


# ── strategy branches via atribuir() ─────────────────────────────────────────


@patch("app.services.assignment.db")
@patch("app.services.assignment.Usuario.get_supervisores_por_area")
def test_atribuir_round_robin_via_atribuir_sucesso(mock_get_sup, mock_db):
    """atribuir() com estrategia=round_robin retorna sucesso=True."""
    from app.services.assignment import AtribuidorAutomatico

    sup = MagicMock()
    sup.id = "sup_rr"
    sup.nome = "Ana RR"
    sup.email = "ana_rr@test.com"
    sup.area = "TI"
    mock_get_sup.return_value = [sup]
    mock_col = MagicMock()
    mock_col.where.return_value = mock_col
    mock_col.limit.return_value = mock_col
    mock_col.stream.return_value = iter([])
    mock_db.collection.return_value = mock_col

    atrib = AtribuidorAutomatico(estrategia="round_robin")
    r = atrib.atribuir(area="TI", categoria="Suporte")
    assert r["sucesso"] is True
    assert r["supervisor"]["nome"] == "Ana RR"


@patch("app.services.assignment.db")
@patch("app.services.assignment.Usuario.get_supervisores_por_area")
def test_atribuir_aleatorio_via_atribuir_sucesso(mock_get_sup, mock_db):
    """atribuir() com estrategia=aleatorio retorna sucesso=True."""
    from app.services.assignment import AtribuidorAutomatico

    sup = MagicMock()
    sup.id = "sup_al"
    sup.nome = "Bruno Aleatório"
    sup.email = "bruno@test.com"
    sup.area = "TI"
    mock_get_sup.return_value = [sup]
    mock_col = MagicMock()
    mock_col.where.return_value = mock_col
    mock_col.limit.return_value = mock_col
    mock_col.stream.return_value = iter([])
    mock_db.collection.return_value = mock_col

    atrib = AtribuidorAutomatico(estrategia="aleatorio")
    r = atrib.atribuir(area="TI", categoria="Suporte")
    assert r["sucesso"] is True


@patch("app.services.assignment.db")
@patch("app.services.assignment.Usuario.get_supervisores_por_area")
def test_atribuir_retorna_falha_quando_escolhido_none(mock_get_sup, mock_db):
    """atribuir() retorna sucesso=False quando _atribuir_balanceamento devolve None."""
    from app.services.assignment import AtribuidorAutomatico

    sup = MagicMock()
    sup.nome = "Ana"
    mock_get_sup.return_value = [sup]
    mock_col = MagicMock()
    mock_col.where.return_value = mock_col
    mock_col.limit.return_value = mock_col
    mock_col.stream.return_value = iter([])
    mock_db.collection.return_value = mock_col

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


@patch("app.services.assignment.db")
@patch("app.services.assignment.Usuario.get_supervisores_por_area")
def test_atribuir_aleatorio_usa_random_choice(mock_get_sup, mock_db):
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
    mock_col = MagicMock()
    mock_col.where.return_value = mock_col
    mock_col.limit.return_value = mock_col
    mock_col.stream.return_value = iter([])
    mock_db.collection.return_value = mock_col

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
