"""
Sistema de Internacionalização (i18n) para múltiplos idiomas.
Suporta: Português-BR, Inglês e Espanhol.
"""

import os
import json

# Cache do dicionário de traduções e caminho do arquivo
_TRANSLATIONS_CACHE = None
_TRANSLATIONS_FILE = os.path.join(os.path.dirname(__file__), 'translations.json')

def get_translations_dict():
    """Carrega e retorna o dicionário de traduções do arquivo JSON."""
    global _TRANSLATIONS_CACHE
    if _TRANSLATIONS_CACHE is None:
        try:
            with open(_TRANSLATIONS_FILE, 'r', encoding='utf-8') as f:
                _TRANSLATIONS_CACHE = json.load(f)
        except Exception as e:
            print(f"Erro ao carregar traduções: {e}")
            _TRANSLATIONS_CACHE = {}
    return _TRANSLATIONS_CACHE

def save_translations_dict(new_translations):
    """Salva o dicionário de traduções no arquivo JSON e atualiza o cache."""
    global _TRANSLATIONS_CACHE
    try:
        with open(_TRANSLATIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(new_translations, f, indent=4, ensure_ascii=False)
        _TRANSLATIONS_CACHE = new_translations
        return True
    except Exception as e:
        print(f"Erro ao salvar traduções: {e}")
        return False

# Idiomas suportados
SUPPORTED_LANGUAGES = {
    'pt_BR': 'Português (Brasil)',
    'en': 'English',
    'es': 'Español',
}

# Mapa de Setores para Chaves de Tradução
SECTOR_KEYS_MAP = {
    'Manutencao': 'maintenance',     # Sem acento no banco de dados
    'Engenharia': 'engineering',
    'Qualidade': 'quality',
    'Comercial': 'commercial',
    'Planejamento': 'planning',
    'Material': 'indirect_material',  # Abreviado no banco de dados
}

# Mapa de Categorias para Chaves de Tradução
CATEGORY_KEYS_MAP = {
    'Projetos': 'projects',
    'Nao Aplicavel': 'not_applicable',  # Sem acento no banco de dados
}

# Mapa de Status para Chaves de Tradução
STATUS_KEYS_MAP = {
    'Aberto': 'option_open',
    'Em Atendimento': 'option_in_progress',
    'Concluído': 'option_completed',
}

def get_language_code(lang_param):
    """
    Valida e retorna o código de idioma.
    Se inválido, retorna o padrão: pt_BR
    """
    if lang_param in SUPPORTED_LANGUAGES:
        return lang_param
    return 'pt_BR'

def get_translated_sector(sector_name, language='pt_BR'):
    """
    Traduz o nome de um setor usando seu mapeamento de chave.
    
    Args:
        sector_name (str): Nome do setor em português (ex: 'Engenharia')
        language (str): Código do idioma (pt_BR, en, es)
    
    Returns:
        str: Texto traduzido ou o nome original se não encontrado
    """
    translation_key = SECTOR_KEYS_MAP.get(sector_name)
    if translation_key:
        return get_translation(translation_key, language)
    return sector_name

def get_translated_category(category_name, language='pt_BR'):
    """
    Traduz o nome de uma categoria usando seu mapeamento de chave.
    
    Args:
        category_name (str): Nome da categoria em português (ex: 'Projetos')
        language (str): Código do idioma (pt_BR, en, es)
    
    Returns:
        str: Texto traduzido ou o nome original se não encontrado
    """
    translation_key = CATEGORY_KEYS_MAP.get(category_name)
    if translation_key:
        return get_translation(translation_key, language)
    return category_name

def get_translated_status(status_name, language='pt_BR'):
    """
    Traduz o nome de um status usando seu mapeamento de chave.
    
    Args:
        status_name (str): Nome do status em português (ex: 'Aberto')
        language (str): Código do idioma (pt_BR, en, es)
    
    Returns:
        str: Texto traduzido ou o nome original se não encontrado
    """
    translation_key = STATUS_KEYS_MAP.get(status_name)
    if translation_key:
        return get_translation(translation_key, language)
    return status_name

def get_translation(key, language='pt_BR'):
    """
    Obtém a tradução de uma chave para um idioma específico.
    
    Args:
        key (str): Chave da tradução
        language (str): Código do idioma (pt_BR, en, es)
    
    Returns:
        str: Texto traduzido ou a chave se não encontrada
    """
    language = get_language_code(language)
    translations = get_translations_dict()
    
    if key in translations and language in translations[key] and translations[key][language]:
        return translations[key][language]
    # Retorna a chave como fallback
    return key
