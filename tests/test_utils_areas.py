"""Testes para utils_areas.py — mapeamento setor → área."""

from unittest.mock import MagicMock, patch

# ── helpers ──────────────────────────────────────────────────────────────────


def _limpar_cache():
    """Remove cache estático de setor_para_area entre testes."""
    from app.cache import static_cache_delete

    static_cache_delete("setor_para_area_map")


# ── testes existentes (fallback estático) ─────────────────────────────────────


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


# ── F-30: leitura do Firestore ────────────────────────────────────────────────


def test_setor_para_area_le_mapa_do_firestore():
    """setor_para_area usa mapa do Firestore quando disponível."""
    _limpar_cache()
    mapa_remoto = {"TI": "TecnologiaInformacao", "Logística": "Logistica"}
    with patch("app.utils_areas._carregar_mapa_firestore", return_value=mapa_remoto):
        from app.utils_areas import setor_para_area

        assert setor_para_area("TI") == "TecnologiaInformacao"
        assert setor_para_area("Logística") == "Logistica"
    _limpar_cache()


def test_setor_para_area_setor_desconhecido_do_firestore_retorna_proprio_nome():
    """Setor não presente no mapa do Firestore → retorna o próprio nome (fallback)."""
    _limpar_cache()
    mapa_remoto = {"TI": "TecnologiaInformacao"}
    with patch("app.utils_areas._carregar_mapa_firestore", return_value=mapa_remoto):
        from app.utils_areas import setor_para_area

        assert setor_para_area("RH") == "RH"
    _limpar_cache()


def test_setor_para_area_cache_evita_re_query():
    """Segunda chamada não re-executa _carregar_mapa_firestore (cache hit)."""
    _limpar_cache()
    mapa = {"TI": "TI_area"}
    with patch("app.utils_areas._carregar_mapa_firestore", return_value=mapa) as mock_carregar:
        from app.utils_areas import setor_para_area

        setor_para_area("TI")
        setor_para_area("TI")
        mock_carregar.assert_called_once()
    _limpar_cache()


def test_invalidar_cache_setor_area_forca_re_query():
    """Após invalidar, próxima chamada re-executa _carregar_mapa_firestore."""
    _limpar_cache()
    mapa = {"TI": "TI_area"}
    with patch("app.utils_areas._carregar_mapa_firestore", return_value=mapa) as mock_carregar:
        from app.utils_areas import invalidar_cache_setor_area, setor_para_area

        setor_para_area("TI")  # warm up cache
        invalidar_cache_setor_area()
        setor_para_area("TI")  # re-executa o fetcher após invalidação
        assert mock_carregar.call_count == 2
    _limpar_cache()


def test_carregar_mapa_firestore_retorna_dict_do_doc():
    """_carregar_mapa_firestore lê campo 'mapa' do doc config/setor_para_area."""
    _limpar_cache()
    mapa_esperado = {"Comercial": "ComercialArea"}
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {"mapa": mapa_esperado}
    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

    with patch("app.utils_areas.db", mock_db):
        from app.utils_areas import _carregar_mapa_firestore

        resultado = _carregar_mapa_firestore()

    assert resultado == mapa_esperado
    mock_db.collection.assert_called_once_with("config")
    mock_db.collection.return_value.document.assert_called_once_with("setor_para_area")
    _limpar_cache()


def test_carregar_mapa_firestore_doc_inexistente_retorna_fallback():
    """Doc inexistente no Firestore → retorna SETOR_PARA_AREA estático."""
    _limpar_cache()
    mock_doc = MagicMock()
    mock_doc.exists = False
    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

    with patch("app.utils_areas.db", mock_db):
        from app.utils_areas import SETOR_PARA_AREA, _carregar_mapa_firestore

        resultado = _carregar_mapa_firestore()

    assert resultado == dict(SETOR_PARA_AREA)
    _limpar_cache()


def test_carregar_mapa_firestore_mapa_vazio_retorna_fallback():
    """Mapa vazio no Firestore → fallback para SETOR_PARA_AREA."""
    _limpar_cache()
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {"mapa": {}}
    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

    with patch("app.utils_areas.db", mock_db):
        from app.utils_areas import SETOR_PARA_AREA, _carregar_mapa_firestore

        resultado = _carregar_mapa_firestore()

    assert resultado == dict(SETOR_PARA_AREA)
    _limpar_cache()


def test_carregar_mapa_firestore_excecao_usa_fallback():
    """Exceção de Firestore → _carregar_mapa_firestore captura e retorna fallback estático."""
    _limpar_cache()
    mock_db = MagicMock()
    mock_db.collection.side_effect = RuntimeError("connection refused")

    with patch("app.utils_areas.db", mock_db):
        from app.utils_areas import SETOR_PARA_AREA, _carregar_mapa_firestore

        resultado = _carregar_mapa_firestore()

    assert resultado == dict(SETOR_PARA_AREA)
    _limpar_cache()
