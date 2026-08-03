"""
Serviço de listagem de chamados.

Centraliza a lógica de listagem para "Meus chamados" (solicitante), com
paginação por cursor (keyset sobre prioridade/data_abertura/id) e contagens
por status via aggregation query no Postgres.
"""

import logging
from collections import defaultdict
from typing import Any

from sqlalchemy import and_, func, or_, select

from app import db as db_module
from app.db.models.chamado import ChamadoObservadorRow, ChamadoParticipanteRow, ChamadoRow
from app.models import Chamado

logger = logging.getLogger(__name__)

_STATUS = ("Aberto", "Em Atendimento", "Concluído", "Cancelado")


def _carregar_participantes_observadores_em_lote(
    session, chamado_ids: list[int]
) -> tuple[dict[int, list[dict]], dict[int, list[dict]]]:
    """Batch-load de participantes/observadores pra evitar N+1 queries na listagem."""
    participantes_por_chamado: dict[int, list[dict]] = defaultdict(list)
    observadores_por_chamado: dict[int, list[dict]] = defaultdict(list)
    if not chamado_ids:
        return participantes_por_chamado, observadores_por_chamado

    rows_part = (
        session.execute(
            select(ChamadoParticipanteRow).where(ChamadoParticipanteRow.chamado_id.in_(chamado_ids))
        )
        .scalars()
        .all()
    )
    for r in rows_part:
        participantes_por_chamado[r.chamado_id].append(
            {
                "supervisor_id": r.supervisor_id,
                "area": r.area,
                "status": r.status,
                "concluido_em": r.concluido_em,
            }
        )

    rows_obs = (
        session.execute(
            select(ChamadoObservadorRow).where(ChamadoObservadorRow.chamado_id.in_(chamado_ids))
        )
        .scalars()
        .all()
    )
    for r in rows_obs:
        observadores_por_chamado[r.chamado_id].append(
            {"usuario_id": r.usuario_id, "nome": r.nome, "email": r.email}
        )

    return participantes_por_chamado, observadores_por_chamado


def _rows_para_chamados(session, rows: list[ChamadoRow]) -> list[Chamado]:
    """Converte ChamadoRow em Chamado, carregando participantes/observadores em lote."""
    ids = [r.id for r in rows]
    participantes_map, observadores_map = _carregar_participantes_observadores_em_lote(session, ids)
    chamados: list[Chamado] = []
    for row in rows:
        try:
            chamados.append(
                Chamado._from_row(
                    row, participantes_map.get(row.id, []), observadores_map.get(row.id, [])
                )
            )
        except Exception as exc:
            logger.warning("Chamado %s ignorado (dados inválidos): %s", row.id, exc)
    return chamados


def _aplicar_grupo_key(chamados: list[Chamado]) -> None:
    """Calcula grupo_key para ordenar grupos AOG/Projetos antes dos demais no Jinja groupby."""
    _grupo_prio: dict = defaultdict(lambda: 1)
    for c in chamados:
        rl = c.rl_codigo or ""
        prio = getattr(c, "prioridade", 1)
        if prio < _grupo_prio[rl]:
            _grupo_prio[rl] = prio
    for c in chamados:
        rl = c.rl_codigo or ""
        c.grupo_key = f"{_grupo_prio[rl]}|{rl}"


def contar_status_por_solicitante(user_id: str) -> dict[str, int]:
    """Contagem por status dos chamados do solicitante (aggregation query, sem
    carregar documentos) — usada no badge do formulário de novo chamado."""
    with db_module.SessionLocal() as session:
        status_counts = {}
        for st in _STATUS:
            stmt = (
                select(func.count())
                .select_from(ChamadoRow)
                .where(ChamadoRow.solicitante_id == user_id, ChamadoRow.status == st)
            )
            status_counts[st] = session.execute(stmt).scalar() or 0
    return status_counts


def listar_chamados_como_observador(
    user_id: str,
    limite: int = 200,
) -> list:
    """Retorna chamados onde user_id consta como observador (chamados_observadores).

    Returns:
        Lista de objetos Chamado com atributo extra em_copia=True.
    """
    with db_module.SessionLocal() as session:
        stmt = (
            select(ChamadoRow)
            .join(ChamadoObservadorRow, ChamadoObservadorRow.chamado_id == ChamadoRow.id)
            .where(ChamadoObservadorRow.usuario_id == user_id)
            .order_by(ChamadoRow.data_abertura.desc())
            .limit(limite)
        )
        rows = session.execute(stmt).scalars().all()
        chamados = _rows_para_chamados(session, rows)

    for c in chamados:
        c.em_copia = True
    return chamados


def listar_meus_chamados(
    user_id: str,
    status_filtro: str = "",
    rl_codigo: str = "",
    cursor: str = "",
    cursor_prev: str = "",
    pagina_atual: int = 1,
    itens_por_pagina: int = 10,
) -> dict[str, Any]:
    """
    Lista chamados do solicitante com paginação por cursor (keyset).

    Returns:
        Dict com: chamados, pagina_atual, total_paginas, total_chamados,
        status_counts, cursor_next, cursor_prev.
    """
    rl_codigo = (rl_codigo or "").strip()

    with db_module.SessionLocal() as session:
        base_filters = [ChamadoRow.solicitante_id == user_id]
        if rl_codigo:
            base_filters.append(ChamadoRow.rl_codigo == rl_codigo)

        filtros = list(base_filters)
        if status_filtro:
            filtros.append(ChamadoRow.status == status_filtro)

        # Cache status_counts por (user_id, rl_codigo) — evita 4 aggregation queries por request
        _status_cache_key = f"status_counts:{user_id}:{rl_codigo}"
        try:
            from app.cache import cache_get

            status_counts = cache_get(_status_cache_key)
        except Exception:
            status_counts = None

        def _contar(filtros_extra) -> int:
            stmt = select(func.count()).select_from(ChamadoRow).where(*filtros_extra)
            return session.execute(stmt).scalar() or 0

        if status_counts is not None:
            # Deriva total a partir do cache — elimina a 5ª query (contar_total) também
            total_chamados = (
                status_counts.get(status_filtro, 0)
                if status_filtro
                else sum(status_counts.values())
            )
        else:
            total_chamados = _contar(filtros)
            status_counts = {
                st: _contar([*base_filters, ChamadoRow.status == st]) for st in _STATUS
            }

            try:
                from app.cache import cache_set

                cache_set(_status_cache_key, status_counts, 45)
            except Exception as e:
                logger.debug("Cache indisponível ao salvar status_counts: %s", e)

        total_paginas = max(1, (total_chamados + itens_por_pagina - 1) // itens_por_pagina)
        pagina_atual = max(1, min(pagina_atual, total_paginas))

        stmt = select(ChamadoRow).where(*filtros)

        cursor_row = None
        if cursor:
            try:
                cursor_row = session.get(ChamadoRow, int(cursor))
            except (TypeError, ValueError) as e:
                logger.debug("Cursor inválido em meus_chamados: %s", e)
                cursor_row = None

        if cursor_row is not None:
            p0, d0, id0 = cursor_row.prioridade, cursor_row.data_abertura, cursor_row.id
            stmt = stmt.where(
                or_(
                    ChamadoRow.prioridade > p0,
                    and_(ChamadoRow.prioridade == p0, ChamadoRow.data_abertura < d0),
                    and_(
                        ChamadoRow.prioridade == p0,
                        ChamadoRow.data_abertura == d0,
                        ChamadoRow.id > id0,
                    ),
                )
            )

        # Ordena por prioridade (Projetos=0 primeiro), depois data_abertura desc,
        # com id como desempate estável (data_abertura pode empatar dentro da
        # mesma transação — server_default now() é por transação, não por statement).
        stmt = stmt.order_by(
            ChamadoRow.prioridade.asc(), ChamadoRow.data_abertura.desc(), ChamadoRow.id.asc()
        ).limit(itens_por_pagina + 1)

        rows = list(session.execute(stmt).scalars().all())
        tem_proxima = len(rows) > itens_por_pagina
        if tem_proxima:
            rows = rows[:itens_por_pagina]

        cursor_next = str(rows[-1].id) if rows and tem_proxima else None
        cursor_prev_resultado = str(rows[0].id) if rows and cursor else None

        chamados = _rows_para_chamados(session, rows)

    _aplicar_grupo_key(chamados)

    return {
        "chamados": chamados,
        "pagina_atual": pagina_atual,
        "total_paginas": total_paginas,
        "total_chamados": total_chamados,
        "status_counts": status_counts,
        "cursor_next": cursor_next,
        "cursor_prev": cursor_prev_resultado,
    }
