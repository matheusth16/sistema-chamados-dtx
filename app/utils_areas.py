"""
Mapeamento entre nome do setor (formulário) e área usada no cadastro de usuários.
Postgres é a fonte de verdade (tabela config_setor_area, coluna mapa).
Fallback: SETOR_PARA_AREA estático se a tabela estiver vazia ou inacessível.
Cache TTL 5 min via get_static_cached.
"""

import logging

from app import db as db_module
from app.cache import get_static_cached, static_cache_delete
from app.db.models.config_setor_area import ConfigSetorAreaRow

logger = logging.getLogger(__name__)

_SETOR_AREA_CACHE_KEY = "setor_para_area_map"
_SETOR_AREA_TTL = 300

SETOR_PARA_AREA = {
    "Material Indireto / Compras": "Material",
    "Manutenção": "Manutencao",
}


def _carregar_mapa_postgres() -> dict:
    try:
        with db_module.SessionLocal() as session:
            row = session.get(ConfigSetorAreaRow, True)
            if row and row.mapa:
                return dict(row.mapa)
    except Exception as exc:
        logger.warning("setor_para_area: usando fallback estático (%s)", exc)
    return dict(SETOR_PARA_AREA)


def setor_para_area(setor_nome: str) -> str:
    """
    Converte nome do setor (valor do formulário Atribuir ao setor) para a área
    usada no cadastro de usuários (supervisores). Assim a busca por
    supervisores e o filtro do dashboard usam o mesmo identificador.
    Fonte de verdade: Postgres config_setor_area. Fallback: dict estático.
    """
    if not setor_nome or not isinstance(setor_nome, str):
        return setor_nome or ""
    mapa = get_static_cached(_SETOR_AREA_CACHE_KEY, _carregar_mapa_postgres, _SETOR_AREA_TTL)
    return mapa.get(setor_nome.strip(), setor_nome.strip())


def invalidar_cache_setor_area() -> None:
    """Força re-leitura do Postgres na próxima chamada a setor_para_area."""
    static_cache_delete(_SETOR_AREA_CACHE_KEY)
