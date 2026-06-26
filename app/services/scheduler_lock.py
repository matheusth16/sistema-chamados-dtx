"""
Lock distribuído via Redis para jobs APScheduler.

Garante que em implantações multi-worker (Gunicorn, Cloud Run) apenas um
processo execute cada job por vez, evitando e-mails duplicados.

Sem REDIS_URL configurada, o job executa diretamente (modo dev/single-worker).
"""

import logging
import os

logger = logging.getLogger(__name__)


def executar_job_com_lock(app, nome_job: str, fn_job) -> None:
    """Executa fn_job em apenas um worker por vez quando REDIS_URL está configurada.

    Sem REDIS_URL → executa diretamente (single-worker / dev).
    Com Redis → adquire lock não-bloqueante; outros workers pulam o job.
    """
    redis_url = (app.config.get("REDIS_URL") or os.getenv("REDIS_URL", "")).strip()
    if not redis_url:
        fn_job()
        return

    try:
        import redis
        from redis.exceptions import LockError
    except ImportError:
        logger.warning("redis-py não instalado; executando job '%s' sem lock.", nome_job)
        fn_job()
        return

    lock_key = f"scheduler_lock:{nome_job}"
    try:
        r = redis.from_url(redis_url)
        with r.lock(lock_key, timeout=300, blocking_timeout=0):
            fn_job()
    except LockError:
        logger.debug("Job '%s' já em execução em outro worker, pulando.", nome_job)
    except Exception as exc:
        logger.exception("Erro ao adquirir lock para job '%s': %s", nome_job, exc)
        fn_job()
