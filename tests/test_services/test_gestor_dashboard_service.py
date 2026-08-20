"""Testes unitários do serviço gestor_dashboard_service (Fases 5 e 6)."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from app.services.gestor_dashboard_service import (
    _is_aberto_sem_resposta,
    _is_multi_setor_travado,
    obter_contexto_gestor_dashboard,
)
from config import Config

# ---------------------------------------------------------------------------
# _is_aberto_sem_resposta — usa business_time (Fase 6)
# ---------------------------------------------------------------------------

# Referência fixa: segunda-feira 2024-06-03 11:00 BRT (dentro do expediente)
# 09:00-11:00 = 120 min úteis; 10:01-11:00 = 59 min úteis; 10:00-11:00 = 60 min úteis
_AGORA_FIXED = datetime(2024, 6, 3, 11, 0)


def _chamado_aberto(minutos_atras: float) -> MagicMock:
    """Cria chamado Aberto com data_abertura = _AGORA_FIXED - minutos_atras (BRT naive).

    Para valores ≤ 90 min dentro de um bloco de expediente, wall-clock ≈ useful minutes.
    """
    c = MagicMock()
    c.status = "Aberto"
    c.data_abertura = _AGORA_FIXED - timedelta(minutes=minutos_atras)
    return c


def test_is_aberto_sem_resposta_true_quando_aberto_ha_mais_de_1h():
    # 11:00 - 61 min = 09:59; 09:59–11:00 = 61 min úteis (seg, sem almoço)
    assert _is_aberto_sem_resposta(_chamado_aberto(61), _AGORA_FIXED) is True


def test_is_aberto_sem_resposta_true_exato_no_limiar():
    # 10:00–11:00 = 60 min úteis exatos
    assert _is_aberto_sem_resposta(_chamado_aberto(60), _AGORA_FIXED) is True


def test_is_aberto_sem_resposta_false_quando_aberto_recente():
    # 10:01–11:00 = 59 min úteis
    assert _is_aberto_sem_resposta(_chamado_aberto(59), _AGORA_FIXED) is False


def test_is_aberto_sem_resposta_false_quando_status_em_atendimento():
    c = MagicMock()
    c.status = "Em Atendimento"
    c.data_abertura = datetime(2024, 6, 3, 9, 0)
    assert _is_aberto_sem_resposta(c, _AGORA_FIXED) is False


def test_is_aberto_sem_resposta_false_quando_status_concluido():
    c = MagicMock()
    c.status = "Concluído"
    c.data_abertura = datetime(2024, 6, 3, 9, 0)
    assert _is_aberto_sem_resposta(c, _AGORA_FIXED) is False


def test_is_aberto_sem_resposta_false_quando_data_abertura_none():
    c = MagicMock()
    c.status = "Aberto"
    c.data_abertura = None
    assert _is_aberto_sem_resposta(c, _AGORA_FIXED) is False


def test_is_aberto_sem_resposta_nao_conta_fim_de_semana():
    """Regressão Fase 6: chamado aberto sexta 16:29 não aparece como sem resposta sábado 17:29.

    Com o cálculo wall-clock antigo (_minutos_desde), 25h corridas marcavam como "sem resposta".
    Com business_time, apenas 1 min útil (16:29–16:30) → False.
    """
    c = MagicMock()
    c.status = "Aberto"
    c.data_abertura = datetime(2024, 6, 7, 16, 29)  # sexta 16:29 BRT
    agora = datetime(2024, 6, 8, 17, 29)  # sábado 17:29 BRT

    assert _is_aberto_sem_resposta(c, agora) is False


# ---------------------------------------------------------------------------
# _is_multi_setor_travado
# ---------------------------------------------------------------------------


def _chamado_multi(status: str, participantes: list) -> MagicMock:
    c = MagicMock()
    c.status = status
    c.participantes = participantes
    return c


def test_is_multi_setor_travado_true_com_participante_pendente():
    c = _chamado_multi("Em Atendimento", [{"supervisor_id": "s1", "status": "pendente"}])
    assert _is_multi_setor_travado(c) is True


def test_is_multi_setor_travado_true_com_status_em_atendimento():
    c = _chamado_multi("Em Atendimento", [{"supervisor_id": "s1", "status": "em_atendimento"}])
    assert _is_multi_setor_travado(c) is True


def test_is_multi_setor_travado_false_quando_todos_concluidos():
    c = _chamado_multi(
        "Em Atendimento",
        [
            {"supervisor_id": "s1", "status": "concluido"},
            {"supervisor_id": "s2", "status": "concluido"},
        ],
    )
    assert _is_multi_setor_travado(c) is False


def test_is_multi_setor_travado_false_quando_sem_participantes():
    c = _chamado_multi("Em Atendimento", [])
    assert _is_multi_setor_travado(c) is False


def test_is_multi_setor_travado_false_quando_participantes_none():
    c = MagicMock()
    c.status = "Em Atendimento"
    c.participantes = None
    assert _is_multi_setor_travado(c) is False


def test_is_multi_setor_travado_false_quando_chamado_concluido():
    c = _chamado_multi("Concluído", [{"supervisor_id": "s1", "status": "pendente"}])
    assert _is_multi_setor_travado(c) is False


def test_is_multi_setor_travado_false_quando_chamado_cancelado():
    c = _chamado_multi("Cancelado", [{"supervisor_id": "s1", "status": "pendente"}])
    assert _is_multi_setor_travado(c) is False


def test_is_multi_setor_travado_misto_pelo_menos_um_pendente():
    c = _chamado_multi(
        "Em Atendimento",
        [
            {"supervisor_id": "s1", "status": "concluido"},
            {"supervisor_id": "s2", "status": "pendente"},
        ],
    )
    assert _is_multi_setor_travado(c) is True


# ---------------------------------------------------------------------------
# obter_contexto_gestor_dashboard
# ---------------------------------------------------------------------------


def _make_chamado_aberto_antigo():
    """Chamado Aberto há 120 min úteis em relação a _AGORA_FIXED → classifica como sem resposta.

    previsao_atendimento/data_em_atendimento explícitos em None: um Chamado
    real sempre tem esses campos (None ou valor) — MagicMock() solto sem eles
    dispara o "trap" do MagicMock (hasattr/isinstance sempre truthy) dentro
    de obter_sla_para_exibicao, que _is_atrasado agora usa de verdade.
    """
    c = MagicMock()
    c.status = "Aberto"
    c.data_abertura = datetime(2024, 6, 3, 9, 0)  # 2h antes de _AGORA_FIXED (11:00)
    c.is_atrasado = False
    c.sla_dias = None
    c.data_conclusao = None
    c.data_em_atendimento = None
    c.previsao_atendimento = None
    c.participantes = []
    return c


def _make_chamado_atrasado():
    """is_atrasado=True dá short-circuit em _is_atrasado antes de chamar
    obter_sla_para_exibicao — não precisa de previsao_atendimento/data_em_atendimento."""
    c = MagicMock()
    c.status = "Em Atendimento"
    c.is_atrasado = True
    c.data_abertura = datetime(2024, 6, 3, 10, 0)
    c.participantes = []
    return c


def _make_chamado_multi_travado():
    c = MagicMock()
    c.status = "Em Atendimento"
    c.is_atrasado = False
    c.sla_dias = None
    c.data_abertura = datetime(2024, 6, 3, 10, 15)  # naive, mesma convenção de _AGORA_FIXED
    c.data_conclusao = None
    c.data_em_atendimento = None
    c.previsao_atendimento = None
    c.participantes = [{"supervisor_id": "s1", "status": "pendente"}]
    return c


def _make_chamado_saudavel():
    """Chamado sem nenhum risco: não atrasado, não aberto-sem-resposta, não multi-travado."""
    c = MagicMock()
    c.status = "Em Atendimento"
    c.is_atrasado = False
    c.sla_dias = None
    c.data_abertura = datetime(2024, 6, 3, 10, 30)
    c.data_conclusao = None
    c.data_em_atendimento = None
    c.previsao_atendimento = None
    c.participantes = []
    return c


def test_obter_contexto_lista_vazia():
    with patch("app.services.gestor_dashboard_service._carregar_todos_chamados", return_value=[]):
        ctx = obter_contexto_gestor_dashboard(agora=_AGORA_FIXED)

    assert ctx["filtro_ativo"] == "todos"
    assert ctx["contadores"]["total"] == 0
    assert ctx["contadores"]["atrasados"] == 0
    assert ctx["contadores"]["aberto_sem_resposta"] == 0
    assert ctx["contadores"]["multi_setor_travado"] == 0
    assert ctx["chamados"] == []


def test_obter_contexto_filtro_todos_retorna_tudo():
    chamados = [_make_chamado_aberto_antigo(), _make_chamado_atrasado()]
    with patch(
        "app.services.gestor_dashboard_service._carregar_todos_chamados", return_value=chamados
    ):
        ctx = obter_contexto_gestor_dashboard(filtro="todos", agora=_AGORA_FIXED)

    assert ctx["filtro_ativo"] == "todos"
    assert ctx["contadores"]["total"] == 2
    assert len(ctx["chamados"]) == 2


def test_obter_contexto_filtro_atrasados():
    atrasado = _make_chamado_atrasado()
    nao_atrasado = _make_chamado_aberto_antigo()
    with patch(
        "app.services.gestor_dashboard_service._carregar_todos_chamados",
        return_value=[atrasado, nao_atrasado],
    ):
        ctx = obter_contexto_gestor_dashboard(filtro="atrasados", agora=_AGORA_FIXED)

    assert ctx["filtro_ativo"] == "atrasados"
    assert ctx["contadores"]["atrasados"] == 1
    assert len(ctx["chamados"]) == 1
    assert ctx["chamados"][0] is atrasado


def test_obter_contexto_filtro_aberto_sem_resposta():
    aberto_antigo = _make_chamado_aberto_antigo()
    with patch(
        "app.services.gestor_dashboard_service._carregar_todos_chamados",
        return_value=[aberto_antigo],
    ):
        ctx = obter_contexto_gestor_dashboard(filtro="aberto_sem_resposta", agora=_AGORA_FIXED)

    assert ctx["filtro_ativo"] == "aberto_sem_resposta"
    assert ctx["contadores"]["aberto_sem_resposta"] == 1
    assert len(ctx["chamados"]) == 1


def test_obter_contexto_filtro_aberto_alias():
    aberto_antigo = _make_chamado_aberto_antigo()
    with patch(
        "app.services.gestor_dashboard_service._carregar_todos_chamados",
        return_value=[aberto_antigo],
    ):
        ctx = obter_contexto_gestor_dashboard(filtro="aberto", agora=_AGORA_FIXED)

    assert ctx["filtro_ativo"] == "aberto"
    assert len(ctx["chamados"]) == 1


def test_obter_contexto_filtro_multi_setor():
    multi = _make_chamado_multi_travado()
    with patch(
        "app.services.gestor_dashboard_service._carregar_todos_chamados",
        return_value=[multi],
    ):
        ctx = obter_contexto_gestor_dashboard(filtro="multi_setor", agora=_AGORA_FIXED)

    assert ctx["filtro_ativo"] == "multi_setor"
    assert ctx["contadores"]["multi_setor_travado"] == 1
    assert len(ctx["chamados"]) == 1


def test_obter_contexto_filtro_invalido_retorna_todos():
    chamados = [_make_chamado_atrasado()]
    with patch(
        "app.services.gestor_dashboard_service._carregar_todos_chamados", return_value=chamados
    ):
        ctx = obter_contexto_gestor_dashboard(filtro="qualquer_coisa_invalida", agora=_AGORA_FIXED)

    assert ctx["filtro_ativo"] == "qualquer_coisa_invalida"
    assert len(ctx["chamados"]) == 1


def test_obter_contexto_sem_filtro_retorna_todos():
    chamados = [_make_chamado_atrasado()]
    with patch(
        "app.services.gestor_dashboard_service._carregar_todos_chamados", return_value=chamados
    ):
        ctx = obter_contexto_gestor_dashboard(agora=_AGORA_FIXED)

    assert ctx["filtro_ativo"] == "todos"
    assert len(ctx["chamados"]) == 1


# ---------------------------------------------------------------------------
# _is_atrasado — linhas 42 e 46-51
# ---------------------------------------------------------------------------


def test_is_atrasado_status_finalizado_retorna_false():
    """_is_atrasado retorna False quando status está em _STATUS_FINALIZADOS (linha 42)."""
    from app.services.gestor_dashboard_service import _is_atrasado

    c = MagicMock()
    c.is_atrasado = None
    c.status = "Concluído"
    assert _is_atrasado(c) is False


def test_is_atrasado_com_sla_e_data_abertura_dentro_do_prazo():
    """_is_atrasado (via obter_sla_para_exibicao) considera dentro do prazo
    quando o tempo corrido desde a abertura ainda não passou de sla_dias."""
    from app.services.gestor_dashboard_service import _is_atrasado

    c = MagicMock()
    c.is_atrasado = None
    c.status = "Em Atendimento"
    c.sla_dias = 5
    c.categoria = "Rotina"
    c.data_abertura = datetime(2024, 6, 3, 9, 0)
    c.data_conclusao = None
    c.data_em_atendimento = None
    c.previsao_atendimento = None

    agora = datetime(2024, 6, 4, 9, 0)  # 1 dia depois, dentro dos 5 dias de SLA
    assert _is_atrasado(c, agora) is False


def test_is_atrasado_com_sla_estourado_fica_atrasado():
    """Complementar: mesmo chamado, mas agora além do sla_dias customizado."""
    from app.services.gestor_dashboard_service import _is_atrasado

    c = MagicMock()
    c.is_atrasado = None
    c.status = "Em Atendimento"
    c.sla_dias = 5
    c.categoria = "Rotina"
    c.data_abertura = datetime(2024, 6, 3, 9, 0)
    c.data_conclusao = None
    c.data_em_atendimento = None
    c.previsao_atendimento = None

    agora = datetime(2024, 6, 9, 9, 0)  # 6 dias depois, além dos 5 dias de SLA
    assert _is_atrasado(c, agora) is True


def test_is_atrasado_com_previsao_aprovada_futura_nunca_atrasado():
    """Previsão de atendimento aprovada e ainda futura vence mesmo com
    sla_dias já estourado — alinhado com obter_sla_para_exibicao."""
    from app.services.gestor_dashboard_service import _is_atrasado

    c = MagicMock()
    c.is_atrasado = None
    c.status = "Em Atendimento"
    c.sla_dias = 1
    c.categoria = "Rotina"
    c.data_abertura = datetime(2024, 6, 3, 9, 0)
    c.data_conclusao = None
    c.data_em_atendimento = None
    c.previsao_atendimento = datetime.now(ZoneInfo(Config.SLA_TIMEZONE)) + timedelta(days=5)

    assert _is_atrasado(c) is False


def test_is_atrasado_sem_sla_customizado_usa_padrao_da_categoria_projetos():
    """Bug real (auditoria QA 2026-08-14): chamado sem sla_dias customizado
    (o caso normal — SLA vem da categoria) sempre voltava False aqui, mesmo
    estourado, porque a função desistia assim que via sla_dias is None em vez
    de cair no fallback por categoria que obter_sla_para_exibicao usa. Isso
    fazia o Painel Gerencial reportar "0 atrasados" com chamados atrasados de
    verdade no Painel de Gestão. Projetos = 2 dias corridos (Config default)."""
    from app.services.gestor_dashboard_service import _is_atrasado

    c = MagicMock()
    c.is_atrasado = None
    c.status = "Aberto"
    c.sla_dias = None
    c.categoria = "Projetos"
    c.data_abertura = datetime(2024, 6, 3, 9, 0)
    c.data_conclusao = None
    c.data_em_atendimento = None
    c.previsao_atendimento = None

    agora = datetime(2024, 6, 7, 9, 0)  # 4 dias corridos > 2 dias do SLA de Projetos
    assert _is_atrasado(c, agora) is True


def test_is_atrasado_sem_sla_customizado_dentro_do_prazo_da_categoria():
    """Mesmo cenário sem sla_dias customizado, mas ainda dentro do prazo
    padrão da categoria (Padrão = 3 dias corridos) — não deve ser atrasado."""
    from app.services.gestor_dashboard_service import _is_atrasado

    c = MagicMock()
    c.is_atrasado = None
    c.status = "Aberto"
    c.sla_dias = None
    c.categoria = "Rotina"
    c.data_abertura = datetime(2024, 6, 3, 9, 0)
    c.data_conclusao = None
    c.data_em_atendimento = None
    c.previsao_atendimento = None

    agora = datetime(2024, 6, 4, 9, 0)  # 1 dia corrido < 3 dias do SLA padrão
    assert _is_atrasado(c, agora) is False


def test_is_atrasado_com_previsao_ja_passada_volta_a_calcular_normal():
    """Previsão já vencida não protege mais — volta a valer sla_dias/tempo decorrido."""
    from app.services.gestor_dashboard_service import _is_atrasado

    c = MagicMock()
    c.is_atrasado = None
    c.status = "Em Atendimento"
    c.sla_dias = 1
    c.categoria = "Rotina"
    c.data_abertura = datetime(2024, 6, 3, 9, 0)
    c.data_conclusao = None
    c.data_em_atendimento = None
    c.previsao_atendimento = datetime.now(ZoneInfo(Config.SLA_TIMEZONE)) - timedelta(days=1)

    assert _is_atrasado(c) is True


# ---------------------------------------------------------------------------
# _carregar_todos_chamados — linhas 81-91
# ---------------------------------------------------------------------------


def test_carregar_todos_chamados_retorna_lista_de_chamados(db_session):
    """_carregar_todos_chamados executa query no Postgres e retorna lista de Chamado."""
    from app.services.gestor_dashboard_service import _carregar_todos_chamados
    from tests.factories import make_chamado

    make_chamado(status="Aberto")

    result = _carregar_todos_chamados()

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].status == "Aberto"


# ---------------------------------------------------------------------------
# Insights de triagem (painel de risco)
# ---------------------------------------------------------------------------


def _make_chamado_atrasado_area(area: str):
    c = MagicMock()
    c.status = "Em Atendimento"
    c.is_atrasado = True
    c.area = area
    c.data_abertura = datetime(2024, 6, 3, 10, 0)
    c.participantes = []
    return c


def test_insights_area_critica_identifica_area_com_mais_atrasados():
    chamados = [
        _make_chamado_atrasado_area("TI"),
        _make_chamado_atrasado_area("TI"),
        _make_chamado_atrasado_area("Facilities"),
    ]
    with patch(
        "app.services.gestor_dashboard_service._carregar_todos_chamados", return_value=chamados
    ):
        ctx = obter_contexto_gestor_dashboard(agora=_AGORA_FIXED)

    assert ctx["insights"]["area_critica"] == {"nome": "TI", "qtd": 2}


def test_insights_area_critica_none_quando_sem_atrasados():
    with patch("app.services.gestor_dashboard_service._carregar_todos_chamados", return_value=[]):
        ctx = obter_contexto_gestor_dashboard(agora=_AGORA_FIXED)

    assert ctx["insights"]["area_critica"] is None


def test_insights_tempo_medio_sem_resposta():
    # 2h atrás → 120 min úteis sem resposta (dentro do expediente, sem almoço)
    chamado = _make_chamado_aberto_antigo()
    with patch(
        "app.services.gestor_dashboard_service._carregar_todos_chamados",
        return_value=[chamado],
    ):
        ctx = obter_contexto_gestor_dashboard(agora=_AGORA_FIXED)

    assert ctx["insights"]["tempo_medio_sem_resposta_min"] == 120


def test_insights_tempo_medio_none_quando_sem_chamados_pendentes():
    with patch("app.services.gestor_dashboard_service._carregar_todos_chamados", return_value=[]):
        ctx = obter_contexto_gestor_dashboard(agora=_AGORA_FIXED)

    assert ctx["insights"]["tempo_medio_sem_resposta_min"] is None


def test_insights_saude_percentual_100_quando_sem_riscos():
    chamado_ok = MagicMock()
    chamado_ok.status = "Concluído"
    chamado_ok.is_atrasado = False
    chamado_ok.participantes = []
    with patch(
        "app.services.gestor_dashboard_service._carregar_todos_chamados",
        return_value=[chamado_ok],
    ):
        ctx = obter_contexto_gestor_dashboard(agora=_AGORA_FIXED)

    assert ctx["insights"]["saude_percentual"] == 100


def test_insights_saude_percentual_reflete_proporcao_em_risco():
    atrasado = _make_chamado_atrasado()
    ok1 = MagicMock(status="Concluído", is_atrasado=False, participantes=[])
    ok2 = MagicMock(status="Concluído", is_atrasado=False, participantes=[])
    ok3 = MagicMock(status="Concluído", is_atrasado=False, participantes=[])
    with patch(
        "app.services.gestor_dashboard_service._carregar_todos_chamados",
        return_value=[atrasado, ok1, ok2, ok3],
    ):
        ctx = obter_contexto_gestor_dashboard(agora=_AGORA_FIXED)

    # 1 de 4 em risco → 75% saudável
    assert ctx["insights"]["saude_percentual"] == 75


def test_insights_em_risco_total_nao_conta_chamado_duplicado():
    """Bug real (auditoria QA 2026-08-14): a string "X chamados carregados; Y
    em algum estado de risco" no template (gestor_dashboard.html) somava os 3
    buckets (atrasados + aberto_sem_resposta + multi_setor) em vez de usar a
    união — um chamado atrasado E sem resposta ao mesmo tempo (caso comum, dá
    pra ver os dois badges juntos no Painel de Gestão) era contado duas
    vezes, chegando a superar o total de chamados carregados (22 carregados;
    23 em risco, visto ao vivo). insights['em_risco_total'] precisa ser a
    união, igual ao que já alimenta saude_percentual."""
    c = MagicMock()
    c.status = "Aberto"
    c.is_atrasado = True  # atrasado
    c.data_abertura = datetime(2024, 6, 3, 9, 0)  # 2h antes de _AGORA_FIXED → também sem resposta
    c.participantes = []

    with patch(
        "app.services.gestor_dashboard_service._carregar_todos_chamados",
        return_value=[c],
    ):
        ctx = obter_contexto_gestor_dashboard(agora=_AGORA_FIXED)

    assert ctx["contadores"]["atrasados"] == 1
    assert ctx["contadores"]["aberto_sem_resposta"] == 1
    assert ctx["insights"]["em_risco_total"] == 1  # união, não soma (2)


def test_insights_saude_percentual_100_quando_lista_vazia():
    with patch("app.services.gestor_dashboard_service._carregar_todos_chamados", return_value=[]):
        ctx = obter_contexto_gestor_dashboard(agora=_AGORA_FIXED)

    assert ctx["insights"]["saude_percentual"] == 100


# ---------------------------------------------------------------------------
# Tagueamento de riscos por chamado (chamado.riscos)
# ---------------------------------------------------------------------------


def test_chamado_atrasado_recebe_tag_riscos():
    atrasado = _make_chamado_atrasado()
    with patch(
        "app.services.gestor_dashboard_service._carregar_todos_chamados",
        return_value=[atrasado],
    ):
        ctx = obter_contexto_gestor_dashboard(agora=_AGORA_FIXED)

    assert "atrasado" in ctx["chamados"][0].riscos


def test_chamado_sem_riscos_recebe_lista_vazia():
    chamado_ok = MagicMock(status="Concluído", is_atrasado=False, participantes=[])
    with patch(
        "app.services.gestor_dashboard_service._carregar_todos_chamados",
        return_value=[chamado_ok],
    ):
        ctx = obter_contexto_gestor_dashboard(agora=_AGORA_FIXED)

    assert ctx["chamados"][0].riscos == []


def test_chamado_pode_acumular_multiplos_riscos():
    """Um chamado atrasado E multi-setor travado deve receber as duas tags."""
    c = MagicMock()
    c.status = "Em Atendimento"
    c.is_atrasado = True
    c.data_abertura = datetime(2024, 6, 3, 10, 0)
    c.participantes = [{"supervisor_id": "s1", "status": "pendente"}]
    with patch(
        "app.services.gestor_dashboard_service._carregar_todos_chamados",
        return_value=[c],
    ):
        ctx = obter_contexto_gestor_dashboard(agora=_AGORA_FIXED)

    assert set(ctx["chamados"][0].riscos) == {"atrasado", "multi_setor"}


# ---------------------------------------------------------------------------
# Grupos (raias de triagem para a visão geral)
# ---------------------------------------------------------------------------


def test_grupos_contem_as_cinco_raias_com_totais_corretos():
    atrasado = _make_chamado_atrasado()
    aberto_antigo = _make_chamado_aberto_antigo()
    multi = _make_chamado_multi_travado()
    with patch(
        "app.services.gestor_dashboard_service._carregar_todos_chamados",
        return_value=[atrasado, aberto_antigo, multi],
    ):
        ctx = obter_contexto_gestor_dashboard(agora=_AGORA_FIXED)

    chaves = {g["chave"] for g in ctx["grupos"]}
    assert chaves == {"atrasados", "aberto_sem_resposta", "multi_setor", "em_dia", "cancelados"}
    por_chave = {g["chave"]: g for g in ctx["grupos"]}
    assert por_chave["atrasados"]["total"] == 1
    assert por_chave["aberto_sem_resposta"]["total"] == 1
    assert por_chave["multi_setor"]["total"] == 1
    assert por_chave["em_dia"]["total"] == 0
    assert por_chave["cancelados"]["total"] == 0


def test_grupos_limita_chamados_por_raia():
    atrasados = [_make_chamado_atrasado() for _ in range(10)]
    with patch(
        "app.services.gestor_dashboard_service._carregar_todos_chamados",
        return_value=atrasados,
    ):
        ctx = obter_contexto_gestor_dashboard(agora=_AGORA_FIXED)

    grupo_atrasados = next(g for g in ctx["grupos"] if g["chave"] == "atrasados")
    assert grupo_atrasados["total"] == 10
    assert len(grupo_atrasados["chamados"]) == 6


def test_grupos_contem_raia_em_dia_com_chamado_sem_risco():
    """Regressão: chamado saudável era contado no Total mas não aparecia em nenhuma raia."""
    saudavel = _make_chamado_saudavel()
    atrasado = _make_chamado_atrasado()
    with patch(
        "app.services.gestor_dashboard_service._carregar_todos_chamados",
        return_value=[atrasado, saudavel],
    ):
        ctx = obter_contexto_gestor_dashboard(agora=_AGORA_FIXED)

    chaves = {g["chave"] for g in ctx["grupos"]}
    assert chaves == {"atrasados", "aberto_sem_resposta", "multi_setor", "em_dia", "cancelados"}
    por_chave = {g["chave"]: g for g in ctx["grupos"]}
    assert por_chave["em_dia"]["total"] == 1
    assert por_chave["em_dia"]["chamados"] == [saudavel]


def test_grupos_em_dia_filtra_chamados_com_risco():
    """Um chamado atrasado nunca deve aparecer na raia em_dia."""
    atrasado = _make_chamado_atrasado()
    with patch(
        "app.services.gestor_dashboard_service._carregar_todos_chamados",
        return_value=[atrasado],
    ):
        ctx = obter_contexto_gestor_dashboard(agora=_AGORA_FIXED)

    por_chave = {g["chave"]: g for g in ctx["grupos"]}
    assert por_chave["em_dia"]["total"] == 0


def _make_chamado_cancelado():
    c = MagicMock()
    c.status = "Cancelado"
    c.is_atrasado = False
    c.data_abertura = datetime(2024, 6, 3, 9, 0)
    c.participantes = []
    return c


def test_grupos_contem_raia_cancelados():
    """Pedido do usuário 2026-08-20: painel gerencial precisa de uma raia
    própria pra chamados cancelados, igual ao e-mail semanal."""
    cancelado = _make_chamado_cancelado()
    with patch(
        "app.services.gestor_dashboard_service._carregar_todos_chamados",
        return_value=[cancelado],
    ):
        ctx = obter_contexto_gestor_dashboard(agora=_AGORA_FIXED)

    por_chave = {g["chave"]: g for g in ctx["grupos"]}
    assert por_chave["cancelados"]["total"] == 1
    assert por_chave["cancelados"]["chamados"] == [cancelado]
    assert ctx["contadores"]["cancelados"] == 1


def test_obter_contexto_filtro_cancelados_retorna_apenas_cancelados():
    cancelado = _make_chamado_cancelado()
    saudavel = _make_chamado_saudavel()
    with patch(
        "app.services.gestor_dashboard_service._carregar_todos_chamados",
        return_value=[cancelado, saudavel],
    ):
        ctx = obter_contexto_gestor_dashboard(filtro="cancelados", agora=_AGORA_FIXED)

    assert ctx["filtro_ativo"] == "cancelados"
    assert ctx["chamados"] == [cancelado]


def test_cancelado_nao_vaza_para_raia_em_dia():
    """Bug real achado 2026-08-20: _carregar_todos_chamados() não filtra
    status nenhum, e só as raias de risco (atrasado/sem_resposta/multi_setor)
    excluíam explicitamente chamados finalizados — um Cancelado que não caísse
    em nenhuma delas ia parar direto na raia 'Em dia', que deveria significar
    'saudável, em andamento', não 'cancelado'."""
    cancelado = _make_chamado_cancelado()
    with patch(
        "app.services.gestor_dashboard_service._carregar_todos_chamados",
        return_value=[cancelado],
    ):
        ctx = obter_contexto_gestor_dashboard(agora=_AGORA_FIXED)

    por_chave = {g["chave"]: g for g in ctx["grupos"]}
    assert por_chave["em_dia"]["total"] == 0
    assert cancelado not in por_chave["em_dia"]["chamados"]


def test_concluido_nao_vaza_para_raia_em_dia():
    """Mesmo bug, mas pra Concluído — também é status finalizado."""
    c = MagicMock()
    c.status = "Concluído"
    c.is_atrasado = False
    c.data_abertura = datetime(2024, 6, 3, 9, 0)
    c.participantes = []
    with patch(
        "app.services.gestor_dashboard_service._carregar_todos_chamados",
        return_value=[c],
    ):
        ctx = obter_contexto_gestor_dashboard(agora=_AGORA_FIXED)

    por_chave = {g["chave"]: g for g in ctx["grupos"]}
    assert por_chave["em_dia"]["total"] == 0


def test_cancelado_recebe_riscos_vazio_para_o_template():
    """chamado.riscos precisa existir mesmo pros cancelados (usado pelo macro
    risk_card no template) — não deve estourar AttributeError."""
    cancelado = _make_chamado_cancelado()
    with patch(
        "app.services.gestor_dashboard_service._carregar_todos_chamados",
        return_value=[cancelado],
    ):
        ctx = obter_contexto_gestor_dashboard(agora=_AGORA_FIXED)

    por_chave = {g["chave"]: g for g in ctx["grupos"]}
    assert por_chave["cancelados"]["chamados"][0].riscos == []


def test_saude_percentual_continua_contando_concluido_e_cancelado():
    """A saúde operacional (insights.saude_percentual) NÃO muda de escopo com
    esse fix — continua olhando pra `todos` (todo o carregado), só a raia
    visual 'Em dia' passou a excluir finalizados. Regressão de guarda pro
    comportamento já testado em test_insights_saude_percentual_reflete_proporcao_em_risco."""
    atrasado = _make_chamado_atrasado()
    ok1 = MagicMock(status="Concluído", is_atrasado=False, participantes=[])
    ok2 = MagicMock(status="Concluído", is_atrasado=False, participantes=[])
    ok3 = MagicMock(status="Concluído", is_atrasado=False, participantes=[])
    with patch(
        "app.services.gestor_dashboard_service._carregar_todos_chamados",
        return_value=[atrasado, ok1, ok2, ok3],
    ):
        ctx = obter_contexto_gestor_dashboard(agora=_AGORA_FIXED)

    assert ctx["insights"]["saude_percentual"] == 75
    assert ctx["contadores"]["total"] == 4


def test_obter_contexto_filtro_em_dia_retorna_apenas_saudaveis():
    saudavel = _make_chamado_saudavel()
    atrasado = _make_chamado_atrasado()
    with patch(
        "app.services.gestor_dashboard_service._carregar_todos_chamados",
        return_value=[atrasado, saudavel],
    ):
        ctx = obter_contexto_gestor_dashboard(filtro="em_dia", agora=_AGORA_FIXED)

    assert ctx["filtro_ativo"] == "em_dia"
    assert len(ctx["chamados"]) == 1
    assert ctx["chamados"][0] is saudavel


# ---------------------------------------------------------------------------
# Nível 3 — escopo por área para gestor_setor (usuario opcional)
# ---------------------------------------------------------------------------


def _make_chamado_em_area(area: str):
    c = MagicMock()
    c.status = "Aberto"
    c.is_atrasado = False
    c.sla_dias = None
    c.area = area
    c.data_abertura = datetime(2024, 6, 3, 9, 0)
    c.data_conclusao = None
    c.data_em_atendimento = None
    c.previsao_atendimento = None
    c.participantes = []
    return c


def test_gestor_setor_ve_apenas_chamados_da_propria_area():
    usuario = MagicMock()
    usuario.nivel_gestao = "gestor_setor"
    usuario.areas = ["Manutencao"]

    dentro = _make_chamado_em_area("Manutencao")
    fora = _make_chamado_em_area("TI")

    with patch(
        "app.services.gestor_dashboard_service._carregar_todos_chamados",
        return_value=[dentro, fora],
    ):
        ctx = obter_contexto_gestor_dashboard(agora=_AGORA_FIXED, usuario=usuario)

    assert ctx["contadores"]["total"] == 1
    assert ctx["chamados"] == [dentro]


def test_gestor_setor_com_multiplas_areas_ve_todas_as_suas():
    usuario = MagicMock()
    usuario.nivel_gestao = "gestor_setor"
    usuario.areas = ["Manutencao", "TI"]

    manutencao = _make_chamado_em_area("Manutencao")
    ti = _make_chamado_em_area("TI")
    outra = _make_chamado_em_area("Financeiro")

    with patch(
        "app.services.gestor_dashboard_service._carregar_todos_chamados",
        return_value=[manutencao, ti, outra],
    ):
        ctx = obter_contexto_gestor_dashboard(agora=_AGORA_FIXED, usuario=usuario)

    assert ctx["contadores"]["total"] == 2


def test_gerente_producao_nao_filtra_por_area():
    """Níveis acima de gestor_setor continuam vendo todas as áreas."""
    usuario = MagicMock()
    usuario.nivel_gestao = "gerente_producao"
    usuario.areas = ["Manutencao"]

    with patch(
        "app.services.gestor_dashboard_service._carregar_todos_chamados",
        return_value=[_make_chamado_em_area("Manutencao"), _make_chamado_em_area("TI")],
    ):
        ctx = obter_contexto_gestor_dashboard(agora=_AGORA_FIXED, usuario=usuario)

    assert ctx["contadores"]["total"] == 2


def test_usuario_none_nao_filtra_por_area():
    """Sem usuario informado (retrocompatibilidade), nenhum filtro de área é aplicado."""
    with patch(
        "app.services.gestor_dashboard_service._carregar_todos_chamados",
        return_value=[_make_chamado_em_area("Manutencao"), _make_chamado_em_area("TI")],
    ):
        ctx = obter_contexto_gestor_dashboard(agora=_AGORA_FIXED)

    assert ctx["contadores"]["total"] == 2


def test_carregar_todos_chamados_retorna_vazio_em_excecao():
    """_carregar_todos_chamados retorna [] em exceção do Firestore (linhas 89-91)."""
    from app.services.gestor_dashboard_service import _carregar_todos_chamados

    with patch(
        "app.services.gestor_dashboard_service.db_module.SessionLocal",
        side_effect=Exception("db error"),
    ):
        result = _carregar_todos_chamados()

    assert result == []
