"""Testes do serviço de tradução (translation_service)."""

import pytest
from app.services.translation_service import traduzir_texto, traduzir_categoria, adicionar_traducao_customizada, TRANSLATION_MAP


def test_traduzir_texto_do_mapa_pt_para_en():
    """Traduz termos do mapa PT -> EN."""
    assert traduzir_texto('Manutencao', 'en') == 'Maintenance'
    assert traduzir_texto('Engenharia', 'en') == 'Engineering'
    assert traduzir_texto('Qualidade', 'en') == 'Quality'


def test_traduzir_texto_do_mapa_pt_para_es():
    """Traduz termos do mapa PT -> ES."""
    assert traduzir_texto('Manutencao', 'es') == 'Mantenimiento'
    assert traduzir_texto('Engenharia', 'es') == 'Ingeniería'


def test_traduzir_texto_nao_encontrado_retorna_original():
    """Termo não presente no mapa retorna o texto original."""
    assert traduzir_texto('TermoQualquer', 'en') == 'TermoQualquer'


def test_traduzir_categoria_retorna_dict_pt_en_es():
    """traduzir_categoria retorna dicionário com chaves pt, en, es."""
    result = traduzir_categoria('Manutencao')
    assert 'pt' in result and 'en' in result and 'es' in result
    assert result['en'] == 'Maintenance'
    assert isinstance(result, dict)


def test_adicionar_traducao_customizada():
    """adicionar_traducao_customizada adiciona entrada ao TRANSLATION_MAP (texto_pt, en, es)."""
    adicionar_traducao_customizada('SetorTeste', 'TestSector', 'SectorPrueba')
    assert 'SetorTeste' in TRANSLATION_MAP['pt_BR']
    assert TRANSLATION_MAP['pt_BR']['SetorTeste']['en'] == 'TestSector'
    assert TRANSLATION_MAP['pt_BR']['SetorTeste']['es'] == 'SectorPrueba'
