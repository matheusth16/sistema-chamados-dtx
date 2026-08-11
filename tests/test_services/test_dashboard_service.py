"""Testes do serviço de dashboard (obter_contexto_admin, _filtrar_chamados_por_permissao)."""

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.usefixtures("db_session")


def test_itens_por_pagina_dashboard_reduzido_para_economizar_leituras():
    """ITENS_POR_PAGINA_DASHBOARD deve ser <= 25 — reduz leituras por visita
    ao dashboard (cada item de página = 1 leitura)."""
    from config import Config

    assert Config.ITENS_POR_PAGINA_DASHBOARD <= 25


def test_usuario_get_by_ids_retorna_dict_vazio_para_lista_vazia(app):
    """get_by_ids com lista vazia retorna {} sem consultar o banco."""
    from app.models_usuario import Usuario

    result = Usuario.get_by_ids([])
    assert result == {}


def test_usuario_get_by_ids_retorna_apenas_encontrados(app):
    """get_by_ids retorna dict {id: Usuario} só com os IDs que existem."""
    from app.models_usuario import Usuario

    with patch("app.models_usuario.is_pii_encryption_enabled", return_value=False):
        Usuario(
            id="user_abc",
            email="a@dtx.aero",
            nome="Alpha",
            perfil="supervisor",
            areas=["Manutencao"],
        ).save()

    result = Usuario.get_by_ids(["user_abc", "user_xyz_nao_existe"])

    assert "user_abc" in result
    assert "user_xyz_nao_existe" not in result
    assert result["user_abc"].email == "a@dtx.aero"


def test_obter_contexto_admin_retorna_dict_com_chaves_esperadas():
    """obter_contexto_admin retorna dicionário com chamados, gates, responsaveis, sla_map, paginação."""
    from app.services.dashboard_service import obter_contexto_admin

    user = MagicMock()
    user.perfil = "admin"
    user.areas = ["Geral"]
    user.id = "admin1"

    with patch("app.services.dashboard_service.get_static_cached") as mock_cache:
        mock_cache.return_value = []
        with patch(
            "app.services.dashboard_service.aplicar_filtros_dashboard_com_paginacao"
        ) as mock_filtros:
            mock_filtros.return_value = {
                "docs": [],
                "proximo_cursor": None,
                "tem_proxima": False,
                "cursor_anterior": None,
                "tem_anterior": False,
            }
            with patch("app.services.dashboard_service.obter_sla_para_exibicao", return_value=None):
                ctx = obter_contexto_admin(user, {}, itens_por_pagina=25)

    assert "chamados" in ctx
    assert "lista_responsaveis" in ctx
    assert "lista_gates" in ctx
    assert "proximo_cursor" in ctx
    assert "tem_proxima" in ctx
    assert "tem_anterior" in ctx
    assert isinstance(ctx["chamados"], list)
    assert isinstance(ctx["lista_responsaveis"], list)
    assert isinstance(ctx["lista_gates"], list)


def test_filtrar_chamados_por_permissao_admin_retorna_todos():
    """_filtrar_chamados_por_permissao com usuário admin retorna todos os chamados convertidos."""
    from app.models import Chamado
    from app.services.dashboard_service import _filtrar_chamados_por_permissao

    user = MagicMock()
    user.perfil = "admin"

    doc1 = MagicMock()
    doc1.id = "d1"
    doc1.to_dict.return_value = {
        "categoria": "Manutencao",
        "tipo_solicitacao": "Corretiva",
        "descricao": "D1",
        "responsavel": "",
        "numero_chamado": "001",
        "area": "Manutencao",
    }
    doc2 = MagicMock()
    doc2.id = "d2"
    doc2.to_dict.return_value = {
        "categoria": "Manutencao",
        "tipo_solicitacao": "Preventiva",
        "descricao": "D2",
        "responsavel": "",
        "numero_chamado": "002",
        "area": "Manutencao",
    }
    docs = [doc1, doc2]

    result = _filtrar_chamados_por_permissao(docs, user)
    assert len(result) == 2
    assert all(isinstance(c, Chamado) for c in result)
    assert result[0].numero_chamado == "001"
    assert result[1].numero_chamado == "002"


def test_filtrar_chamados_por_permissao_supervisor_filtra_por_area():
    """_filtrar_chamados_por_permissao com supervisor usa usuario_pode_ver_chamado_otimizado."""
    from app.services.dashboard_service import _filtrar_chamados_por_permissao

    user = MagicMock()
    user.perfil = "supervisor"
    user.areas = ["Manutencao"]
    user.is_admin_or_above = False

    doc1 = MagicMock()
    doc1.id = "d1"
    doc1.to_dict.return_value = {
        "categoria": "Manutencao",
        "tipo_solicitacao": "Corretiva",
        "descricao": "D1",
        "responsavel": "",
        "numero_chamado": "001",
        "area": "Manutencao",
        "responsavel_id": None,
    }
    docs = [doc1]

    with (
        patch("app.services.dashboard_service.Usuario.get_by_ids", return_value={}),
        patch("app.services.dashboard_service.usuario_pode_ver_chamado_otimizado") as mock_perm,
    ):
        mock_perm.return_value = True
        result = _filtrar_chamados_por_permissao(docs, user)
    assert len(result) == 1
    mock_perm.assert_called()


def test_ordenar_metricas_supervisores_por_sla_null_vai_ao_final():
    """campo='sla': None vai ao final; valores maiores ficam primeiro (asc=False)."""
    from app.services.dashboard_service import ordenar_metricas_supervisores

    lista = [
        {"supervisor_nome": "A", "percentual_dentro_sla": None},
        {"supervisor_nome": "B", "percentual_dentro_sla": 95.0},
        {"supervisor_nome": "C", "percentual_dentro_sla": 80.0},
    ]
    result = ordenar_metricas_supervisores(lista, "sla", asc=False)
    assert result[0]["percentual_dentro_sla"] == 95.0
    assert result[1]["percentual_dentro_sla"] == 80.0
    assert result[2]["percentual_dentro_sla"] is None


def test_ordenar_metricas_supervisores_por_sla_asc():
    """campo='sla', asc=True: None vai ao final, menores primeiro."""
    from app.services.dashboard_service import ordenar_metricas_supervisores

    lista = [
        {"supervisor_nome": "A", "percentual_dentro_sla": 95.0},
        {"supervisor_nome": "B", "percentual_dentro_sla": None},
        {"supervisor_nome": "C", "percentual_dentro_sla": 80.0},
    ]
    result = ordenar_metricas_supervisores(lista, "sla", asc=True)
    assert result[-1]["percentual_dentro_sla"] is None


def test_ordenar_metricas_areas_por_total_desc():
    """ordenar_metricas_areas com campo='total' e asc=False: maior primeiro."""
    from app.services.dashboard_service import ordenar_metricas_areas

    lista = [
        {"area": "B", "total_chamados": 5},
        {"area": "A", "total_chamados": 10},
        {"area": "C", "total_chamados": 1},
    ]
    result = ordenar_metricas_areas(lista, "total", asc=False)
    assert result[0]["total_chamados"] == 10
    assert result[-1]["total_chamados"] == 1


def test_ordenar_metricas_areas_campo_desconhecido_retorna_original():
    """ordenar_metricas_areas com campo não mapeado retorna lista sem alteração."""
    from app.services.dashboard_service import ordenar_metricas_areas

    lista = [{"area": "X"}, {"area": "Y"}]
    result = ordenar_metricas_areas(lista, "campo_invalido", asc=True)
    assert result == lista


def test_preparar_metricas_paginadas_retorna_pagina_e_total_corretos():
    """preparar_metricas_paginadas retorna items, total, total_paginas e pagina corretos."""
    from app.services.dashboard_service import (
        ordenar_metricas_supervisores,
        preparar_metricas_paginadas,
    )

    items = [{"supervisor_nome": str(i), "total_chamados": i} for i in range(10)]
    result = preparar_metricas_paginadas(
        items,
        "total",
        False,
        pagina=1,
        itens_por_pagina=5,
        ordenar_fn=ordenar_metricas_supervisores,
    )
    assert result["total"] == 10
    assert result["total_paginas"] == 2
    assert len(result["items"]) == 5
    assert result["pagina"] == 1


def test_preparar_metricas_paginadas_clampeia_pagina_fora_do_intervalo():
    """preparar_metricas_paginadas clampeia pagina > total_paginas para total_paginas."""
    from app.services.dashboard_service import (
        ordenar_metricas_supervisores,
        preparar_metricas_paginadas,
    )

    items = [{"supervisor_nome": "X", "total_chamados": 1}]
    result = preparar_metricas_paginadas(
        items,
        "total",
        True,
        pagina=99,
        itens_por_pagina=10,
        ordenar_fn=ordenar_metricas_supervisores,
    )
    assert result["pagina"] == 1


def test_obter_contexto_admin_projetos_no_topo_e_grupo_key_definido(db_session):
    """Chamados Projetos ficam no topo e recebem grupo_key iniciando com '0|'."""
    from app.services.dashboard_service import obter_contexto_admin
    from tests.factories import make_chamado

    user = MagicMock()
    user.perfil = "admin"
    user.areas = ["Geral"]
    user.id = "admin1"
    user.is_admin_or_above = True

    docs = [
        make_chamado(categoria="Manutencao", numero_chamado="00003", status="Aberto"),
        make_chamado(
            categoria="Projetos", numero_chamado="00001", rl_codigo="RL-001", status="Aberto"
        ),
    ]

    with (
        patch("app.services.dashboard_service.get_static_cached", return_value=[]),
        patch("app.services.dashboard_service.filtrar_supervisores_por_area", return_value=[]),
        patch(
            "app.services.dashboard_service.aplicar_filtros_dashboard_com_paginacao"
        ) as mock_filtros,
        patch("app.services.dashboard_service.obter_sla_para_exibicao", return_value=None),
    ):
        mock_filtros.return_value = {
            "docs": docs,
            "proximo_cursor": None,
            "tem_proxima": False,
            "cursor_anterior": None,
            "tem_anterior": False,
        }
        ctx = obter_contexto_admin(user, {}, itens_por_pagina=25)

    chamados = ctx["chamados"]
    assert len(chamados) == 2
    assert chamados[0].categoria == "Projetos", "Projetos deve aparecer primeiro"
    for c in chamados:
        assert hasattr(c, "grupo_key"), "grupo_key deve ser definido em todos os chamados"
    projetos_c = next(c for c in chamados if c.categoria == "Projetos")
    assert projetos_c.grupo_key.startswith("0|")


def test_obter_contexto_admin_aog_acima_de_projetos(db_session):
    """AOG fica acima de Projetos, que fica acima do resto; grupo_key de AOG começa com '-1|'."""
    from app.services.dashboard_service import obter_contexto_admin
    from tests.factories import make_chamado

    user = MagicMock()
    user.perfil = "admin"
    user.areas = ["Geral"]
    user.id = "admin1"
    user.is_admin_or_above = True

    docs = [
        make_chamado(categoria="Manutencao", numero_chamado="00003", status="Aberto"),
        make_chamado(
            categoria="Projetos", numero_chamado="00001", rl_codigo="RL-001", status="Aberto"
        ),
        make_chamado(categoria="AOG", numero_chamado="00002", rl_codigo="AOG-001", status="Aberto"),
    ]

    with (
        patch("app.services.dashboard_service.get_static_cached", return_value=[]),
        patch("app.services.dashboard_service.filtrar_supervisores_por_area", return_value=[]),
        patch(
            "app.services.dashboard_service.aplicar_filtros_dashboard_com_paginacao"
        ) as mock_filtros,
        patch("app.services.dashboard_service.obter_sla_para_exibicao", return_value=None),
    ):
        mock_filtros.return_value = {
            "docs": docs,
            "proximo_cursor": None,
            "tem_proxima": False,
            "cursor_anterior": None,
            "tem_anterior": False,
        }
        ctx = obter_contexto_admin(user, {}, itens_por_pagina=25)

    chamados = ctx["chamados"]
    assert chamados[0].categoria == "AOG", "AOG deve aparecer primeiro, acima de Projetos"
    assert chamados[1].categoria == "Projetos", "Projetos deve aparecer logo após AOG"
    aog_c = next(c for c in chamados if c.categoria == "AOG")
    assert aog_c.grupo_key.startswith("-1|")


def test_obter_contexto_admin_supervisor_aplica_filtro_por_areas():
    """obter_contexto_admin com perfil supervisor passa condição de escopo por área
    (supervisor_ids_com_acesso) em condicoes_base pra aplicar_filtros_dashboard_com_paginacao."""
    from app.services.dashboard_service import obter_contexto_admin

    user = MagicMock()
    user.perfil = "supervisor"
    user.areas = ["Manutencao"]
    user.id = "sup1"
    user.is_admin_or_above = False

    with (
        patch("app.services.dashboard_service.get_static_cached", return_value=[]),
        patch("app.services.dashboard_service.filtrar_supervisores_por_area", return_value=[]),
        patch(
            "app.services.dashboard_service.aplicar_filtros_dashboard_com_paginacao"
        ) as mock_filtros,
        patch("app.services.dashboard_service.obter_sla_para_exibicao", return_value=None),
    ):
        mock_filtros.return_value = {
            "docs": [],
            "proximo_cursor": None,
            "tem_proxima": False,
            "cursor_anterior": None,
            "tem_anterior": False,
        }
        obter_contexto_admin(user, {}, itens_por_pagina=25)

    condicoes_base_passada = mock_filtros.call_args[0][0]
    assert len(condicoes_base_passada) == 1, (
        "supervisor com áreas deve passar 1 condição de escopo em condicoes_base"
    )


def test_obter_contexto_admin_meus_pendentes_filtra_por_responsavel_e_status():
    """?meus_pendentes=1 adiciona condições responsavel_id==user.id e
    status IN (Aberto, Em Atendimento) em condicoes_base — usado pelo link
    'Open system' do digest diário e do aviso prévio de escalonamento."""
    from app.services.dashboard_service import obter_contexto_admin

    user = MagicMock()
    user.perfil = "admin"
    user.areas = []
    user.id = "julia1"
    user.is_admin_or_above = True

    with (
        patch("app.services.dashboard_service.get_static_cached", return_value=[]),
        patch("app.services.dashboard_service.filtrar_supervisores_por_area", return_value=[]),
        patch(
            "app.services.dashboard_service.aplicar_filtros_dashboard_com_paginacao"
        ) as mock_filtros,
        patch("app.services.dashboard_service.obter_sla_para_exibicao", return_value=None),
    ):
        mock_filtros.return_value = {
            "docs": [],
            "proximo_cursor": None,
            "tem_proxima": False,
            "cursor_anterior": None,
            "tem_anterior": False,
        }
        obter_contexto_admin(user, {"meus_pendentes": "1"}, itens_por_pagina=25)

    condicoes_base_passada = mock_filtros.call_args[0][0]
    assert len(condicoes_base_passada) == 2


def test_obter_contexto_admin_meus_pendentes_ignora_outros_filtros_da_querystring():
    """Com meus_pendentes=1, filtros normais (status/categoria/etc.) da querystring
    são ignorados — não interferem na lista fixa de 'meus chamados pendentes'."""
    from app.services.dashboard_service import obter_contexto_admin

    user = MagicMock()
    user.perfil = "admin"
    user.areas = []
    user.id = "julia1"
    user.is_admin_or_above = True

    with (
        patch("app.services.dashboard_service.get_static_cached", return_value=[]),
        patch("app.services.dashboard_service.filtrar_supervisores_por_area", return_value=[]),
        patch(
            "app.services.dashboard_service.aplicar_filtros_dashboard_com_paginacao"
        ) as mock_filtros,
        patch("app.services.dashboard_service.obter_sla_para_exibicao", return_value=None),
    ):
        mock_filtros.return_value = {
            "docs": [],
            "proximo_cursor": None,
            "tem_proxima": False,
            "cursor_anterior": None,
            "tem_anterior": False,
        }
        obter_contexto_admin(
            user,
            {"meus_pendentes": "1", "status": "Concluído", "categoria": "Projetos"},
            itens_por_pagina=25,
        )

    args_passados = mock_filtros.call_args[0][1]
    assert "status" not in args_passados
    assert "categoria" not in args_passados


def test_obter_contexto_admin_meus_pendentes_ordena_por_prioridade_categoria(db_session):
    """Chamados de 'meus pendentes' seguem a mesma ordenação AOG > Projetos >
    demais já aplicada no dashboard normal (reaproveitada, não duplicada)."""
    from app.services.dashboard_service import obter_contexto_admin
    from tests.factories import make_chamado

    user = MagicMock()
    user.perfil = "admin"
    user.areas = []
    user.id = "julia1"
    user.is_admin_or_above = True

    docs = [
        make_chamado(
            categoria="Manutencao", numero_chamado="00003", status="Aberto", responsavel_id="julia1"
        ),
        make_chamado(
            categoria="AOG",
            numero_chamado="00002",
            rl_codigo="AOG-001",
            status="Aberto",
            responsavel_id="julia1",
        ),
    ]

    with (
        patch("app.services.dashboard_service.get_static_cached", return_value=[]),
        patch("app.services.dashboard_service.filtrar_supervisores_por_area", return_value=[]),
        patch(
            "app.services.dashboard_service.aplicar_filtros_dashboard_com_paginacao"
        ) as mock_filtros,
        patch("app.services.dashboard_service.obter_sla_para_exibicao", return_value=None),
    ):
        mock_filtros.return_value = {
            "docs": docs,
            "proximo_cursor": None,
            "tem_proxima": False,
            "cursor_anterior": None,
            "tem_anterior": False,
        }
        ctx = obter_contexto_admin(user, {"meus_pendentes": "1"}, itens_por_pagina=25)

    assert ctx["chamados"][0].categoria == "AOG"


def test_filtrar_chamados_usa_batch_fetch_nao_n_mais_1():
    """_filtrar_chamados_por_permissao usa get_by_ids (1 query) e não get_by_id em loop (N queries)."""
    from app.services.dashboard_service import _filtrar_chamados_por_permissao

    user = MagicMock()
    user.perfil = "supervisor"
    user.areas = ["Manutencao"]
    user.is_admin_or_above = False

    def _doc(num, resp_id):
        d = MagicMock()
        d.id = f"doc_{num}"
        d.to_dict.return_value = {
            "categoria": "Chamado",
            "tipo_solicitacao": "Corretiva",
            "descricao": f"D{num}",
            "responsavel": "",
            "numero_chamado": str(num),
            "area": "Manutencao",
            "responsavel_id": resp_id,
        }
        return d

    docs = [_doc(1, "user_a"), _doc(2, "user_b"), _doc(3, "user_a")]

    with (
        patch("app.services.dashboard_service.Usuario.get_by_ids") as mock_batch,
        patch(
            "app.services.dashboard_service.usuario_pode_ver_chamado_otimizado",
            return_value=True,
        ),
    ):
        mock_batch.return_value = {}
        _filtrar_chamados_por_permissao(docs, user)

    # get_by_ids deve ser chamado exatamente 1 vez com todos os IDs únicos
    mock_batch.assert_called_once()
    ids_passados = set(mock_batch.call_args[0][0])
    assert ids_passados == {"user_a", "user_b"}
