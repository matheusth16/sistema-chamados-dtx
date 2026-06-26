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
