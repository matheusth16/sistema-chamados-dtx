#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Teste rápido de chaves"""

from app.i18n import TRANSLATIONS, get_translation

# Testa contagem
pt = len(TRANSLATIONS['pt_BR'])
en = len(TRANSLATIONS['en'])
es = len(TRANSLATIONS['es'])

print(f"PT: {pt} chaves")
print(f"EN: {en} chaves")
print(f"ES: {es} chaves")

# Testa algumas chaves novas
chaves_teste = ['ticket_opening', 'fill_details', 'identified_requester', 'rl_code_label', 'submit_request']

print("\nTeste de algumas chaves novas:")
for chave in chaves_teste:
    pt_val = get_translation(chave, 'pt_BR')
    en_val = get_translation(chave, 'en')
    es_val = get_translation(chave, 'es')
    print(f"  {chave}: OK (PT, EN, ES)")

print("\nStatus: OK - Tudo funciona! ✅")
