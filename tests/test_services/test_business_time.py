"""Testes TDD para app/services/business_time.py — Motor de Tempo Útil DTX.

Convenção: datetimes naive nos testes representam horário local BRT (America/Sao_Paulo).
Datetimes aware devem usar ZoneInfo("America/Sao_Paulo") ou UTC (via datetime.timezone.utc).
"""

from datetime import UTC, datetime

import pytest

# ---------------------------------------------------------------------------
# Task 1.2 — dentro_janela_util + pode_enviar_notificacao_agora
# ---------------------------------------------------------------------------


def test_dentro_janela_util_manha():
    from app.services.business_time import dentro_janela_util

    assert dentro_janela_util(datetime(2026, 6, 22, 9, 0)) is True  # segunda 09:00


def test_fora_janela_apos_teto_1630():
    from app.services.business_time import dentro_janela_util

    assert dentro_janela_util(datetime(2026, 6, 22, 16, 31)) is False  # 16:31


def test_exatamente_no_teto_1630_fora():
    from app.services.business_time import dentro_janela_util

    # 16:30 exato — teto é exclusivo (>= 16:30 → fora)
    assert dentro_janela_util(datetime(2026, 6, 22, 16, 30)) is False


def test_fora_janela_almoco():
    from app.services.business_time import dentro_janela_util

    assert dentro_janela_util(datetime(2026, 6, 22, 12, 0)) is False  # 12:00 = almoço


def test_fora_janela_almoco_inicio_exato():
    from app.services.business_time import dentro_janela_util

    # 11:30 exato — início do almoço (inclusivo) → fora
    assert dentro_janela_util(datetime(2026, 6, 22, 11, 30)) is False


def test_dentro_janela_antes_almoco():
    from app.services.business_time import dentro_janela_util

    assert dentro_janela_util(datetime(2026, 6, 22, 11, 29)) is True


def test_dentro_janela_apos_almoco():
    from app.services.business_time import dentro_janela_util

    # 13:00 = fim do almoço (exclusivo) → dentro
    assert dentro_janela_util(datetime(2026, 6, 22, 13, 0)) is True


def test_fora_janela_sabado():
    from app.services.business_time import dentro_janela_util

    assert dentro_janela_util(datetime(2026, 6, 20, 9, 0)) is False  # sábado


def test_fora_janela_domingo():
    from app.services.business_time import dentro_janela_util

    assert dentro_janela_util(datetime(2026, 6, 21, 10, 0)) is False  # domingo


def test_dentro_janela_tarde():
    from app.services.business_time import dentro_janela_util

    assert dentro_janela_util(datetime(2026, 6, 22, 14, 0)) is True  # tarde


def test_fora_janela_antes_inicio():
    from app.services.business_time import dentro_janela_util

    assert dentro_janela_util(datetime(2026, 6, 22, 6, 59)) is False  # antes das 07:00


def test_nao_envia_notificacao_sexta_1645():
    from app.services.business_time import pode_enviar_notificacao_agora

    # sexta 16:45 BRT → não disparar e-mail
    assert pode_enviar_notificacao_agora(datetime(2026, 6, 19, 16, 45)) is False


def test_nao_envia_notificacao_almoco():
    from app.services.business_time import pode_enviar_notificacao_agora

    assert pode_enviar_notificacao_agora(datetime(2026, 6, 22, 11, 45)) is False


def test_envia_notificacao_dentro_janela():
    from app.services.business_time import pode_enviar_notificacao_agora

    assert pode_enviar_notificacao_agora(datetime(2026, 6, 22, 10, 0)) is True


def test_sexta_1645_brt_fora_janela():
    """Garante que datetime aware BRT (America/Sao_Paulo) é tratado corretamente."""
    from zoneinfo import ZoneInfo

    from app.services.business_time import dentro_janela_util

    dt_aware = datetime(2026, 6, 19, 16, 45, tzinfo=ZoneInfo("America/Sao_Paulo"))
    assert dentro_janela_util(dt_aware) is False


# ---------------------------------------------------------------------------
# Task 1.3 — minutos_uteis_entre
# ---------------------------------------------------------------------------


def test_minutos_uteis_simples():
    from app.services.business_time import minutos_uteis_entre

    # segunda 09:00 → 10:00 = 60 min
    assert minutos_uteis_entre(datetime(2026, 6, 22, 9, 0), datetime(2026, 6, 22, 10, 0)) == 60


def test_minutos_uteis_cruzando_almoco():
    from app.services.business_time import minutos_uteis_entre

    # 11:00 → 13:30: 30 min manhã (11:00–11:30) + 30 min tarde (13:00–13:30) = 60 min
    assert minutos_uteis_entre(datetime(2026, 6, 22, 11, 0), datetime(2026, 6, 22, 13, 30)) == 60


def test_minutos_uteis_cruzando_fim_de_semana():
    from app.services.business_time import minutos_uteis_entre

    # sexta 16:00 → segunda 07:30: 30 min sexta + 30 min segunda = 60 min
    assert minutos_uteis_entre(datetime(2026, 6, 19, 16, 0), datetime(2026, 6, 22, 7, 30)) == 60


def test_minutos_uteis_inicio_igual_fim():
    from app.services.business_time import minutos_uteis_entre

    dt = datetime(2026, 6, 22, 9, 0)
    assert minutos_uteis_entre(dt, dt) == 0


def test_minutos_uteis_fora_janela():
    from app.services.business_time import minutos_uteis_entre

    # sábado inteiro → 0 min úteis
    assert minutos_uteis_entre(datetime(2026, 6, 20, 9, 0), datetime(2026, 6, 20, 17, 0)) == 0


def test_minutos_uteis_fim_antes_inicio_retorna_zero():
    from app.services.business_time import minutos_uteis_entre

    # fim < início → 0
    assert minutos_uteis_entre(datetime(2026, 6, 22, 10, 0), datetime(2026, 6, 22, 9, 0)) == 0


# ---------------------------------------------------------------------------
# Task 1.4 — adicionar_minutos_uteis + adicionar_dias_uteis
# ---------------------------------------------------------------------------


def test_adicionar_minutos_uteis_simples():
    from app.services.business_time import adicionar_minutos_uteis

    resultado = adicionar_minutos_uteis(datetime(2026, 6, 22, 9, 0), 60)
    assert resultado == datetime(2026, 6, 22, 10, 0)


def test_adicionar_minutos_uteis_cruzando_almoco():
    from app.services.business_time import adicionar_minutos_uteis

    # +1h útil a partir de 11:00 = 13:30 (não 12:30)
    resultado = adicionar_minutos_uteis(datetime(2026, 6, 22, 11, 0), 60)
    assert resultado == datetime(2026, 6, 22, 13, 30)


def test_adicionar_minutos_uteis_cruzando_fim_de_semana():
    from app.services.business_time import adicionar_minutos_uteis

    # sexta 16:00 + 60 min úteis = segunda 07:30
    # (30 min úteis restam na sexta 16:00–16:30; +30 min na segunda 07:00–07:30)
    # Consistente com minutos_uteis_entre(sexta 16:00, segunda 07:30) == 60
    resultado = adicionar_minutos_uteis(datetime(2026, 6, 19, 16, 0), 60)
    assert resultado == datetime(2026, 6, 22, 7, 30)


def test_adicionar_minutos_uteis_zero():
    from app.services.business_time import adicionar_minutos_uteis

    inicio = datetime(2026, 6, 22, 9, 0)
    assert adicionar_minutos_uteis(inicio, 0) == inicio


def test_adicionar_dias_uteis_projetos_2_dias():
    from app.services.business_time import adicionar_dias_uteis

    # segunda + 2 dias úteis = terça 16:30
    resultado = adicionar_dias_uteis(datetime(2026, 6, 22, 9, 0), 2)
    assert resultado == datetime(2026, 6, 23, 16, 30)


def test_adicionar_dias_uteis_cruzando_fim_de_semana():
    from app.services.business_time import adicionar_dias_uteis

    # sexta + 3 dias úteis = terça seguinte às 16:30
    # (sexta=dia1, segunda=dia2, terça=dia3; dia atual conta como dia 1)
    resultado = adicionar_dias_uteis(datetime(2026, 6, 19, 9, 0), 3)
    assert resultado == datetime(2026, 6, 23, 16, 30)


def test_adicionar_dias_uteis_1_dia():
    from app.services.business_time import adicionar_dias_uteis

    # quarta + 1 dia útil = quarta 16:30 (dia atual conta como dia 1)
    resultado = adicionar_dias_uteis(datetime(2026, 6, 24, 9, 0), 1)
    assert resultado == datetime(2026, 6, 24, 16, 30)


# ---------------------------------------------------------------------------
# Task 1.5 — percentual_prazo_resolucao
# ---------------------------------------------------------------------------


def test_percentual_prazo_inicio():
    from app.services.business_time import percentual_prazo_resolucao

    # Recém virou Em Atendimento — quase 0%
    data_em_atendimento = datetime(2026, 6, 22, 7, 0)
    pct = percentual_prazo_resolucao(data_em_atendimento, "Projetos", datetime(2026, 6, 22, 7, 1))
    assert pct < 0.05


def test_percentual_prazo_apos_deadline():
    from app.services.business_time import percentual_prazo_resolucao

    # Bem além do deadline — >= 1.0
    data_em_atendimento = datetime(2026, 6, 22, 7, 0)
    agora = datetime(2026, 6, 30, 16, 30)  # muitos dias depois
    pct = percentual_prazo_resolucao(data_em_atendimento, "Projetos", agora)
    assert pct >= 1.0


def test_percentual_prazo_categoria_padrao_usa_3_dias():
    from app.services.business_time import percentual_prazo_resolucao

    data_em_atendimento = datetime(2026, 6, 22, 7, 0)  # segunda
    # Em terça 16:30: Projetos já atingiu deadline (2 dias), Manutenção não (3 dias)
    pct_padrao = percentual_prazo_resolucao(
        data_em_atendimento, "Manutenção", datetime(2026, 6, 23, 16, 30)
    )
    pct_projetos = percentual_prazo_resolucao(
        data_em_atendimento, "Projetos", datetime(2026, 6, 23, 16, 30)
    )
    # Manutenção tem deadline mais longo → percentual menor no mesmo instante
    assert pct_padrao < pct_projetos


def test_percentual_prazo_projetos_deadline_exato():
    from app.services.business_time import percentual_prazo_resolucao

    # segunda 07:00 + 2 dias úteis = terça 16:30 → 100%
    data_em_atendimento = datetime(2026, 6, 22, 7, 0)
    pct = percentual_prazo_resolucao(data_em_atendimento, "Projetos", datetime(2026, 6, 23, 16, 30))
    assert pct >= 1.0


def test_percentual_prazo_manutencao_50_pct():
    from app.services.business_time import percentual_prazo_resolucao

    # Manutenção: 3 dias úteis = 3 × 480 min = 1440 min; ~50% = 720 min
    # segunda 07:00 + 480 min = fim da segunda; + 240 min na terça = 11:00
    # agora = terça 10:45 → ~705 min = 48.9% → dentro de [0.45, 0.55]
    data_em_atendimento = datetime(2026, 6, 22, 7, 0)
    agora = datetime(2026, 6, 23, 10, 45)
    pct = percentual_prazo_resolucao(data_em_atendimento, "Manutenção", agora)
    assert 0.45 <= pct <= 0.55


# ---------------------------------------------------------------------------
# Novos casos de borda (lacunas identificadas na revisão)
# ---------------------------------------------------------------------------


def test_minutos_uteis_dia_constante():
    """MINUTOS_UTEIS_DIA deve ser 480: manhã 07:00–11:30 (270) + tarde 13:00–16:30 (210)."""
    from app.services.business_time import MINUTOS_UTEIS_DIA

    assert MINUTOS_UTEIS_DIA == 480


def test_dentro_janela_util_utc_cai_no_almoco_brt():
    """UTC 14:45 = 11:45 BRT (almoço) → fora da janela."""

    from app.services.business_time import dentro_janela_util

    # 2026-06-22 (segunda); UTC-3 = BRT; 14:45 UTC = 11:45 BRT (almoço 11:30–13:00)
    dt_utc = datetime(2026, 6, 22, 14, 45, tzinfo=UTC)
    assert dentro_janela_util(dt_utc) is False


def test_dentro_janela_util_utc_apos_teto_brt():
    """UTC 20:00 = 17:00 BRT (após 16:30) → fora da janela."""

    from app.services.business_time import dentro_janela_util

    # 20:00 UTC = 17:00 BRT → após teto 16:30
    dt_utc = datetime(2026, 6, 22, 20, 0, tzinfo=UTC)
    assert dentro_janela_util(dt_utc) is False


def test_dentro_janela_util_utc_dentro_janela_brt():
    """UTC 13:00 = 10:00 BRT → dentro da janela."""

    from app.services.business_time import dentro_janela_util

    # 13:00 UTC = 10:00 BRT → dentro (manhã, antes almoço)
    dt_utc = datetime(2026, 6, 22, 13, 0, tzinfo=UTC)
    assert dentro_janela_util(dt_utc) is True


def test_adicionar_minutos_uteis_aware_preserva_tz():
    """Entrada aware BRT → retorno também aware BRT."""
    from zoneinfo import ZoneInfo

    from app.services.business_time import adicionar_minutos_uteis

    brt = ZoneInfo("America/Sao_Paulo")
    inicio = datetime(2026, 6, 22, 9, 0, tzinfo=brt)
    resultado = adicionar_minutos_uteis(inicio, 60)
    assert resultado.tzinfo is not None
    assert resultado == datetime(2026, 6, 22, 10, 0, tzinfo=brt)


def test_adicionar_dias_uteis_aware_preserva_tz():
    """Entrada aware BRT → retorno também aware BRT na mesma tz."""
    from zoneinfo import ZoneInfo

    from app.services.business_time import adicionar_dias_uteis

    brt = ZoneInfo("America/Sao_Paulo")
    inicio = datetime(2026, 6, 22, 9, 0, tzinfo=brt)  # segunda
    resultado = adicionar_dias_uteis(inicio, 2)
    assert resultado.tzinfo is not None
    assert resultado.replace(tzinfo=None) == datetime(2026, 6, 23, 16, 30)  # terça 16:30


def test_adicionar_dias_uteis_sexta_mais_2_projetos():
    """sexta + 2 dias úteis (Projetos) = segunda 16:30 (cruzando fim de semana)."""
    from app.services.business_time import adicionar_dias_uteis

    # sexta=dia1, segunda=dia2 → segunda 16:30
    resultado = adicionar_dias_uteis(datetime(2026, 6, 19, 9, 0), 2)
    assert resultado == datetime(2026, 6, 22, 16, 30)


def test_percentual_prazo_total_minutos_zero_retorna_1():
    """Branch: total_minutos==0 → retorna 1.0 (não divide por zero)."""
    from unittest.mock import patch

    from app.services.business_time import percentual_prazo_resolucao

    # Forçar minutos_uteis_entre a retornar 0 para o deadline
    with patch("app.services.business_time.minutos_uteis_entre", return_value=0):
        pct = percentual_prazo_resolucao(
            datetime(2026, 6, 22, 9, 0), "Projetos", datetime(2026, 6, 22, 9, 0)
        )
    assert pct == 1.0


def test_adicionar_minutos_uteis_negativo_levanta_erro():
    """Minutos negativos devem levantar ValueError (comportamento explícito)."""
    from app.services.business_time import adicionar_minutos_uteis

    with pytest.raises(ValueError, match="minutos"):
        adicionar_minutos_uteis(datetime(2026, 6, 22, 9, 0), -1)


# ---------------------------------------------------------------------------
# minutos_corridos_entre — tempo calendário (sem filtro de expediente), uso AOG
# ---------------------------------------------------------------------------


def test_minutos_corridos_dentro_do_expediente():
    from app.services.business_time import minutos_corridos_entre

    assert minutos_corridos_entre(datetime(2026, 6, 22, 9, 0), datetime(2026, 6, 22, 10, 0)) == 60


def test_minutos_corridos_ignora_almoco():
    from app.services.business_time import minutos_corridos_entre

    # 11:00 -> 13:30 corrido = 150 min (não desconta almoço, ao contrário de minutos_uteis_entre)
    assert (
        minutos_corridos_entre(datetime(2026, 6, 22, 11, 0), datetime(2026, 6, 22, 13, 30)) == 150
    )


def test_minutos_corridos_ignora_fim_de_semana():
    from app.services.business_time import minutos_corridos_entre

    # sábado 09:00 -> sábado 17:00 = 480 min corridos (minutos_uteis_entre seria 0)
    assert minutos_corridos_entre(datetime(2026, 6, 20, 9, 0), datetime(2026, 6, 20, 17, 0)) == 480


def test_minutos_corridos_cruzando_madrugada():
    from app.services.business_time import minutos_corridos_entre

    # 23:00 -> 01:00 do dia seguinte = 120 min, fora de qualquer janela útil
    assert minutos_corridos_entre(datetime(2026, 6, 22, 23, 0), datetime(2026, 6, 23, 1, 0)) == 120


def test_minutos_corridos_inicio_igual_fim():
    from app.services.business_time import minutos_corridos_entre

    dt = datetime(2026, 6, 22, 9, 0)
    assert minutos_corridos_entre(dt, dt) == 0


def test_minutos_corridos_fim_antes_inicio_retorna_zero():
    from app.services.business_time import minutos_corridos_entre

    assert minutos_corridos_entre(datetime(2026, 6, 22, 10, 0), datetime(2026, 6, 22, 9, 0)) == 0
