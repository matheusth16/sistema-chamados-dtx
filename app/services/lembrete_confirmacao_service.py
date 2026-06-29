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

from google.cloud.firestore_v1.base_query import FieldFilter

from app.database import db
from app.models_usuario import Usuario
from app.services.notifications import notificar_solicitante_lembrete_confirmacao

logger = logging.getLogger(__name__)

_LEMBRETE_1_HORAS = 24
_LEMBRETE_2_HORAS = 48


def _criar_inapp_lembrete(
    chamado_id: str, solicitante_id: str, numero_chamado: str, categoria: str, numero: int
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
    """Converte um Firestore Timestamp (ou datetime) para datetime UTC aware."""
    if ts is None:
        return None
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            return ts.replace(tzinfo=UTC)
        return ts.astimezone(UTC)
    if hasattr(ts, "ToDatetime"):
        return ts.ToDatetime(tzinfo=UTC)
    return None


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
        docs = (
            db.collection("chamados")
            .where(filter=FieldFilter("status", "==", "Concluído"))
            .where(filter=FieldFilter("confirmacao_solicitante", "==", "pendente"))
            .limit(500)
            .stream()
        )
    except Exception as exc:
        logger.exception("Lembretes: erro ao consultar Firestore: %s", exc)
        stats["erros"] += 1
        return stats

    for doc in docs:
        stats["processados"] += 1
        try:
            _processar_chamado(doc, agora, stats)
        except Exception as exc:
            logger.exception("Lembretes: erro ao processar chamado %s: %s", doc.id, exc)
            stats["erros"] += 1

    return stats


def _processar_chamado(doc, agora: datetime, stats: dict) -> None:
    data = doc.to_dict()

    data_conclusao = _ts_para_datetime(data.get("data_conclusao"))
    if data_conclusao is None:
        return

    horas_decorridas = (agora - data_conclusao).total_seconds() / 3600

    enviou_1 = bool(data.get("lembrete_confirmacao_1_enviado"))
    enviou_2 = bool(data.get("lembrete_confirmacao_2_enviado"))

    if enviou_2:
        return  # ambos os lembretes já enviados

    solicitante_id = data.get("solicitante_id")
    numero_chamado = data.get("numero_chamado") or "N/A"
    categoria = data.get("categoria") or "Chamado"

    if not enviou_1 and horas_decorridas >= _LEMBRETE_1_HORAS:
        solicitante = Usuario.get_by_id(solicitante_id) if solicitante_id else None
        enviado = notificar_solicitante_lembrete_confirmacao(
            chamado_id=doc.id,
            numero_chamado=numero_chamado,
            categoria=categoria,
            solicitante_usuario=solicitante,
            numero_lembrete=1,
        )
        if enviado:
            db.collection("chamados").document(doc.id).update(
                {"lembrete_confirmacao_1_enviado": True}
            )
            stats["lembrete_1"] += 1
            logger.info("Lembrete 1 enviado para chamado %s", doc.id)
            if solicitante_id:
                _criar_inapp_lembrete(doc.id, solicitante_id, numero_chamado, categoria, 1)
        else:
            logger.warning("Lembrete 1 falhou para chamado %s — será tentado novamente", doc.id)

    elif enviou_1 and not enviou_2 and horas_decorridas >= _LEMBRETE_2_HORAS:
        solicitante = Usuario.get_by_id(solicitante_id) if solicitante_id else None
        enviado = notificar_solicitante_lembrete_confirmacao(
            chamado_id=doc.id,
            numero_chamado=numero_chamado,
            categoria=categoria,
            solicitante_usuario=solicitante,
            numero_lembrete=2,
        )
        if enviado:
            db.collection("chamados").document(doc.id).update(
                {"lembrete_confirmacao_2_enviado": True}
            )
            stats["lembrete_2"] += 1
            logger.info("Lembrete 2 enviado para chamado %s", doc.id)
            if solicitante_id:
                _criar_inapp_lembrete(doc.id, solicitante_id, numero_chamado, categoria, 2)
        else:
            logger.warning("Lembrete 2 falhou para chamado %s — será tentado novamente", doc.id)
