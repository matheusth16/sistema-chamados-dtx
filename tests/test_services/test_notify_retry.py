"""Testes unitários do utilitário de retry com backoff exponencial."""

from unittest.mock import patch

import pytest


def test_executar_com_retry_sucesso_na_primeira_tentativa():
    """Função que tem sucesso imediato é chamada uma vez e retorna o valor."""
    from app.services.notify_retry import executar_com_retry

    def func(x):
        return x * 2

    result = executar_com_retry(func, 5)
    assert result == 10


def test_executar_com_retry_sucesso_na_terceira_tentativa():
    """Função que falha duas vezes e tem sucesso na terceira é chamada 3x e retorna o valor."""
    from app.services.notify_retry import executar_com_retry

    call_count = 0

    def flaky_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("temporário")
        return "ok"

    with patch("app.services.notify_retry.time.sleep"):
        result = executar_com_retry(flaky_func, max_tentativas=3, backoff_base=1.0)

    assert result == "ok"
    assert call_count == 3


def test_executar_com_retry_todas_tentativas_falham_propaga_excecao():
    """Quando todas as tentativas falham, a última exceção é propagada."""
    from app.services.notify_retry import executar_com_retry

    def always_fails():
        raise ValueError("sempre falha")

    with (
        patch("app.services.notify_retry.time.sleep"),
        pytest.raises(ValueError, match="sempre falha"),
    ):
        executar_com_retry(always_fails, max_tentativas=3, backoff_base=1.0)


def test_executar_com_retry_registra_warning_entre_tentativas():
    """Warning é logado entre tentativas fracassadas."""
    from app.services.notify_retry import executar_com_retry

    call_count = 0

    def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RuntimeError("falha temporária")
        return "pronto"

    with (
        patch("app.services.notify_retry.time.sleep"),
        patch("app.services.notify_retry.logger") as mock_logger,
    ):
        result = executar_com_retry(flaky, max_tentativas=3, backoff_base=1.0)

    assert result == "pronto"
    assert mock_logger.warning.call_count == 2  # 2 tentativas com falha → 2 warnings
