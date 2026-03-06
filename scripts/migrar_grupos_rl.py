#!/usr/bin/env python3
"""
Migração de grupos RL:

- Cria documentos na coleção `grupos_rl` a partir dos chamados existentes
  com categoria "Projetos" e campo rl_codigo preenchido.
- Atualiza cada chamado elegível com o campo `grupo_rl_id` correspondente.

Uso:
    python scripts/migrar_grupos_rl.py
"""

import os
import sys

# Adiciona a raiz do projeto ao path (script está em scripts/)
_raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _raiz)

from app.database import db  # noqa: E402
from app.models_grupo_rl import GrupoRL  # noqa: E402


def migrar_grupos_rl():
    print("\n" + "=" * 70)
    print("  🔄 MIGRAÇÃO - Grupos RL (grupos_rl + grupo_rl_id nos chamados)")
    print("=" * 70)

    chamados_ref = db.collection("chamados")
    docs = chamados_ref.stream()

    total = 0
    atualizados = 0
    ignorados_sem_rl = 0
    ignorados_categoria = 0
    ja_com_grupo = 0
    erros = 0

    for doc in docs:
        total += 1
        try:
            data = doc.to_dict() or {}
            categoria = data.get("categoria")
            rl_codigo = (data.get("rl_codigo") or "").strip()
            grupo_rl_id_atual = data.get("grupo_rl_id")

            if categoria != "Projetos":
                ignorados_categoria += 1
                continue

            if not rl_codigo:
                ignorados_sem_rl += 1
                continue

            if grupo_rl_id_atual:
                ja_com_grupo += 1
                continue

            # Cria ou obtém grupo RL e atualiza o chamado
            grupo = GrupoRL.get_or_create(
                rl_codigo=rl_codigo,
                criado_por_id=data.get("solicitante_id"),
                area=data.get("area"),
            )
            chamados_ref.document(doc.id).update({"grupo_rl_id": grupo.id})
            atualizados += 1
            print(f"   ✅ Chamado {doc.id} atualizado com grupo_rl_id={grupo.id}")

        except Exception as e:  # pragma: no cover - script de migração
            erros += 1
            print(f"   ❌ Erro ao processar chamado {doc.id}: {e}")

    print("\n" + "=" * 70)
    print("  📊 RESUMO DA MIGRAÇÃO DE GRUPOS RL")
    print("=" * 70)
    print(f"Total de chamados lidos:         {total}")
    print(f"Chamados categoria 'Projetos':   {total - ignorados_categoria}")
    print(f"  ➜ Ignorados sem rl_codigo:     {ignorados_sem_rl}")
    print(f"  ➜ Já tinham grupo_rl_id:       {ja_com_grupo}")
    print(f"  ➜ Atualizados com grupo_rl_id: {atualizados}")
    print(f"Erros durante processamento:     {erros}")
    print("=" * 70)


if __name__ == "__main__":  # pragma: no cover - execução direta
    migrar_grupos_rl()

