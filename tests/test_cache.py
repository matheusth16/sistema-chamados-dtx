"""Testes do módulo de cache (fallback em memória quando Redis não está configurado)."""

from unittest.mock import patch

from app.cache import cache_delete, cache_get, cache_set, is_redis_available


def test_cache_set_get_sem_redis():
    """Com _get_redis retornando None, cache_set e cache_get usam memória e funcionam."""
    with patch("app.cache._get_redis", return_value=None):
        cache_delete("test_key_i18n_xyz")
        cache_set("test_key_i18n_xyz", 42, ttl_seconds=60)
        val = cache_get("test_key_i18n_xyz")
        assert val == 42
        cache_delete("test_key_i18n_xyz")
        assert cache_get("test_key_i18n_xyz") is None


def test_cache_delete_chave_inexistente_nao_quebra():
    """cache_delete de chave inexistente não levanta exceção."""
    with patch("app.cache._get_redis", return_value=None):
        cache_delete("chave_que_nao_existe_abc")
        cache_delete("outra_chave_xyz")


def test_is_redis_available_reflete_estado():
    """is_redis_available retorna False quando _get_redis retorna None."""
    with patch("app.cache._get_redis", return_value=None):
        assert is_redis_available() is False
