"""Limpeza manual de documentos antigos na coleção contadores_uso.

Documentos com campo `data` anterior ao corte (padrão: 90 dias) são removidos.
Por padrão roda em modo dry-run: apenas conta e exibe os documentos afetados.

Uso:
    python scripts/limpar_contadores_uso.py              # dry-run (só conta)
    python scripts/limpar_contadores_uso.py --apply      # deleta de verdade
    python scripts/limpar_contadores_uso.py --dias 30    # retenção de 30 dias
    python scripts/limpar_contadores_uso.py --apply --dias 30
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Limpa documentos antigos de contadores_uso no Firestore."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Executa a deleção (padrão: dry-run)",
    )
    parser.add_argument(
        "--dias",
        type=int,
        default=90,
        help="Retenção em dias (padrão: 90)",
    )
    args = parser.parse_args()

    dry_run = not args.apply

    if dry_run:
        logger.info("Modo DRY-RUN — nenhum documento será deletado.")
    else:
        logger.info("Modo APPLY — documentos anteriores a %d dias serão DELETADOS.", args.dias)

    from app import create_app

    app = create_app()
    with app.app_context():
        from app.services.contadores_uso import limpar_contadores_antigos

        resultado = limpar_contadores_antigos(dias=args.dias, dry_run=dry_run)

    if dry_run:
        print(f"[DRY-RUN] Documentos que seriam removidos: {resultado['removidos']}")
    else:
        print(f"Documentos removidos: {resultado['removidos']}")

    if resultado["erros"]:
        print(f"Erros encontrados: {resultado['erros']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
