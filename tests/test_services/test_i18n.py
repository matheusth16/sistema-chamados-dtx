"""
Testes unitários do módulo i18n.
Cobre: get_language_code, get_translation, get_translated_sector/category/status/field_label,
get_translated_sector_list, flash_t, resolve_flash_message, _build_reverse_map,
get_translations_dict (cache), save_translations_dict.
"""

from unittest.mock import mock_open, patch

# ── get_language_code ──────────────────────────────────────────────────────────


def test_get_language_code_valido_retorna_codigo():
    """Idioma suportado é retornado sem alteração."""
    from app.i18n import get_language_code

    assert get_language_code("pt_BR") == "pt_BR"
    assert get_language_code("en") == "en"
    assert get_language_code("es") == "es"


def test_get_language_code_invalido_retorna_en():
    """Idioma inválido retorna 'en' como fallback."""
    from app.i18n import get_language_code

    assert get_language_code("fr") == "en"
    assert get_language_code("") == "en"
    assert get_language_code("xx_XX") == "en"


# ── get_translations_dict ──────────────────────────────────────────────────────


def test_get_translations_dict_carrega_do_arquivo():
    """get_translations_dict carrega e retorna dicionário do JSON."""
    import json

    from app import i18n

    sample = {"hello": {"pt_BR": "Olá", "en": "Hello", "es": "Hola"}}
    json_str = json.dumps(sample)

    # Resetar cache para forçar recarga
    i18n._TRANSLATIONS_CACHE = None
    i18n._TRANSLATIONS_MTIME = None

    with (
        patch("app.i18n.os.path.isfile", return_value=True),
        patch("app.i18n.os.path.getmtime", return_value=12345.0),
        patch("builtins.open", mock_open(read_data=json_str)),
    ):
        result = i18n.get_translations_dict()

    assert result == sample
    # Restaura estado
    i18n._TRANSLATIONS_CACHE = None
    i18n._TRANSLATIONS_MTIME = None


def test_get_translations_dict_usa_cache_quando_mtime_igual():
    """get_translations_dict usa cache se mtime não mudou."""
    from app import i18n

    i18n._TRANSLATIONS_CACHE = {"cached_key": {"en": "cached"}}
    i18n._TRANSLATIONS_MTIME = 99999.0

    with (
        patch("app.i18n.os.path.isfile", return_value=True),
        patch("app.i18n.os.path.getmtime", return_value=99999.0),
    ):
        result = i18n.get_translations_dict()

    assert result == {"cached_key": {"en": "cached"}}
    # Restaura estado
    i18n._TRANSLATIONS_CACHE = None
    i18n._TRANSLATIONS_MTIME = None


def test_get_translations_dict_excecao_retorna_dict_vazio():
    """get_translations_dict retorna {} quando arquivo não existe/falha."""
    from app import i18n

    i18n._TRANSLATIONS_CACHE = None
    i18n._TRANSLATIONS_MTIME = None

    with (
        patch("app.i18n.os.path.isfile", return_value=False),
        patch("builtins.open", side_effect=FileNotFoundError("no file")),
    ):
        # Mesmo sem arquivo, mtime=0 → tentará abrir → falha → cache vazio
        result = i18n.get_translations_dict()

    assert isinstance(result, dict)
    # Restaura estado
    i18n._TRANSLATIONS_CACHE = None
    i18n._TRANSLATIONS_MTIME = None


# ── save_translations_dict ────────────────────────────────────────────────────


def test_save_translations_dict_salva_e_retorna_true():
    """save_translations_dict escreve no arquivo e retorna True."""
    from app.i18n import save_translations_dict

    sample = {"k": {"pt_BR": "V", "en": "V", "es": "V"}}

    with patch("builtins.open", mock_open()) as mock_f:
        result = save_translations_dict(sample)

    assert result is True
    mock_f.assert_called_once()


def test_save_translations_dict_excecao_retorna_false():
    """save_translations_dict retorna False quando falha ao escrever."""
    from app.i18n import save_translations_dict

    with patch("builtins.open", side_effect=PermissionError("no write")):
        result = save_translations_dict({"k": {}})

    assert result is False


# ── get_translation ───────────────────────────────────────────────────────────


_SAMPLE_TRANSLATIONS = {
    "hello": {"pt_BR": "Olá", "en": "Hello", "es": "Hola"},
    "greeting": {
        "pt_BR": "Bem-vindo, {name}!",
        "en": "Welcome, {name}!",
        "es": "Bienvenido, {name}!",
    },
    "pt_only": {"pt_BR": "Apenas PT"},
}


def test_get_translation_idioma_solicitado():
    """get_translation retorna tradução no idioma solicitado."""
    from app.i18n import get_translation

    with patch("app.i18n.get_translations_dict", return_value=_SAMPLE_TRANSLATIONS):
        assert get_translation("hello", "en") == "Hello"
        assert get_translation("hello", "es") == "Hola"
        assert get_translation("hello", "pt_BR") == "Olá"


def test_get_translation_fallback_para_ptbr():
    """get_translation faz fallback para pt_BR quando idioma não tem a chave."""
    from app.i18n import get_translation

    with patch("app.i18n.get_translations_dict", return_value=_SAMPLE_TRANSLATIONS):
        result = get_translation("pt_only", "en")
    assert result == "Apenas PT"


def test_get_translation_chave_inexistente_retorna_chave():
    """get_translation retorna a própria chave quando não encontrada."""
    from app.i18n import get_translation

    with patch("app.i18n.get_translations_dict", return_value=_SAMPLE_TRANSLATIONS):
        result = get_translation("chave_nao_existe", "en")
    assert result == "chave_nao_existe"


def test_get_translation_com_kwargs_formata_string():
    """get_translation com kwargs formata a string de tradução."""
    from app.i18n import get_translation

    with patch("app.i18n.get_translations_dict", return_value=_SAMPLE_TRANSLATIONS):
        result = get_translation("greeting", "en", name="João")
    assert result == "Welcome, João!"


def test_get_translation_kwargs_keyerror_retorna_sem_formato():
    """get_translation com kwargs errados retorna string sem formato (KeyError tratado)."""
    from app.i18n import get_translation

    with patch("app.i18n.get_translations_dict", return_value=_SAMPLE_TRANSLATIONS):
        result = get_translation("greeting", "en", errada="x")
    # Deve retornar a string sem formatação (fallback)
    assert "{name}" in result or "Welcome" in result


# ── get_translated_sector ─────────────────────────────────────────────────────


def test_get_translated_sector_setor_conhecido():
    """get_translated_sector traduz setor conhecido."""
    from app.i18n import get_translated_sector

    sample = {"maintenance": {"pt_BR": "Manutenção", "en": "Maintenance", "es": "Mantenimiento"}}
    with patch("app.i18n.get_translations_dict", return_value=sample):
        result = get_translated_sector("Manutencao", "en")
    assert result == "Maintenance"


def test_get_translated_sector_desconhecido_retorna_original():
    """get_translated_sector retorna nome original quando setor não mapeado."""
    from app.i18n import get_translated_sector

    with patch("app.i18n.get_translations_dict", return_value={}):
        result = get_translated_sector("Setor Desconhecido", "en")
    assert result == "Setor Desconhecido"


def test_get_translated_sector_list_traduz_multiplos():
    """get_translated_sector_list traduz lista separada por vírgula."""
    from app.i18n import get_translated_sector_list

    sample = {
        "maintenance": {"pt_BR": "Manutenção", "en": "Maintenance", "es": "Mantenimiento"},
        "quality": {"pt_BR": "Qualidade", "en": "Quality", "es": "Calidad"},
    }
    with patch("app.i18n.get_translations_dict", return_value=sample):
        result = get_translated_sector_list("Manutencao, Qualidade", "en")
    assert "Maintenance" in result
    assert "Quality" in result


def test_get_translated_sector_list_vazio_retorna_vazio():
    """get_translated_sector_list com string vazia retorna a própria string."""
    from app.i18n import get_translated_sector_list

    result = get_translated_sector_list("", "en")
    assert result == ""


# ── get_translated_category / status / field_label ────────────────────────────


def test_get_translated_category_projetos():
    """get_translated_category traduz 'Projetos'."""
    from app.i18n import get_translated_category

    sample = {"projects": {"pt_BR": "Projetos", "en": "Projects", "es": "Proyectos"}}
    with patch("app.i18n.get_translations_dict", return_value=sample):
        result = get_translated_category("Projetos", "en")
    assert result == "Projects"


def test_get_translated_category_desconhecida_retorna_original():
    """get_translated_category retorna original quando categoria não mapeada."""
    from app.i18n import get_translated_category

    with patch("app.i18n.get_translations_dict", return_value={}):
        result = get_translated_category("Desconhecida", "en")
    assert result == "Desconhecida"


def test_get_translated_status_aberto():
    """get_translated_status traduz 'Aberto'."""
    from app.i18n import get_translated_status

    sample = {"option_open": {"pt_BR": "Aberto", "en": "Open", "es": "Abierto"}}
    with patch("app.i18n.get_translations_dict", return_value=sample):
        result = get_translated_status("Aberto", "en")
    assert result == "Open"


def test_get_translated_status_desconhecido_retorna_original():
    """get_translated_status retorna original quando status não mapeado."""
    from app.i18n import get_translated_status

    with patch("app.i18n.get_translations_dict", return_value={}):
        result = get_translated_status("Pendente", "en")
    assert result == "Pendente"


def test_get_translated_field_label_campo_conhecido():
    """get_translated_field_label traduz campo conhecido."""
    from app.i18n import get_translated_field_label

    sample = {"status": {"pt_BR": "Status", "en": "Status", "es": "Estado"}}
    with patch("app.i18n.get_translations_dict", return_value=sample):
        result = get_translated_field_label("status", "en")
    assert result == "Status"


def test_get_translated_field_label_vazio_retorna_vazio():
    """get_translated_field_label com campo vazio/None retorna o mesmo."""
    from app.i18n import get_translated_field_label

    assert get_translated_field_label("", "en") == ""
    assert get_translated_field_label(None, "en") is None


def test_get_translated_field_label_desconhecido_retorna_original():
    """get_translated_field_label retorna original quando campo não mapeado."""
    from app.i18n import get_translated_field_label

    with patch("app.i18n.get_translations_dict", return_value={}):
        result = get_translated_field_label("campo_nao_mapeado", "en")
    assert result == "campo_nao_mapeado"


# ── flash_t ────────────────────────────────────────────────────────────────────


def test_flash_t_sem_kwargs_enfileira_chave(app):
    """flash_t sem kwargs enfileira a chave diretamente."""
    from app.i18n import flash_t

    with app.test_request_context("/"):
        with patch("app.i18n.flash") as mock_flash:
            flash_t("ticket_created_success", "success")
        mock_flash.assert_called_once_with("ticket_created_success", "success")


def test_flash_t_com_kwargs_enfileira_formato_t(app):
    """flash_t com kwargs enfileira no formato '_t_:key|arg=val'."""
    from app.i18n import flash_t

    with app.test_request_context("/"):
        with patch("app.i18n.flash") as mock_flash:
            flash_t("greeting", "info", name="João")
        called_msg = mock_flash.call_args[0][0]
        assert called_msg.startswith("_t_:greeting|")
        assert "name=João" in called_msg


# ── resolve_flash_message ────────────────────────────────────────────────────


def test_resolve_flash_message_formato_t_com_kwargs():
    """resolve_flash_message decodifica formato '_t_:key|arg=val'."""
    from app.i18n import resolve_flash_message

    sample = {"greeting": {"pt_BR": "Bem-vindo, {name}!", "en": "Welcome, {name}!", "es": ""}}
    with patch("app.i18n.get_translations_dict", return_value=sample):
        result = resolve_flash_message("_t_:greeting|name=Teste", "en")
    assert result == "Welcome, Teste!"


def test_resolve_flash_message_chave_direta():
    """resolve_flash_message resolve chave direta."""
    from app.i18n import resolve_flash_message

    sample = {
        "ticket_created_success": {"pt_BR": "Chamado criado!", "en": "Ticket created!", "es": ""}
    }
    with patch("app.i18n.get_translations_dict", return_value=sample):
        result = resolve_flash_message("ticket_created_success", "en")
    assert result == "Ticket created!"


def test_resolve_flash_message_texto_ptbr_legado():
    """resolve_flash_message resolve texto pt_BR via reverse lookup."""
    from app.i18n import resolve_flash_message

    sample = {"some_key": {"pt_BR": "Texto legado", "en": "Legacy text", "es": ""}}
    with patch("app.i18n.get_translations_dict", return_value=sample):
        result = resolve_flash_message("Texto legado", "en")
    assert result == "Legacy text"


def test_resolve_flash_message_sem_traducao_retorna_original():
    """resolve_flash_message retorna a própria mensagem quando não encontrada."""
    from app.i18n import resolve_flash_message

    with patch("app.i18n.get_translations_dict", return_value={}):
        result = resolve_flash_message("mensagem_sem_traducao", "en")
    assert result == "mensagem_sem_traducao"
