"""
Serviço de Filtros para Dashboard de Chamados

Aplica múltiplos filtros a uma consulta Postgres (SQLAlchemy) para buscar
chamados específicos. Usa keyset pagination (data_abertura DESC, id DESC)
para paginação por cursor consistente e eficiente (sem OFFSET).

**Filtros Disponíveis:**

| Parâmetro | Exemplos | Comportamento |
|-----------|----------|---------------|
| `status` | 'Aberto', 'Em Atendimento', 'Concluído' | Filtra por status exato |
| `categoria` | 'Projetos', 'Manutenção' | Filtra por categoria |
| `gate` | 'Gate 1', 'Gate 2' | Filtra por gate (produção) |
| `responsavel` | Nome do responsável | Chamados atribuídos a supervisor |
| `rl_codigo` | Código RL | Chamados de uma RL específica |
| `search` | Qualquer texto | Busca em descrição, código RL, etc (case-insensitive) |
| Valor 'Todos'/'Todas' | Qualquer filtro | Ignora o filtro (retorna tudo) |

**Estratégia:**

1. **Condições SQL:** status, gate, responsavel, rl_codigo, categoria viram WHERE
   (índices compostos cobrem essas combinações — ver `app/db/models/chamado.py`).
2. **Filtro em Memória:** search (substring match) é aplicado após buscar do
   Postgres — sem suporte nativo a substring indexado nas colunas de texto.
3. **Cursor-Based Pagination:** keyset (data_abertura, id) em vez de OFFSET.

**Exemplos de Uso:**

```python
condicoes_base = [ChamadoRow.supervisor_ids_com_acesso.contains([user.id])]
resultado = aplicar_filtros_dashboard_com_paginacao(
    condicoes_base, args={'status': 'Aberto'}, limite=50, cursor=None
)
if resultado['tem_proxima']:
    # Buscar próxima página usando resultado['proximo_cursor']
```

**Notas Importantes:**
- Filtros são case-sensitive para status/categoria
- Search é substring match (parcial), case-insensitive
- Valor vazio em status/gate/categoria ignora o filtro
- Cursor vazio ou inválido reinicia do início
"""

import logging
from typing import Any

from sqlalchemy import and_, or_, select

from app import db as db_module
from app.db.models.chamado import ChamadoRow

logger = logging.getLogger(__name__)


def _construir_condicoes_filtro(
    args: dict[str, Any],
) -> tuple[list[Any], str | None, str | None, str | None]:
    """Monta as condições SQL (status, gate, responsavel, rl_codigo, categoria).

    Returns:
        Tuple (condicoes, status, gate, categoria).
    """
    status = args.get("status")
    gate = args.get("gate")
    categoria = args.get("categoria")
    responsavel = (args.get("responsavel") or "").strip()
    rl_codigo = (args.get("rl_codigo") or "").strip()

    condicoes: list[Any] = []

    if status and status not in ("", "Todos"):
        condicoes.append(ChamadoRow.status == status)

    if gate and gate not in ("", "Todos"):
        condicoes.append(ChamadoRow.gate == gate)

    if responsavel:
        condicoes.append(ChamadoRow.responsavel == responsavel)

    if rl_codigo:
        condicoes.append(ChamadoRow.rl_codigo == rl_codigo)

    if categoria and categoria not in ("", "Todas"):
        condicoes.append(ChamadoRow.categoria == categoria)

    return condicoes, status, gate, categoria


def construir_condicoes_para_contagem(args: dict[str, Any]) -> list[Any]:
    """Retorna as mesmas condições de filtro usadas no dashboard, pra uso em COUNT(*).

    Quando há filtro em memória (search), a contagem retornada pode ser maior
    que o número real de resultados exibidos.
    """
    condicoes, _, _, _ = _construir_condicoes_filtro(args)
    return condicoes


def _aplicar_busca_em_memoria(chamados: list[Any], search: str | None) -> list[Any]:
    """Busca por texto (case-insensitive) — único filtro genuinamente em memória.

    Substring match não tem suporte nativo indexado no schema atual; aplicado
    sobre a página já carregada (não sobre a coleção inteira).
    """
    if not search:
        return chamados
    termo = search.lower()
    return [
        c
        for c in chamados
        if termo in (c.descricao or "").lower()
        or termo in (c.rl_codigo or "").lower()
        or termo in (c.responsavel or "").lower()
        or termo in (c.numero_chamado or "").lower()
    ]


def _obter_ancora(session, cursor_id: str | None) -> ChamadoRow | None:
    """Busca a linha-âncora do cursor (para montar a condição de keyset)."""
    if not cursor_id:
        return None
    try:
        cid = int(cursor_id)
    except (TypeError, ValueError):
        return None
    return session.get(ChamadoRow, cid)


def aplicar_filtros_dashboard_com_paginacao(
    condicoes_base: list[Any],
    args: dict[str, Any],
    limite: int = 50,
    cursor: str | None = None,
    cursor_anterior: str | None = None,
) -> dict[str, Any]:
    """
    Paginação por cursor (keyset pagination) sobre chamados no Postgres.

    Ordem fixa: data_abertura DESC, id DESC (desempate) — índices compostos em
    `app/db/models/chamado.py` cobrem as combinações de filtro mais comuns.

    Args:
        condicoes_base: condições SQL de escopo (ex.: permissão por perfil/área),
            aplicadas em conjunto com os filtros de `args`.
        args: Argumentos da URL (filtros: status, gate, categoria, responsavel,
            rl_codigo, search).
        limite: Chamados por página (padrão: 50).
        cursor: ID do último chamado da página anterior (para próxima página).
        cursor_anterior: ID do primeiro chamado da página atual (para página anterior).

    Returns:
        {
            'docs': [Chamado, ...],
            'proximo_cursor': ID do último chamado da página,
            'tem_proxima': bool,
            'cursor_anterior': ID do primeiro chamado da página (para link "voltar"),
            'tem_anterior': bool
        }
    """
    from app.models import Chamado

    condicoes_extra, _, _, _ = _construir_condicoes_filtro(args)
    search = args.get("search")
    todas_condicoes = [*condicoes_base, *condicoes_extra]

    with db_module.SessionLocal() as session:
        if cursor_anterior:
            stmt = select(ChamadoRow).where(*todas_condicoes)
            ancora = _obter_ancora(session, cursor_anterior)
            if ancora is not None:
                stmt = stmt.where(
                    or_(
                        ChamadoRow.data_abertura > ancora.data_abertura,
                        and_(
                            ChamadoRow.data_abertura == ancora.data_abertura,
                            ChamadoRow.id > ancora.id,
                        ),
                    )
                )
            stmt = stmt.order_by(ChamadoRow.data_abertura.asc(), ChamadoRow.id.asc()).limit(
                limite + 1
            )
            rows = list(session.execute(stmt).scalars().all())
            tem_anterior = len(rows) > limite
            if tem_anterior:
                rows = rows[:limite]
            rows.reverse()
            chamados = _aplicar_busca_em_memoria([Chamado._from_row(r) for r in rows], search)
            primeiro_id = str(chamados[0].id) if chamados else None
            ultimo_id = str(chamados[-1].id) if chamados else None
            return {
                "docs": chamados,
                "proximo_cursor": ultimo_id,
                "tem_proxima": True,
                "cursor_anterior": primeiro_id,
                "tem_anterior": tem_anterior,
            }

        stmt = select(ChamadoRow).where(*todas_condicoes)
        ancora = _obter_ancora(session, cursor)
        if ancora is not None:
            stmt = stmt.where(
                or_(
                    ChamadoRow.data_abertura < ancora.data_abertura,
                    and_(
                        ChamadoRow.data_abertura == ancora.data_abertura,
                        ChamadoRow.id < ancora.id,
                    ),
                )
            )
        stmt = stmt.order_by(ChamadoRow.data_abertura.desc(), ChamadoRow.id.desc()).limit(
            limite + 1
        )
        rows = list(session.execute(stmt).scalars().all())
        tem_proxima = len(rows) > limite
        if tem_proxima:
            rows = rows[:limite]
        chamados = _aplicar_busca_em_memoria([Chamado._from_row(r) for r in rows], search)
        proximo_cursor = str(chamados[-1].id) if chamados else None
        primeiro_id = str(chamados[0].id) if chamados else None
        return {
            "docs": chamados,
            "proximo_cursor": proximo_cursor,
            "tem_proxima": tem_proxima and len(chamados) == limite,
            "cursor_anterior": primeiro_id,
            "tem_anterior": bool(cursor),
        }


def aplicar_filtros_dashboard(condicoes_base: list[Any], args: dict[str, Any]) -> list[Any]:
    """
    Função legada mantida para compatibilidade — sem cursor (começa do início).

    IMPORTANTE: Para usar cursor-based pagination, use aplicar_filtros_dashboard_com_paginacao()
    """
    resultado = aplicar_filtros_dashboard_com_paginacao(
        condicoes_base, args, limite=50, cursor=None
    )
    return resultado["docs"]
