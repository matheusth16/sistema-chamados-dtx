"""
Utilitário para retry de operações Firebase com backoff exponencial.
Implementa padrão de retry automático para falhas de conexão e indisponibilidade.
"""

import time
import logging
from typing import TypeVar, Callable, Any
from functools import wraps
from google.api_core.exceptions import (
    DeadlineExceeded,
    Unknown,
    InternalServerError,
    ServiceUnavailable
)

logger = logging.getLogger(__name__)

# Exceções do Firebase que são retentáveis
RETRYABLE_EXCEPTIONS = (
    DeadlineExceeded,
    Unknown,
    InternalServerError,
    ServiceUnavailable
)

F = TypeVar('F', bound=Callable[..., Any])


def firebase_retry(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 32.0,
    exponential_base: float = 2.0
) -> Callable[[F], F]:
    """
    Decorator para retry automático em operações Firebase com backoff exponencial.
    
    Args:
        max_retries: Número máximo de tentativas (incluindo a primeira)
        initial_delay: Delay inicial em segundos
        max_delay: Delay máximo em segundos
        exponential_base: Multiplicador para backoff exponencial (padrão: 2.0)
    
    Exemplo:
        @firebase_retry(max_retries=3)
        def salvar_documento(doc_ref, data):
            doc_ref.set(data)
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    logger.debug(f"Firebase operation '{func.__name__}' - attempt {attempt + 1}/{max_retries}")
                    return func(*args, **kwargs)
                
                except RETRYABLE_EXCEPTIONS as e:
                    last_exception = e
                    
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"Firebase operation '{func.__name__}' failed (attempt {attempt + 1}/{max_retries}): {type(e).__name__}. "
                            f"Retrying in {delay:.1f}s..."
                        )
                        time.sleep(delay)
                        delay = min(delay * exponential_base, max_delay)
                    else:
                        logger.error(
                            f"Firebase operation '{func.__name__}' failed after {max_retries} attempts: {e}"
                        )
                
                except Exception as e:
                    # Exceções não-retentáveis são relançadas imediatamente
                    logger.error(f"Firebase operation '{func.__name__}' failed with non-retryable error: {e}")
                    raise
            
            # Se chegou aqui, todos os retries falharam
            if last_exception:
                raise last_exception
        
        return wrapper
    
    return decorator


def firebase_retry_transaction(
    max_retries: int = 3,
    initial_delay: float = 0.5,
    max_delay: float = 10.0
):
    """
    Retry decorator específico para transações Firestore.
    Usa delays menores que operações normais.
    
    Args:
        max_retries: Número máximo de tentativas
        initial_delay: Delay inicial em segundos (padrão: 0.5)
        max_delay: Delay máximo em segundos
    """
    return firebase_retry(
        max_retries=max_retries,
        initial_delay=initial_delay,
        max_delay=max_delay,
        exponential_base=2.0
    )


def execute_with_retry(
    func: Callable,
    *args,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    **kwargs
) -> Any:
    """
    Executa uma função com retry (alternativa à decorator).
    
    Args:
        func: Função a executar
        *args: Argumentos posicionais
        max_retries: Número máximo de tentativas
        initial_delay: Delay inicial em segundos
        **kwargs: Argumentos nomeados
    
    Retorna:
        Resultado da função
    
    Exemplo:
        resultado = execute_with_retry(
            db.collection('usuarios').document(user_id).set,
            user_data,
            max_retries=3
        )
    """
    decorated_func = firebase_retry(max_retries=max_retries, initial_delay=initial_delay)(
        lambda: func(*args, **kwargs)
    )
    return decorated_func()
