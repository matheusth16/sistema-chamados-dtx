"""
Sistema de Internacionalização (i18n) para múltiplos idiomas.
Suporta: Português-BR, Inglês e Espanhol.
"""

import json
import os

from flask import flash

# Cache do dicionário de traduções e caminho do arquivo
_TRANSLATIONS_CACHE = None
_TRANSLATIONS_FILE = os.path.join(os.path.dirname(__file__), "translations.json")
_TRANSLATIONS_MTIME = None


def get_translations_dict():
    """Carrega e retorna o dicionário de traduções do arquivo JSON. Recarrega se o arquivo foi alterado."""
    global _TRANSLATIONS_CACHE, _TRANSLATIONS_MTIME
    try:
        mtime = os.path.getmtime(_TRANSLATIONS_FILE) if os.path.isfile(_TRANSLATIONS_FILE) else 0
        if _TRANSLATIONS_CACHE is None or mtime != _TRANSLATIONS_MTIME:
            _TRANSLATIONS_MTIME = mtime
            with open(_TRANSLATIONS_FILE, encoding="utf-8") as f:
                _TRANSLATIONS_CACHE = json.load(f)
    except Exception as e:
        print(f"Erro ao carregar traduções: {e}")
        if _TRANSLATIONS_CACHE is None:
            _TRANSLATIONS_CACHE = {}
    return _TRANSLATIONS_CACHE


# Idiomas suportados
SUPPORTED_LANGUAGES = {
    "pt_BR": "Português (Brasil)",
    "en": "English",
    "es": "Español",
}

# Mapa de Setores para Chaves de Tradução
SECTOR_KEYS_MAP = {
    # --- Setores com nome em português ---
    "Manutencao": "maintenance",  # Sem acento no banco de dados
    "Manutenção": "maintenance",
    "Engenharia": "engineering",
    "Qualidade": "quality",
    "Comercial": "commercial",
    "Planejamento": "planning",
    "Material": "indirect_material",  # Abreviado no banco de dados
    "RH": "hr",
    "TI": "it",
    # Nome novo (canônico) e alias legado para histórico
    "Planejamento de Produção": "ppcp",
    "PPCP": "ppcp",
    "Planejamento Materiais": "material_planning",
    "Suprimentos": "supplies",
    "Logistica": "logistics",
    "Logística": "logistics",
    "Infraestrutura": "facility",
    # Setores de Produção mantidos apenas para histórico (ativos desativados no Firestore)
    "Produção - Usinagem": "production_machining",
    "Produção - Montagem": "production_assembly",
    "Produção - Inspeções": "production_inspections",
    "Produção - Processos Especiais": "production_special_processes",
    # Fallback genérico
    "Geral": "general",
    "General": "general",
    # --- Setores já cadastrados em inglês no banco ---
    "Engineering": "engineering",
    "Quality": "quality",
    "Commercial": "commercial",
    # Nome novo (canônico) e alias legado Procurement para histórico
    "Compras": "procurement",
    "Procurement": "procurement",
    "IT": "it",
    "HR": "hr",
    "Logistics": "logistics",
    "Facility": "facility",
    "Supplies": "supplies",
}

# Mapa de Categorias para Chaves de Tradução
CATEGORY_KEYS_MAP = {
    "Projetos": "projects",
    "Nao Aplicavel": "not_applicable",  # Sem acento no banco de dados
}

# Mapa de Status para Chaves de Tradução
STATUS_KEYS_MAP = {
    "Aberto": "option_open",
    "Em Atendimento": "option_in_progress",
    "Concluído": "option_completed",
    "Cancelado": "option_cancelled",
}

# Mapa de valores de Gate → chave de tradução
GATE_KEYS_MAP: dict[str, str] = {
    # Valores canônicos completos (16)
    "Gate 1 - Desmontagem": "gate_1_desmontagem",
    "Gate 1 - Limpeza": "gate_1_limpeza",
    "Gate 1 - Remoção de Tinta": "gate_1_remocao_tinta",
    "Gate 1 - Reconciliação": "gate_1_reconciliacao",
    "Gate 2 - Forno": "gate_2_forno",
    "Gate 2 - FPI": "gate_2_fpi",
    "Gate 2 - MPI": "gate_2_mpi",
    "Gate 2 - Inspeção": "gate_2_inspecao",
    "Gate 3 - Galvanoplastia": "gate_3_galvanoplastia",
    "Gate 3 - Usinagem": "gate_3_usinagem",
    "Gate 3 - Bucha": "gate_3_bucha",
    "Gate 3 - Pintura": "gate_3_pintura",
    "Gate 4 - Inspeção de Partes": "gate_4_inspecao_partes",
    "Gate 4 - Montagem": "gate_4_montagem",
    "Gate 4 - Testes": "gate_4_testes",
    "Gate 4 - Inspeção Final": "gate_4_inspecao_final",
    # N/A
    "N/A": "not_applicable_short",
    # Aliases legados (somente leitura — histórico de chamados antigos)
    "Gate 1": "gate_1",
    "Gate 2": "gate_2",
    "Gate 3": "gate_3",
    "Gate 4": "gate_4",
}

# Mapa de Perfis de usuário para Chaves de Tradução
ROLE_KEYS_MAP = {
    "supervisor": "profile_supervisor",
    "solicitante": "profile_solicitante",
    "admin": "profile_admin",
    "admin_global": "profile_admin_global",
}

# Nomes de campos (histórico/auditoria) -> chave de tradução para o rótulo exibido
FIELD_LABEL_KEYS = {
    "motivo_cancelamento": "cancellation_reason",
    "status": "status",
    "responsável": "assigned_to",
    "descrição": "description",
    "anexo": "attached_file",
    "novo anexo": "new_attachment",
    "setores adicionais": "additional_sectors",
}


def get_language_code(lang_param):
    """
    Valida e retorna o código de idioma.
    Se inválido ou None, retorna o padrão: en
    """
    if lang_param in SUPPORTED_LANGUAGES:
        return lang_param
    return "en"


def get_translated_sector(sector_name, language="pt_BR"):
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


def get_translated_sector_list(sector_string, language="pt_BR"):
    """
    Traduz uma string de setores separados por vírgula.
    Ex: 'Comercial, Planejamento' → 'Commercial, Planning'
    """
    if not sector_string:
        return sector_string
    parts = [p.strip() for p in sector_string.split(",")]
    return ", ".join(get_translated_sector(p, language) for p in parts)


def get_translated_category(category_name, language="pt_BR"):
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


def get_translated_status(status_name, language="pt_BR"):
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


def get_translated_gate(gate_value, language="pt_BR"):
    """
    Traduz o valor canônico de um gate para o idioma solicitado.

    Args:
        gate_value (str): Valor canônico gravado no Firestore (ex: 'Gate 1 - Desmontagem', 'N/A')
        language (str): Código do idioma (pt_BR, en, es)

    Returns:
        str: Texto traduzido ou o valor original se não mapeado
    """
    translation_key = GATE_KEYS_MAP.get(gate_value)
    if translation_key:
        return get_translation(translation_key, language)
    return gate_value


def get_translated_role(role_name, language="en"):
    """
    Traduz o nome interno de um perfil de usuário para o idioma solicitado.

    Args:
        role_name (str): Identificador interno (ex: 'supervisor', 'solicitante')
        language (str): Código do idioma (pt_BR, en, es)

    Returns:
        str: Texto traduzido ou o valor original se não mapeado
    """
    translation_key = ROLE_KEYS_MAP.get(role_name)
    if translation_key:
        return get_translation(translation_key, language)
    return role_name


def get_translated_field_label(field_name, language="pt_BR"):
    """
    Traduz o nome de um campo (ex: motivo_cancelamento) para o rótulo exibido no histórico.
    """
    if not field_name:
        return field_name
    key = FIELD_LABEL_KEYS.get(field_name)
    if key:
        return get_translation(key, language)
    return field_name


def get_translation(key, language="pt_BR", **kwargs):
    """
    Obtém a tradução de uma chave para um idioma específico.

    Args:
        key (str): Chave da tradução
        language (str): Código do idioma (pt_BR, en, es)
        **kwargs: Argumentos para formatação da string traduzida

    Returns:
        str: Texto traduzido ou a chave se não encontrada
    """
    language = get_language_code(language)
    translations = get_translations_dict()

    if key in translations:
        d = translations[key]
        # Tenta o idioma solicitado
        if language in d and d[language]:
            texto = d[language]
            if kwargs:
                try:
                    return texto.format(**kwargs)
                except KeyError:
                    pass
            return texto
        # Fallback para pt_BR se o idioma solicitado não tiver a chave
        if "pt_BR" in d and d["pt_BR"]:
            return d["pt_BR"]
    # Retorna a chave só se a chave não existir no dicionário
    return key


def flash_t(key, category="message", **kwargs):
    """
    Enfileira uma mensagem flash para ser traduzida na renderização do template.

    Sem kwargs: armazena a chave diretamente (ex: 'ticket_created_success').
    Com kwargs: armazena no formato '_t_:key|arg1=val1|arg2=val2' para que
    o filtro resolve_flash_message possa reconstituir e traduzir.
    """
    if not kwargs:
        flash(key, category)
    else:
        encoded = "_t_:" + key + "|" + "|".join(f"{k}={v}" for k, v in kwargs.items())
        flash(encoded, category)


def _build_reverse_map():
    """Constrói mapa de texto pt_BR → chave para reverse lookup."""
    translations = get_translations_dict()
    reverse = {}
    for key, langs in translations.items():
        pt_text = langs.get("pt_BR", "")
        if pt_text:
            reverse[pt_text] = key
    return reverse


def resolve_flash_message(message, language):
    """
    Resolve uma mensagem flash para o idioma dado.
    Suporta três formatos:
    1. Chave direta: 'ticket_created_success'
    2. Chave com kwargs: '_t_:key|arg=val'
    3. Texto pt_BR legado: encontra a chave via reverse lookup e traduz
    """
    if message.startswith("_t_:"):
        parts = message[4:].split("|")
        key = parts[0]
        kwargs = {}
        for part in parts[1:]:
            if "=" in part:
                k, v = part.split("=", 1)
                kwargs[k] = v
        return get_translation(key, language, **kwargs)

    # Tenta como chave direta
    translated = get_translation(message, language)
    if translated != message:
        return translated

    # Reverse lookup: texto pt_BR → chave → idioma correto
    reverse_map = _build_reverse_map()
    key = reverse_map.get(message)
    if key:
        return get_translation(key, language)

    return message
