"""Serviço de lembretes de confirmação de resolução.

Agenda:
  - 1º lembrete: 24 h após data_conclusao  (flag lembrete_confirmacao_1_enviado)
  - 2º lembrete: 48 h após data_conclusao  (flag lembrete_confirmacao_2_enviado)

Apenas chamados com status == "Concluído" e confirmacao_solicitante == "pendente" são
processados.  A flag é gravada APÓS envio bem-sucedido: se o e-mail falhar, o chamado
será retentado na próxima execução do job (a cada 6 h).
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select, update

from app import db as db_module
from app.db.models.chamado import ChamadoRow
from app.models_historico import Historico
from app.models_usuario import Usuario
from app.services.notifications import notificar_solicitante_lembrete_confirmacao

logger = logging.getLogger(__name__)

_LEMBRETE_1_HORAS = 24
_LEMBRETE_2_HORAS = 48


def _criar_inapp_lembrete(
    chamado_id: int, solicitante_id: str, numero_chamado: str, categoria: str, numero: int
) -> None:
    """Cria notificação in-app de lembrete de confirmação. Falha silenciosa com log."""
    try:
        from app.services.notifications_inapp import criar_notificacao_solicitante

        tipo = f"lembrete_confirmacao_{numero}"
        criar_notificacao_solicitante(
            solicitante_id=solicitante_id,
            chamado_id=chamado_id,
            numero_chamado=numero_chamado,
            categoria=categoria,
            tipo=tipo,
        )
    except Exception as exc:
        logger.warning("Lembrete %s in-app não criado para chamado %s: %s", numero, chamado_id, exc)


def _ts_para_datetime(ts) -> datetime | None:
    """Converte um timestamp (ou datetime) para datetime UTC aware."""
    if ts is None:
        return None
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            return ts.replace(tzinfo=UTC)
        return ts.astimezone(UTC)
    if hasattr(ts, "ToDatetime"):
        return ts.ToDatetime(tzinfo=UTC)
    return None


def _marcar_lembrete_enviado(chamado_id: int, numero: int) -> None:
    campo = f"lembrete_confirmacao_{numero}_enviado"
    with db_module.SessionLocal() as session, session.begin():
        row = session.get(ChamadoRow, chamado_id)
        if row is not None:
            setattr(row, campo, True)

    Historico(
        chamado_id=chamado_id,
        usuario_id="sistema",
        usuario_nome="Sistema (Lembrete de Confirmação)",
        acao="lembrete_confirmacao_enviado",
        campo_alterado=campo,
        valor_anterior=None,
        valor_novo=str(numero),
        detalhe=f"{numero}º lembrete ({_LEMBRETE_1_HORAS if numero == 1 else _LEMBRETE_2_HORAS}h após conclusão)",
    ).save()


def _claim_lembrete(chamado_id: int, numero: int) -> bool:
    campo = getattr(ChamadoRow, f"lembrete_confirmacao_{numero}_enviado")
    stmt = (
        update(ChamadoRow)
        .where(
            ChamadoRow.id == chamado_id,
            ChamadoRow.status == "Concluído",
            ChamadoRow.confirmacao_solicitante == "pendente",
            campo.is_(False),
        )
        .values({campo.key: True})
        .returning(ChamadoRow.id)
    )
    if numero == 2:
        stmt = stmt.where(ChamadoRow.lembrete_confirmacao_1_enviado.is_(True))
    with db_module.SessionLocal() as session, session.begin():
        return session.execute(stmt).scalar_one_or_none() is not None


def _liberar_lembrete(chamado_id: int, numero: int) -> None:
    campo = getattr(ChamadoRow, f"lembrete_confirmacao_{numero}_enviado")
    with db_module.SessionLocal() as session, session.begin():
        session.execute(
            update(ChamadoRow)
            .where(
                ChamadoRow.id == chamado_id,
                ChamadoRow.status == "Concluído",
                ChamadoRow.confirmacao_solicitante == "pendente",
                campo.is_(True),
            )
            .values({campo.key: False})
        )


def processar_lembretes_confirmacao(agora: datetime | None = None) -> dict:
    """Verifica chamados Concluídos pendentes de confirmação e envia lembretes.

    Retorna um dict de contadores: processados, lembrete_1, lembrete_2, erros.
    """
    if agora is None:
        agora = datetime.now(UTC)

    stats = {"processados": 0, "lembrete_1": 0, "lembrete_2": 0, "erros": 0}

    try:
        # limit(500): cobre o volume esperado em DTX. Se o backlog superar 500 chamados
        # pendentes de confirmação simultaneamente, os excedentes serão processados na
        # próxima execução do job (6 h). Adicione paginação por cursor se isso ocorrer.
        with db_module.SessionLocal() as session:
            stmt = (
                select(ChamadoRow)
                .where(
                    ChamadoRow.status == "Concluído",
                    ChamadoRow.confirmacao_solicitante == "pendente",
                )
                .limit(500)
            )
            rows = session.execute(stmt).scalars().all()
    except Exception as exc:
        logger.exception("Lembretes: erro ao consultar chamados pendentes: %s", exc)
        stats["erros"] += 1
        return stats

    for row in rows:
        stats["processados"] += 1
        try:
            _processar_chamado(row, agora, stats)
        except Exception as exc:
            logger.exception("Lembretes: erro ao processar chamado %s: %s", row.id, exc)
            stats["erros"] += 1

    return stats


def _processar_chamado(row: ChamadoRow, agora: datetime, stats: dict) -> None:
    data_conclusao = _ts_para_datetime(row.data_conclusao)
    if data_conclusao is None:
        return

    horas_decorridas = (agora - data_conclusao).total_seconds() / 3600

    enviou_1 = bool(row.lembrete_confirmacao_1_enviado)
    enviou_2 = bool(row.lembrete_confirmacao_2_enviado)

    if enviou_2:
        return  # ambos os lembretes já enviados

    chamado_id = row.id
    solicitante_id = row.solicitante_id
    numero_chamado = row.numero_chamado or "N/A"
    categoria = row.categoria or "Chamado"

    if not enviou_1 and horas_decorridas >= _LEMBRETE_1_HORAS:
        if not _claim_lembrete(chamado_id, 1):
            return
        solicitante = Usuario.get_by_id(solicitante_id) if solicitante_id else None
        enviado = notificar_solicitante_lembrete_confirmacao(
            chamado_id=chamado_id,
            numero_chamado=numero_chamado,
            categoria=categoria,
            solicitante_usuario=solicitante,
            numero_lembrete=1,
        )
        if enviado:
            _marcar_lembrete_enviado(chamado_id, 1)
            stats["lembrete_1"] += 1
            logger.info("Lembrete 1 enviado para chamado %s", chamado_id)
            if solicitante_id:
                _criar_inapp_lembrete(chamado_id, solicitante_id, numero_chamado, categoria, 1)
        else:
            _liberar_lembrete(chamado_id, 1)
            logger.warning("Lembrete 1 falhou para chamado %s — será tentado novamente", chamado_id)

    elif enviou_1 and not enviou_2 and horas_decorridas >= _LEMBRETE_2_HORAS:
        if not _claim_lembrete(chamado_id, 2):
            return
        solicitante = Usuario.get_by_id(solicitante_id) if solicitante_id else None
        enviado = notificar_solicitante_lembrete_confirmacao(
            chamado_id=chamado_id,
            numero_chamado=numero_chamado,
            categoria=categoria,
            solicitante_usuario=solicitante,
            numero_lembrete=2,
        )
        if enviado:
            _marcar_lembrete_enviado(chamado_id, 2)
            stats["lembrete_2"] += 1
            logger.info("Lembrete 2 enviado para chamado %s", chamado_id)
            if solicitante_id:
                _criar_inapp_lembrete(chamado_id, solicitante_id, numero_chamado, categoria, 2)
        else:
            _liberar_lembrete(chamado_id, 2)
            logger.warning("Lembrete 2 falhou para chamado %s — será tentado novamente", chamado_id)
