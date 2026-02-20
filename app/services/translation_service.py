"""
Serviço de tradução automática para múltiplos idiomas.
Suporta tradução de Português para Inglês e Espanhol.
"""
import logging
from typing import Dict

logger = logging.getLogger(__name__)

# Mapeamento de traduções comuns (fallback se API não disponível)
TRANSLATION_MAP = {
    'pt_BR': {
        'Manutencao': {'en': 'Maintenance', 'es': 'Mantenimiento'},
        'Manutenção': {'en': 'Maintenance', 'es': 'Mantenimiento'},
        'Engenharia': {'en': 'Engineering', 'es': 'Ingeniería'},
        'Compras': {'en': 'Procurement', 'es': 'Compras'},
        'Qualidade': {'en': 'Quality', 'es': 'Calidad'},
        'TI': {'en': 'IT', 'es': 'TI'},
        'Administrativo': {'en': 'Administrative', 'es': 'Administrativo'},
        'Recursos Humanos': {'en': 'Human Resources', 'es': 'Recursos Humanos'},
        'Financeiro': {'en': 'Finance', 'es': 'Finanzas'},
        
        # Gates
        'Gate 1': {'en': 'Gate 1', 'es': 'Gate 1'},
        'Gate 2': {'en': 'Gate 2', 'es': 'Gate 2'},
        'Gate 3': {'en': 'Gate 3', 'es': 'Gate 3'},
        'Gate 4': {'en': 'Gate 4', 'es': 'Gate 4'},
        'Gate 5': {'en': 'Gate 5', 'es': 'Gate 5'},
        
        # Impactos
        'Crítico': {'en': 'Critical', 'es': 'Crítico'},
        'Alto': {'en': 'High', 'es': 'Alto'},
        'Médio': {'en': 'Medium', 'es': 'Medio'},
        'Baixo': {'en': 'Low', 'es': 'Bajo'},
    }
}


def traduzir_texto(texto: str, idioma_destino: str = 'en') -> str:
    """
    Traduz um texto para o idioma de destino.
    Primeiro tenta o mapa local, depois poderia integrar API se necessário.
    
    Args:
        texto: Texto a ser traduzido
        idioma_destino: 'en' para inglês, 'es' para espanhol
        
    Returns:
        Texto traduzido ou o original se não encontrado
    """
    try:
        # Tenta encontrar no mapa local
        if texto in TRANSLATION_MAP['pt_BR']:
            return TRANSLATION_MAP['pt_BR'][texto].get(idioma_destino, texto)
        
        # Se não encontrado, tenta com case insensitive
        for chave, traducoes in TRANSLATION_MAP['pt_BR'].items():
            if chave.lower() == texto.lower():
                return traducoes.get(idioma_destino, texto)
        
        logger.warning(f"Tradução não encontrada para: {texto}")
        return texto
    except Exception as e:
        logger.error(f"Erro ao traduzir: {e}")
        return texto


def traduzir_categoria(
    texto_pt: str
) -> Dict[str, str]:
    """
    Traduz uma categoria para múltiplos idiomas.
    
    Args:
        texto_pt: Texto em português
        
    Returns:
        Dicionário com tradução em PT, EN e ES
    """
    return {
        'pt': texto_pt,
        'en': traduzir_texto(texto_pt, 'en'),
        'es': traduzir_texto(texto_pt, 'es'),
    }


def adicionar_traducao_customizada(
    texto_pt: str,
    en: str,
    es: str
) -> None:
    """
    Adiciona uma tradução customizada ao mapa.
    
    Args:
        texto_pt: Texto em português
        en: Tradução em inglês
        es: Tradução em espanhol
    """
    if 'pt_BR' not in TRANSLATION_MAP:
        TRANSLATION_MAP['pt_BR'] = {}
    
    TRANSLATION_MAP['pt_BR'][texto_pt] = {'en': en, 'es': es}
    logger.info(f"Tradução customizada adicionada: {texto_pt}")
