"""Testes do serviço de tentativas de login (LoginAttemptTracker)."""

from unittest.mock import patch

from app.services.login_attempts import (
    LoginAttemptTracker,
    MAX_LOGIN_ATTEMPTS,
)


def test_get_attempt_count_sem_tentativas_retorna_zero():
    """get_attempt_count sem tentativas em cache retorna 0."""
    with patch('app.services.login_attempts.cache_get', return_value=None):
        count = LoginAttemptTracker.get_attempt_count('192.168.1.1')
    assert count == 0


def test_get_attempt_count_com_tentativas_retorna_valor():
    """get_attempt_count com valor em cache retorna o valor."""
    with patch('app.services.login_attempts.cache_get', return_value=3):
        count = LoginAttemptTracker.get_attempt_count('user@test.com')
    assert count == 3


def test_increment_attempt_aumenta_contador():
    """increment_attempt retorna contador incrementado e chama cache_set."""
    with patch('app.services.login_attempts.cache_get', return_value=2):
        with patch('app.services.login_attempts.cache_set') as mock_set:
            new_count = LoginAttemptTracker.increment_attempt('ip1')
    assert new_count == 3
    mock_set.assert_called_once()
    assert mock_set.call_args[0][1] == 3


def test_is_locked_out_sem_lockout_retorna_false():
    """is_locked_out quando não há chave de lockout retorna False."""
    with patch('app.services.login_attempts.cache_get', return_value=None):
        assert LoginAttemptTracker.is_locked_out('ip1') is False


def test_is_locked_out_com_lockout_retorna_true():
    """is_locked_out quando há chave de lockout retorna True."""
    with patch('app.services.login_attempts.cache_get', return_value=True):
        assert LoginAttemptTracker.is_locked_out('ip1') is True


def test_reset_attempts_limpa_cache():
    """reset_attempts chama cache_delete para attempt e lockout."""
    with patch('app.services.login_attempts.cache_delete') as mock_del:
        LoginAttemptTracker.reset_attempts('email@test.com')
    assert mock_del.call_count == 2
    calls = [c[0][0] for c in mock_del.call_args_list]
    assert 'login_attempt:email@test.com' in calls
    assert 'login_lockout:email@test.com' in calls
