"""Testes do módulo de cache (memória e Redis)."""

import os
import sys
import time
from unittest.mock import MagicMock, patch

from app.cache import (
    cache_delete,
    cache_get,
    cache_set,
    get_static_cached,
    is_redis_available,
    static_cache_delete,
)

# ── Memória (sem Redis) ──────────────────────────────────────────────────────


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


def test_cache_get_ttl_expirado_remove_chave_memoria():
    """cache_get com TTL expirado remove a chave da memória e retorna None."""
    import app.cache as cache_mod

    key = "test_expired_ttl_key"
    cache_mod._memory_cache[key] = "dado"
    cache_mod._MEMORY_TTL[key] = time.time() - 1  # já expirou

    with patch("app.cache._get_redis", return_value=None):
        result = cache_get(key)

    assert result is None
    assert key not in cache_mod._memory_cache
    assert key not in cache_mod._MEMORY_TTL


# ── _get_redis ───────────────────────────────────────────────────────────────


def test_get_redis_retorna_none_quando_redis_url_vazia():
    """_get_redis retorna None quando REDIS_URL está vazia."""
    import app.cache as cache_mod

    original = cache_mod._redis_client
    cache_mod._redis_client = None
    try:
        with patch.dict(os.environ, {"REDIS_URL": ""}, clear=False):
            r = cache_mod._get_redis()
        assert r is None
    finally:
        cache_mod._redis_client = original


def test_get_redis_retorna_cliente_quando_url_e_ping_ok():
    """_get_redis retorna cliente Redis quando URL válida e ping bem-sucedido."""
    import app.cache as cache_mod

    original = cache_mod._redis_client
    cache_mod._redis_client = None
    mock_redis_mod = MagicMock()
    mock_client = MagicMock()
    mock_redis_mod.from_url.return_value = mock_client
    try:
        with (
            patch.dict(os.environ, {"REDIS_URL": "redis://testhost:6379"}, clear=False),
            patch.dict(sys.modules, {"redis": mock_redis_mod}),
        ):
            r = cache_mod._get_redis()
        assert r is mock_client
        mock_redis_mod.from_url.assert_called_once()
        mock_client.ping.assert_called_once()
    finally:
        cache_mod._redis_client = original


def test_get_redis_retorna_none_quando_ping_falha():
    """_get_redis retorna None quando ping levanta exceção."""
    import app.cache as cache_mod

    original = cache_mod._redis_client
    cache_mod._redis_client = None
    mock_redis_mod = MagicMock()
    mock_client = MagicMock()
    mock_client.ping.side_effect = Exception("connection refused")
    mock_redis_mod.from_url.return_value = mock_client
    try:
        with (
            patch.dict(os.environ, {"REDIS_URL": "redis://testhost:6379"}, clear=False),
            patch.dict(sys.modules, {"redis": mock_redis_mod}),
        ):
            r = cache_mod._get_redis()
        assert r is None
    finally:
        cache_mod._redis_client = original


# ── Cache com Redis ──────────────────────────────────────────────────────────


def test_cache_get_usa_redis_quando_disponivel():
    """cache_get com Redis deserializa JSON retornado pelo cliente."""
    import json

    mock_redis = MagicMock()
    mock_redis.get.return_value = json.dumps({"valor": 42})
    with patch("app.cache._get_redis", return_value=mock_redis):
        result = cache_get("redis_get_key")
    assert result == {"valor": 42}
    mock_redis.get.assert_called_once_with("redis_get_key")


def test_cache_get_redis_chave_ausente_retorna_none():
    """cache_get com Redis retorna None quando chave não existe."""
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    with patch("app.cache._get_redis", return_value=mock_redis):
        result = cache_get("missing_key")
    assert result is None


def test_cache_get_redis_excecao_retorna_none():
    """cache_get com Redis retorna None quando operação get levanta exceção."""
    mock_redis = MagicMock()
    mock_redis.get.side_effect = Exception("redis unavailable")
    with patch("app.cache._get_redis", return_value=mock_redis):
        result = cache_get("err_key")
    assert result is None


def test_cache_set_usa_redis_quando_disponivel():
    """cache_set com Redis chama setex com key, ttl e JSON serializado."""
    mock_redis = MagicMock()
    with patch("app.cache._get_redis", return_value=mock_redis):
        cache_set("set_key", [1, 2, 3], ttl_seconds=120)
    mock_redis.setex.assert_called_once()
    args = mock_redis.setex.call_args[0]
    assert args[0] == "set_key"
    assert args[1] == 120


def test_cache_set_redis_excecao_nao_propaga():
    """cache_set com Redis que levanta exceção não propaga o erro."""
    mock_redis = MagicMock()
    mock_redis.setex.side_effect = Exception("redis write error")
    with patch("app.cache._get_redis", return_value=mock_redis):
        cache_set("err_set", "value")  # não deve levantar


def test_cache_delete_usa_redis_quando_disponivel():
    """cache_delete com Redis chama r.delete com a chave."""
    mock_redis = MagicMock()
    with patch("app.cache._get_redis", return_value=mock_redis):
        cache_delete("del_key")
    mock_redis.delete.assert_called_once_with("del_key")


def test_is_redis_available_retorna_true_quando_redis_ativo():
    """is_redis_available retorna True quando _get_redis retorna um cliente."""
    mock_redis = MagicMock()
    with patch("app.cache._get_redis", return_value=mock_redis):
        assert is_redis_available() is True


# ── Cache estático (get_static_cached / static_cache_delete) ────────────────


def test_get_static_cached_chama_fetcher_na_primeira_vez():
    """get_static_cached chama fetcher quando chave não está no cache."""
    static_cache_delete("sc_first_key")
    fetcher = MagicMock(return_value={"a": 1})
    result = get_static_cached("sc_first_key", fetcher, ttl_seconds=60)
    assert result == {"a": 1}
    fetcher.assert_called_once()
    static_cache_delete("sc_first_key")


def test_get_static_cached_nao_chama_fetcher_no_cache_hit():
    """get_static_cached não chama fetcher na segunda chamada (cache hit)."""
    static_cache_delete("sc_hit_key")
    fetcher = MagicMock(return_value=42)
    get_static_cached("sc_hit_key", fetcher, ttl_seconds=60)
    get_static_cached("sc_hit_key", fetcher, ttl_seconds=60)
    assert fetcher.call_count == 1
    static_cache_delete("sc_hit_key")


def test_get_static_cached_rechama_fetcher_apos_ttl():
    """get_static_cached chama fetcher novamente após TTL expirar."""
    static_cache_delete("sc_ttl_key")
    fetcher = MagicMock(side_effect=["primeiro", "segundo"])
    get_static_cached("sc_ttl_key", fetcher, ttl_seconds=1)
    with patch("app.cache.time.time", return_value=time.time() + 200):
        result2 = get_static_cached("sc_ttl_key", fetcher, ttl_seconds=1)
    assert result2 == "segundo"
    assert fetcher.call_count == 2
    static_cache_delete("sc_ttl_key")


def test_static_cache_delete_forca_re_fetch():
    """static_cache_delete invalida cache e força nova chamada ao fetcher."""
    static_cache_delete("sc_del_key")
    fetcher = MagicMock(return_value="dado")
    get_static_cached("sc_del_key", fetcher, ttl_seconds=300)
    static_cache_delete("sc_del_key")
    get_static_cached("sc_del_key", fetcher, ttl_seconds=300)
    assert fetcher.call_count == 2
