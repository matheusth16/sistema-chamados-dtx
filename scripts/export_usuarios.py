#!/usr/bin/env python3
"""
Exporta nome, email, perfil e área de todos os usuários cadastrados para CSV.

Uso (a partir da raiz do projeto):
    python scripts/export_usuarios.py
    python scripts/export_usuarios.py --saida usuarios.csv
"""

import argparse
import csv
import os
import sys

_raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _raiz)

from app.models_usuario import Usuario  # noqa: E402


def _init_db_module() -> None:
    """Inicializa app.db.engine/SessionLocal sem subir a app Flask inteira
    (evita disparar o scheduler/APScheduler só para um export pontual)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import scoped_session, sessionmaker

    from app import db as db_module
    from app.db import normalizar_url_driver

    if db_module.SessionLocal is not None:
        return

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL não configurada no ambiente.")

    db_module.engine = create_engine(normalizar_url_driver(database_url), pool_pre_ping=True)
    db_module.SessionLocal = scoped_session(
        sessionmaker(bind=db_module.engine, autoflush=False, expire_on_commit=False)
    )


def main() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(os.path.join(_raiz, ".env"))
    except ImportError:
        pass

    _init_db_module()

    parser = argparse.ArgumentParser(
        description="Exporta usuários (nome, email, perfil, área) para CSV."
    )
    parser.add_argument(
        "--saida",
        default="usuarios_export.csv",
        help="Caminho do arquivo CSV de saída (padrão: usuarios_export.csv)",
    )
    args = parser.parse_args()

    usuarios = Usuario.get_all()
    if not usuarios:
        print("[INFO] Nenhum usuário encontrado.")
        return

    with open(args.saida, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["nome", "email", "perfil", "areas", "nivel_gestao", "ativo"])
        for u in usuarios:
            writer.writerow(
                [
                    u.nome,
                    u.email,
                    u.perfil,
                    ";".join(u.areas or []),
                    u.nivel_gestao or "",
                    "sim" if getattr(u, "ativo", True) else "não",
                ]
            )

    print(f"[OK] {len(usuarios)} usuário(s) exportado(s) para: {args.saida}")


if __name__ == "__main__":
    main()
