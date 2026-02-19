#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script de teste para verificar o sistema de i18n
Valida se as traduções estão carregadas corretamente
"""

import sys
import os

# Adiciona o diretório do projeto ao path
sys.path.insert(0, os.path.dirname(__file__))

from app.i18n import TRANSLATIONS, SUPPORTED_LANGUAGES, get_translation

def testar_i18n():
    """Executa testes no sistema de i18n"""
    
    print("=" * 70)
    print("🧪 TESTE DO SISTEMA DE INTERNACIONALIZAÇÃO (i18n)")
    print("=" * 70)
    print()
    
    # Teste 1: Verificar idiomas suportados
    print("✅ TESTE 1: Idiomas Suportados")
    print("-" * 70)
    for code, nome in SUPPORTED_LANGUAGES.items():
        print(f"  [{code}] {nome}")
    print()
    
    # Teste 2: Verificar chaves traduzidas
    print("✅ TESTE 2: Quantidade de Chaves por Idioma")
    print("-" * 70)
    for lang, chaves in TRANSLATIONS.items():
        nome = SUPPORTED_LANGUAGES.get(lang, lang)
        quantidade = len(chaves)
        print(f"  {nome:20} → {quantidade:3d} chaves")
    print()
    
    # Teste 3: Verificar chaves comuns
    print("✅ TESTE 3: Chaves Comuns (presentes em todos os idiomas)")
    print("-" * 70)
    
    # Encontra chaves comuns
    chaves_pt = set(TRANSLATIONS['pt_BR'].keys())
    chaves_en = set(TRANSLATIONS['en'].keys())
    chaves_es = set(TRANSLATIONS['es'].keys())
    
    chaves_comuns = chaves_pt & chaves_en & chaves_es
    print(f"  Total de chaves comuns: {len(chaves_comuns)}")
    
    # Mostra as primeiras 10
    print(f"\n  Exemplos:")
    for i, chave in enumerate(sorted(chaves_comuns)[:10], 1):
        pt = TRANSLATIONS['pt_BR'][chave]
        en = TRANSLATIONS['en'][chave]
        es = TRANSLATIONS['es'][chave]
        print(f"    {i}. {chave}")
        print(f"       PT: {pt}")
        print(f"       EN: {en}")
        print(f"       ES: {es}")
    print()
    
    # Teste 4: Testar função get_translation
    print("✅ TESTE 4: Função get_translation()")
    print("-" * 70)
    
    test_key = 'dashboard_title'
    for lang in ['pt_BR', 'en', 'es']:
        resultado = get_translation(test_key, lang)
        print(f"  get_translation('{test_key}', '{lang}')")
        print(f"    → {resultado}")
    print()
    
    # Teste 5: Testar chaves faltando em algum idioma
    print("✅ TESTE 5: Verificar Completude das Traduções")
    print("-" * 70)
    
    # Encontra chaves que faltam em alguns idiomas
    todas_chaves = chaves_pt | chaves_en | chaves_es
    
    chaves_faltando = {
        'pt_BR': sorted(todas_chaves - chaves_pt),
        'en': sorted(todas_chaves - chaves_en),
        'es': sorted(todas_chaves - chaves_es),
    }
    
    incompleto = any(chaves_faltando.values())
    
    if incompleto:
        print("  ⚠️  Aviso: Algumas chaves estão faltando!")
        for lang, chaves in chaves_faltando.items():
            if chaves:
                print(f"    {lang}: faltando {len(chaves)} chave(s)")
                for chave in chaves[:3]:
                    print(f"      - {chave}")
    else:
        print("  ✅ Todas as chaves estão traduzidas em todos os idiomas!")
    print()
    
    # Teste 6: Validar fallback
    print("✅ TESTE 6: Teste de Fallback (chave inexistente)")
    print("-" * 70)
    
    resultado = get_translation('chave_inexistente', 'pt_BR')
    print(f"  get_translation('chave_inexistente', 'pt_BR')")
    print(f"    → {resultado} (retorna a própria chave)")
    print()
    
    # Teste 7: Exemplo de uso em template
    print("✅ TESTE 7: Exemplos de Uso em Templates")
    print("-" * 70)
    exemplos = [
        ("{{ t('dashboard_title') }}", "Título do dashboard"),
        ("{{ t('search_placeholder') }}", "Placeholder de busca"),
        ("{{ t('export') }}", "Botão de exportar"),
        ("{{ t('category') }}", "Label de categoria"),
    ]
    
    for template, descricao in exemplos:
        pt_valor = get_translation(template[5:-3], 'pt_BR')
        print(f"  {descricao}:")
        print(f"    Template: {template}")
        print(f"    PT-BR: {pt_valor}")
    print()
    
    # Resumo
    print("=" * 70)
    print("📊 RESUMO DOS TESTES")
    print("=" * 70)
    print(f"  ✅ Idiomas suportados: {len(SUPPORTED_LANGUAGES)}")
    print(f"  ✅ Chaves em PT-BR: {len(TRANSLATIONS['pt_BR'])}")
    print(f"  ✅ Chaves em EN: {len(TRANSLATIONS['en'])}")
    print(f"  ✅ Chaves em ES: {len(TRANSLATIONS['es'])}")
    print(f"  ✅ Chaves comuns: {len(chaves_comuns)}")
    print()
    
    if incompleto:
        print("  ⚠️  STATUS: Incompleto (algumas chaves faltando)")
        return 1
    else:
        print("  ✅ STATUS: OK - Sistema pronto para uso!")
        return 0

if __name__ == '__main__':
    exit_code = testar_i18n()
    sys.exit(exit_code)
