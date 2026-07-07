"""
Serviço de tradução automática para múltiplos idiomas.
Suporta tradução de Português para Inglês e Espanhol.

Prioridade: mapa estático → MyMemory API → texto original (fallback).
"""

import json
import logging
import os
import re
import threading
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

_translation_map_lock = threading.RLock()

_MYMEMORY_TIMEOUT = 5  # segundos; falha silenciosa se API demorar

# MyMemory às vezes devolve "tradução" sem nenhuma letra (ex.: "&&", "...", "123")
# quando o termo é curto/ambíguo. Sem essa checagem, o lixo é aceito e cacheado
# permanentemente em TRANSLATION_MAP.
_RESPOSTA_TEM_LETRA = re.compile(r"[^\W\d_]", re.UNICODE)


def _traduzir_via_mymemory(texto: str, idioma_destino: str) -> str | None:
    """Chama MyMemory API (pt → idioma_destino). Retorna None em qualquer falha."""
    try:
        params: dict = {"q": texto, "langpair": f"pt|{idioma_destino}"}
        email = os.environ.get("MYMEMORY_EMAIL", "").strip()
        if email:
            params["de"] = email
        url = "https://api.mymemory.translated.net/get?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=_MYMEMORY_TIMEOUT) as resp:  # nosec B310
            data = json.loads(resp.read().decode())
        if data.get("responseStatus") == 200:
            traduzido = data["responseData"].get("translatedText", "")
            if traduzido and "LIMIT" not in traduzido.upper():
                if _RESPOSTA_TEM_LETRA.search(traduzido):
                    return traduzido
                logger.warning(
                    "MyMemory devolveu tradução sem letras para '%s' → %s: %r",
                    texto,
                    idioma_destino,
                    traduzido,
                )
                return None
        logger.warning(
            "MyMemory retornou status inesperado para '%s': %s", texto, data.get("responseStatus")
        )
    except Exception as e:
        logger.warning("MyMemory API indisponível para '%s' → %s: %s", texto, idioma_destino, e)
    return None


# Mapeamento de traduções comuns (fallback se API não disponível)
TRANSLATION_MAP = {
    "pt_BR": {
        # Setores
        "Manutencao": {"en": "Maintenance", "es": "Mantenimiento"},
        "Manutenção": {"en": "Maintenance", "es": "Mantenimiento"},
        "Engenharia": {"en": "Engineering", "es": "Ingeniería"},
        # Nome novo (canônico) e alias legado Procurement para histórico
        "Compras": {"en": "Procurement", "es": "Aprovisionamiento"},
        "Qualidade": {"en": "Quality", "es": "Calidad"},
        "TI": {"en": "IT", "es": "TI"},
        "Administrativo": {"en": "Administrative", "es": "Administrativo"},
        "Recursos Humanos": {"en": "Human Resources", "es": "Recursos Humanos"},
        "Financeiro": {"en": "Finance", "es": "Finanzas"},
        # Nome novo (canônico) e alias legado PPCP para histórico
        "Planejamento de Produção": {
            "en": "Production Planning",
            "es": "Planificación de Producción",
        },
        "PPCP": {"en": "Production Planning", "es": "Planificación de Producción"},
        "Commercial": {"en": "Commercial", "es": "Comercial"},
        "Suprimentos": {"en": "Supplies", "es": "Suministros"},
        "Planejamento Materiais": {"en": "Material Planning", "es": "Planificación de Materiales"},
        "Logistica": {"en": "Logistics", "es": "Logística"},
        "Logística": {"en": "Logistics", "es": "Logística"},
        "Infraestrutura": {"en": "Facility", "es": "Instalaciones"},
        "RH": {"en": "HR", "es": "RRHH"},
        "Produção - Montagem": {"en": "Production - Assembly", "es": "Producción - Montaje"},
        "Produção - Usinagem": {"en": "Production - Machining", "es": "Producción - Mecanizado"},
        "Produção - Inspeções": {
            "en": "Production - Inspections",
            "es": "Producción - Inspecciones",
        },
        "Produção - Processos Especiais": {
            "en": "Production - Special Processes",
            "es": "Producción - Procesos Especiales",
        },
        "Procurement": {"en": "Procurement", "es": "Aprovisionamiento"},
        # Gates — aliases legados (leitura de histórico antigo)
        "Gate 1": {"en": "Gate 1", "es": "Gate 1"},
        "Gate 2": {"en": "Gate 2", "es": "Gate 2"},
        "Gate 3": {"en": "Gate 3", "es": "Gate 3"},
        "Gate 4": {"en": "Gate 4", "es": "Gate 4"},
        "Gate 5": {"en": "Gate 5", "es": "Gate 5"},
        # Valores canônicos completos
        "Gate 1 - Desmontagem": {"en": "Gate 1 - Disassembly", "es": "Gate 1 - Desmontaje"},
        "Gate 1 - Limpeza": {"en": "Gate 1 - Cleaning", "es": "Gate 1 - Limpieza"},
        "Gate 1 - Remoção de Tinta": {
            "en": "Gate 1 - Paint Removal",
            "es": "Gate 1 - Remoción de Pintura",
        },
        "Gate 1 - Reconciliação": {
            "en": "Gate 1 - Reconciliation",
            "es": "Gate 1 - Reconciliación",
        },
        "Gate 2 - Forno": {"en": "Gate 2 - Oven", "es": "Gate 2 - Horno"},
        "Gate 2 - FPI": {"en": "Gate 2 - FPI", "es": "Gate 2 - FPI"},
        "Gate 2 - MPI": {"en": "Gate 2 - MPI", "es": "Gate 2 - MPI"},
        "Gate 2 - Inspeção": {"en": "Gate 2 - Inspection", "es": "Gate 2 - Inspección"},
        "Gate 3 - Galvanoplastia": {
            "en": "Gate 3 - Electroplating",
            "es": "Gate 3 - Galvanoplastia",
        },
        "Gate 3 - Usinagem": {"en": "Gate 3 - Machining", "es": "Gate 3 - Mecanizado"},
        "Gate 3 - Bucha": {"en": "Gate 3 - Bushing", "es": "Gate 3 - Buje"},
        "Gate 3 - Pintura": {"en": "Gate 3 - Painting", "es": "Gate 3 - Pintura"},
        "Gate 4 - Inspeção de Partes": {
            "en": "Gate 4 - Parts Inspection",
            "es": "Gate 4 - Inspección de Partes",
        },
        "Gate 4 - Montagem": {"en": "Gate 4 - Assembly", "es": "Gate 4 - Montaje"},
        "Gate 4 - Testes": {"en": "Gate 4 - Tests", "es": "Gate 4 - Pruebas"},
        "Gate 4 - Inspeção Final": {
            "en": "Gate 4 - Final Inspection",
            "es": "Gate 4 - Inspección Final",
        },
        # Impactos
        "Crítico": {"en": "Critical", "es": "Crítico"},
        "Alto": {"en": "High", "es": "Alto"},
        "Médio": {"en": "Medium", "es": "Medio"},
        "Baixo": {"en": "Low", "es": "Bajo"},
    }
}


def traduzir_texto(texto: str, idioma_destino: str = "en") -> str:
    """Traduz texto PT → idioma_destino.

    Ordem: mapa estático → MyMemory API → texto original.
    Resultados da API são cacheados no mapa para evitar chamadas repetidas.
    """
    try:
        # 1–2. Mapa estático/cache (leitura protegida por lock)
        with _translation_map_lock:
            entrada = TRANSLATION_MAP["pt_BR"].get(texto)
            if entrada and idioma_destino in entrada:
                return entrada[idioma_destino]

            if not entrada:
                for chave, traducoes in TRANSLATION_MAP["pt_BR"].items():
                    if chave.lower() == texto.lower():
                        if idioma_destino in traducoes:
                            return traducoes[idioma_destino]
                        break

        # 3. API MyMemory (fora do lock — rede pode demorar)
        traduzido = _traduzir_via_mymemory(texto, idioma_destino)
        if traduzido:
            with _translation_map_lock:
                TRANSLATION_MAP["pt_BR"].setdefault(texto, {})[idioma_destino] = traduzido
            return traduzido

        logger.warning("Tradução não encontrada para: %s → %s", texto, idioma_destino)
        return texto
    except Exception as e:
        logger.error("Erro ao traduzir: %s", e)
        return texto


def traduzir_categoria(texto_pt: str) -> dict[str, str]:
    """
    Traduz uma categoria para múltiplos idiomas.

    Args:
        texto_pt: Texto em português

    Returns:
        Dicionário com tradução em PT, EN e ES
    """
    return {
        "pt": texto_pt,
        "en": traduzir_texto(texto_pt, "en"),
        "es": traduzir_texto(texto_pt, "es"),
    }


def adicionar_traducao_customizada(texto_pt: str, en: str, es: str) -> None:
    """
    Adiciona uma tradução customizada ao mapa.

    Args:
        texto_pt: Texto em português
        en: Tradução em inglês
        es: Tradução em espanhol
    """
    with _translation_map_lock:
        if "pt_BR" not in TRANSLATION_MAP:
            TRANSLATION_MAP["pt_BR"] = {}

        TRANSLATION_MAP["pt_BR"][texto_pt] = {"en": en, "es": es}
    logger.info("Tradução customizada adicionada: %s", texto_pt)
