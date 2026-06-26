"""Script manual para reset do ranking semanal de gamificação.

Para execução automática, o APScheduler chama GamificationService.resetar_ranking_semanal()
toda domingo às 23h59 (BRT). Este script é mantido para execuções manuais com confirmação.

Uso:
    python scripts/reset_ranking_semanal.py          # pede confirmação interativa
    python scripts/reset_ranking_semanal.py --force  # executa sem confirmação
"""

import logging
import os
import sys

# Adicionar a raiz do projeto ao sys.path para importações absolutas
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def resetar_ranking_semanal():
    """Delega para GamificationService.resetar_ranking_semanal() — fonte única de verdade."""
    from app.services.gamification_service import GamificationService

    return GamificationService.resetar_ranking_semanal()


if __name__ == "__main__":
    from app import create_app

    app = create_app()
    with app.app_context():
        if "--force" not in sys.argv:
            try:
                resp = input(
                    "Tem certeza que deseja ZERAR o ranking semanal de todos os usuários? (s/N): "
                )
            except EOFError:
                resp = "n"
            if resp.lower() not in ["s", "sim", "y", "yes"]:
                print("Operação cancelada.")
                sys.exit(0)

        ok = resetar_ranking_semanal()
        if ok:
            print("Sucesso! Ranking semanal resetado.")
        else:
            print("Erro ao resetar ranking semanal. Verifique os logs.")
            sys.exit(1)
