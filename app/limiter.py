"""
Rate limiter compartilhado entre blueprints.

Em produção: use REDIS_URL em config para que o limite seja compartilhado entre
todos os workers (Gunicorn/Cloud Run). Sem Redis, cada processo tem seu próprio
contador em memória (limites efetivos maiores por usuário).
"""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["2000 per day", "200 per hour"],
)
