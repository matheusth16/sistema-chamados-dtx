"""Geração de senha aleatória segura.

Extraído de app/routes/usuarios.py (era privado, usado só na criação/reset
manual de conta pelo admin) pra ser reaproveitado por
app/services/mfa_lembrete_service.py — que reseta a senha de contas nunca
acessadas (must_change_password=True) junto com o lembrete de MFA pendente.
"""

import secrets
import string


def gerar_senha_aleatoria(tamanho: int = 12) -> str:
    """Gera senha aleatória segura com maiúsculas, minúsculas, dígitos e símbolos.
    Garante ao menos 1 char de cada classe para satisfazer políticas de complexidade."""
    especiais = "!@#$%&*"
    alfabeto = string.ascii_letters + string.digits + especiais
    # Posições fixas garantem representação mínima de cada classe
    obrigatorios = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice(especiais),
    ]
    restante = [secrets.choice(alfabeto) for _ in range(tamanho - 4)]
    senha = obrigatorios + restante
    secrets.SystemRandom().shuffle(senha)
    return "".join(senha)
