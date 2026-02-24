"""
Cache opcional com Redis para relatórios e listas.

- Se REDIS_URL estiver definida no ambiente: usa Redis (compartilhado entre workers).
- Senão: usa cache em memória (dict) por processo.

Reduz 30-50% de queries ao Firestore em relatórios e listas pesadas.
Em produção com Gunicorn/Cloud Run, defina REDIS_URL para cache e rate limit compartilhados.
"""
import os
import time
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_redis_client = None
_memory_cache: dict = {}
_MEMORY_TTL: dict = {}  # key -> expires_at


def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    url = os.getenv('REDIS_URL', '').strip()
    if not url:
        return None
    try:
        import redis
        _redis_client = redis.from_url(url, decode_responses=True)
        _redis_client.ping()
        logger.info("Cache Redis conectado")
        return _redis_client
    except Exception as e:
        logger.warning("Redis não disponível, usando cache em memória: %s", e)
        return None


def cache_get(key: str) -> Optional[Any]:
    """Obtém valor do cache. Retorna None se não existir ou estiver expirado."""
    r = _get_redis()
    if r:
        try:
            import json
            val = r.get(key)
            return json.loads(val) if val else None
        except Exception as e:
            logger.debug("Cache get falhou: %s", e)
            return None
    # Memória
    if key in _MEMORY_TTL and time.time() < _MEMORY_TTL[key]:
        return _memory_cache.get(key)
    if key in _memory_cache:
        del _memory_cache[key]
        del _MEMORY_TTL[key]
    return None


def cache_set(key: str, value: Any, ttl_seconds: int = 300) -> None:
    """Grava valor no cache com TTL em segundos."""
    r = _get_redis()
    if r:
        try:
            import json
            r.setex(key, ttl_seconds, json.dumps(value, default=str))
        except Exception as e:
            logger.debug("Cache set falhou: %s", e)
        return
    _memory_cache[key] = value
    _MEMORY_TTL[key] = time.time() + ttl_seconds


def cache_delete(key: str) -> None:
    """Remove uma chave do cache."""
    r = _get_redis()
    if r:
        try:
            r.delete(key)
        except Exception:
            pass
        return
    _memory_cache.pop(key, None)
    _MEMORY_TTL.pop(key, None)


def is_redis_available() -> bool:
    """Retorna True se o Redis está em uso."""
    return _get_redis() is not None
