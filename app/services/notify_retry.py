"""
Utilitário de retry com backoff exponencial para notificações.

Uso: substituir threading.Thread fire-and-forget por uma thread com retry.
Se o servidor de e-mail estiver temporariamente indisponível, as tentativas
são repetidas com espera crescente antes de desistir e logar o erro.
"""

import logging
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


def executar_com_retry(
    func: Callable,
    *args: Any,
    max_tentativas: int = 3,
    backoff_base: float = 2.0,
    **kwargs: Any,
) -> Any:
    """Executa func(*args, **kwargs) com retry e backoff exponencial.

    Espera entre tentativas: backoff_base^0 = 1s, backoff_base^1 = 2s, etc.
    Se todas as tentativas falharem, loga o erro e propaga a última exceção.

    Args:
        func: callable a executar
        *args: argumentos posicionais para func
        max_tentativas: número máximo de tentativas (padrão 3)
        backoff_base: base do backoff exponencial em segundos (padrão 2.0)
        **kwargs: argumentos nomeados para func

    Returns:
        Retorno de func em caso de sucesso.

    Raises:
        Exception: última exceção se todas as tentativas falharem.
    """
    ultima_exc: Exception | None = None
    for tentativa in range(max_tentativas):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            ultima_exc = exc
            if tentativa < max_tentativas - 1:
                espera = backoff_base**tentativa
                logger.warning(
                    "%s falhou (tentativa %d/%d): %s. Retry em %.0fs.",
                    getattr(func, "__name__", str(func)),
                    tentativa + 1,
                    max_tentativas,
                    exc,
                    espera,
                )
                time.sleep(espera)
            else:
                logger.error(
                    "%s falhou após %d tentativas: %s",
                    getattr(func, "__name__", str(func)),
                    max_tentativas,
                    exc,
                )
    raise ultima_exc
