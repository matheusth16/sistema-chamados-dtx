"""
Mapeamento entre nome do setor (formulário) e área usada no cadastro de usuários.
Firestore é a fonte de verdade (doc config/setor_para_area, campo mapa).
Fallback: SETOR_PARA_AREA estático se Firestore vazio ou inacessível.
Cache TTL 5 min via get_static_cached.
"""

import logging

from app.cache import get_static_cached, static_cache_delete
from app.database import db

logger = logging.getLogger(__name__)

_SETOR_AREA_CACHE_KEY = "setor_para_area_map"
_SETOR_AREA_TTL = 300

SETOR_PARA_AREA = {
    "Material Indireto / Compras": "Material",
    "Manutenção": "Manutencao",
}


def _carregar_mapa_firestore() -> dict:
    try:
        doc = db.collection("config").document("setor_para_area").get()
        if doc.exists:
            mapa = doc.to_dict().get("mapa", {})
            if mapa:
                return dict(mapa)
    except Exception as exc:
        logger.warning("setor_para_area: usando fallback estático (%s)", exc)
    return dict(SETOR_PARA_AREA)


def setor_para_area(setor_nome: str) -> str:
    """
    Converte nome do setor (valor do formulário Atribuir ao setor) para a área
    usada no cadastro de usuários (supervisores). Assim a busca por
    supervisores e o filtro do dashboard usam o mesmo identificador.
    Fonte de verdade: Firestore config/setor_para_area. Fallback: dict estático.
    """
    if not setor_nome or not isinstance(setor_nome, str):
        return setor_nome or ""
    mapa = get_static_cached(_SETOR_AREA_CACHE_KEY, _carregar_mapa_firestore, _SETOR_AREA_TTL)
    return mapa.get(setor_nome.strip(), setor_nome.strip())


def invalidar_cache_setor_area() -> None:
    """Força re-leitura do Firestore na próxima chamada a setor_para_area."""
    static_cache_delete(_SETOR_AREA_CACHE_KEY)
