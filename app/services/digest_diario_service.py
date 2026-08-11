"""Serviço de digest diário de chamados abertos.

Feature separada do motor de escalonamento (app/services/sla_escalacao_
service.py): uma vez por dia, cada responsável com chamados `Aberto`/`Em
Atendimento` recebe um e-mail-resumo com TODOS eles (não só o que está
prestes a escalar), agrupados em "Vencidos / perto de vencer" (TAT já
estourado ou >=80% consumido) e "Abertos" (dentro do prazo normal) — cada
grupo ordenado por prioridade de categoria (AOG > Projetos > demais).

Gatilho por PESSOA, não por chamado: dispara 24h depois da abertura do
chamado pendente mais antigo dela (se nunca recebeu digest), e depois se
repete a cada 24h enquanto ela continuar com chamados abertos. O job
APScheduler chama processar_digest_diario() a cada 30 minutos.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app import db as db_module
from app.db.models.apoio import DigestDiarioUsuarioRow
from app.db.models.chamado import ChamadoRow
from app.models import Chamado
from app.services.notifications import notificar_digest_diario
from app.services.sla_escalacao_service import calcular_deadline_inicial
from config import Config

logger = logging.getLogger(__name__)

_JANELA_DIGEST = timedelta(hours=24)
_LIMIAR_PERTO_DE_VENCER = 0.8

_PRIORIDADE_CATEGORIA: dict[str, int] = {"AOG": 0, "Projetos": 1}
_PRIORIDADE_PADRAO = 2


def _prioridade_categoria(categoria: str) -> int:
    return _PRIORIDADE_CATEGORIA.get(categoria, _PRIORIDADE_PADRAO)


def _naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def _percentual_tat_consumido(
    categoria: str, status: str, data_abertura: datetime, agora: datetime
) -> float:
    """% do TAT consumido — reaproveita o mesmo cálculo de deadline do motor
    de escalonamento unificado, só pra decidir o agrupamento do digest (não
    grava nada, é derivado on-the-fly)."""
    deadline = calcular_deadline_inicial(categoria, status, data_abertura)
    total = (_naive(deadline) - _naive(data_abertura)).total_seconds()
    if total <= 0:
        return 1.0
    decorrido = (_naive(agora) - _naive(data_abertura)).total_seconds()
    return max(0.0, decorrido / total)


def processar_digest_diario(agora: datetime | None = None) -> dict:
    """Processa o digest diário pra todos os responsáveis elegíveis.

    Returns:
        dict com contadores: usuarios_processados, digests_enviados, erros
    """
    if agora is None:
        agora = datetime.now(ZoneInfo(Config.SLA_TIMEZONE))

    stats: dict = {"usuarios_processados": 0, "digests_enviados": 0, "erros": 0}

    try:
        with db_module.SessionLocal() as session:
            stmt = select(ChamadoRow).where(
                ChamadoRow.status.in_(("Aberto", "Em Atendimento")),
                ChamadoRow.responsavel_id.isnot(None),
            )
            rows = session.execute(stmt).scalars().all()
    except Exception as exc:
        logger.exception("Digest diário: erro ao consultar chamados: %s", exc)
        stats["erros"] += 1
        return stats

    por_usuario: dict[str, list[ChamadoRow]] = {}
    for row in rows:
        por_usuario.setdefault(row.responsavel_id, []).append(row)

    for usuario_id, chamados_rows in por_usuario.items():
        stats["usuarios_processados"] += 1
        try:
            if _processar_usuario(usuario_id, chamados_rows, agora):
                stats["digests_enviados"] += 1
        except Exception as exc:
            logger.exception("Digest diário: erro ao processar usuário %s: %s", usuario_id, exc)
            stats["erros"] += 1

    return stats


def _processar_usuario(usuario_id: str, chamados_rows: list[ChamadoRow], agora: datetime) -> bool:
    agora_naive = _naive(agora)
    mais_antigo_naive = min(_naive(row.data_abertura) for row in chamados_rows)

    with db_module.SessionLocal() as session:
        estado = session.get(DigestDiarioUsuarioRow, usuario_id)
        ultimo_envio = estado.ultimo_envio_em if estado else None

    if ultimo_envio is not None:
        elegivel = agora_naive - _naive(ultimo_envio) >= _JANELA_DIGEST
    else:
        elegivel = agora_naive - mais_antigo_naive >= _JANELA_DIGEST

    if not elegivel:
        return False

    from app.models_usuario import Usuario

    usuario = Usuario.get_by_id(usuario_id)
    email_dest = (getattr(usuario, "email", None) or "").strip() if usuario else ""
    if not email_dest:
        logger.warning("Digest diário: usuário %s sem e-mail cadastrado; pulado.", usuario_id)
        return False

    grupos = _ordenar_e_agrupar(chamados_rows, agora)
    notificar_digest_diario(
        usuario_id=usuario_id,
        email_dest=email_dest,
        vencidos_ou_perto=grupos["vencidos_ou_perto"],
        abertos=grupos["abertos"],
    )

    with db_module.SessionLocal() as session, session.begin():
        estado = session.get(DigestDiarioUsuarioRow, usuario_id)
        if estado is None:
            session.add(DigestDiarioUsuarioRow(usuario_id=usuario_id, ultimo_envio_em=agora_naive))
        else:
            estado.ultimo_envio_em = agora_naive

    return True


def _ordenar_e_agrupar(chamados_rows: list[ChamadoRow], agora: datetime) -> dict:
    vencidos_ou_perto: list[dict] = []
    abertos: list[dict] = []

    for row in chamados_rows:
        chamado = Chamado._from_row(row)
        data = chamado.to_dict()
        pct = _percentual_tat_consumido(
            data["categoria"], data["status"], data["data_abertura"], agora
        )
        item = {**data, "id": chamado.id, "_pct_tat": pct}
        (vencidos_ou_perto if pct >= _LIMIAR_PERTO_DE_VENCER else abertos).append(item)

    def _chave_ordenacao(item: dict) -> tuple:
        return (_prioridade_categoria(item["categoria"]), -item["_pct_tat"])

    vencidos_ou_perto.sort(key=_chave_ordenacao)
    abertos.sort(key=_chave_ordenacao)
    return {"vencidos_ou_perto": vencidos_ou_perto, "abertos": abertos}
