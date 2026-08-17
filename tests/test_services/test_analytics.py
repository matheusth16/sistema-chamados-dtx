"""Testes do serviço de analytics/relatórios.

Fase 2 (Marco 7): a busca de chamados agora passa por
AnalisadorChamados._buscar_chamados_dicts() (Postgres, via db_session) em vez
de self.get_db().collection("chamados")...stream() — get_db() foi removido.
Testes que já usavam chamados_pre_carregados (lista de dicts real) não
precisam mudar a lógica de negócio, só remover o mock de get_db, que ficou
morto (a função nunca chega a consultar o banco quando os dados já vêm
pré-carregados). Testes que exercitavam a query direta agora mockam
_buscar_chamados_dicts (retorna lista de dicts, não docs Firestore) ou usam o
banco de teste real (vazio por padrão) via fixture db_session.
"""

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.usefixtures("db_session")


def test_obter_metricas_gerais_retorna_dict_com_chaves_esperadas():
    """obter_metricas_gerais retorna dict com periodo_dias, total_chamados, etc."""
    from app.services.analytics import AnalisadorChamados

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

    with (
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


def test_calcular_deltas_inclui_concluidos_mas_nao_abertos_em_andamento():
    """concluidos_delta é calculado (comparação justa de throughput), mas
    abertos/em_andamento não geram delta — comparariam coortes de idades
    diferentes e sempre cairiam, mascarando o desempenho real."""
    from app.services.analytics import AnalisadorChamados

    atual = {"concluidos": 20, "abertos": 5, "em_andamento": 3}
    anterior = {"concluidos": 15, "abertos": 12, "em_andamento": 8}
    deltas = AnalisadorChamados._calcular_deltas(atual, anterior)
    assert deltas["concluidos_delta"] == 5
    assert "abertos_delta" not in deltas
    assert "em_andamento_delta" not in deltas


# ── Testes N+1 elimination ────────────────────────────────────────────────────


def test_obter_metricas_supervisores_usa_dados_pre_carregados_sem_query():
    """Com chamados_pre_carregados, obter_metricas_supervisores não deve consultar o banco."""
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

    with (
        patch.object(AnalisadorChamados, "_buscar_chamados_dicts") as mock_buscar,
        patch("app.models_usuario.Usuario") as mock_usuario,
    ):
        mock_usuario.get_all.return_value = [sup_mock]
        a = AnalisadorChamados()
        resultado = a.obter_metricas_supervisores(chamados_pre_carregados=chamados)

    # Nenhuma query de chamados deve ter sido feita
    mock_buscar.assert_not_called()
    assert len(resultado) == 1
    assert resultado[0]["supervisor_id"] == "sup1"
    assert resultado[0]["total_chamados"] == 2
    assert resultado[0]["concluidos"] == 1
    assert resultado[0]["abertos"] == 1


def test_obter_metricas_areas_usa_dados_pre_carregados_sem_query_chamados():
    """Com chamados_pre_carregados, obter_metricas_areas não deve consultar chamados (só Usuario.get_all)."""
    from app.services.analytics import AnalisadorChamados

    sup_mock = MagicMock()
    sup_mock.id = "sup1"
    sup_mock.perfil = "supervisor"
    sup_mock.areas = ["TI"]
    sup_mock.area = None

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

    with (
        patch.object(AnalisadorChamados, "_buscar_chamados_dicts") as mock_buscar,
        patch("app.models_usuario.Usuario.get_all", return_value=[sup_mock]),
    ):
        a = AnalisadorChamados()
        resultado = a.obter_metricas_areas(chamados_pre_carregados=chamados)

    mock_buscar.assert_not_called()
    assert len(resultado) == 1
    assert resultado[0]["area"] == "TI"
    assert resultado[0]["total_chamados"] == 2
    assert resultado[0]["atribuidos_automaticamente"] == 1


def test_obter_metricas_areas_inclui_area_sem_supervisor_cadastrado():
    """Regressão: chamado numa área sem nenhum supervisor era contado no total geral
    mas ficava invisível em 'Performance por Área' — areas_uniques só incluía áreas
    com supervisor cadastrado, então a área nunca aparecia na tabela de métricas."""
    from app.services.analytics import AnalisadorChamados

    chamados = [
        {
            "area": "TI",
            "status": "Aberto",
            "data_abertura": None,
            "data_conclusao": None,
            "motivo_atribuicao": "",
        }
    ]

    with patch("app.models_usuario.Usuario.get_all", return_value=[]):
        a = AnalisadorChamados()
        resultado = a.obter_metricas_areas(chamados_pre_carregados=chamados)

    assert len(resultado) == 1
    assert resultado[0]["area"] == "TI"
    assert resultado[0]["total_chamados"] == 1
    assert resultado[0]["supervisores_alocados"] == 0


def test_obter_metricas_gerais_usa_chamados_pre_carregados_sem_query():
    """Com chamados_pre_carregados, obter_metricas_gerais não deve consultar o banco."""
    from datetime import UTC, datetime, timedelta

    from app.services.analytics import AnalisadorChamados

    agora = datetime.now(UTC)
    chamados = [
        {
            "status": "Aberto",
            "data_abertura": agora - timedelta(days=5),
            "data_conclusao": None,
            "categoria": "TI",
            "prioridade": 1,
        },
        {
            "status": "Concluído",
            "data_abertura": agora - timedelta(days=10),
            "data_conclusao": agora - timedelta(days=8),
            "categoria": "TI",
            "prioridade": 1,
            "sla_dias": None,
        },
    ]
    with patch.object(AnalisadorChamados, "_buscar_chamados_dicts") as mock_buscar:
        a = AnalisadorChamados()
        r = a.obter_metricas_gerais(dias=30, chamados_pre_carregados=chamados)

    mock_buscar.assert_not_called()
    assert r["total_chamados"] == 2
    assert r["abertos"] == 1
    assert r["concluidos"] == 1


def test_obter_metricas_gerais_com_data_abertura_tz_aware_nao_retorna_vazio():
    """data_abertura tz-aware (UTC) comparado com datetime.now() naive (sem tz)
    causaria TypeError, engolido pelo except geral — obter_metricas_gerais
    retornaria {} e os gráficos ficariam vazios."""
    from datetime import UTC, datetime, timedelta

    from app.services.analytics import AnalisadorChamados

    agora_aware = datetime.now(UTC)
    chamados = [
        {
            "status": "Aberto",
            "data_abertura": agora_aware - timedelta(days=5),
            "data_conclusao": None,
            "categoria": "TI",
            "prioridade": 1,
        },
    ]
    a = AnalisadorChamados()
    r = a.obter_metricas_gerais(dias=30, chamados_pre_carregados=chamados)

    assert r != {}
    assert r["total_chamados"] == 1


def test_obter_metricas_periodo_anterior_com_data_abertura_tz_aware_nao_retorna_vazio():
    """Mesmo bug de datetime naive vs aware, agora em obter_metricas_periodo_anterior
    (usado para calcular os deltas/badges de tendência dos relatórios)."""
    from datetime import UTC, datetime, timedelta

    from app.services.analytics import AnalisadorChamados

    agora_aware = datetime.now(UTC)
    chamados = [
        {
            "status": "Concluído",
            "data_abertura": agora_aware - timedelta(days=45),
            "data_conclusao": agora_aware - timedelta(days=40),
            "categoria": "TI",
            "sla_dias": None,
        },
    ]
    a = AnalisadorChamados()
    r = a.obter_metricas_periodo_anterior(chamados_pre_carregados=chamados)

    assert r != {}
    assert r["total_chamados"] == 1


def test_obter_metricas_gerais_distribuicao_prioridade_chaves_sempre_str():
    """Chamados sem campo 'prioridade' (legado) caem no fallback str 'Indefinido',
    misturado com prioridades numericas (-1/0/1) quebra json.dumps(sort_keys=True)
    no template ('<' not supported between instances of 'str' and 'int') — as
    chaves do dict devem ser sempre do mesmo tipo (str) para serializar com
    segurança."""
    from datetime import UTC, datetime, timedelta

    from app.services.analytics import AnalisadorChamados

    agora = datetime.now(UTC)
    chamados = [
        {
            "status": "Aberto",
            "data_abertura": agora - timedelta(days=1),
            "categoria": "AOG",
            "prioridade": -1,
        },
        {
            "status": "Aberto",
            "data_abertura": agora - timedelta(days=1),
            "categoria": "TI",
            # sem "prioridade" — chamado legado, cai no fallback "Indefinido"
        },
    ]
    a = AnalisadorChamados()
    r = a.obter_metricas_gerais(dias=30, chamados_pre_carregados=chamados)

    dp = r["distribuicao_prioridade"]
    assert all(isinstance(k, str) for k in dp)
    import json

    json.dumps(dp, sort_keys=True)  # não deve levantar TypeError


def test_obter_metricas_periodo_anterior_usa_chamados_pre_carregados_sem_query():
    """Com chamados_pre_carregados, obter_metricas_periodo_anterior não deve consultar o banco."""
    from datetime import UTC, datetime, timedelta

    from app.services.analytics import AnalisadorChamados

    agora = datetime.now(UTC)
    chamados = [
        {
            "status": "Concluído",
            "data_abertura": agora - timedelta(days=45),
            "data_conclusao": agora - timedelta(days=40),
            "categoria": "TI",
            "sla_dias": None,
        },
        {
            "status": "Aberto",
            "data_abertura": agora - timedelta(days=5),
            "data_conclusao": None,
            "categoria": "TI",
            "sla_dias": None,
        },
    ]
    with patch.object(AnalisadorChamados, "_buscar_chamados_dicts") as mock_buscar:
        a = AnalisadorChamados()
        r = a.obter_metricas_periodo_anterior(chamados_pre_carregados=chamados)

    mock_buscar.assert_not_called()
    assert r["total_chamados"] == 1
    assert r["taxa_resolucao_percentual"] == 100.0


def test_obter_metricas_periodo_anterior_usa_janela_proporcional_ao_dias():
    """Com dias=7, período anterior deve ser 7-14 dias atrás (não fixo em 30-60).

    Chamado aberto há 10 dias cai dentro da janela 7-14 quando dias=7, mas
    ficaria fora da janela 30-60 usada quando dias=30 (o antigo hardcode).
    """
    from datetime import UTC, datetime, timedelta

    from app.services.analytics import AnalisadorChamados

    agora = datetime.now(UTC)
    chamados = [
        {
            "status": "Aberto",
            "data_abertura": agora - timedelta(days=10),
            "data_conclusao": None,
            "categoria": "TI",
        },
    ]
    a = AnalisadorChamados()
    r_7 = a.obter_metricas_periodo_anterior(chamados_pre_carregados=chamados, dias=7)
    r_30 = a.obter_metricas_periodo_anterior(chamados_pre_carregados=chamados, dias=30)

    assert r_7["total_chamados"] == 1
    assert r_30["total_chamados"] == 0


def test_obter_metricas_periodo_anterior_inclui_concluidos():
    """obter_metricas_periodo_anterior retorna 'concluidos' pro delta do card
    de concluídos (antes só tinha total_chamados/taxa/sla/tempo)."""
    from datetime import UTC, datetime, timedelta

    from app.services.analytics import AnalisadorChamados

    agora = datetime.now(UTC)
    chamados = [
        {
            "status": "Concluído",
            "data_abertura": agora - timedelta(days=40),
            "data_conclusao": agora - timedelta(days=35),
            "categoria": "TI",
            "sla_dias": None,
        },
        {
            "status": "Aberto",
            "data_abertura": agora - timedelta(days=45),
            "data_conclusao": None,
            "categoria": "TI",
        },
    ]
    a = AnalisadorChamados()
    r = a.obter_metricas_periodo_anterior(chamados_pre_carregados=chamados, dias=30)

    assert r["concluidos"] == 1


def test_obter_metricas_areas_filtra_por_perfil_supervisor():
    """obter_metricas_areas deve filtrar Usuario.get_all() por perfil==supervisor."""
    from app.services.analytics import AnalisadorChamados

    sup = MagicMock()
    sup.id = "sup1"
    sup.perfil = "supervisor"
    sup.areas = ["TI"]
    sup.area = None
    solicitante = MagicMock()
    solicitante.id = "sol1"
    solicitante.perfil = "solicitante"
    solicitante.areas = ["TI"]
    solicitante.area = None

    with patch("app.models_usuario.Usuario.get_all", return_value=[sup, solicitante]):
        a = AnalisadorChamados()
        resultado = a.obter_metricas_areas(chamados_pre_carregados=[])

    assert len(resultado) == 1
    assert resultado[0]["area"] == "TI"
    assert resultado[0]["supervisores_alocados"] == 1, (
        "Só o usuário com perfil=='supervisor' deve contar como supervisor alocado"
    )


def test_carregar_chamados_analytics_retorna_lista_e_usa_cache(app):
    """_carregar_chamados_analytics deve retornar lista de dicts e armazenar em cache."""
    from app.services.analytics import AnalisadorChamados

    with (
        app.app_context(),
        patch.object(
            AnalisadorChamados,
            "_buscar_chamados_dicts",
            return_value=[{"status": "Aberto", "area": "TI"}],
        ),
        patch("app.cache.cache_get", return_value=None),
        patch("app.cache.cache_set") as mock_cache_set,
    ):
        a = AnalisadorChamados()
        result = a._carregar_chamados_analytics()

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["status"] == "Aberto"
    mock_cache_set.assert_called_once()


def test_obter_relatorio_completo_faz_unica_query_chamados_para_metricas(app):
    """obter_relatorio_completo deve reusar chamados entre supervisores e áreas (N+1 eliminado)."""
    from app.services.analytics import AnalisadorChamados

    with (
        app.app_context(),
        patch.object(AnalisadorChamados, "_buscar_chamados_dicts", return_value=[]) as mock_buscar,
        patch("app.models_usuario.Usuario.get_all", return_value=[]),
        patch("app.cache.cache_get", return_value=None),
        patch("app.cache.cache_set"),
    ):
        a = AnalisadorChamados()
        a.obter_relatorio_completo(usar_cache=False)

    # A busca de chamados deve ser feita uma única vez (via
    # _carregar_chamados_analytics), reaproveitada entre supervisores e áreas —
    # não deve crescer com o número de supervisores/áreas.
    assert mock_buscar.call_count == 1, (
        f"N+1 detectado: _buscar_chamados_dicts chamado {mock_buscar.call_count}x "
        "(esperado exatamente 1x, reaproveitado entre todas as métricas)"
    )


# ── S1-02: datetime.utcnow() deprecation (F-04) ──────────────────────────────


def test_obter_sla_para_exibicao_nao_usa_utcnow_deprecated():
    """obter_sla_para_exibicao não deve emitir DeprecationWarning de datetime.utcnow().

    Python 3.12+ depreca datetime.utcnow(). Chamadas com data_abertura naive (sem tzinfo)
    atingem o else-branch que antes usava utcnow(). Agora deve usar datetime.now(UTC).
    """
    import warnings
    from datetime import datetime, timedelta

    from app.services.analytics import obter_sla_para_exibicao

    # data_abertura naive (sem tzinfo) — aciona o else-branch do código
    chamado = type(
        "C",
        (),
        {
            "data_abertura": datetime.now() - timedelta(days=1),
            "data_conclusao": None,
            "categoria": "TI",
            "status": "Aberto",
            "sla_dias": None,
        },
    )()

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        obter_sla_para_exibicao(chamado)

    utcnow_warnings = [
        w
        for w in captured
        if "utcnow" in str(w.message).lower() and issubclass(w.category, DeprecationWarning)
    ]
    assert not utcnow_warnings, (
        f"Não deve usar datetime.utcnow() (deprecated); aviso capturado: {utcnow_warnings}"
    )


# ── Onda 3: helpers privados ───────────────────────────────────────────────────


def test_sla_dias_custom_usa_valor_fornecido():
    """_sla_dias_por_categoria retorna sla_dias_custom quando válido (>0)."""
    from app.services.analytics import _sla_dias_por_categoria

    assert _sla_dias_por_categoria("TI", sla_dias_custom=5) == 5
    assert _sla_dias_por_categoria("Projetos", sla_dias_custom=7) == 7


def test_sla_dias_projetos_retorna_2():
    """_sla_dias_por_categoria retorna 2 para categoria Projetos sem custom."""
    from app.services.analytics import _sla_dias_por_categoria

    assert _sla_dias_por_categoria("Projetos") == 2
    assert _sla_dias_por_categoria("  Projetos  ") == 2


def test_sla_dias_padrao_retorna_3():
    """_sla_dias_por_categoria retorna 3 para qualquer outra categoria."""
    from app.services.analytics import _sla_dias_por_categoria

    assert _sla_dias_por_categoria("TI") == 3
    assert _sla_dias_por_categoria("") == 3
    assert _sla_dias_por_categoria("Manutencao") == 3


def test_sla_dias_padrao_acompanha_config_nao_fica_hardcoded():
    """Achado da auditoria 2026-08-06: analytics.py duplicava
    SLA_DIAS_PADRAO/SLA_DIAS_PROJETOS como constantes de módulo fixas, em vez
    de ler de config.Config (que já é configurável via env var e é a fonte de
    verdade usada por sla_escalacao_service.py). Isso podia divergir da
    escalação real sem ninguém perceber. Este teste prova que analytics.py
    agora reflete config.Config em vez de ter seu próprio valor hardcoded."""
    from unittest.mock import patch

    from app.services.analytics import _sla_dias_por_categoria

    with (
        patch("config.Config.SLA_DIAS_RESOLUCAO_PADRAO", 5),
        patch("config.Config.SLA_DIAS_RESOLUCAO_PROJETOS", 9),
    ):
        assert _sla_dias_por_categoria("TI") == 5
        assert _sla_dias_por_categoria("Projetos") == 9


def test_to_datetime_none_retorna_none():
    from app.services.analytics import _to_datetime

    assert _to_datetime(None) is None


def test_to_datetime_datetime_retorna_mesmo():
    from datetime import datetime

    from app.services.analytics import _to_datetime

    dt = datetime(2024, 6, 1, 12, 0)
    assert _to_datetime(dt) is dt


def test_to_datetime_firestore_timestamp_chama_to_pydatetime():
    from datetime import datetime

    from app.services.analytics import _to_datetime

    ts = MagicMock()
    expected = datetime(2024, 6, 1, 12, 0)
    ts.to_pydatetime.return_value = expected
    assert _to_datetime(ts) == expected


def test_to_datetime_tipo_desconhecido_retorna_none():
    from app.services.analytics import _to_datetime

    assert _to_datetime("2024-01-01") is None
    assert _to_datetime(12345) is None


def test_dentro_sla_true_quando_concluido_no_prazo():
    from datetime import datetime

    from app.services.analytics import _dentro_sla

    ab = datetime(2024, 1, 1)
    co = datetime(2024, 1, 2)  # 1 dia, SLA=3
    assert _dentro_sla(ab, co, "TI") is True


def test_dentro_sla_false_quando_fora_do_prazo():
    from datetime import datetime

    from app.services.analytics import _dentro_sla

    ab = datetime(2024, 1, 1)
    co = datetime(2024, 1, 10)  # 9 dias, SLA=3
    assert _dentro_sla(ab, co, "TI") is False


def test_dentro_sla_none_quando_sem_datas():
    from app.services.analytics import _dentro_sla

    assert _dentro_sla(None, None, "TI") is None
    assert _dentro_sla(None, "x", "TI") is None


def test_dentro_sla_com_custom_sla():
    from datetime import datetime

    from app.services.analytics import _dentro_sla

    ab = datetime(2024, 1, 1)
    co = datetime(2024, 1, 6)  # 5 dias, sla_dias_custom=7 -> dentro
    assert _dentro_sla(ab, co, "TI", sla_dias_custom=7) is True


# ── Onda 3: obter_sla_para_exibicao ───────────────────────────────────────────


def test_obter_sla_sem_data_abertura_retorna_none():
    from app.services.analytics import obter_sla_para_exibicao

    chamado = type(
        "C",
        (),
        {
            "data_abertura": None,
            "data_conclusao": None,
            "categoria": "TI",
            "status": "Aberto",
            "sla_dias": None,
        },
    )()
    assert obter_sla_para_exibicao(chamado) is None


def test_obter_sla_cancelado_retorna_none():
    from datetime import datetime, timedelta

    from app.services.analytics import obter_sla_para_exibicao

    chamado = type(
        "C",
        (),
        {
            "data_abertura": datetime.now() - timedelta(days=1),
            "data_conclusao": None,
            "categoria": "TI",
            "status": "Cancelado",
            "sla_dias": None,
        },
    )()
    assert obter_sla_para_exibicao(chamado) is None


def test_obter_sla_concluido_no_prazo_retorna_label():
    from datetime import datetime, timedelta

    from app.services.analytics import obter_sla_para_exibicao

    ab = datetime.now() - timedelta(days=10)
    co = ab + timedelta(hours=12)
    chamado = type(
        "C",
        (),
        {
            "data_abertura": ab,
            "data_conclusao": co,
            "categoria": "TI",
            "status": "Concluído",
            "sla_dias": None,
        },
    )()
    r = obter_sla_para_exibicao(chamado)
    assert r is not None
    assert r["label"] == "No prazo"
    assert r["dentro_prazo"] is True
    assert r["em_risco"] is False


def test_obter_sla_concluido_atrasado_retorna_label():
    from datetime import datetime, timedelta

    from app.services.analytics import obter_sla_para_exibicao

    ab = datetime.now() - timedelta(days=10)
    co = ab + timedelta(days=5)  # 5 dias, SLA=3
    chamado = type(
        "C",
        (),
        {
            "data_abertura": ab,
            "data_conclusao": co,
            "categoria": "TI",
            "status": "Concluído",
            "sla_dias": None,
        },
    )()
    r = obter_sla_para_exibicao(chamado)
    assert r is not None
    assert r["label"] == "Atrasado"
    assert r["dentro_prazo"] is False


def test_obter_sla_concluido_sem_data_conclusao_retorna_none():
    from datetime import datetime, timedelta

    from app.services.analytics import obter_sla_para_exibicao

    chamado = type(
        "C",
        (),
        {
            "data_abertura": datetime.now() - timedelta(days=10),
            "data_conclusao": None,
            "categoria": "TI",
            "status": "Concluído",
            "sla_dias": None,
        },
    )()
    assert obter_sla_para_exibicao(chamado) is None


def test_obter_sla_aberto_atrasado():
    from datetime import datetime, timedelta

    from app.services.analytics import obter_sla_para_exibicao

    chamado = type(
        "C",
        (),
        {
            "data_abertura": datetime.now() - timedelta(days=5),
            "data_conclusao": None,
            "categoria": "TI",
            "status": "Aberto",
            "sla_dias": None,
        },
    )()
    r = obter_sla_para_exibicao(chamado)
    assert r is not None
    assert r["label"] == "Atrasado"
    assert r["dentro_prazo"] is False


def test_obter_sla_aberto_em_risco():
    """Status 'Em risco' quando resta < 1 dia. Usa UTC-aware para evitar offsets de fuso."""
    from datetime import UTC, datetime, timedelta

    from app.services.analytics import obter_sla_para_exibicao

    chamado = type(
        "C",
        (),
        {
            "data_abertura": datetime.now(UTC) - timedelta(hours=71),  # 1h restante (SLA=3d)
            "data_conclusao": None,
            "categoria": "TI",
            "status": "Aberto",
            "sla_dias": None,
        },
    )()
    r = obter_sla_para_exibicao(chamado)
    assert r is not None
    assert r["label"] == "Em risco"
    assert r["em_risco"] is True
    assert r["dentro_prazo"] is None


def test_obter_sla_aberto_no_prazo():
    from datetime import datetime, timedelta

    from app.services.analytics import obter_sla_para_exibicao

    chamado = type(
        "C",
        (),
        {
            "data_abertura": datetime.now() - timedelta(hours=12),
            "data_conclusao": None,
            "categoria": "TI",
            "status": "Aberto",
            "sla_dias": None,
        },
    )()
    r = obter_sla_para_exibicao(chamado)
    assert r is not None
    assert r["label"] == "No prazo"
    assert r["dentro_prazo"] is True


def test_obter_sla_tz_aware_abertura():
    """Com data_abertura tz-aware o branch usa datetime.now(UTC)."""
    from datetime import UTC, datetime, timedelta

    from app.services.analytics import obter_sla_para_exibicao

    chamado = type(
        "C",
        (),
        {
            "data_abertura": datetime.now(UTC) - timedelta(days=5),
            "data_conclusao": None,
            "categoria": "TI",
            "status": "Aberto",
            "sla_dias": None,
        },
    )()
    r = obter_sla_para_exibicao(chamado)
    assert r is not None
    assert r["label"] == "Atrasado"


# ── Previsão de atendimento aprovada alarga o prazo (não só silencia e-mail) ───


def test_obter_sla_aberto_atrasado_com_previsao_futura_vira_no_prazo():
    """TAT original já venceu, mas o gestor aprovou previsão pra daqui a 5 dias
    — o chamado deixa de contar como atrasado até essa nova data passar."""
    from datetime import datetime, timedelta

    from app.services.analytics import obter_sla_para_exibicao

    chamado = type(
        "C",
        (),
        {
            "data_abertura": datetime.now() - timedelta(days=5),  # SLA=3d, já venceu
            "data_conclusao": None,
            "categoria": "TI",
            "status": "Aberto",
            "sla_dias": None,
            "previsao_atendimento": datetime.now() + timedelta(days=5),
        },
    )()
    r = obter_sla_para_exibicao(chamado)
    assert r is not None
    assert r["label"] == "No prazo"
    assert r["dentro_prazo"] is True


def test_obter_sla_previsao_ja_passada_nao_protege_mais():
    """Previsão aprovada que já venceu não protege mais — volta a valer o
    prazo original (agora ambos vencidos, continua atrasado)."""
    from datetime import datetime, timedelta

    from app.services.analytics import obter_sla_para_exibicao

    chamado = type(
        "C",
        (),
        {
            "data_abertura": datetime.now() - timedelta(days=10),
            "data_conclusao": None,
            "categoria": "TI",
            "status": "Aberto",
            "sla_dias": None,
            "previsao_atendimento": datetime.now() - timedelta(days=1),
        },
    )()
    r = obter_sla_para_exibicao(chamado)
    assert r is not None
    assert r["label"] == "Atrasado"


def test_obter_sla_concluido_apos_tat_mas_dentro_da_previsao_aprovada():
    """Resolvido depois do TAT original, mas antes da previsão aprovada —
    conta como 'No prazo', não 'Atrasado' (a previsão virou o prazo oficial)."""
    from datetime import datetime, timedelta

    from app.services.analytics import obter_sla_para_exibicao

    ab = datetime.now() - timedelta(days=10)
    previsao = ab + timedelta(days=8)  # bem depois do SLA padrão (3d)
    co = ab + timedelta(days=7)  # depois do TAT original, antes da previsão
    chamado = type(
        "C",
        (),
        {
            "data_abertura": ab,
            "data_conclusao": co,
            "categoria": "TI",
            "status": "Concluído",
            "sla_dias": None,
            "previsao_atendimento": previsao,
        },
    )()
    r = obter_sla_para_exibicao(chamado)
    assert r is not None
    assert r["label"] == "No prazo"
    assert r["dentro_prazo"] is True


def test_obter_sla_em_atendimento_previsao_futura_ignora_percentual_estourado():
    """Em Atendimento com >80% do prazo de resolução consumido normalmente
    seria 'Atrasado'/'Em risco', mas uma previsão aprovada ainda futura vence."""
    from datetime import datetime, timedelta

    from app.services.analytics import obter_sla_para_exibicao

    chamado = type(
        "C",
        (),
        {
            "data_abertura": datetime.now() - timedelta(days=5),
            "data_conclusao": None,
            "categoria": "TI",
            "status": "Em Atendimento",
            "data_em_atendimento": datetime.now() - timedelta(days=4),  # bem estourado
            "sla_dias": None,
            "previsao_atendimento": datetime.now() + timedelta(days=3),
        },
    )()
    r = obter_sla_para_exibicao(chamado)
    assert r is not None
    assert r["label"] == "No prazo"


def test_obter_sla_em_atendimento_previsao_ja_passada_nao_protege_mais():
    """Bug real (auditoria 2026-08-13): a checagem de previsão em 'Em
    Atendimento' comparava `now` contra o `limite` alargado (que nunca
    encurta abaixo do TAT original) em vez de contra a própria data da
    previsão — então, uma vez aprovada, o chamado ficava 'No prazo' pelo
    resto da vida útil mesmo com a previsão já vencida havia muito tempo,
    enquanto o TAT original (3 dias) ainda não tivesse estourado. Depois que
    a previsão aprovada vence, ela deve deixar de proteger e o cálculo
    normal (percentual de tempo útil) volta a valer — mesmo comportamento já
    coberto para o status 'Aberto' em test_obter_sla_previsao_ja_passada_nao_protege_mais.

    Datas fixas (não datetime.now()) — bug real de flakiness achado em CI
    2026-08-14: com datetime.now() relativo, "4 dias atrás" podia cair do
    outro lado de um fim de semana dependendo de QUANDO o teste roda,
    derrubando o percentual de tempo útil decorrido pra menos de 100% e
    fazendo o teste falhar por sorte de calendário, não por bug de código.
    data_em_atendimento 2 semanas antes de agora garante >3 dias úteis
    decorridos (SLA padrão) não importa o dia da semana.

    `agora` precisa ser aware no fuso de negócio (mesmo fuso que
    _previsao_atendimento_instante já assume pra datas naive) — misturar
    agora UTC-aware com previsao_atendimento naive (interpretada como BRT)
    desalinha os dois por ~3h e pode inverter passado/futuro."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.services.analytics import obter_sla_para_exibicao
    from config import Config

    agora = datetime(2024, 6, 10, 11, 0, tzinfo=ZoneInfo(Config.SLA_TIMEZONE))  # segunda-feira
    chamado = type(
        "C",
        (),
        {
            "data_abertura": datetime(2024, 6, 9, 11, 0),  # TAT=3d, ainda longe
            "data_conclusao": None,
            "categoria": "TI",
            "status": "Em Atendimento",
            "data_em_atendimento": datetime(2024, 5, 27, 9, 0),  # 2 semanas atrás, bem estourado
            "sla_dias": None,
            "previsao_atendimento": datetime(2024, 6, 10, 9, 0),  # já venceu (2h antes de agora)
        },
    )()
    r = obter_sla_para_exibicao(chamado, agora=agora)
    assert r is not None
    assert r["label"] != "No prazo"


def test_metricas_gerais_nao_conta_atrasado_com_previsao_aprovada_futura():
    """AnalisadorChamados.obter_metricas_gerais (resumo_sla agregado do
    dashboard) também não deve contar um chamado como atrasado enquanto a
    previsão aprovada não vencer — mesma regra do badge individual."""
    from datetime import UTC, datetime, timedelta

    from app.services.analytics import AnalisadorChamados

    ab = datetime.now(UTC) - timedelta(days=5)
    chamados = [
        {
            "status": "Aberto",
            "data_abertura": ab,
            "categoria": "TI",
            "sla_dias": None,
            "previsao_atendimento": datetime.now(UTC) + timedelta(days=5),
            "prioridade": 1,
        }
    ]

    a = AnalisadorChamados()
    r = a.obter_metricas_gerais(dias=30, chamados_pre_carregados=chamados)

    assert r["resumo_sla"]["atrasado"] == 0
    assert r["resumo_sla"]["em_risco"] == 0


# ── Onda 3: cache hits ─────────────────────────────────────────────────────────


def test_obter_metricas_gerais_retorna_cache_quando_disponivel(app):
    """obter_metricas_gerais retorna cached quando cache_get devolve dados."""
    from app.services.analytics import AnalisadorChamados

    cached_data = {"periodo_dias": 30, "total_chamados": 99}
    with (
        app.app_context(),
        patch("app.cache.cache_get", return_value=cached_data),
    ):
        a = AnalisadorChamados()
        r = a.obter_metricas_gerais(dias=30)
    assert r == cached_data


def test_obter_metricas_gerais_salva_em_cache_sem_pre_carregados(app):
    """obter_metricas_gerais sem pre_carregados faz query ao banco e salva cache."""
    from app.services.analytics import AnalisadorChamados

    with (
        app.app_context(),
        patch.object(AnalisadorChamados, "_buscar_chamados_dicts", return_value=[]),
        patch("app.cache.cache_get", return_value=None),
        patch("app.cache.cache_set") as mock_set,
    ):
        a = AnalisadorChamados()
        r = a.obter_metricas_gerais()

    assert isinstance(r, dict)
    mock_set.assert_called_once()


def test_obter_metricas_gerais_exception_retorna_dict_vazio(app):
    """obter_metricas_gerais retorna {} quando ocorre exceção (cache miss + db falha)."""
    from app.services.analytics import AnalisadorChamados

    with (
        app.app_context(),
        patch.object(
            AnalisadorChamados, "_buscar_chamados_dicts", side_effect=Exception("timeout")
        ),
        patch("app.cache.cache_get", return_value=None),
    ):
        a = AnalisadorChamados()
        r = a.obter_metricas_gerais()

    assert r == {}


# ── Onda 3: obter_metricas_gerais com SLA e em_risco via pre_carregados ────────


def test_obter_metricas_gerais_calcula_sla_e_em_risco():
    """obter_metricas_gerais calcula concluidos_dentro_sla e em_risco corretamente."""
    from datetime import UTC, datetime, timedelta

    from app.services.analytics import AnalisadorChamados

    agora = datetime.now(UTC)
    chamados = [
        {  # Concluído dentro do SLA (1 dia, SLA=3)
            "status": "Concluído",
            "data_abertura": agora - timedelta(days=10),
            "data_conclusao": agora - timedelta(days=9),
            "categoria": "TI",
            "prioridade": 1,
            "sla_dias": None,
        },
        {  # Concluído fora do SLA (5 dias, SLA=3)
            "status": "Concluído",
            "data_abertura": agora - timedelta(days=20),
            "data_conclusao": agora - timedelta(days=15),
            "categoria": "TI",
            "prioridade": 1,
            "sla_dias": None,
        },
        {  # Aberto atrasado
            "status": "Aberto",
            "data_abertura": agora - timedelta(days=5),
            "data_conclusao": None,
            "categoria": "TI",
            "prioridade": 2,
            "sla_dias": None,
        },
    ]
    a = AnalisadorChamados()
    r = a.obter_metricas_gerais(dias=30, chamados_pre_carregados=chamados)

    assert r["concluidos_dentro_sla"] == 1
    assert r["concluidos_fora_sla"] == 1
    assert r["resumo_sla"]["atrasado"] >= 1


# ── Onda 3: obter_metricas_supervisores SLA path ──────────────────────────────


def test_obter_metricas_supervisores_calcula_sla_e_tempo():
    """obter_metricas_supervisores calcula tempo médio e SLA com chamados concretos."""
    from datetime import datetime, timedelta

    from app.services.analytics import AnalisadorChamados

    agora = datetime.now()
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
            "data_abertura": agora - timedelta(hours=24),
            "data_conclusao": agora - timedelta(hours=12),
            "categoria": "TI",
            "sla_dias": None,
        },
        {
            "responsavel_id": "sup1",
            "status": "Concluído",
            "data_abertura": agora - timedelta(days=10),
            "data_conclusao": agora - timedelta(days=6),  # fora SLA
            "categoria": "TI",
            "sla_dias": None,
        },
    ]

    with patch("app.models_usuario.Usuario") as mock_usuario:
        mock_usuario.get_all.return_value = [sup_mock]
        a = AnalisadorChamados()
        resultado = a.obter_metricas_supervisores(chamados_pre_carregados=chamados)

    assert len(resultado) == 1
    r = resultado[0]
    assert r["concluidos"] == 2
    assert r["tempo_medio_resolucao_horas"] > 0
    assert r["percentual_dentro_sla"] is not None


def test_obter_metricas_supervisores_query_sem_pre_carregados():
    """obter_metricas_supervisores faz query ao banco quando chamados_pre_carregados=None."""
    from app.services.analytics import AnalisadorChamados

    with (
        patch.object(AnalisadorChamados, "_buscar_chamados_dicts", return_value=[]) as mock_buscar,
        patch("app.models_usuario.Usuario") as mock_usuario,
    ):
        mock_usuario.get_all.return_value = []
        a = AnalisadorChamados()
        resultado = a.obter_metricas_supervisores()

    mock_buscar.assert_called_once()
    assert resultado == []


def test_obter_metricas_supervisores_exception_retorna_lista_vazia():
    """obter_metricas_supervisores retorna [] quando ocorre exceção."""
    from app.services.analytics import AnalisadorChamados

    with patch("app.models_usuario.Usuario") as mock_usuario:
        mock_usuario.get_all.side_effect = Exception("db error")
        a = AnalisadorChamados()
        resultado = a.obter_metricas_supervisores()

    assert resultado == []


# ── Onda 3: obter_metricas_areas query e exception ────────────────────────────


def test_obter_metricas_areas_query_sem_pre_carregados():
    """obter_metricas_areas sem pre_carregados busca supervisores e chamados reais."""
    from app.services.analytics import AnalisadorChamados

    sup = MagicMock()
    sup.id = "sup1"
    sup.perfil = "supervisor"
    sup.areas = ["TI"]
    sup.area = None

    chamado_dict = {
        "area": "TI",
        "status": "Concluído",
        "data_abertura": None,
        "data_conclusao": None,
        "motivo_atribuicao": "",
    }

    with (
        patch("app.models_usuario.Usuario.get_all", return_value=[sup]),
        patch.object(
            AnalisadorChamados, "_buscar_chamados_dicts", return_value=[chamado_dict]
        ) as mock_buscar,
    ):
        a = AnalisadorChamados()
        resultado = a.obter_metricas_areas()

    mock_buscar.assert_called_once()
    assert len(resultado) == 1
    assert resultado[0]["area"] == "TI"


def test_obter_metricas_areas_calcula_tempo_medio():
    """obter_metricas_areas calcula tempo_medio_resolucao_horas para concluídos."""
    from datetime import datetime, timedelta

    from app.services.analytics import AnalisadorChamados

    agora = datetime.now()
    sup = MagicMock()
    sup.id = "sup1"
    sup.perfil = "supervisor"
    sup.areas = ["TI"]
    sup.area = None

    chamados = [
        {
            "area": "TI",
            "status": "Concluído",
            "data_abertura": agora - timedelta(hours=24),
            "data_conclusao": agora - timedelta(hours=12),
            "motivo_atribuicao": "Atribuído automaticamente",
        }
    ]

    with patch("app.models_usuario.Usuario.get_all", return_value=[sup]):
        a = AnalisadorChamados()
        resultado = a.obter_metricas_areas(chamados_pre_carregados=chamados)

    assert len(resultado) == 1
    assert resultado[0]["tempo_medio_resolucao_horas"] == 12.0
    assert resultado[0]["atribuidos_automaticamente"] == 1


def test_obter_metricas_areas_exception_retorna_lista_vazia():
    """obter_metricas_areas retorna [] quando ocorre exceção."""
    from app.services.analytics import AnalisadorChamados

    with patch("app.models_usuario.Usuario.get_all", side_effect=Exception("db error")):
        a = AnalisadorChamados()
        resultado = a.obter_metricas_areas()

    assert resultado == []


# ── Onda 3: obter_analise_atribuicao ──────────────────────────────────────────


def test_obter_analise_atribuicao_retorna_estrutura_com_docs():
    """obter_analise_atribuicao calcula estatísticas para chamados automáticos e manuais."""
    from datetime import datetime, timedelta

    from app.services.analytics import AnalisadorChamados

    agora = datetime.now()

    chamados = [
        {
            "motivo_atribuicao": "Atribuído automaticamente por regra X",
            "status": "Concluído",
            "data_abertura": agora - timedelta(hours=10),
            "data_conclusao": agora - timedelta(hours=5),
        },
        {
            "motivo_atribuicao": "Atribuído manualmente pelo admin",
            "status": "Aberto",
            "data_abertura": agora - timedelta(hours=8),
            "data_conclusao": None,
        },
    ]

    with patch.object(AnalisadorChamados, "_buscar_chamados_dicts", return_value=chamados):
        a = AnalisadorChamados()
        r = a.obter_analise_atribuicao()

    assert "atribuicao_automatica" in r
    assert "atribuicao_manual" in r
    assert "melhoria_taxa_percentual" in r
    assert "melhoria_tempo_horas" in r
    assert "total_chamados" in r
    assert "percentual_automatico" in r
    assert r["total_chamados"] == 2
    assert r["atribuicao_automatica"]["total"] == 1
    assert r["atribuicao_automatica"]["concluidos"] == 1
    assert r["atribuicao_manual"]["total"] == 1
    assert r["percentual_automatico"] == 50.0


def test_obter_analise_atribuicao_lista_vazia():
    """obter_analise_atribuicao com zero chamados retorna percentual_automatico=0."""
    from app.services.analytics import AnalisadorChamados

    with patch.object(AnalisadorChamados, "_buscar_chamados_dicts", return_value=[]):
        a = AnalisadorChamados()
        r = a.obter_analise_atribuicao()

    assert r["total_chamados"] == 0
    assert r["percentual_automatico"] == 0
    assert r["atribuicao_automatica"]["total"] == 0
    assert r["atribuicao_manual"]["total"] == 0


def test_obter_analise_atribuicao_calcula_tempo_medio():
    """obter_analise_atribuicao calcula tempo_medio_resolucao_horas para concluídos."""
    from datetime import datetime, timedelta

    from app.services.analytics import AnalisadorChamados

    agora = datetime.now()

    chamados = [
        {
            "motivo_atribuicao": "Atribuído automaticamente",
            "status": "Concluído",
            "data_abertura": agora - timedelta(hours=10),
            "data_conclusao": agora - timedelta(hours=6),
        },
        {
            "motivo_atribuicao": "Atribuído automaticamente",
            "status": "Concluído",
            "data_abertura": agora - timedelta(hours=8),
            "data_conclusao": agora - timedelta(hours=4),
        },
    ]

    with patch.object(AnalisadorChamados, "_buscar_chamados_dicts", return_value=chamados):
        a = AnalisadorChamados()
        r = a.obter_analise_atribuicao()

    assert r["atribuicao_automatica"]["tempo_medio_resolucao_horas"] == 4.0
    assert r["atribuicao_manual"]["total"] == 0
    assert r["percentual_automatico"] == 100.0


def test_obter_analise_atribuicao_exception_retorna_dict_vazio():
    """obter_analise_atribuicao retorna {} quando ocorre exceção."""
    from app.services.analytics import AnalisadorChamados

    with patch.object(
        AnalisadorChamados, "_buscar_chamados_dicts", side_effect=Exception("timeout")
    ):
        a = AnalisadorChamados()
        r = a.obter_analise_atribuicao()

    assert r == {}


# ── Onda 3: obter_insights ─────────────────────────────────────────────────────


def test_obter_insights_sla_ok_quando_percentual_alto():
    """obter_insights gera insight_sla_ok quando percentual_dentro_sla >= 80."""
    from app.services.analytics import AnalisadorChamados

    sups = [{"supervisor_nome": "João", "taxa_resolucao_percentual": 90.0, "carga_atual": 5}]
    areas = [{"area": "TI", "taxa_resolucao_percentual": 70.0}]
    gerais = {"percentual_dentro_sla": 85.0}

    a = AnalisadorChamados()
    insights = a.obter_insights(
        metricas_supervisores=sups, metricas_areas=areas, metricas_gerais=gerais
    )

    titulo_keys = [i.get("titulo_key") for i in insights]
    assert any("sla_ok" in k for k in titulo_keys)


def test_obter_insights_sla_low_quando_percentual_baixo():
    """obter_insights gera insight_sla_low quando percentual_dentro_sla < 60."""
    from app.services.analytics import AnalisadorChamados

    sups = [{"supervisor_nome": "João", "taxa_resolucao_percentual": 90.0, "carga_atual": 5}]
    areas = [{"area": "TI", "taxa_resolucao_percentual": 70.0}]
    gerais = {"percentual_dentro_sla": 50.0}

    a = AnalisadorChamados()
    insights = a.obter_insights(
        metricas_supervisores=sups, metricas_areas=areas, metricas_gerais=gerais
    )

    titulo_keys = [i.get("titulo_key") for i in insights]
    assert any("sla_low" in k for k in titulo_keys)


def test_obter_insights_supervisor_sobrecarregado():
    """obter_insights gera insight de supervisor sobrecarregado quando carga_atual > 10."""
    from app.services.analytics import AnalisadorChamados

    sups = [
        {
            "supervisor_nome": "Sobrecarregado",
            "taxa_resolucao_percentual": 60.0,
            "carga_atual": 15,
        }
    ]
    areas = [{"area": "TI", "taxa_resolucao_percentual": 70.0}]

    a = AnalisadorChamados()
    insights = a.obter_insights(metricas_supervisores=sups, metricas_areas=areas)

    titulo_keys = [i.get("titulo_key") for i in insights]
    assert any("overloaded" in k for k in titulo_keys)


def test_obter_insights_area_baixa_performance():
    """obter_insights gera insight de área baixa quando taxa_resolucao < 40."""
    from app.services.analytics import AnalisadorChamados

    sups = [{"supervisor_nome": "João", "taxa_resolucao_percentual": 90.0, "carga_atual": 3}]
    areas = [{"area": "RH", "taxa_resolucao_percentual": 20.0}]

    a = AnalisadorChamados()
    insights = a.obter_insights(metricas_supervisores=sups, metricas_areas=areas)

    titulo_keys = [i.get("titulo_key") for i in insights]
    assert any("low_area" in k for k in titulo_keys)


def test_obter_insights_exception_retorna_lista_vazia():
    """obter_insights retorna [] quando ocorre exceção interna."""
    from app.services.analytics import AnalisadorChamados

    a = AnalisadorChamados()
    # Passa estrutura inválida para forçar KeyError dentro de obter_insights
    insights = a.obter_insights(
        metricas_supervisores=[{"missing_key": "no_carga"}],
        metricas_areas=[],
    )

    assert insights == []


def test_obter_insights_sem_metricas_supervisores_chama_metodo():
    """obter_insights sem metricas_supervisores chama self.obter_metricas_supervisores()."""
    from app.services.analytics import AnalisadorChamados

    a = AnalisadorChamados()
    with patch.object(a, "obter_metricas_supervisores", return_value=[]) as mock_sup:
        a.obter_insights(metricas_areas=[], metricas_gerais={})
    mock_sup.assert_called_once()


# ── Onda 3: obter_metricas_periodo_anterior ────────────────────────────────────


def test_obter_metricas_periodo_anterior_retorna_cache_quando_disponivel(app):
    """obter_metricas_periodo_anterior retorna cached sem query ao banco."""
    from app.services.analytics import AnalisadorChamados

    cached_data = {"total_chamados": 10, "taxa_resolucao_percentual": 80.0}
    with (
        app.app_context(),
        patch("app.cache.cache_get", return_value=cached_data),
    ):
        a = AnalisadorChamados()
        r = a.obter_metricas_periodo_anterior()

    assert r == cached_data


def test_obter_metricas_periodo_anterior_query_sem_cache(app):
    """obter_metricas_periodo_anterior sem cache faz query ao banco."""
    from app.services.analytics import AnalisadorChamados

    with (
        app.app_context(),
        patch.object(AnalisadorChamados, "_buscar_chamados_dicts", return_value=[]) as mock_buscar,
        patch("app.cache.cache_get", return_value=None),
        patch("app.cache.cache_set"),
    ):
        a = AnalisadorChamados()
        r = a.obter_metricas_periodo_anterior()

    assert isinstance(r, dict)
    assert "total_chamados" in r
    mock_buscar.assert_called_once()


def test_obter_metricas_periodo_anterior_exception_retorna_dict_vazio():
    """obter_metricas_periodo_anterior retorna {} quando ocorre exceção."""
    from app.services.analytics import AnalisadorChamados

    with patch.object(
        AnalisadorChamados, "_buscar_chamados_dicts", side_effect=Exception("db error")
    ):
        a = AnalisadorChamados()
        r = a.obter_metricas_periodo_anterior()

    assert r == {}


# ── Onda 3: _carregar_chamados_analytics cache hit ────────────────────────────


def test_carregar_chamados_analytics_retorna_cache_hit(app):
    """_carregar_chamados_analytics retorna dados do cache sem query ao banco."""
    from app.services.analytics import AnalisadorChamados

    cached = [{"status": "Aberto", "area": "TI"}]

    with (
        app.app_context(),
        patch.object(AnalisadorChamados, "_buscar_chamados_dicts") as mock_buscar,
        patch("app.cache.cache_get", return_value=cached),
    ):
        a = AnalisadorChamados()
        result = a._carregar_chamados_analytics()

    assert result == cached
    mock_buscar.assert_not_called()


# ── Onda 3: obter_relatorio_completo cache paths ───────────────────────────────


def test_obter_relatorio_completo_retorna_cache_redis(app):
    """obter_relatorio_completo retorna cached do Redis quando disponível."""
    from app.services.analytics import AnalisadorChamados

    cached = {
        "data_geracao": "2024-01-01",
        "metricas_gerais": {},
        "metricas_supervisores": [],
        "metricas_areas": [],
        "insights": [],
    }

    with (
        app.app_context(),
        patch("app.cache.cache_get", return_value=cached),
    ):
        a = AnalisadorChamados()
        r = a.obter_relatorio_completo(usar_cache=True)

    assert r == cached


def test_obter_relatorio_completo_salva_cache_e_memoria(app):
    """obter_relatorio_completo sem cache calcula e salva em cache Redis + memória."""
    from app.services.analytics import AnalisadorChamados

    with (
        app.app_context(),
        patch.object(AnalisadorChamados, "obter_metricas_gerais", return_value={}),
        patch.object(AnalisadorChamados, "obter_metricas_periodo_anterior", return_value={}),
        patch.object(AnalisadorChamados, "obter_metricas_supervisores", return_value=[]),
        patch.object(AnalisadorChamados, "obter_metricas_areas", return_value=[]),
        patch.object(AnalisadorChamados, "obter_insights", return_value=[]),
        patch("app.cache.cache_get", return_value=None),
        patch("app.cache.cache_set") as mock_set,
    ):
        a = AnalisadorChamados()
        r = a.obter_relatorio_completo(usar_cache=True)

    assert "metricas_gerais" in r
    mock_set.assert_called()


def test_obter_relatorio_completo_propaga_dias_para_metricas_gerais_e_delta(app):
    """obter_relatorio_completo(dias=7) deve usar 7 dias tanto na Visão Geral
    quanto no cálculo de delta (período anterior), e não misturar cache com
    outros períodos (ex.: 30 dias)."""
    from app.services.analytics import AnalisadorChamados

    with (
        app.app_context(),
        patch.object(AnalisadorChamados, "obter_metricas_gerais", return_value={}) as mock_mg,
        patch.object(
            AnalisadorChamados, "obter_metricas_periodo_anterior", return_value={}
        ) as mock_mpa,
        patch.object(AnalisadorChamados, "obter_metricas_supervisores", return_value=[]),
        patch.object(AnalisadorChamados, "obter_metricas_areas", return_value=[]),
        patch.object(AnalisadorChamados, "obter_insights", return_value=[]),
        patch("app.cache.cache_get", return_value=None),
        patch("app.cache.cache_set"),
    ):
        a = AnalisadorChamados()
        a.obter_relatorio_completo(usar_cache=True, dias=7)

    assert mock_mg.call_args.kwargs["dias"] == 7
    assert mock_mpa.call_args.kwargs["dias"] == 7


def test_obter_relatorio_completo_exception_retorna_estrutura_vazia(app):
    """obter_relatorio_completo retorna estrutura vazia quando ocorre exceção."""
    from app.services.analytics import AnalisadorChamados

    with (
        app.app_context(),
        patch("app.cache.cache_get", side_effect=Exception("redis down")),
        patch.object(
            AnalisadorChamados,
            "_carregar_chamados_analytics",
            side_effect=Exception("db down"),
        ),
    ):
        a = AnalisadorChamados()
        r = a.obter_relatorio_completo(usar_cache=False)

    assert r["data_geracao"] is None
    assert r["metricas_gerais"] == {}
    assert r["metricas_supervisores"] == []


def test_obter_relatorio_completo_com_areas_filtra_chamados_e_metricas(app):
    """obter_relatorio_completo(areas=[...]) restringe chamados_pre_carregados às áreas
    informadas e filtra fora as linhas de metricas_supervisores/metricas_areas de outras
    áreas — usado pelo Gestor do Setor, que só pode ver dado da própria área."""
    from app.services.analytics import AnalisadorChamados

    chamados = [
        {"area": "TI", "status": "Aberto"},
        {"area": "RH", "status": "Aberto"},
    ]
    sup_ti = {"supervisor_nome": "Ana", "area": "TI", "total_chamados": 1}
    sup_rh = {"supervisor_nome": "Bob", "area": "RH", "total_chamados": 1}
    area_ti = {"area": "TI", "total_chamados": 1}
    area_rh = {"area": "RH", "total_chamados": 1}

    with (
        app.app_context(),
        patch.object(AnalisadorChamados, "_carregar_chamados_analytics", return_value=chamados),
        patch.object(AnalisadorChamados, "obter_metricas_gerais", return_value={}) as mock_mg,
        patch.object(AnalisadorChamados, "obter_metricas_periodo_anterior", return_value={}),
        patch.object(
            AnalisadorChamados, "obter_metricas_supervisores", return_value=[sup_ti, sup_rh]
        ),
        patch.object(AnalisadorChamados, "obter_metricas_areas", return_value=[area_ti, area_rh]),
        patch.object(AnalisadorChamados, "obter_insights", return_value=[]),
        patch("app.cache.cache_get", return_value=None),
        patch("app.cache.cache_set"),
    ):
        a = AnalisadorChamados()
        r = a.obter_relatorio_completo(usar_cache=True, areas=["TI"])

    chamados_repassados = mock_mg.call_args.kwargs["chamados_pre_carregados"]
    assert all(c["area"] == "TI" for c in chamados_repassados)
    assert [m["area"] for m in r["metricas_supervisores"]] == ["TI"]
    assert [m["area"] for m in r["metricas_areas"]] == ["TI"]


def test_obter_relatorio_completo_com_areas_vazia_nao_vaza_dado_de_outra_area(app):
    """obter_relatorio_completo(areas=[]) é um escopo válido (usuário sem área
    associada) — não deve cair para a visão company-wide."""
    from app.services.analytics import AnalisadorChamados

    chamados = [{"area": "TI", "status": "Aberto"}]
    sup_ti = {"supervisor_nome": "Ana", "area": "TI", "total_chamados": 1}

    with (
        app.app_context(),
        patch.object(AnalisadorChamados, "_carregar_chamados_analytics", return_value=chamados),
        patch.object(AnalisadorChamados, "obter_metricas_gerais", return_value={}) as mock_mg,
        patch.object(AnalisadorChamados, "obter_metricas_periodo_anterior", return_value={}),
        patch.object(AnalisadorChamados, "obter_metricas_supervisores", return_value=[sup_ti]),
        patch.object(AnalisadorChamados, "obter_metricas_areas", return_value=[]),
        patch.object(AnalisadorChamados, "obter_insights", return_value=[]),
        patch("app.cache.cache_get", return_value=None),
        patch("app.cache.cache_set"),
    ):
        a = AnalisadorChamados()
        r = a.obter_relatorio_completo(usar_cache=True, areas=[])

    assert mock_mg.call_args.kwargs["chamados_pre_carregados"] == []
    assert r["metricas_supervisores"] == []


# ── Fase 7 — obter_sla_para_exibicao: Em Atendimento + data_em_atendimento ────


def test_em_atendimento_sem_data_em_atendimento_usa_logica_calendario():
    """Em Atendimento sem data_em_atendimento cai no ramo calendário (comportamento antigo)."""
    from datetime import datetime, timedelta

    from app.services.analytics import obter_sla_para_exibicao

    # Aberto há 12h — dentro de qualquer SLA de calendário
    chamado = type(
        "C",
        (),
        {
            "data_abertura": datetime.now() - timedelta(hours=12),
            "data_conclusao": None,
            "categoria": "TI",
            "status": "Em Atendimento",
            "sla_dias": None,
            "data_em_atendimento": None,
        },
    )()
    r = obter_sla_para_exibicao(chamado)
    assert r is not None
    assert r["label"] == "No prazo"
    assert r["dentro_prazo"] is True


def test_em_atendimento_dentro_prazo_usa_percentual_resolucao():
    """Em Atendimento com data_em_atendimento recente usa percentual_prazo_resolucao e retorna No prazo."""
    from datetime import datetime, timedelta

    from app.services.analytics import obter_sla_para_exibicao

    agora = datetime.now()
    chamado = type(
        "C",
        (),
        {
            "data_abertura": agora - timedelta(hours=2),
            "data_conclusao": None,
            "categoria": "Manutenção",
            "status": "Em Atendimento",
            "sla_dias": None,
            "data_em_atendimento": agora - timedelta(hours=1),
        },
    )()
    # percentual < 0.5 → No prazo
    with patch("app.services.analytics.percentual_prazo_resolucao", return_value=0.3) as mock_pct:
        r = obter_sla_para_exibicao(chamado)
    mock_pct.assert_called_once()
    assert r is not None
    assert r["label"] == "No prazo"
    assert r["dentro_prazo"] is True
    assert r["em_risco"] is False


def test_em_atendimento_atrasado_usa_percentual_resolucao():
    """Em Atendimento com data_em_atendimento passada usa percentual_prazo_resolucao e retorna Atrasado."""
    from datetime import datetime, timedelta

    from app.services.analytics import obter_sla_para_exibicao

    agora = datetime.now()
    chamado = type(
        "C",
        (),
        {
            "data_abertura": agora - timedelta(days=5),
            "data_conclusao": None,
            "categoria": "Manutenção",
            "status": "Em Atendimento",
            "sla_dias": None,
            "data_em_atendimento": agora - timedelta(days=4),
        },
    )()
    # percentual > 1.0 → Atrasado
    with patch("app.services.analytics.percentual_prazo_resolucao", return_value=1.5) as mock_pct:
        r = obter_sla_para_exibicao(chamado)
    mock_pct.assert_called_once()
    assert r is not None
    assert r["label"] == "Atrasado"
    assert r["dentro_prazo"] is False
    assert r["em_risco"] is False


def test_em_atendimento_em_risco_quando_percentual_50():
    """percentual=0.55 → label 'Em risco', em_risco=True, dentro_prazo=None."""
    from datetime import datetime, timedelta

    from app.services.analytics import obter_sla_para_exibicao

    agora = datetime.now()
    chamado = type(
        "C",
        (),
        {
            "data_abertura": agora - timedelta(hours=4),
            "data_conclusao": None,
            "categoria": "Manutenção",
            "status": "Em Atendimento",
            "sla_dias": None,
            "data_em_atendimento": agora - timedelta(hours=3),
        },
    )()
    with patch("app.services.analytics.percentual_prazo_resolucao", return_value=0.55):
        r = obter_sla_para_exibicao(chamado)
    assert r is not None
    assert r["label"] == "Em risco"
    assert r["em_risco"] is True
    assert r["dentro_prazo"] is None


def test_em_atendimento_em_risco_quando_percentual_79():
    """percentual=0.79 → 'Em risco' (threshold agora é 50%, não mais 80%)."""
    from datetime import datetime, timedelta

    from app.services.analytics import obter_sla_para_exibicao

    agora = datetime.now()
    chamado = type(
        "C",
        (),
        {
            "data_abertura": agora - timedelta(hours=4),
            "data_conclusao": None,
            "categoria": "Manutenção",
            "status": "Em Atendimento",
            "sla_dias": None,
            "data_em_atendimento": agora - timedelta(hours=3),
        },
    )()
    with patch("app.services.analytics.percentual_prazo_resolucao", return_value=0.79):
        r = obter_sla_para_exibicao(chamado)
    assert r is not None
    assert r["label"] == "Em risco"
    assert r["em_risco"] is True


def test_obter_metricas_gerais_em_atendimento_em_risco_por_percentual_resolucao():
    """Chamado Em Atendimento com data_em_atendimento → em_risco via percentual_prazo_resolucao."""
    from datetime import UTC, datetime, timedelta

    from app.services.analytics import AnalisadorChamados

    agora = datetime.now(UTC)
    chamados = [
        {
            "status": "Em Atendimento",
            "data_abertura": agora - timedelta(days=2),
            "data_conclusao": None,
            "data_em_atendimento": agora - timedelta(days=1),
            "categoria": "Manutenção",
            "prioridade": "Normal",
            "sla_dias": None,
        },
    ]

    with patch("app.services.analytics.percentual_prazo_resolucao", return_value=0.6):
        a = AnalisadorChamados()
        r = a.obter_metricas_gerais(dias=30, chamados_pre_carregados=chamados)

    assert r["resumo_sla"]["em_risco"] == 1
