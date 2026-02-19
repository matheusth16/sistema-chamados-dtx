#!/usr/bin/env python
"""Teste de importação de todos os módulos críticos."""

import sys
import traceback

modules_to_test = [
    'app.models',
    'app.models_usuario',
    'app.models_historico',
    'app.database',
    'app.services.analytics',
    'app.services.assignment',
    'app.services.excel_export_service',
    'app.routes.admin',
    'app.routes.chamados',
    'app',
]

errors = []
for module in modules_to_test:
    try:
        __import__(module)
        print(f"✓ {module}")
    except Exception as e:
        print(f"✗ {module}: {str(e)}")
        errors.append((module, e))

if errors:
    print(f"\n{len(errors)} erro(s) encontrado(s):")
    for mod, err in errors:
        print(f"\n{mod}:")
        traceback.print_exception(type(err), err, err.__traceback__)
    sys.exit(1)
else:
    print(f"\n✓ Todos os {len(modules_to_test)} módulos importados com sucesso!")
    sys.exit(0)
