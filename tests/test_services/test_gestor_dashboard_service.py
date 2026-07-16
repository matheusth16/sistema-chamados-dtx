"""Testes unitários do serviço gestor_dashboard_service (Fases 5 e 6)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from app.services.gestor_dashboard_service import (
    _is_aberto_sem_resposta,
    _is_multi_setor_travado,
    obter_contexto_gestor_dashboard,
)

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
    """Chamado Aberto há 120 min úteis em relação a _AGORA_FIXED → classifica como sem resposta."""
    c = MagicMock()
    c.status = "Aberto"
    c.data_abertura = datetime(2024, 6, 3, 9, 0)  # 2h antes de _AGORA_FIXED (11:00)
    c.is_atrasado = False
    c.sla_dias = None
    c.participantes = []
    return c


def _make_chamado_atrasado():
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
    c.data_abertura = datetime.now(tz=UTC)
    c.participantes = [{"supervisor_id": "s1", "status": "pendente"}]
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
    """_is_atrasado calcula minutos úteis quando sla_dias e data_abertura preenchidos (linhas 46-51)."""
    from app.services.gestor_dashboard_service import _is_atrasado

    c = MagicMock()
    c.is_atrasado = None
    c.status = "Em Atendimento"
    c.sla_dias = 5
    c.data_abertura = datetime(2024, 6, 3, 9, 0)

    with patch("app.services.gestor_dashboard_service.minutos_uteis_entre", return_value=100):
        result = _is_atrasado(c)

    assert result is False  # 100 min < 5*24*60 = 7200 min


# ---------------------------------------------------------------------------
# _carregar_todos_chamados — linhas 81-91
# ---------------------------------------------------------------------------


def test_carregar_todos_chamados_retorna_lista_de_chamados():
    """_carregar_todos_chamados executa query no Firestore e retorna lista (linhas 81-88)."""
    from app.services.gestor_dashboard_service import _carregar_todos_chamados

    doc = MagicMock()
    doc.to_dict.return_value = {"status": "Aberto"}
    doc.id = "ch_1"

    with (
        patch("app.services.gestor_dashboard_service.db") as mock_db,
        patch("app.services.gestor_dashboard_service.Chamado") as mock_chamado_cls,
    ):
        mock_db.collection.return_value.order_by.return_value.limit.return_value.stream.return_value = [
            doc
        ]
        mock_chamado_cls.from_dict.return_value = MagicMock()
        result = _carregar_todos_chamados()

    assert isinstance(result, list)
    assert len(result) == 1


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


def test_grupos_contem_as_tres_raias_com_totais_corretos():
    atrasado = _make_chamado_atrasado()
    aberto_antigo = _make_chamado_aberto_antigo()
    multi = _make_chamado_multi_travado()
    with patch(
        "app.services.gestor_dashboard_service._carregar_todos_chamados",
        return_value=[atrasado, aberto_antigo, multi],
    ):
        ctx = obter_contexto_gestor_dashboard(agora=_AGORA_FIXED)

    chaves = {g["chave"] for g in ctx["grupos"]}
    assert chaves == {"atrasados", "aberto_sem_resposta", "multi_setor"}
    por_chave = {g["chave"]: g for g in ctx["grupos"]}
    assert por_chave["atrasados"]["total"] == 1
    assert por_chave["aberto_sem_resposta"]["total"] == 1
    assert por_chave["multi_setor"]["total"] == 1


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

    with patch("app.services.gestor_dashboard_service.db") as mock_db:
        mock_db.collection.return_value.order_by.return_value.limit.return_value.stream.side_effect = Exception(
            "db error"
        )
        result = _carregar_todos_chamados()

    assert result == []
