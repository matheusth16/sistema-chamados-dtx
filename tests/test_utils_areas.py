"""Testes para utils_areas.py — mapeamento setor → área (Fase 2, Marco 9:
leitura contra Postgres real, tabela config_setor_area)."""

from unittest.mock import patch

import pytest

from app.db.models.config_setor_area import ConfigSetorAreaRow

pytestmark = pytest.mark.usefixtures("db_session")


def _limpar_cache():
    """Remove cache estático de setor_para_area entre testes."""
    from app.cache import static_cache_delete

    static_cache_delete("setor_para_area_map")


# ── fallback estático (tabela config_setor_area vazia) ────────────────────────


def test_setor_material_indireto_mapeia_para_material():
    from app.utils_areas import setor_para_area

    assert setor_para_area("Material Indireto / Compras") == "Material"


def test_setor_manutencao_mapeia_sem_acento():
    from app.utils_areas import setor_para_area

    assert setor_para_area("Manutenção") == "Manutencao"


def test_setor_nao_mapeado_retorna_o_proprio_valor():
    from app.utils_areas import setor_para_area

    assert setor_para_area("TI") == "TI"
    assert setor_para_area("RH") == "RH"


def test_setor_vazio_retorna_string_vazia():
    from app.utils_areas import setor_para_area

    assert setor_para_area("") == ""


def test_setor_none_retorna_string_vazia():
    from app.utils_areas import setor_para_area

    assert setor_para_area(None) == ""


def test_setor_com_espacos_extras_normaliza():
    from app.utils_areas import setor_para_area

    assert setor_para_area("  TI  ") == "TI"


def test_setor_nao_string_retorna_valor_original():
    from app.utils_areas import setor_para_area

    # int truthy: retorna o próprio valor (type hint é str, uso apenas com strings)
    assert setor_para_area(123) == 123


# ── leitura real do Postgres ───────────────────────────────────────────────────


def test_setor_para_area_le_mapa_do_postgres(db_session):
    """setor_para_area usa o mapa persistido em config_setor_area quando existe."""
    _limpar_cache()
    db_session.add(
        ConfigSetorAreaRow(id=True, mapa={"TI": "TecnologiaInformacao", "Logística": "Logistica"})
    )
    db_session.commit()

    from app.utils_areas import setor_para_area

    assert setor_para_area("TI") == "TecnologiaInformacao"
    assert setor_para_area("Logística") == "Logistica"
    _limpar_cache()


def test_setor_para_area_setor_desconhecido_do_postgres_retorna_proprio_nome(db_session):
    """Setor não presente no mapa persistido → retorna o próprio nome (fallback pontual)."""
    _limpar_cache()
    db_session.add(ConfigSetorAreaRow(id=True, mapa={"TI": "TecnologiaInformacao"}))
    db_session.commit()

    from app.utils_areas import setor_para_area

    assert setor_para_area("RH") == "RH"
    _limpar_cache()


def test_setor_para_area_cache_evita_re_query():
    """Segunda chamada não re-executa _carregar_mapa_postgres (cache hit)."""
    _limpar_cache()
    mapa = {"TI": "TI_area"}
    with patch("app.utils_areas._carregar_mapa_postgres", return_value=mapa) as mock_carregar:
        from app.utils_areas import setor_para_area

        setor_para_area("TI")
        setor_para_area("TI")
        mock_carregar.assert_called_once()
    _limpar_cache()


def test_invalidar_cache_setor_area_forca_re_query():
    """Após invalidar, próxima chamada re-executa _carregar_mapa_postgres."""
    _limpar_cache()
    mapa = {"TI": "TI_area"}
    with patch("app.utils_areas._carregar_mapa_postgres", return_value=mapa) as mock_carregar:
        from app.utils_areas import invalidar_cache_setor_area, setor_para_area

        setor_para_area("TI")  # warm up cache
        invalidar_cache_setor_area()
        setor_para_area("TI")  # re-executa o fetcher após invalidação
        assert mock_carregar.call_count == 2
    _limpar_cache()


def test_carregar_mapa_postgres_retorna_dict_da_linha(db_session):
    """_carregar_mapa_postgres lê a coluna 'mapa' da linha única de config_setor_area."""
    mapa_esperado = {"Comercial": "ComercialArea"}
    db_session.add(ConfigSetorAreaRow(id=True, mapa=mapa_esperado))
    db_session.commit()

    from app.utils_areas import _carregar_mapa_postgres

    assert _carregar_mapa_postgres() == mapa_esperado


def test_carregar_mapa_postgres_linha_inexistente_retorna_fallback():
    """Tabela sem a linha singleton → retorna SETOR_PARA_AREA estático."""
    from app.utils_areas import SETOR_PARA_AREA, _carregar_mapa_postgres

    assert _carregar_mapa_postgres() == dict(SETOR_PARA_AREA)


def test_carregar_mapa_postgres_mapa_vazio_retorna_fallback(db_session):
    """Linha existe mas mapa é {} → fallback para SETOR_PARA_AREA."""
    db_session.add(ConfigSetorAreaRow(id=True, mapa={}))
    db_session.commit()

    from app.utils_areas import SETOR_PARA_AREA, _carregar_mapa_postgres

    assert _carregar_mapa_postgres() == dict(SETOR_PARA_AREA)


def test_carregar_mapa_postgres_excecao_usa_fallback(monkeypatch):
    """Exceção de banco → _carregar_mapa_postgres captura e retorna fallback estático."""
    from app import utils_areas

    def _explode():
        raise RuntimeError("banco indisponível")

    monkeypatch.setattr(utils_areas.db_module, "SessionLocal", _explode)

    from app.utils_areas import SETOR_PARA_AREA, _carregar_mapa_postgres

    assert _carregar_mapa_postgres() == dict(SETOR_PARA_AREA)
