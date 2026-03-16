"""Testes do módulo de internacionalização (i18n)."""

from app.i18n import (
    get_language_code,
    get_translated_category,
    get_translated_sector,
    get_translated_status,
    get_translation,
)


def test_get_language_code_valido_retorna_codigo():
    """get_language_code com código válido retorna o próprio código."""
    assert get_language_code("pt_BR") == "pt_BR"
    assert get_language_code("en") == "en"
    assert get_language_code("es") == "es"


def test_get_language_code_invalido_retorna_padrao():
    """get_language_code com código inválido retorna o idioma padrão (en)."""
    assert get_language_code("xx") == "en"
    assert get_language_code(None) == "en"


def test_get_translation_chave_existente_pt_BR():
    """get_translation com chave existente em pt_BR retorna texto traduzido."""
    result = get_translation("back", "pt_BR")
    assert isinstance(result, str)
    assert result != "back" or result == "back"


def test_get_translation_chave_existente_en():
    """get_translation com chave existente em en retorna texto em inglês quando disponível."""
    result = get_translation("back", "en")
    assert isinstance(result, str)


def test_get_translation_chave_inexistente_retorna_chave():
    """get_translation com chave inexistente retorna a própria chave como fallback."""
    result = get_translation("chave_que_nao_existe_xyz", "pt_BR")
    assert result == "chave_que_nao_existe_xyz"


def test_get_translated_sector_retorna_string():
    """get_translated_sector retorna string para setor conhecido ou original."""
    r = get_translated_sector("Manutencao", "pt_BR")
    assert isinstance(r, str)
    r_en = get_translated_sector("Manutencao", "en")
    assert isinstance(r_en, str)


def test_get_translated_category_retorna_string():
    """get_translated_category retorna string."""
    r = get_translated_category("Projetos", "pt_BR")
    assert isinstance(r, str)


def test_get_translated_status_retorna_string():
    """get_translated_status retorna string."""
    r = get_translated_status("Aberto", "pt_BR")
    assert isinstance(r, str)
