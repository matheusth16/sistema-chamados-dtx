#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Teste rápido para validar tradução de setores e categorias
"""

from app.i18n import get_translated_sector, get_translated_category, SECTOR_KEYS_MAP, CATEGORY_KEYS_MAP

# Testa setores em PT-BR
print("=== TESTE SETORES ===")
print("\nPortuguês (PT-BR):")
for setor_pt, chave in SECTOR_KEYS_MAP.items():
    traducao_pt = get_translated_sector(setor_pt, 'pt_BR')
    print(f"  {setor_pt:20} -> {traducao_pt}")

print("\nEnglish:")
for setor_pt, chave in SECTOR_KEYS_MAP.items():
    traducao_en = get_translated_sector(setor_pt, 'en')
    print(f"  {setor_pt:20} -> {traducao_en}")

print("\nEspañol:")
for setor_pt, chave in SECTOR_KEYS_MAP.items():
    traducao_es = get_translated_sector(setor_pt, 'es')
    print(f"  {setor_pt:20} -> {traducao_es}")

# Testa categorias em PT-BR
print("\n=== TESTE CATEGORIAS ===")
print("\nPortuguês (PT-BR):")
for cat_pt, chave in CATEGORY_KEYS_MAP.items():
    traducao_pt = get_translated_category(cat_pt, 'pt_BR')
    print(f"  {cat_pt:20} -> {traducao_pt}")

print("\nEnglish:")
for cat_pt, chave in CATEGORY_KEYS_MAP.items():
    traducao_en = get_translated_category(cat_pt, 'en')
    print(f"  {cat_pt:20} -> {traducao_en}")

print("\nEspañol:")
for cat_pt, chave in CATEGORY_KEYS_MAP.items():
    traducao_es = get_translated_category(cat_pt, 'es')
    print(f"  {cat_pt:20} -> {traducao_es}")

print("\n✅ Teste concluído!")
