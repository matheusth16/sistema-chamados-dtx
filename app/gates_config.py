"""Configuração canônica de Gates e sub-etapas DTX.

Valores gravados no Firestore são sempre os valores PT completos, ex.:
'Gate 1 - Desmontagem'. A tradução para exibição é feita via i18n.
"""

# Opções do select pai (valor, label PT)
GATE_PAI_OPCOES: list[tuple[str, str]] = [
    ("N/A", "N/A"),
    ("Gate 1", "Gate 1"),
    ("Gate 2", "Gate 2"),
    ("Gate 3", "Gate 3"),
    ("Gate 4", "Gate 4"),
]

# Sub-etapas por gate — valores canônicos gravados no Firestore
GATE_SUBETAPAS: dict[str, list[str]] = {
    "Gate 1": [
        "Gate 1 - Desmontagem",
        "Gate 1 - Limpeza",
        "Gate 1 - Remoção de Tinta",
        "Gate 1 - Reconciliação",
    ],
    "Gate 2": [
        "Gate 2 - Forno",
        "Gate 2 - FPI",
        "Gate 2 - MPI",
        "Gate 2 - Inspeção",
    ],
    "Gate 3": [
        "Gate 3 - Galvanoplastia",
        "Gate 3 - Usinagem",
        "Gate 3 - Bucha",
        "Gate 3 - Pintura",
    ],
    "Gate 4": [
        "Gate 4 - Inspeção de Partes",
        "Gate 4 - Montagem",
        "Gate 4 - Testes",
        "Gate 4 - Inspeção Final",
    ],
}

# Allowlist completa de valores aceitos em novos chamados
_TODOS_VALORES: set[str] | None = None


def todos_valores_gate_validos() -> set[str]:
    """Retorna conjunto completo de valores aceitos (N/A + 16 valores completos)."""
    global _TODOS_VALORES
    if _TODOS_VALORES is None:
        validos: set[str] = {"N/A"}
        for etapas in GATE_SUBETAPAS.values():
            validos.update(etapas)
        _TODOS_VALORES = validos
    return _TODOS_VALORES


def gate_valor_completo(gate_pai: str, etapa: str) -> str:
    """Monta o valor canônico a partir do gate pai e da etapa selecionada."""
    if gate_pai == "N/A":
        return "N/A"
    return f"{gate_pai} - {etapa}"


def is_gate_valido(valor: str) -> bool:
    """Retorna True se o valor estiver na allowlist de valores aceitos em novos chamados."""
    return valor in todos_valores_gate_validos()
