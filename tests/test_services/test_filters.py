"""Testes do serviço de filtros e paginação do dashboard (Fase 2 — Postgres real).

Persistência via Chamado.salvar() (db_session); filtros e paginação por keyset
exercitados contra o banco de teste de verdade, não mais mock de query Firestore.
"""

import pytest

from app.models import Chamado
from app.services.filters import (
    _construir_condicoes_filtro,
    aplicar_filtros_dashboard,
    aplicar_filtros_dashboard_com_paginacao,
    construir_condicoes_para_contagem,
)

pytestmark = pytest.mark.usefixtures("db_session")


def _criar_chamado(
    solicitante_id: str,
    *,
    status: str = "Aberto",
    categoria: str = "Manutencao",
    gate: str | None = None,
    responsavel: str = "Responsável Teste",
    rl_codigo: str | None = None,
    descricao: str = "Descrição de teste",
    numero_chamado: str | None = None,
) -> Chamado:
    chamado = Chamado(
        categoria=categoria,
        tipo_solicitacao="Manutencao",
        descricao=descricao,
        responsavel=responsavel,
        responsavel_id="resp1",
        solicitante_id=solicitante_id,
        solicitante_nome="Solicitante Teste",
        status=status,
        prioridade=1,
        gate=gate,
        rl_codigo=rl_codigo,
        numero_chamado=numero_chamado,
    )
    chamado_id = chamado.salvar()
    assert chamado_id is not None
    return Chamado.get_by_id(chamado_id)


# ── _construir_condicoes_filtro ─────────────────────────────────────────────


def test_construir_condicoes_filtro_sem_filtros_retorna_lista_vazia():
    condicoes, status, gate, categoria = _construir_condicoes_filtro({})
    assert condicoes == []
    assert status is None
    assert gate is None
    assert categoria is None


def test_construir_condicoes_filtro_com_status_aplica_condicao():
    _criar_chamado("user_status_a", status="Aberto")
    _criar_chamado("user_status_a", status="Concluído")

    condicoes, status, _, _ = _construir_condicoes_filtro({"status": "Aberto"})
    assert status == "Aberto"
    resultado = aplicar_filtros_dashboard_com_paginacao(condicoes, {"status": "Aberto"}, limite=50)
    assert all(c.status == "Aberto" for c in resultado["docs"])
    assert any(c.solicitante_id == "user_status_a" for c in resultado["docs"])


def test_construir_condicoes_filtro_ignora_status_todos():
    condicoes_todos, _, _, _ = _construir_condicoes_filtro({"status": "Todos"})
    condicoes_vazio, _, _, _ = _construir_condicoes_filtro({"status": ""})
    assert condicoes_todos == []
    assert condicoes_vazio == []


def test_construir_condicoes_filtro_com_gate_aplica_condicao():
    condicoes, _, gate, _ = _construir_condicoes_filtro({"gate": "G1"})
    assert gate == "G1"
    assert len(condicoes) == 1


def test_construir_condicoes_filtro_com_responsavel_aplica_condicao():
    condicoes, _, _, _ = _construir_condicoes_filtro({"responsavel": "Ana"})
    assert len(condicoes) == 1


def test_construir_condicoes_filtro_com_rl_codigo_aplica_condicao():
    condicoes, _, _, _ = _construir_condicoes_filtro({"rl_codigo": "RL-001"})
    assert len(condicoes) == 1


def test_construir_condicoes_filtro_com_categoria_aplica_condicao():
    condicoes, _, _, categoria = _construir_condicoes_filtro({"categoria": "Projetos"})
    assert categoria == "Projetos"
    assert len(condicoes) == 1


def test_construir_condicoes_filtro_ignora_categoria_todas():
    for args in [{"categoria": "Todas"}, {"categoria": ""}]:
        condicoes, _, _, _ = _construir_condicoes_filtro(args)
        assert condicoes == []


def test_construir_condicoes_para_contagem_retorna_mesmas_condicoes():
    condicoes_contagem = construir_condicoes_para_contagem({"status": "Aberto"})
    condicoes_base, _, _, _ = _construir_condicoes_filtro({"status": "Aberto"})
    assert len(condicoes_contagem) == len(condicoes_base) == 1


# ── busca em memória (search) ───────────────────────────────────────────────


def test_busca_por_texto_filtra_por_descricao():
    _criar_chamado("user_busca_1", descricao="Falha no equipamento")
    _criar_chamado("user_busca_1", descricao="Outro tema qualquer")

    resultado = aplicar_filtros_dashboard_com_paginacao([], {"search": "equipamento"}, limite=50)

    assert len(resultado["docs"]) == 1
    assert "equipamento" in resultado["docs"][0].descricao.lower()


def test_busca_por_texto_case_insensitive():
    _criar_chamado("user_busca_2", descricao="Falha no Equipamento")

    resultado = aplicar_filtros_dashboard_com_paginacao([], {"search": "EQUIPAMENTO"}, limite=50)

    assert len(resultado["docs"]) == 1


def test_busca_por_texto_considera_rl_codigo_responsavel_numero_chamado():
    _criar_chamado("user_busca_3", rl_codigo="RL-XYZ", descricao="nada a ver")
    _criar_chamado("user_busca_3", responsavel="Fulano Especial", descricao="nada a ver")

    resultado_rl = aplicar_filtros_dashboard_com_paginacao([], {"search": "RL-XYZ"}, limite=50)
    resultado_resp = aplicar_filtros_dashboard_com_paginacao([], {"search": "Especial"}, limite=50)

    assert len(resultado_rl["docs"]) == 1
    assert len(resultado_resp["docs"]) == 1


def test_sem_search_nao_filtra_em_memoria():
    _criar_chamado("user_busca_4")
    _criar_chamado("user_busca_4")

    resultado = aplicar_filtros_dashboard_com_paginacao(
        [], {"solicitante_id": "user_busca_4"}, limite=50
    )
    # sem search, nada é descartado em memória (filtro por solicitante não existe
    # em _construir_condicoes_filtro — só valida que search=None não quebra nada)
    assert isinstance(resultado["docs"], list)


# ── aplicar_filtros_dashboard_com_paginacao — estrutura e paginação ────────


def test_paginacao_retorna_estrutura_esperada():
    resultado = aplicar_filtros_dashboard_com_paginacao([], {}, limite=50, cursor=None)
    assert "docs" in resultado
    assert "proximo_cursor" in resultado
    assert "tem_proxima" in resultado
    assert "cursor_anterior" in resultado
    assert "tem_anterior" in resultado


def test_paginacao_sem_chamados_retorna_vazio():
    resultado = aplicar_filtros_dashboard_com_paginacao(
        [], {"rl_codigo": "RL-INEXISTENTE"}, limite=50, cursor=None
    )
    assert resultado["docs"] == []
    assert resultado["tem_proxima"] is False
    assert resultado["proximo_cursor"] is None


def test_paginacao_tem_proxima_quando_excede_limite():
    for _ in range(3):
        _criar_chamado("user_pag_1", rl_codigo="RL-PAG-1")

    resultado = aplicar_filtros_dashboard_com_paginacao(
        [], {"rl_codigo": "RL-PAG-1"}, limite=2, cursor=None
    )

    assert len(resultado["docs"]) == 2
    assert resultado["tem_proxima"] is True
    assert resultado["proximo_cursor"] is not None


def test_paginacao_cursor_avanca_para_proxima_pagina():
    criados = [_criar_chamado("user_pag_2", rl_codigo="RL-PAG-2") for _ in range(3)]
    assert len(criados) == 3

    pagina1 = aplicar_filtros_dashboard_com_paginacao(
        [], {"rl_codigo": "RL-PAG-2"}, limite=2, cursor=None
    )
    pagina2 = aplicar_filtros_dashboard_com_paginacao(
        [], {"rl_codigo": "RL-PAG-2"}, limite=2, cursor=pagina1["proximo_cursor"]
    )

    ids_pagina1 = {c.id for c in pagina1["docs"]}
    ids_pagina2 = {c.id for c in pagina2["docs"]}
    assert ids_pagina1.isdisjoint(ids_pagina2)
    assert len(pagina2["docs"]) == 1
    assert pagina2["tem_proxima"] is False


def test_paginacao_cursor_anterior_volta_para_pagina_anterior():
    criados = [_criar_chamado("user_pag_3", rl_codigo="RL-PAG-3") for _ in range(3)]
    assert len(criados) == 3

    pagina1 = aplicar_filtros_dashboard_com_paginacao(
        [], {"rl_codigo": "RL-PAG-3"}, limite=2, cursor=None
    )
    pagina2 = aplicar_filtros_dashboard_com_paginacao(
        [], {"rl_codigo": "RL-PAG-3"}, limite=2, cursor=pagina1["proximo_cursor"]
    )
    volta = aplicar_filtros_dashboard_com_paginacao(
        [],
        {"rl_codigo": "RL-PAG-3"},
        limite=2,
        cursor_anterior=pagina2["cursor_anterior"],
    )

    ids_pagina1 = [c.id for c in pagina1["docs"]]
    ids_volta = [c.id for c in volta["docs"]]
    assert ids_volta == ids_pagina1


def test_paginacao_respeita_condicoes_base():
    _criar_chamado("user_pag_scope_a", rl_codigo="RL-SCOPE")
    _criar_chamado("user_pag_scope_b", rl_codigo="RL-SCOPE")

    from app.db.models.chamado import ChamadoRow

    condicoes_base = [ChamadoRow.solicitante_id == "user_pag_scope_a"]
    resultado = aplicar_filtros_dashboard_com_paginacao(
        condicoes_base, {"rl_codigo": "RL-SCOPE"}, limite=50
    )

    assert len(resultado["docs"]) == 1
    assert resultado["docs"][0].solicitante_id == "user_pag_scope_a"


# ── aplicar_filtros_dashboard (legado, sem cursor) ──────────────────────────


def test_aplicar_filtros_dashboard_retorna_lista():
    docs = aplicar_filtros_dashboard([], {"rl_codigo": "RL-INEXISTENTE-2"})
    assert isinstance(docs, list)
    assert docs == []


def test_aplicar_filtros_dashboard_aplica_filtros():
    _criar_chamado("user_legado", status="Aberto", rl_codigo="RL-LEGADO")
    _criar_chamado("user_legado", status="Concluído", rl_codigo="RL-LEGADO")

    docs = aplicar_filtros_dashboard([], {"rl_codigo": "RL-LEGADO", "status": "Aberto"})

    assert len(docs) == 1
    assert docs[0].status == "Aberto"
