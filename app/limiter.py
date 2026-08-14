"""
Rate limiter compartilhado entre blueprints.

Em produção: use REDIS_URL em config para que o limite seja compartilhado entre
todos os workers (Gunicorn/Cloud Run). Sem Redis, cada processo tem seu próprio
contador em memória (limites efetivos maiores por usuário).
"""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import current_user


def rate_limit_key() -> str:
    """Separa usuários autenticados por IP+ID e pré-auth apenas por IP."""
    ip = get_remote_address()
    if current_user.is_authenticated and getattr(current_user, "id", None):
        return f"{ip}:user:{current_user.id}"
    return ip


limiter = Limiter(key_func=rate_limit_key)
