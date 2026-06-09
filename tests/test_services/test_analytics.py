"""Testes do serviço de analytics/relatórios."""

from unittest.mock import MagicMock, patch


def test_obter_metricas_gerais_retorna_dict_com_chaves_esperadas():
    """obter_metricas_gerais retorna dict com periodo_dias, total_chamados, etc."""
    from app.services.analytics import AnalisadorChamados

    mock_where = MagicMock()
    mock_where.stream.return_value = []  # lista vazia = nenhum chamado
    mock_collection = MagicMock()
    mock_collection.where.return_value = mock_where
    mock_db = MagicMock()
    mock_db.collection.return_value = mock_collection
    with patch.object(AnalisadorChamados, "get_db", return_value=mock_db):
        a = AnalisadorChamados()
        r = a.obter_metricas_gerais(dias=30)
    assert isinstance(r, dict)
    assert "periodo_dias" in r
    assert "total_chamados" in r
    assert "abertos" in r
    assert "concluidos" in r
    assert "taxa_resolucao_percentual" in r
    assert "resumo_sla" in r
    assert "distribuicao_categoria" in r
    assert r["periodo_dias"] == 30
    assert set(r["resumo_sla"].keys()) == {"no_prazo", "atrasado", "em_risco"}


def test_obter_relatorio_completo_retorna_dict_com_secoes():
    """obter_relatorio_completo retorna dict com metricas_gerais, insights, metricas_delta, etc."""
    from app.services.analytics import AnalisadorChamados

    mock_db = MagicMock()
    mock_col = MagicMock()
    mock_col.limit.return_value = mock_col
    mock_col.stream.return_value = iter([])
    mock_db.collection.return_value = mock_col

    with (
        patch.object(AnalisadorChamados, "get_db", return_value=mock_db),
        patch.object(AnalisadorChamados, "obter_metricas_gerais", return_value={}),
        patch.object(AnalisadorChamados, "obter_metricas_periodo_anterior", return_value={}),
        patch.object(AnalisadorChamados, "obter_metricas_supervisores", return_value=[]),
        patch.object(AnalisadorChamados, "obter_metricas_areas", return_value=[]),
        patch.object(AnalisadorChamados, "obter_insights", return_value=[]),
    ):
        a = AnalisadorChamados()
        r = a.obter_relatorio_completo(usar_cache=False)
    assert "metricas_gerais" in r
    assert "metricas_delta" in r
    assert "metricas_supervisores" in r
    assert "metricas_areas" in r
    assert "insights" in r
    assert "data_geracao" in r


def test_calcular_deltas_retorna_valores_corretos():
    """_calcular_deltas calcula diferenças entre período atual e anterior."""
    from app.services.analytics import AnalisadorChamados

    atual = {
        "total_chamados": 50,
        "taxa_resolucao_percentual": 75.0,
        "percentual_dentro_sla": 80.0,
        "tempo_medio_resolucao_horas": 12.0,
    }
    anterior = {
        "total_chamados": 40,
        "taxa_resolucao_percentual": 70.0,
        "percentual_dentro_sla": None,
        "tempo_medio_resolucao_horas": 15.0,
    }
    deltas = AnalisadorChamados._calcular_deltas(atual, anterior)
    assert deltas["total_chamados_delta"] == 10
    assert deltas["taxa_resolucao_percentual_delta"] == 5.0
    assert deltas["percentual_dentro_sla_delta"] is None
    assert deltas["tempo_medio_resolucao_horas_delta"] == -3.0


# ── Testes N+1 elimination ────────────────────────────────────────────────────


def test_obter_metricas_supervisores_usa_dados_pre_carregados_sem_query():
    """Com chamados_pre_carregados, obter_metricas_supervisores não deve chamar .stream()."""
    from unittest.mock import MagicMock, patch

    from app.services.analytics import AnalisadorChamados

    sup_mock = MagicMock()
    sup_mock.id = "sup1"
    sup_mock.nome = "Ana"
    sup_mock.email = "ana@dtx.aero"
    sup_mock.perfil = "supervisor"
    sup_mock.area = "TI"

    chamados = [
        {
            "responsavel_id": "sup1",
            "status": "Concluído",
            "data_abertura": None,
            "data_conclusao": None,
            "categoria": "TI",
        },
        {
            "responsavel_id": "sup1",
            "status": "Aberto",
            "data_abertura": None,
            "data_conclusao": None,
            "categoria": "TI",
        },
    ]

    mock_db = MagicMock()
    with (
        patch.object(AnalisadorChamados, "get_db", return_value=mock_db),
        patch("app.models_usuario.Usuario") as mock_usuario,
    ):
        mock_usuario.get_all.return_value = [sup_mock]
        a = AnalisadorChamados()
        resultado = a.obter_metricas_supervisores(chamados_pre_carregados=chamados)

    # Nenhuma query de chamados deve ter sido feita
    mock_db.collection.assert_not_called()
    assert len(resultado) == 1
    assert resultado[0]["supervisor_id"] == "sup1"
    assert resultado[0]["total_chamados"] == 2
    assert resultado[0]["concluidos"] == 1
    assert resultado[0]["abertos"] == 1


def test_obter_metricas_areas_usa_dados_pre_carregados_sem_query_chamados():
    """Com chamados_pre_carregados, obter_metricas_areas faz apenas 1 query (usuarios)."""
    from unittest.mock import MagicMock, patch

    from app.services.analytics import AnalisadorChamados

    # Simular resultado de .stream() para usuários
    doc_sup = MagicMock()
    doc_sup.id = "sup1"
    doc_sup.to_dict.return_value = {
        "perfil": "supervisor",
        "areas": ["TI"],
        "email": "ana@dtx.aero",
    }

    mock_stream = MagicMock(return_value=iter([doc_sup]))
    mock_collection = MagicMock()
    mock_collection.stream = mock_stream
    mock_db = MagicMock()
    mock_db.collection.return_value = mock_collection

    chamados = [
        {
            "area": "TI",
            "status": "Concluído",
            "data_abertura": None,
            "data_conclusao": None,
            "motivo_atribuicao": "",
        },
        {
            "area": "TI",
            "status": "Aberto",
            "data_abertura": None,
            "data_conclusao": None,
            "motivo_atribuicao": "Atribuído automaticamente",
        },
    ]

    with patch.object(AnalisadorChamados, "get_db", return_value=mock_db):
        a = AnalisadorChamados()
        resultado = a.obter_metricas_areas(chamados_pre_carregados=chamados)

    # Deve ter chamado .collection() apenas para "usuarios" (não para "chamados")
    calls_collection = [str(c) for c in mock_db.collection.call_args_list]
    assert any("usuarios" in c for c in calls_collection), "Esperava query de usuarios"
    assert not any("chamados" in c for c in calls_collection), "Não devia ter query de chamados"

    assert len(resultado) == 1
    assert resultado[0]["area"] == "TI"
    assert resultado[0]["total_chamados"] == 2
    assert resultado[0]["atribuidos_automaticamente"] == 1


def test_obter_relatorio_completo_faz_unica_query_chamados_para_metricas(app):
    """obter_relatorio_completo deve reusar chamados entre supervisores e áreas (N+1 eliminado)."""
    from unittest.mock import MagicMock, patch

    from app.services.analytics import AnalisadorChamados

    # Contagem de chamadas a .collection("chamados")
    chamados_queries = []

    def _mock_collection(name):
        if name == "chamados":
            chamados_queries.append(name)
        mock_col = MagicMock()
        mock_col.where.return_value = mock_col
        mock_col.limit.return_value = mock_col
        mock_col.stream.return_value = iter([])
        return mock_col

    mock_db = MagicMock()
    mock_db.collection.side_effect = _mock_collection

    with (
        app.app_context(),
        patch.object(AnalisadorChamados, "get_db", return_value=mock_db),
        patch("app.models_usuario.Usuario") as mock_usuario,
        patch("app.cache.cache_get", return_value=None),
        patch("app.cache.cache_set"),
    ):
        mock_usuario.get_all.return_value = []
        a = AnalisadorChamados()
        a.obter_relatorio_completo(usar_cache=False)

    # O número de chamadas a collection("chamados") deve ser pequeno e fixo,
    # não crescer com o número de supervisores ou áreas.
    assert len(chamados_queries) <= 4, (
        f"N+1 detectado: {len(chamados_queries)} queries a 'chamados' "
        "(esperado <= 4 independente do número de supervisores/áreas)"
    )
