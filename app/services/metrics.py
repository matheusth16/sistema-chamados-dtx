"""
Métricas de negócio — log estruturado de eventos.

Emit eventos chave como linhas JSON no logger `app.metrics`. No Railway,
essas linhas aparecem nos logs do deploy e podem ser exportadas via log drain
para qualquer destino (Datadog, Logtail, etc.).

Uso:
    from app.services.metrics import log_evento

    log_evento("chamado_criado", user_id=uid, setor=setor, tipo=tipo)
    log_evento("status_alterado", chamado_id=cid, de="Aberto", para="Concluído")
"""

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from typing import Any

logger = logging.getLogger("app.metrics")


def log_evento(evento: str, **campos: Any) -> None:
    """Emite um evento de negócio como linha de log estruturado.

    Args:
        evento: Nome do evento (ex: "chamado_criado", "login_sucesso").
        **campos: Metadados do evento (user_id, chamado_id, duração, etc.).
    """
    logger.info(
        "event=%s ts=%s %s",
        evento,
        datetime.now(UTC).isoformat(),
        " ".join(f"{k}={v}" for k, v in campos.items() if v is not None),
    )


# ---------------------------------------------------------------------------
# Eventos de chamados
# ---------------------------------------------------------------------------


def chamado_criado(user_id: str, chamado_id: str, setor: str, tipo: str) -> None:
    log_evento("chamado_criado", user_id=user_id, chamado_id=chamado_id, setor=setor, tipo=tipo)


def chamado_status_alterado(
    chamado_id: str, de: str, para: str, user_id: str | None = None
) -> None:
    log_evento("chamado_status_alterado", chamado_id=chamado_id, de=de, para=para, user_id=user_id)


def chamado_resolucao_confirmada(chamado_id: str, user_id: str) -> None:
    log_evento("chamado_resolucao_confirmada", chamado_id=chamado_id, user_id=user_id)


# ---------------------------------------------------------------------------
# Eventos de autenticação
# ---------------------------------------------------------------------------


def login_sucesso(user_id: str, perfil: str) -> None:
    log_evento("login_sucesso", user_id=user_id, perfil=perfil)


def login_falha(email: str, motivo: str = "credenciais") -> None:
    # Não loga o email diretamente para evitar dados pessoais no log
    log_evento("login_falha", motivo=motivo)


def logout(user_id: str) -> None:
    log_evento("logout", user_id=user_id)


# ---------------------------------------------------------------------------
# Eventos de SLA
# ---------------------------------------------------------------------------


def sla_prazo_proximo(chamado_id: str, horas_restantes: float) -> None:
    log_evento(
        "sla_prazo_proximo", chamado_id=chamado_id, horas_restantes=round(horas_restantes, 1)
    )


def sla_vencido(chamado_id: str) -> None:
    log_evento("sla_vencido", chamado_id=chamado_id)


# ---------------------------------------------------------------------------
# Decorador de performance para serviços críticos
# ---------------------------------------------------------------------------


def medir_duracao(nome_operacao: str) -> Callable:
    """Decorador que registra duração em ms de uma função no logger de métricas.

    Uso:
        @medir_duracao("firestore_query_chamados")
        def buscar_chamados(...): ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            t0 = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                duracao_ms = round((time.perf_counter() - t0) * 1000, 1)
                log_evento("operacao_ok", operacao=nome_operacao, duration_ms=duracao_ms)
                return result
            except Exception:
                duracao_ms = round((time.perf_counter() - t0) * 1000, 1)
                log_evento("operacao_erro", operacao=nome_operacao, duration_ms=duracao_ms)
                raise

        return wrapper

    return decorator
