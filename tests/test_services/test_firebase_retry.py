"""Testes para firebase_retry.py — retry com backoff exponencial."""

from unittest.mock import MagicMock, patch

import pytest
from google.api_core.exceptions import ServiceUnavailable


def _wrap(mock_call):
    """Envolve um MagicMock numa função nomeada para compatibilidade com firebase_retry."""

    def _func(*args, **kwargs):
        return mock_call(*args, **kwargs)

    return _func


# ── firebase_retry decorator ───────────────────────────────────────────────────


def test_firebase_retry_sucesso_na_primeira_tentativa():
    from app.firebase_retry import firebase_retry

    call = MagicMock(return_value="ok")
    decorated = firebase_retry(max_retries=3)(_wrap(call))
    result = decorated()
    assert result == "ok"
    assert call.call_count == 1


def test_firebase_retry_sucesso_na_segunda_tentativa():
    from app.firebase_retry import firebase_retry

    call = MagicMock(side_effect=[ServiceUnavailable("temp"), "ok"])
    with patch("app.firebase_retry.time.sleep"):
        decorated = firebase_retry(max_retries=3, initial_delay=0.01)(_wrap(call))
        result = decorated()
    assert result == "ok"
    assert call.call_count == 2


def test_firebase_retry_esgota_tentativas_e_levanta_excecao():
    from app.firebase_retry import firebase_retry

    call = MagicMock(side_effect=ServiceUnavailable("persistente"))
    with patch("app.firebase_retry.time.sleep"):
        decorated = firebase_retry(max_retries=3, initial_delay=0.01)(_wrap(call))
        with pytest.raises(ServiceUnavailable):
            decorated()
    assert call.call_count == 3


def test_firebase_retry_excecao_nao_retentavel_levanta_imediatamente():
    from app.firebase_retry import firebase_retry

    call = MagicMock(side_effect=ValueError("invalido"))
    decorated = firebase_retry(max_retries=3)(_wrap(call))
    with pytest.raises(ValueError, match="invalido"):
        decorated()
    assert call.call_count == 1


def test_firebase_retry_passa_argumentos():
    from app.firebase_retry import firebase_retry

    call = MagicMock(return_value=42)
    decorated = firebase_retry()(_wrap(call))
    result = decorated("arg1", key="val")
    assert result == 42
    call.assert_called_once_with("arg1", key="val")


# ── firebase_retry_transaction ─────────────────────────────────────────────────


def test_firebase_retry_transaction_retorna_decorador():
    from app.firebase_retry import firebase_retry_transaction

    deco = firebase_retry_transaction(max_retries=2, initial_delay=0.1)
    assert callable(deco)


def test_firebase_retry_transaction_sucesso():
    from app.firebase_retry import firebase_retry_transaction

    call = MagicMock(return_value="tx_ok")
    decorated = firebase_retry_transaction(max_retries=2)(_wrap(call))
    result = decorated()
    assert result == "tx_ok"


# ── execute_with_retry ─────────────────────────────────────────────────────────


def test_execute_with_retry_sucesso():
    from app.firebase_retry import execute_with_retry

    func = MagicMock(return_value="resultado")
    result = execute_with_retry(func, "a", "b", max_retries=2)
    assert result == "resultado"
    func.assert_called_once_with("a", "b")


def test_execute_with_retry_retenta_em_erro_transitorio():
    from app.firebase_retry import execute_with_retry

    func = MagicMock(side_effect=[ServiceUnavailable("t"), "retentou"])
    with patch("app.firebase_retry.time.sleep"):
        result = execute_with_retry(func, max_retries=3, initial_delay=0.01)
    assert result == "retentou"
