"""
Testes do serviço de listagem de chamados (Fase 2 — Postgres real).

Persistência via Chamado.salvar() (db_session); listagem exercitada contra o
banco de teste de verdade, não mais mock de query Firestore. O antigo
fallback de índice ausente (_eh_erro_indice_firestore/listar_meus_chamados_
fallback) não existe mais — Postgres não tem esse modo de falha.
"""

from unittest.mock import patch

import pytest

from app.models import Chamado
from app.services.chamados_listagem_service import (
    contar_status_por_solicitante,
    listar_chamados_como_observador,
    listar_meus_chamados,
)

pytestmark = pytest.mark.usefixtures("db_session")


def _criar_chamado(
    solicitante_id: str,
    *,
    status: str = "Aberto",
    prioridade: int | None = 1,
    categoria: str = "Manutencao",
    rl_codigo: str | None = None,
    observadores: list | None = None,
) -> int:
    chamado = Chamado(
        categoria=categoria,
        tipo_solicitacao="Manutencao",
        descricao="Descrição de teste",
        responsavel="Responsável Teste",
        responsavel_id="resp1",
        solicitante_id=solicitante_id,
        solicitante_nome="Solicitante Teste",
        status=status,
        prioridade=prioridade,
        rl_codigo=rl_codigo,
        observadores=observadores,
    )
    chamado_id = chamado.salvar()
    assert chamado_id is not None
    return chamado_id


# ── listar_meus_chamados ───────────────────────────────────────────────────────


def test_listar_meus_chamados_sem_chamados_retorna_vazio():
    result = listar_meus_chamados("user_sem_chamados")

    assert result["chamados"] == []
    assert result["total_chamados"] == 0
    assert result["cursor_next"] is None
    assert result["cursor_prev"] is None


def test_listar_meus_chamados_retorna_chamados_do_solicitante():
    _criar_chamado("user_listagem_1")
    _criar_chamado("user_listagem_1")
    _criar_chamado("outro_usuario")

    result = listar_meus_chamados("user_listagem_1")

    assert result["total_chamados"] == 2
    assert len(result["chamados"]) == 2
    assert all(c.solicitante_id == "user_listagem_1" for c in result["chamados"])


def test_listar_meus_chamados_filtra_por_status():
    _criar_chamado("user_listagem_status", status="Aberto")
    _criar_chamado("user_listagem_status", status="Concluído")

    result = listar_meus_chamados("user_listagem_status", status_filtro="Concluído")

    assert result["total_chamados"] == 1
    assert result["chamados"][0].status == "Concluído"


def test_listar_meus_chamados_filtra_por_rl_codigo():
    _criar_chamado("user_listagem_rl", rl_codigo="RL-100")
    _criar_chamado("user_listagem_rl", rl_codigo="RL-200")

    result = listar_meus_chamados("user_listagem_rl", rl_codigo="RL-100")

    assert result["total_chamados"] == 1
    assert result["chamados"][0].rl_codigo == "RL-100"


def test_listar_meus_chamados_status_counts_corretos():
    _criar_chamado("user_listagem_counts", status="Aberto")
    _criar_chamado("user_listagem_counts", status="Aberto")
    _criar_chamado("user_listagem_counts", status="Concluído")

    result = listar_meus_chamados("user_listagem_counts")

    assert result["status_counts"]["Aberto"] == 2
    assert result["status_counts"]["Concluído"] == 1
    assert result["status_counts"]["Em Atendimento"] == 0
    assert result["status_counts"]["Cancelado"] == 0


def test_listar_meus_chamados_paginacao_com_cursor_percorre_tudo_sem_repetir():
    """Cria 25 chamados, pagina de 10 em 10 via cursor_next e confere: sem
    repetição, sem pular nenhum, total bate com o esperado."""
    ids_criados = {_criar_chamado("user_listagem_paginacao") for _ in range(25)}

    vistos: set[int] = set()
    cursor = ""
    paginas = 0
    while True:
        result = listar_meus_chamados("user_listagem_paginacao", cursor=cursor, itens_por_pagina=10)
        assert result["total_chamados"] == 25
        for c in result["chamados"]:
            assert c.id not in vistos, f"chamado {c.id} repetido entre páginas"
            vistos.add(c.id)
        paginas += 1
        if not result["cursor_next"]:
            break
        cursor = result["cursor_next"]
        assert paginas <= 10, "paginação não terminou — possível loop infinito"

    assert vistos == ids_criados
    assert paginas == 3


def test_listar_meus_chamados_cursor_next_presente_quando_ha_mais_paginas():
    for _ in range(11):
        _criar_chamado("user_listagem_cursor_next")

    result = listar_meus_chamados("user_listagem_cursor_next", itens_por_pagina=10)

    assert len(result["chamados"]) == 10
    assert result["cursor_next"] is not None


def test_listar_meus_chamados_sem_cursor_cursor_prev_e_none():
    _criar_chamado("user_listagem_sem_cursor")

    result = listar_meus_chamados("user_listagem_sem_cursor")

    assert result["cursor_prev"] is None


def test_listar_meus_chamados_com_cursor_cursor_prev_e_id_do_primeiro_da_pagina():
    ids = [_criar_chamado("user_listagem_cursor_prev") for _ in range(3)]

    pagina1 = listar_meus_chamados("user_listagem_cursor_prev", itens_por_pagina=1)
    pagina2 = listar_meus_chamados(
        "user_listagem_cursor_prev", cursor=pagina1["cursor_next"], itens_por_pagina=1
    )

    assert pagina2["cursor_prev"] == str(pagina2["chamados"][0].id)
    assert pagina2["chamados"][0].id in ids


def test_listar_meus_chamados_cursor_invalido_cai_no_limite_simples():
    _criar_chamado("user_listagem_cursor_invalido")

    result = listar_meus_chamados("user_listagem_cursor_invalido", cursor="nao-e-um-id")

    assert result["total_chamados"] == 1
    assert len(result["chamados"]) == 1


def test_listar_meus_chamados_cursor_de_outro_chamado_inexistente():
    """Cursor com id numérico mas que não existe no banco não deve quebrar,
    apenas cair no limite simples (comportamento equivalente ao doc inexistente
    do Firestore original)."""
    _criar_chamado("user_listagem_cursor_ghost")

    result = listar_meus_chamados("user_listagem_cursor_ghost", cursor="999999999")

    assert result["total_chamados"] == 1


def test_listar_meus_chamados_grupo_key_ordena_aog_antes_de_projetos():
    _criar_chamado("user_listagem_grupo", categoria="AOG", rl_codigo="RL-AOG")
    _criar_chamado("user_listagem_grupo", categoria="Projetos", rl_codigo="RL-PROJ")
    _criar_chamado("user_listagem_grupo", categoria="Manutencao")

    result = listar_meus_chamados("user_listagem_grupo")

    grupo_keys = {c.rl_codigo or "": c.grupo_key for c in result["chamados"]}
    assert grupo_keys["RL-AOG"] == "-1|RL-AOG"
    assert grupo_keys["RL-PROJ"] == "0|RL-PROJ"
    assert grupo_keys[""] == "1|"


def test_listar_meus_chamados_usa_cache_de_status_counts():
    """Com cache quente, status_counts vem do cache e não recalcula via aggregation."""
    _criar_chamado("user_listagem_cache_hit")

    cached = {"Aberto": 7, "Em Atendimento": 1, "Concluído": 2, "Cancelado": 0}
    with patch("app.cache.cache_get", return_value=cached):
        result = listar_meus_chamados("user_listagem_cache_hit")

    assert result["status_counts"] == cached
    assert result["total_chamados"] == sum(cached.values())


def test_listar_meus_chamados_cache_get_falha_recalcula():
    """Exceção em cache_get não propaga — recalcula status_counts do zero."""
    _criar_chamado("user_listagem_cache_falha")

    with patch("app.cache.cache_get", side_effect=Exception("cache indisponível")):
        result = listar_meus_chamados("user_listagem_cache_falha")

    assert result["total_chamados"] == 1


def test_listar_meus_chamados_cache_set_falha_nao_propaga():
    """Exceção em cache_set é silenciada, não quebra a listagem."""
    _criar_chamado("user_listagem_cache_set_falha")

    with (
        patch("app.cache.cache_get", return_value=None),
        patch("app.cache.cache_set", side_effect=Exception("cache indisponível")),
    ):
        result = listar_meus_chamados("user_listagem_cache_set_falha")

    assert result["total_chamados"] == 1


# ── listar_chamados_como_observador ───────────────────────────────────────────


def test_listar_chamados_como_observador_retorna_chamado_com_flag():
    obs = [{"usuario_id": "obs_listagem_1", "nome": "Obs Um", "email": "obs1@test.com"}]
    _criar_chamado("solicitante_x", observadores=obs)

    resultado = listar_chamados_como_observador("obs_listagem_1")

    assert len(resultado) == 1
    assert resultado[0].em_copia is True
    assert resultado[0].observadores[0]["usuario_id"] == "obs_listagem_1"


def test_listar_chamados_como_observador_nao_retorna_chamado_de_outro_observador():
    obs = [{"usuario_id": "obs_listagem_dono", "nome": "Dono", "email": "dono@test.com"}]
    _criar_chamado("solicitante_y", observadores=obs)

    resultado = listar_chamados_como_observador("obs_listagem_estranho")

    assert resultado == []


def test_listar_chamados_como_observador_sem_observadores_retorna_vazio():
    _criar_chamado("solicitante_z")

    resultado = listar_chamados_como_observador("qualquer_um")

    assert resultado == []


# ── contar_status_por_solicitante ─────────────────────────────────────────────


def test_contar_status_por_solicitante():
    _criar_chamado("user_contagem", status="Aberto")
    _criar_chamado("user_contagem", status="Aberto")
    _criar_chamado("user_contagem", status="Em Atendimento")

    resultado = contar_status_por_solicitante("user_contagem")

    assert resultado["Aberto"] == 2
    assert resultado["Em Atendimento"] == 1
    assert resultado["Concluído"] == 0
    assert resultado["Cancelado"] == 0


def test_contar_status_por_solicitante_sem_chamados():
    resultado = contar_status_por_solicitante("user_sem_nenhum_chamado")

    assert resultado == {"Aberto": 0, "Em Atendimento": 0, "Concluído": 0, "Cancelado": 0}


def test_contar_status_por_solicitante_usa_uma_unica_query(db_session):
    """Achado BAIXO da auditoria 2026-08-06: contar_status_por_solicitante fazia
    4 SELECT COUNT(*) em loop (um por status) — deveria ser 1 único GROUP BY."""
    from sqlalchemy import event

    _criar_chamado("user_group_by", status="Aberto")
    _criar_chamado("user_group_by", status="Aberto")
    _criar_chamado("user_group_by", status="Em Atendimento")

    statements = []
    connection = db_session.get_bind()

    def _capturar(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(connection, "before_cursor_execute", _capturar)
    try:
        resultado = contar_status_por_solicitante("user_group_by")
    finally:
        event.remove(connection, "before_cursor_execute", _capturar)

    selects_chamados = [s for s in statements if "FROM chamados" in s]
    assert len(selects_chamados) == 1, (
        f"esperava 1 única query (GROUP BY), achou {len(selects_chamados)}: {selects_chamados}"
    )
    assert resultado["Aberto"] == 2
    assert resultado["Em Atendimento"] == 1
