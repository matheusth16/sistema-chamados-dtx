"""
Contadores de uso por usuário por dia (relatórios e export).

Usado para limite opcional por usuário: cada um pode gerar no máximo N
"ações pesadas" por dia (atualizar relatório, exportar Excel), evitando
limite global injusto quando todos compartilham o mesmo sistema.

Fase 2: armazenamento migrado de Firestore para PostgreSQL. A verificação e o
incremento são feitos numa única query atômica (INSERT ... ON CONFLICT DO
UPDATE ... WHERE contador < limite RETURNING) — sem transação explícita, o
próprio Postgres garante atomicidade contra requests simultâneos (F-13).
"""

import logging
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app import db as db_module
from app.db.models.apoio import ContadorUsoRow
from app.i18n import get_translation_session

logger = logging.getLogger(__name__)

CAMPO_RELATORIO = "relatorio_geracoes"
CAMPO_EXPORT = "export_excel_geracoes"


def _t(key, **kwargs):
    return get_translation_session(key, **kwargs)


def _hoje() -> date:
    return datetime.now(UTC).date()


def _verificar_incrementar(campo: str, limite: int, user_id: str) -> bool:
    """Verifica o limite e incrementa o contador atomicamente.

    Retorna True se a ação foi permitida (contador incrementado), False se o
    limite já havia sido atingido.
    """
    tabela = ContadorUsoRow.__table__
    campo_col = tabela.c[campo]
    hoje = _hoje()

    stmt = (
        pg_insert(ContadorUsoRow)
        .values(user_id=user_id, data=hoje, **{campo: 1})
        .on_conflict_do_update(
            index_elements=["user_id", "data"],
            set_={campo: campo_col + 1},
            where=campo_col < limite,
        )
        .returning(campo_col)
    )
    with db_module.SessionLocal() as session, session.begin():
        return session.execute(stmt).first() is not None


def verificar_e_incrementar_relatorio(user_id: str, limite_diario: int) -> tuple[bool, str | None]:
    """
    Verifica se o usuário pode gerar mais uma "atualização de relatório" hoje.
    Se sim, incrementa o contador e retorna (True, None).
    Se não, retorna (False, mensagem_erro).
    Se limite_diario <= 0, não aplica limite (retorna True).
    """
    if not user_id or limite_diario <= 0:
        return (True, None)
    try:
        permitido = _verificar_incrementar(CAMPO_RELATORIO, limite_diario, user_id)
        if not permitido:
            return (False, _t("report_update_limit_reached", limite=limite_diario))
        return (True, None)
    except Exception as e:
        logger.warning("Contador de uso (relatório): %s", e)
        return (True, None)


def verificar_e_incrementar_export(user_id: str, limite_diario: int) -> tuple[bool, str | None]:
    """
    Verifica se o usuário pode gerar mais um export Excel hoje.
    Se sim, incrementa e retorna (True, None). Senão (False, mensagem).
    Se limite_diario <= 0, não aplica limite.
    """
    if not user_id or limite_diario <= 0:
        return (True, None)
    try:
        permitido = _verificar_incrementar(CAMPO_EXPORT, limite_diario, user_id)
        if not permitido:
            return (False, _t("export_limit_reached", limite=limite_diario))
        return (True, None)
    except Exception as e:
        logger.warning("Contador de uso (export): %s", e)
        return (True, None)


def limpar_contadores_antigos(dias: int = 90, dry_run: bool = True) -> dict:
    """Remove registros de contadores_uso com mais de `dias` dias.

    Política de retenção: 90 dias (ver docs/ARQUITETURA.md).

    Args:
        dias: Registros mais antigos que este número de dias serão removidos.
        dry_run: Se True, apenas conta e loga sem deletar (padrão seguro).

    Returns:
        {"removidos": int, "dry_run": bool, "erros": int}
    """
    corte = (datetime.now(UTC) - timedelta(days=dias)).date()

    try:
        with db_module.SessionLocal() as session, session.begin():
            if dry_run:
                removidos = (
                    session.execute(
                        select(ContadorUsoRow.user_id).where(ContadorUsoRow.data < corte)
                    )
                    .scalars()
                    .all()
                )
                total = len(removidos)
                logger.info(
                    "limpar_contadores_antigos (dry-run): dias=%d corte=%s encontrados=%d",
                    dias,
                    corte,
                    total,
                )
                return {"removidos": total, "dry_run": True, "erros": 0}

            resultado = session.execute(delete(ContadorUsoRow).where(ContadorUsoRow.data < corte))
            total = resultado.rowcount
        logger.info(
            "limpar_contadores_antigos: dias=%d corte=%s removidos=%d erros=0", dias, corte, total
        )
        return {"removidos": total, "dry_run": False, "erros": 0}
    except Exception as e:
        logger.exception("Erro ao limpar contadores antigos: %s", e)
        return {"removidos": 0, "dry_run": dry_run, "erros": 1}
