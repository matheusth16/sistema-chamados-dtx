"""Testes para utils_areas.py — mapeamento setor → área."""


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
