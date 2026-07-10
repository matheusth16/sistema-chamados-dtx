"""Motor de Tempo Útil DTX.

Janela útil: seg–sex, 07:00–11:30, 13:00–16:30 (BRT).
Sábado e domingo são excluídos na v1.

SLA_INCLUI_FIM_DE_SEMANA existe em config.py mas não está conectada à lógica
nesta versão (v1): sáb/dom são sempre excluídos. A flag está reservada para v2
caso seja necessário incluir fins de semana excepcionais.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from config import Config

_TZ = ZoneInfo(Config.SLA_TIMEZONE)

_INICIO = time(*map(int, Config.SLA_HORARIO_INICIO.split(":")))
_FIM = time(*map(int, Config.SLA_HORARIO_FIM.split(":")))
_ALMOCO_INI = time(*map(int, Config.SLA_ALMOCO_INICIO.split(":")))
_ALMOCO_FIM = time(*map(int, Config.SLA_ALMOCO_FIM.split(":")))

# Minutos úteis por dia de trabalho completo (manhã + tarde, sem almoço).
# Exposta para uso nos jobs de escalada (Fases 6-7).
MINUTOS_UTEIS_DIA: int = (
    (_ALMOCO_INI.hour * 60 + _ALMOCO_INI.minute)
    - (_INICIO.hour * 60 + _INICIO.minute)
    + (_FIM.hour * 60 + _FIM.minute)
    - (_ALMOCO_FIM.hour * 60 + _ALMOCO_FIM.minute)
)


def _as_local(dt: datetime) -> datetime:
    """Normaliza dt para BRT: naive → assume BRT; aware → converte para BRT."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_TZ)
    return dt.astimezone(_TZ)


def dentro_janela_util(dt: datetime) -> bool:
    """True se o instante cai dentro da janela de expediente DTX."""
    local = _as_local(dt)
    if local.weekday() >= 5:  # sábado=5, domingo=6
        return False
    t = local.time().replace(second=0, microsecond=0)
    if t < _INICIO or t >= _FIM:
        return False
    return not _ALMOCO_INI <= t < _ALMOCO_FIM


def pode_enviar_notificacao_agora(dt: datetime) -> bool:
    """Alias de dentro_janela_util — indica se é seguro disparar notificações."""
    return dentro_janela_util(dt)


def minutos_uteis_entre(inicio: datetime, fim: datetime) -> int:
    """Conta minutos úteis entre dois instantes (início inclusivo, fim exclusivo)."""
    inicio_local = _as_local(inicio)
    fim_local = _as_local(fim)
    if fim_local <= inicio_local:
        return 0
    contagem = 0
    cursor = inicio_local.replace(second=0, microsecond=0)
    fim_trunc = fim_local.replace(second=0, microsecond=0)
    while cursor < fim_trunc:
        if dentro_janela_util(cursor):
            contagem += 1
        cursor += timedelta(minutes=1)
    return contagem


def adicionar_minutos_uteis(inicio: datetime, minutos: int) -> datetime:
    """Avança `minutos` minutos úteis a partir de `inicio`.

    Raises:
        ValueError: se `minutos` for negativo.
    """
    if minutos < 0:
        raise ValueError(f"minutos deve ser >= 0, recebido: {minutos}")
    if minutos == 0:
        return inicio
    local = _as_local(inicio).replace(second=0, microsecond=0)
    restante = minutos
    while restante > 0:
        local += timedelta(minutes=1)
        if dentro_janela_util(local):
            restante -= 1
    # Retorna naive se a entrada era naive
    if inicio.tzinfo is None:
        return local.replace(tzinfo=None)
    return local


def minutos_corridos_entre(inicio: datetime, fim: datetime) -> int:
    """Conta minutos corridos (calendário) entre dois instantes, sem filtro de expediente.

    Uso exclusivo AOG (Config.SLA_AOG_*): aeronave parada não espera expediente —
    diferente de minutos_uteis_entre, não desconta fim de semana, almoço nem fora
    da janela DTX.
    """
    inicio_local = _as_local(inicio)
    fim_local = _as_local(fim)
    if fim_local <= inicio_local:
        return 0
    return int((fim_local - inicio_local).total_seconds() // 60)


def adicionar_dias_uteis(inicio: datetime, n: int) -> datetime:
    """Retorna o N-ésimo dia útil a partir de `inicio` (inclusive), às 16:30 (teto DTX).

    O dia de `inicio` conta como dia 1 se for dia útil; fins-de-semana são pulados.
    Exemplo: segunda + 2 = terça 16:30; sexta + 3 = terça 16:30 (próx. semana).
    """
    local = _as_local(inicio)
    cursor = local.replace(hour=0, minute=0, second=0, microsecond=0)
    dias_uteis = 0
    while True:
        if cursor.weekday() < 5:  # seg–sex
            dias_uteis += 1
            if dias_uteis == n:
                resultado = cursor.replace(
                    hour=_FIM.hour, minute=_FIM.minute, second=0, microsecond=0
                )
                if inicio.tzinfo is None:
                    return resultado.replace(tzinfo=None)
                return resultado
        cursor += timedelta(days=1)


def percentual_prazo_resolucao(
    data_em_atendimento: datetime,
    categoria: str,
    agora: datetime,
) -> float:
    """Retorna o percentual (0.0–1.0+) do prazo de resolução consumido.

    Projetos → SLA_DIAS_RESOLUCAO_PROJETOS dias úteis.
    Demais    → SLA_DIAS_RESOLUCAO_PADRAO dias úteis.
    """
    from config import Config

    dias = (
        Config.SLA_DIAS_RESOLUCAO_PROJETOS
        if categoria == "Projetos"
        else Config.SLA_DIAS_RESOLUCAO_PADRAO
    )
    deadline = adicionar_dias_uteis(data_em_atendimento, dias)
    total_minutos = minutos_uteis_entre(data_em_atendimento, deadline)
    if total_minutos == 0:
        return 1.0
    decorridos = minutos_uteis_entre(data_em_atendimento, agora)
    return decorridos / total_minutos
