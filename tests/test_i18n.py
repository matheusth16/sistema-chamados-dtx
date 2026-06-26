"""Testes do módulo de internacionalização (i18n)."""

import pytest

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
    """F-61: get_language_code com código inválido retorna en (idioma padrão do sistema)."""
    assert get_language_code("xx") == "en"
    assert get_language_code(None) == "en"
    assert get_language_code("xyz") == "en"
    assert get_language_code("") == "en"


def test_get_translation_chave_existente_pt_BR():
    """get_translation com chave existente em pt_BR retorna texto traduzido."""
    result = get_translation("back", "pt_BR")
    assert isinstance(result, str)
    assert result == "Voltar"


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


@pytest.mark.parametrize(
    "lang,expected_substr",
    [
        ("pt_BR", "Transferir"),
        ("en", "Transfer"),
        ("es", "Transferir"),
    ],
)
def test_escalation_transfer_area_btn_i18n(lang, expected_substr):
    """escalation_transfer_area_btn existe e contém substring esperada nos 3 idiomas."""
    result = get_translation("escalation_transfer_area_btn", lang)
    assert expected_substr.lower() in result.lower()


@pytest.mark.parametrize(
    "lang,expected_substr",
    [
        ("pt_BR", "Escalonar"),
        ("en", "Escalate"),
        ("es", "Escalar"),
    ],
)
def test_escalation_escalate_colleague_btn_i18n(lang, expected_substr):
    """escalation_escalate_colleague_btn existe e contém substring esperada nos 3 idiomas."""
    result = get_translation("escalation_escalate_colleague_btn", lang)
    assert expected_substr.lower() in result.lower()


def test_participant_status_keys_all_languages():
    """Chaves de status de participante existem nos 3 idiomas e não retornam a própria chave."""
    for lang in ("pt_BR", "en", "es"):
        for key in (
            "participant_status_pending",
            "participant_status_in_progress",
            "participant_status_done",
        ):
            result = get_translation(key, lang)
            assert result != key, f"Chave '{key}' retornou fallback para idioma '{lang}'"


def test_escalation_js_error_keys_all_languages():
    """Chaves de erro JS de escalonamento existem nos 3 idiomas."""
    error_keys = [
        "error_select_dest_area",
        "error_select_dest_responsible",
        "error_select_colleague",
        "error_select_area",
        "error_select_supervisor",
        "error_reason_required",
        "error_transfer",
        "error_escalate",
        "error_include_participants",
        "error_add_at_least_one_supervisor",
    ]
    for lang in ("pt_BR", "en", "es"):
        for key in error_keys:
            result = get_translation(key, lang)
            assert result != key, f"Chave '{key}' retornou fallback para idioma '{lang}'"
