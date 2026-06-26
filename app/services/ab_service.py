"""Serviço de A/B testing determinístico por usuário."""

import hashlib


def get_variante(uid: str, experimento_id: str, split: float = 0.5) -> str:
    """Retorna 'A' ou 'B' de forma determinística por usuário e experimento.

    A determinismo garante que o mesmo usuário sempre vê a mesma variante,
    sem cookie extra. O split padrão é 50/50.
    """
    hash_val = int(
        hashlib.md5(f"{experimento_id}:{uid}".encode(), usedforsecurity=False).hexdigest(), 16
    )
    return "B" if (hash_val % 100) < int(split * 100) else "A"
