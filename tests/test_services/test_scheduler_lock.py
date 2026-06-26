"""Testes do lock distribuído Redis para jobs APScheduler (S4-01 / F-02)."""

from unittest.mock import MagicMock, patch


def test_executar_sem_redis_url_chama_job_diretamente(app):
    """Sem REDIS_URL configurada, fn_job() é chamado diretamente."""
    from app.services.scheduler_lock import executar_job_com_lock

    app.config.pop("REDIS_URL", None)
    fn = MagicMock()
    with patch.dict("os.environ", {"REDIS_URL": ""}):
        executar_job_com_lock(app, "job_teste", fn)
    fn.assert_called_once()


def test_executar_com_redis_lock_adquirido_chama_job(app):
    """Com Redis disponível e lock adquirido, fn_job() é executado."""
    from app.services.scheduler_lock import executar_job_com_lock

    fn = MagicMock()
    mock_redis_inst = MagicMock()
    mock_lock_ctx = MagicMock()
    mock_lock_ctx.__enter__ = MagicMock(return_value=None)
    mock_lock_ctx.__exit__ = MagicMock(return_value=False)
    mock_redis_inst.lock.return_value = mock_lock_ctx

    with (
        patch.dict(app.config, {"REDIS_URL": "redis://localhost:6379"}),
        patch("redis.from_url", return_value=mock_redis_inst),
    ):
        executar_job_com_lock(app, "job_teste", fn)

    fn.assert_called_once()
    mock_redis_inst.lock.assert_called_once_with(
        "scheduler_lock:job_teste", timeout=300, blocking_timeout=0
    )


def test_executar_com_redis_lock_error_nao_chama_job(app):
    """Com LockError (outro worker já executa), fn_job() NÃO é chamado."""
    from redis.exceptions import LockError

    from app.services.scheduler_lock import executar_job_com_lock

    fn = MagicMock()
    mock_redis_inst = MagicMock()
    mock_redis_inst.lock.side_effect = LockError("already locked")

    with (
        patch.dict(app.config, {"REDIS_URL": "redis://localhost:6379"}),
        patch("redis.from_url", return_value=mock_redis_inst),
    ):
        executar_job_com_lock(app, "job_teste", fn)

    fn.assert_not_called()


def test_executar_redis_excecao_generica_chama_job_como_fallback(app):
    """Exceção genérica ao adquirir lock → fn_job() é executado como fallback."""
    from app.services.scheduler_lock import executar_job_com_lock

    fn = MagicMock()
    mock_redis_inst = MagicMock()
    mock_redis_inst.lock.side_effect = ConnectionError("redis unreachable")

    with (
        patch.dict(app.config, {"REDIS_URL": "redis://localhost:6379"}),
        patch("redis.from_url", return_value=mock_redis_inst),
    ):
        executar_job_com_lock(app, "job_teste", fn)

    fn.assert_called_once()


def test_executar_sem_redis_py_chama_job_como_fallback(app):
    """Se redis-py não estiver instalado, fn_job() é chamado sem lock."""
    from app.services.scheduler_lock import executar_job_com_lock

    fn = MagicMock()
    with (
        patch.dict(app.config, {"REDIS_URL": "redis://localhost:6379"}),
        patch.dict("os.environ", {"REDIS_URL": "redis://localhost:6379"}),
        patch.dict("sys.modules", {"redis": None}),
    ):
        executar_job_com_lock(app, "job_teste", fn)

    fn.assert_called_once()
