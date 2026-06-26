"""Service de gates: constrói o dict de sub-etapas e valida valores.

Firestore é a fonte de verdade. Fallback para GATE_SUBETAPAS estático se o
banco estiver vazio ou inacessível (ex.: ambiente de testes sem credenciais).
"""

import logging

from app.cache import get_static_cached
from app.gates_config import GATE_SUBETAPAS, todos_valores_gate_validos
from app.models_categorias import CategoriaGate

logger = logging.getLogger(__name__)

_GATES_VALIDOS_CACHE_KEY = "gates_validos_set"
_GATES_VALIDOS_TTL = 300  # 5 minutos


def build_gate_subetapas() -> dict[str, list[str]]:
    """Retorna dict {gate_pai: [nome_pt, ...]} a partir do Firestore.

    Fallback: GATE_SUBETAPAS estático se Firestore vazio ou com erro.
    """
    try:
        gates = CategoriaGate.get_all_ativos()
        if not gates:
            return dict(GATE_SUBETAPAS)
        result: dict[str, list[str]] = {}
        for gate in gates:
            if gate.gate_pai and gate.nome_pt:
                result.setdefault(gate.gate_pai, []).append(gate.nome_pt)
        return result if result else dict(GATE_SUBETAPAS)
    except Exception as e:
        logger.warning("Erro ao buscar gates do Firestore, usando fallback estático: %s", e)
        return dict(GATE_SUBETAPAS)


def is_gate_valido(valor: str) -> bool:
    """Retorna True se valor == 'N/A' ou existe gate ativo com nome_pt == valor.

    Fallback: allowlist estática de GATE_SUBETAPAS se Firestore vazio ou com erro.
    Resultado é cacheado 5 min para evitar leitura no Firestore a cada validação.
    """
    if valor == "N/A":
        return True

    def _fetch() -> frozenset[str]:
        try:
            gates = CategoriaGate.get_all_ativos()
            if gates:
                return frozenset(g.nome_pt for g in gates)
        except Exception as e:
            logger.warning("Erro ao validar gate no Firestore, usando fallback estático: %s", e)
        return frozenset()

    gate_names = get_static_cached(_GATES_VALIDOS_CACHE_KEY, _fetch, ttl_seconds=_GATES_VALIDOS_TTL)
    if gate_names:
        return valor in gate_names
    return valor in todos_valores_gate_validos()
