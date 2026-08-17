"""
Serviço de Análise e Relatórios.

Fornece métricas de performance, insights e análises dos chamados:
- Métricas gerais (total, abertos, concluídos, taxa de resolução, tempo médio)
- Métricas por supervisor e por área
- Relatório completo com cache (Redis ou memória)
- Análise de atribuição e insights sugeridos
"""

import logging
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from statistics import mean
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select

import config as config_module
from app import db as db_module
from app.db.models.chamado import ChamadoRow
from app.services.business_time import percentual_prazo_resolucao

logger = logging.getLogger(__name__)

# Cache em memória (fallback quando Redis não está configurado), por período
# (dias) + escopo de área — cada seleção de período/área no seletor da UI tem
# sua própria entrada (chave: "relatorio_completo_{dias}_{areas ou 'all'}").
_RELATORIO_CACHE: dict[str, dict[str, Any]] = {}
_RELATORIO_CACHE_TTL_SEC = 300  # 5 minutos
# TTL para queries analíticas individuais — curto o suficiente para manter dados
# razoavelmente frescos, longo o suficiente para não re-escanear 2000 docs por minuto.
_ANALYTICS_QUERY_TTL_SEC = 60  # 1 minuto

# Limite máximo de registros em queries de analytics (protege performance/memória)
MAX_CHAMADOS_ANALYTICS = 2000


def _sla_dias_por_categoria(categoria: str, sla_dias_custom: int | None = None) -> int:
    """Retorna o prazo em dias do SLA. Se sla_dias_custom for fornecido (>0), usa-o.

    Lê de config.Config (SLA_DIAS_RESOLUCAO_PROJETOS/SLA_DIAS_RESOLUCAO_PADRAO)
    em vez de manter constantes hardcoded próprias — achado da auditoria
    2026-08-06: valores duplicados aqui podiam divergir silenciosamente do que
    sla_escalacao_service.py de fato usa pra escalar (fonte de verdade real).

    Resolve `config_module.Config` em tempo de chamada (não `from config import
    Config` no topo do arquivo): alguns testes fazem `importlib.reload(config)`,
    o que troca o objeto da classe Config — um bind feito na importação ficaria
    apontando pra classe antiga e nunca veria o valor atualizado.
    """
    if sla_dias_custom is not None and isinstance(sla_dias_custom, int) and sla_dias_custom > 0:
        return sla_dias_custom
    return (
        config_module.Config.SLA_DIAS_RESOLUCAO_PROJETOS
        if (categoria or "").strip() == "Projetos"
        else config_module.Config.SLA_DIAS_RESOLUCAO_PADRAO
    )


# Colunas DateTime(timezone=True) do Postgres sempre devolvem datetimes
# tz-aware (UTC); usar um mínimo naive aqui quebraria a comparação com
# data_limite/agora (também tz-aware) com TypeError.
_DATETIME_MIN_UTC = datetime.min.replace(tzinfo=UTC)


def _to_datetime(ts: Any) -> datetime | None:
    """Converte valor (datetime ou objeto tipo-Timestamp) para datetime. Evita queries extras."""
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts
    if hasattr(ts, "to_pydatetime"):
        return ts.to_pydatetime()
    return None


def _comparavel(dt: datetime, referencia: datetime) -> datetime:
    """Ajusta `dt` pra ter a mesma "awareness" de `referencia` (anexa UTC se
    referencia for aware e dt for naive; descarta tzinfo se referencia for
    naive e dt for aware) — evita TypeError comparando datetime tz-aware com
    naive. `_prazo_efetivo` pode devolver um `limite` tz-aware (quando há
    previsao_atendimento) mesmo que a data original de abertura/conclusão
    seja naive (comum em objetos de teste)."""
    if (dt.tzinfo is None) == (referencia.tzinfo is None):
        return dt
    return dt.replace(tzinfo=None) if referencia.tzinfo is None else dt.replace(tzinfo=UTC)


def _dentro_sla(
    data_abertura,
    data_conclusao,
    categoria: str,
    sla_dias_custom: int | None = None,
    previsao_atendimento: Any = None,
) -> bool | None:
    """True se concluído dentro do SLA, False se fora. None se não for possível calcular.

    previsao_atendimento (aprovada — ver previsao_atendimento_service.py) alarga
    o prazo quando for mais tarde que o TAT/sla_dias, nunca encurta."""
    dt_abertura = _to_datetime(data_abertura)
    dt_conclusao = _to_datetime(data_conclusao)
    if not dt_abertura or not dt_conclusao:
        return None
    dias = _sla_dias_por_categoria(categoria or "", sla_dias_custom)
    limite = _prazo_efetivo(dt_abertura + timedelta(days=dias), previsao_atendimento)
    return _comparavel(dt_conclusao, limite) <= limite


def _previsao_atendimento_instante(previsao_atendimento: Any) -> datetime | None:
    """Interpreta `previsao_atendimento` (aprovada — ver
    previsao_atendimento_service.py) como um horário no fuso de negócio
    (Config.SLA_TIMEZONE) — mesma convenção usada na escrita
    (solicitar_previsao_atendimento recebe naive do <input type=datetime-local>)
    e na leitura em sla_escalacao_service.py (compara ambos os lados como
    naive, no fuso de negócio).

    Colunas DateTime(timezone=True) do Postgres sempre devolvem datetimes
    tz-aware na leitura, mas o tzinfo anexado pelo driver não reflete o fuso
    de negócio — os dígitos continuam sendo o horário local gravado. Bug
    real (auditoria 2026-08-13): comparar esse valor direto contra
    datetime.now(UTC), como se o tzinfo anexado já fosse a hora UTC
    correta, introduzia um erro silencioso igual ao offset de
    Config.SLA_TIMEZONE. Por isso qualquer tzinfo existente é descartado e
    o valor é relocalizado antes de virar um instante comparável."""
    dt_previsao = _to_datetime(previsao_atendimento)
    if dt_previsao is None:
        return None
    return dt_previsao.replace(tzinfo=ZoneInfo(config_module.Config.SLA_TIMEZONE))


def _prazo_efetivo(limite: datetime, previsao_atendimento: Any) -> datetime:
    """Alarga `limite` pra `previsao_atendimento` (previsão de atendimento
    APROVADA — ver previsao_atendimento_service.py) quando ela for mais
    tarde que o TAT original. Nunca encurta: uma previsão que caiu antes do
    TAT original (não deveria acontecer no fluxo normal, mas por segurança)
    não teria efeito nenhum aqui."""
    dt_previsao = _previsao_atendimento_instante(previsao_atendimento)
    if dt_previsao is None:
        return limite
    a, b = limite, dt_previsao
    if a.tzinfo is None:
        a = a.replace(tzinfo=UTC)
    return dt_previsao if b > a else limite


def obter_sla_para_exibicao(chamado: Any, agora: datetime | None = None) -> dict[str, Any] | None:
    """Retorna dict para exibir SLA na Gestão (dashboard). Sem query ao banco.

    chamado: objeto com .data_abertura, .data_conclusao, .categoria, .status
    e opcionalmente .data_em_atendimento (usado quando status == 'Em Atendimento')
    e .previsao_atendimento (previsão de atendimento aprovada pelo gestor do
    setor — ver previsao_atendimento_service.py; unifica o antigo "Prazo do
    chamado (dias)" com "Adiar avisos de escalonamento": a data aprovada
    também vira o prazo oficial usado aqui, não só silencia e-mail).

    agora: instante de referência opcional (default: datetime.now(UTC)) — só
    pra permitir thread-through de um instante fixo em quem precisa de um
    único "agora" consistente entre várias chamadas (ex.: gestor_dashboard_service).

    Para status 'Em Atendimento' com data_em_atendimento presente, o percentual é
    calculado em tempo útil via percentual_prazo_resolucao (Escada B / SLA resolução).
    Nos demais casos usa a lógica de calendário (timedelta dias).

    Retorno: {'label': 'No prazo'|'Atrasado'|'Em risco', 'dentro_prazo': bool|None,
    'em_risco': bool} ou None."""
    data_abertura = getattr(chamado, "data_abertura", None)
    data_conclusao = getattr(chamado, "data_conclusao", None)
    categoria = getattr(chamado, "categoria", None) or ""
    status = getattr(chamado, "status", None) or "Aberto"
    sla_dias_custom = getattr(chamado, "sla_dias", None)
    data_em_atendimento = getattr(chamado, "data_em_atendimento", None)
    previsao_atendimento = getattr(chamado, "previsao_atendimento", None)
    dt_abertura = _to_datetime(data_abertura)
    if not dt_abertura:
        return None
    _agora_aware = agora or datetime.now(UTC)
    dias = _sla_dias_por_categoria(categoria, sla_dias_custom)
    limite = _prazo_efetivo(dt_abertura + timedelta(days=dias), previsao_atendimento)
    # Comparação consistente: ambos naive ou ambos aware (evita TypeError)
    if limite.tzinfo is not None:
        now = _agora_aware
    else:
        now = _agora_aware.replace(tzinfo=None) if _agora_aware.tzinfo else _agora_aware
    if status == "Cancelado":
        return None  # Chamados cancelados não entram em SLA
    if status == "Concluído":
        dt_conclusao = _to_datetime(data_conclusao)
        if not dt_conclusao:
            return None
        dentro = _comparavel(dt_conclusao, limite) <= limite
        return {
            "label": "No prazo" if dentro else "Atrasado",
            "dentro_prazo": dentro,
            "em_risco": False,
        }
    # Em Atendimento com data_em_atendimento — usa tempo útil (SLA resolução / Escada B).
    # Previsão de atendimento aprovada e ainda futura vale mais que o percentual
    # calculado sobre o TAT antigo: enquanto durar a previsão, o chamado está
    # "no prazo" mesmo que já tivesse estourado 50%/80% do prazo original.
    if status == "Em Atendimento":
        # Compara contra a própria data da previsão (não contra `limite`,
        # que nunca encurta abaixo do TAT original) — senão, uma vez
        # aprovada, o chamado ficaria "No prazo" pro resto da vida útil
        # mesmo com a previsão já vencida há muito tempo (bug real,
        # auditoria 2026-08-13).
        dt_previsao_instante = _previsao_atendimento_instante(previsao_atendimento)
        if dt_previsao_instante is not None and _agora_aware < dt_previsao_instante:
            return {"label": "No prazo", "dentro_prazo": True, "em_risco": False}
        dt_em_atendimento = _to_datetime(data_em_atendimento)
        if dt_em_atendimento is not None:
            # Normaliza para naive para compatibilidade com business_time
            agora_naive = now.replace(tzinfo=None) if now.tzinfo else now
            dt_naive = (
                dt_em_atendimento.replace(tzinfo=None)
                if dt_em_atendimento.tzinfo
                else dt_em_atendimento
            )
            pct = percentual_prazo_resolucao(dt_naive, categoria, agora_naive)
            if pct > 1.0:
                return {"label": "Atrasado", "dentro_prazo": False, "em_risco": False}
            if pct >= 0.5:  # alinhado com aviso 50% de processar_avisos_resolucao
                return {"label": "Em risco", "dentro_prazo": None, "em_risco": True}
            return {"label": "No prazo", "dentro_prazo": True, "em_risco": False}
    # Aberto ou Em Atendimento sem data_em_atendimento — lógica calendário
    if now > limite:
        return {"label": "Atrasado", "dentro_prazo": False, "em_risco": False}
    um_dia = timedelta(days=1)
    if (limite - now) <= um_dia:
        return {"label": "Em risco", "dentro_prazo": None, "em_risco": True}
    return {"label": "No prazo", "dentro_prazo": True, "em_risco": False}


class AnalisadorChamados:
    """Análise de performance e insights dos chamados"""

    @staticmethod
    def _buscar_chamados_dicts(
        data_abertura_gte: datetime | None = None,
        data_abertura_lt: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Busca chamados no Postgres e retorna como lista de dicts (mesmo
        shape de Chamado.to_dict()) — preserva a lógica de métricas abaixo,
        que opera inteiramente sobre dicts."""
        from app.models import Chamado

        with db_module.SessionLocal() as session:
            stmt = select(ChamadoRow).limit(MAX_CHAMADOS_ANALYTICS)
            if data_abertura_gte is not None:
                stmt = stmt.where(ChamadoRow.data_abertura >= data_abertura_gte)
            if data_abertura_lt is not None:
                stmt = stmt.where(ChamadoRow.data_abertura < data_abertura_lt)
            rows = session.execute(stmt).scalars().all()
        return [Chamado._from_row(row).to_dict() for row in rows]

    # ========== MÉTRICAS GERAIS ==========

    def obter_metricas_gerais(
        self, dias: int = 30, chamados_pre_carregados: list | None = None
    ) -> dict[str, Any]:
        """Retorna métricas gerais dos últimos N dias (até MAX_CHAMADOS_ANALYTICS docs).

        Se chamados_pre_carregados for fornecido (lista de dicts já materializados),
        filtra por data em Python — nenhuma query ao banco é feita.
        """
        cache_key = f"analytics_metricas_gerais_{dias}"
        if chamados_pre_carregados is None:
            try:
                from app.cache import cache_get

                cached = cache_get(cache_key)
                if cached is not None:
                    return cached
            except Exception as e:
                logger.debug("Cache indisponível (analytics): %s", e)
        try:
            data_limite = datetime.now(UTC) - timedelta(days=dias)

            if chamados_pre_carregados is not None:
                todos_chamados = [
                    c
                    for c in chamados_pre_carregados
                    if (_to_datetime(c.get("data_abertura")) or _DATETIME_MIN_UTC) >= data_limite
                ]
            else:
                todos_chamados = self._buscar_chamados_dicts(data_abertura_gte=data_limite)

            total = len(todos_chamados)
            abertos = sum(1 for c in todos_chamados if c.get("status") == "Aberto")
            concluidos = sum(1 for c in todos_chamados if c.get("status") == "Concluído")
            em_andamento = sum(1 for c in todos_chamados if c.get("status") == "Em Atendimento")

            taxa_resolucao = (concluidos / total * 100) if total > 0 else 0

            tempos_resolucao = []
            concluidos_dentro_sla = 0
            concluidos_fora_sla = 0
            for chamado in todos_chamados:
                if chamado.get("status") == "Concluído" and chamado.get("data_conclusao"):
                    data_abertura = chamado.get("data_abertura")
                    data_conclusao = chamado.get("data_conclusao")
                    categoria = chamado.get("categoria") or ""
                    dt_ab = _to_datetime(data_abertura)
                    dt_con = _to_datetime(data_conclusao)
                    if dt_ab and dt_con:
                        tempo = (dt_con - dt_ab).total_seconds() / 3600
                        tempos_resolucao.append(tempo)
                    sla_dias_raw = chamado.get("sla_dias")
                    dentro = _dentro_sla(
                        data_abertura,
                        data_conclusao,
                        categoria,
                        sla_dias_raw,
                        chamado.get("previsao_atendimento"),
                    )
                    if dentro is True:
                        concluidos_dentro_sla += 1
                    elif dentro is False:
                        concluidos_fora_sla += 1

            tempo_medio_resolucao = mean(tempos_resolucao) if tempos_resolucao else 0
            total_concluidos_sla = concluidos_dentro_sla + concluidos_fora_sla
            percentual_dentro_sla = (
                round((concluidos_dentro_sla / total_concluidos_sla * 100), 2)
                if total_concluidos_sla > 0
                else None
            )

            prioridades = {}
            categorias = {}
            em_risco_count = 0
            atrasado_abertos = 0
            um_dia = timedelta(days=1)

            for chamado in todos_chamados:
                # Chave sempre str: chamados sem "prioridade" (legado) caem no
                # fallback "Indefinido" (str), misturado com prioridades numericas
                # (-1/0/1/2...) quebra json.dumps(sort_keys=True) — "'<' not
                # supported between instances of 'str' and 'int'".
                prio = str(chamado.get("prioridade", "Indefinido"))
                prioridades[prio] = prioridades.get(prio, 0) + 1
                cat = chamado.get("categoria") or "Indefinido"
                categorias[cat] = categorias.get(cat, 0) + 1

                if chamado.get("status") not in ("Concluído",):
                    status_ch = chamado.get("status") or ""
                    dt_em_at = _to_datetime(chamado.get("data_em_atendimento"))
                    previsao_atendimento = chamado.get("previsao_atendimento")
                    # Previsão de atendimento aprovada e ainda futura vale mais que o
                    # percentual/calendário calculados sobre o TAT antigo — alinhado
                    # com obter_sla_para_exibicao (badge do chamado individual).
                    dt_previsao_instante = _previsao_atendimento_instante(previsao_atendimento)
                    agora_utc = datetime.now(UTC)
                    previsao_ainda_futura = (
                        dt_previsao_instante is not None and dt_previsao_instante > agora_utc
                    )
                    if previsao_ainda_futura:
                        pass  # nem atrasado nem em risco enquanto a previsão não vence
                    elif status_ch == "Em Atendimento" and dt_em_at is not None:
                        # Usa tempo útil para chamados Em Atendimento (alinhado com badge)
                        categoria = chamado.get("categoria") or ""
                        agora_naive = agora_utc.replace(tzinfo=None)
                        dt_naive = dt_em_at.replace(tzinfo=None) if dt_em_at.tzinfo else dt_em_at
                        pct = percentual_prazo_resolucao(dt_naive, categoria, agora_naive)
                        if pct > 1.0:
                            atrasado_abertos += 1
                        elif pct >= 0.5:
                            em_risco_count += 1
                    else:
                        data_abertura = chamado.get("data_abertura")
                        categoria = chamado.get("categoria") or ""
                        dt_ab = _to_datetime(data_abertura)
                        if dt_ab is not None:
                            dias_sla = _sla_dias_por_categoria(categoria, chamado.get("sla_dias"))
                            limite = _prazo_efetivo(
                                dt_ab + timedelta(days=dias_sla), previsao_atendimento
                            )
                            if limite.tzinfo is not None:
                                now = datetime.now(UTC)
                            else:
                                now = datetime.now(UTC).replace(tzinfo=None)
                            if now > limite:
                                atrasado_abertos += 1
                            elif (limite - now) <= um_dia:
                                em_risco_count += 1

            resumo_sla = {
                "no_prazo": concluidos_dentro_sla,
                "atrasado": concluidos_fora_sla + atrasado_abertos,
                "em_risco": em_risco_count,
            }

            resultado = {
                "periodo_dias": dias,
                "total_chamados": total,
                "abertos": abertos,
                "em_andamento": em_andamento,
                "concluidos": concluidos,
                "taxa_resolucao_percentual": round(taxa_resolucao, 2),
                "tempo_medio_resolucao_horas": round(tempo_medio_resolucao, 2),
                "concluidos_dentro_sla": concluidos_dentro_sla,
                "concluidos_fora_sla": concluidos_fora_sla,
                "percentual_dentro_sla": percentual_dentro_sla,
                "distribuicao_prioridade": prioridades,
                "distribuicao_categoria": categorias,
                "resumo_sla": resumo_sla,
            }
            if chamados_pre_carregados is None:
                try:
                    from app.cache import cache_set

                    cache_set(cache_key, resultado, _ANALYTICS_QUERY_TTL_SEC)
                except Exception as e:
                    logger.debug("Cache indisponível (analytics): %s", e)
            return resultado

        except Exception as e:
            logger.exception("Erro ao obter métricas gerais: %s", e)
            return {}

    # ========== MÉTRICAS POR SUPERVISOR ==========

    def obter_metricas_supervisores(
        self, chamados_pre_carregados: list | None = None
    ) -> list[dict[str, Any]]:
        """Retorna métricas de desempenho de cada supervisor.

        Quando chamados_pre_carregados é fornecido (lista de to_dict() já materializados),
        nenhuma query adicional ao banco é feita — elimina o N+1 anterior que fazia
        1 query por supervisor. O chamador (obter_relatorio_completo) reutiliza a mesma
        carga de chamados entre todas as métricas.
        """
        try:
            from app.models_usuario import Usuario

            supervisores = Usuario.get_all()
            supervisores_ativos = [u for u in supervisores if u.perfil == "supervisor"]

            # Única query quando nenhum dado pré-carregado for fornecido
            if chamados_pre_carregados is None:
                todos_chamados = self._buscar_chamados_dicts()
            else:
                todos_chamados = chamados_pre_carregados

            # Agrupar por responsavel_id em Python — zero queries adicionais
            chamados_por_sup: dict[str, list] = defaultdict(list)
            for c in todos_chamados:
                resp_id = c.get("responsavel_id")
                if resp_id:
                    chamados_por_sup[resp_id].append(c)

            metricas = []
            for sup in supervisores_ativos:
                chamados = chamados_por_sup.get(sup.id, [])
                total = len(chamados)
                abertos = sum(1 for c in chamados if c.get("status") == "Aberto")
                concluidos = sum(1 for c in chamados if c.get("status") == "Concluído")
                em_andamento = sum(1 for c in chamados if c.get("status") == "Em Atendimento")

                taxa_resolucao = (concluidos / total * 100) if total > 0 else 0

                tempos_resolucao = []
                dentro_sla = 0
                fora_sla = 0
                categorias: dict[str, int] = {}
                for chamado in chamados:
                    cat = chamado.get("categoria") or "Indefinido"
                    categorias[cat] = categorias.get(cat, 0) + 1
                    if chamado.get("status") == "Concluído" and chamado.get("data_conclusao"):
                        data_abertura = chamado.get("data_abertura")
                        data_conclusao = chamado.get("data_conclusao")
                        categoria = chamado.get("categoria") or ""
                        dt_ab = _to_datetime(data_abertura)
                        dt_con = _to_datetime(data_conclusao)
                        if dt_ab and dt_con:
                            tempos_resolucao.append((dt_con - dt_ab).total_seconds() / 3600)
                        d = _dentro_sla(
                            data_abertura, data_conclusao, categoria, chamado.get("sla_dias")
                        )
                        if d is True:
                            dentro_sla += 1
                        elif d is False:
                            fora_sla += 1

                tempo_medio = mean(tempos_resolucao) if tempos_resolucao else 0
                total_sla = dentro_sla + fora_sla
                percentual_dentro_sla = (
                    round((dentro_sla / total_sla * 100), 2) if total_sla > 0 else None
                )

                metricas.append(
                    {
                        "supervisor_id": sup.id,
                        "supervisor_nome": sup.nome,
                        "supervisor_email": sup.email,
                        "area": sup.area or "Não definida",
                        "total_chamados": total,
                        "abertos": abertos,
                        "em_andamento": em_andamento,
                        "concluidos": concluidos,
                        "carga_atual": abertos + em_andamento,
                        "taxa_resolucao_percentual": round(taxa_resolucao, 2),
                        "tempo_medio_resolucao_horas": round(tempo_medio, 2),
                        "percentual_dentro_sla": percentual_dentro_sla,
                        "distribuicao_categoria": categorias,
                    }
                )

            metricas.sort(key=lambda x: x["carga_atual"], reverse=True)
            return metricas

        except Exception as e:
            logger.exception("Erro ao obter métricas de supervisores: %s", e)
            return []

    # ========== MÉTRICAS POR ÁREA ==========

    def obter_metricas_areas(
        self, chamados_pre_carregados: list | None = None
    ) -> list[dict[str, Any]]:
        """Retorna métricas de desempenho por área.

        Quando chamados_pre_carregados é fornecido, nenhuma query adicional ao banco
        é feita — elimina o N+1 anterior que fazia 1 query por área.
        """
        try:
            from app.models_usuario import Usuario

            supervisores = [u for u in Usuario.get_all() if u.perfil == "supervisor"]
            areas_uniques: set[str] = set()
            area_to_supervisor_ids: dict[str, set] = defaultdict(set)
            for usuario in supervisores:
                areas_list = getattr(usuario, "areas", None) or []
                if not areas_list and getattr(usuario, "area", None):
                    areas_list = [usuario.area]
                for a in areas_list:
                    areas_uniques.add(a)
                    area_to_supervisor_ids[a].add(usuario.id)

            # Única query de chamados quando nenhum dado pré-carregado for fornecido
            if chamados_pre_carregados is None:
                todos_chamados = self._buscar_chamados_dicts()
            else:
                todos_chamados = chamados_pre_carregados

            # Agrupar por área em Python — zero queries adicionais
            chamados_por_area: dict[str, list] = defaultdict(list)
            for c in todos_chamados:
                if area := c.get("area"):
                    chamados_por_area[area].append(c)

            # Áreas sem nenhum supervisor cadastrado também entram — senão, chamados
            # nela ficam contados no total geral mas invisíveis nesta métrica por área.
            areas_uniques.update(chamados_por_area.keys())

            metricas = []
            for area in sorted(areas_uniques):
                chamados = chamados_por_area.get(area, [])
                total = len(chamados)
                abertos = sum(1 for c in chamados if c.get("status") == "Aberto")
                concluidos = sum(1 for c in chamados if c.get("status") == "Concluído")

                taxa_resolucao = (concluidos / total * 100) if total > 0 else 0
                num_supervisores = len(area_to_supervisor_ids.get(area, set()))

                atribuidos_auto = sum(
                    1
                    for c in chamados
                    if "Atribuído automaticamente" in (c.get("motivo_atribuicao") or "")
                )

                tempos_resolucao = []
                for c in chamados:
                    if (
                        c.get("status") == "Concluído"
                        and c.get("data_conclusao")
                        and c.get("data_abertura")
                    ):
                        dt_ab = _to_datetime(c.get("data_abertura"))
                        dt_con = _to_datetime(c.get("data_conclusao"))
                        if dt_ab and dt_con:
                            tempos_resolucao.append((dt_con - dt_ab).total_seconds() / 3600)
                tempo_medio = round(mean(tempos_resolucao), 2) if tempos_resolucao else 0

                metricas.append(
                    {
                        "area": area,
                        "total_chamados": total,
                        "abertos": abertos,
                        "concluidos": concluidos,
                        "taxa_resolucao_percentual": round(taxa_resolucao, 2),
                        "tempo_medio_resolucao_horas": tempo_medio,
                        "supervisores_alocados": num_supervisores,
                        "chamados_por_supervisor": round(total / num_supervisores, 2)
                        if num_supervisores > 0
                        else 0,
                        "atribuidos_automaticamente": atribuidos_auto,
                        "atribuidos_manualmente": total - atribuidos_auto,
                        "taxa_automacao_percentual": round(atribuidos_auto / total * 100, 2)
                        if total > 0
                        else 0,
                    }
                )

            return metricas

        except Exception as e:
            logger.exception("Erro ao obter métricas de áreas: %s", e)
            return []

    # ========== ANÁLISE DE ATRIBUIÇÃO ==========

    def obter_analise_atribuicao(self, dias: int = 180) -> dict[str, Any]:
        """Análise da performance da atribuição automática

        Comparando:
        - Taxa de resolução: Automática vs Manual
        - Tempo médio de resolução: Automática vs Manual
        - Distribuição de carga após atribuição

        Limita aos últimos `dias` e a MAX_CHAMADOS_ANALYTICS registros (performance).
        """
        try:
            data_limite = datetime.now() - timedelta(days=dias)
            chamados = self._buscar_chamados_dicts(data_abertura_gte=data_limite)

            # Separar automáticos e manuais
            chamados_auto = [
                c
                for c in chamados
                if "Atribuído automaticamente" in (c.get("motivo_atribuicao") or "")
            ]
            chamados_manual = [
                c
                for c in chamados
                if "Atribuído automaticamente" not in (c.get("motivo_atribuicao") or "")
            ]

            def calcular_stats(lista_chamados):
                """Helper para calcular estatísticas"""
                if not lista_chamados:
                    return {
                        "total": 0,
                        "concluidos": 0,
                        "taxa_resolucao": 0,
                        "tempo_medio_resolucao_horas": 0,
                    }

                total = len(lista_chamados)
                concluidos = sum(
                    1 for chamado in lista_chamados if chamado.get("status") == "Concluído"
                )
                taxa = (concluidos / total * 100) if total > 0 else 0

                tempos = []
                for chamado in lista_chamados:
                    if chamado.get("status") == "Concluído" and chamado.get("data_conclusao"):
                        data_abertura = chamado.get("data_abertura", datetime.now())
                        data_conclusao = chamado.get("data_conclusao", datetime.now())

                        if isinstance(data_abertura, datetime) and isinstance(
                            data_conclusao, datetime
                        ):
                            tempo = (data_conclusao - data_abertura).total_seconds() / 3600
                            tempos.append(tempo)

                tempo_medio = mean(tempos) if tempos else 0

                return {
                    "total": total,
                    "concluidos": concluidos,
                    "taxa_resolucao": round(taxa, 2),
                    "tempo_medio_resolucao_horas": round(tempo_medio, 2),
                }

            stats_auto = calcular_stats(chamados_auto)
            stats_manual = calcular_stats(chamados_manual)

            # Calcular melhoria
            melhoria_taxa = stats_auto["taxa_resolucao"] - stats_manual["taxa_resolucao"]
            melhoria_tempo = (
                stats_manual["tempo_medio_resolucao_horas"]
                - stats_auto["tempo_medio_resolucao_horas"]
            )

            return {
                "atribuicao_automatica": stats_auto,
                "atribuicao_manual": stats_manual,
                "melhoria_taxa_percentual": round(melhoria_taxa, 2),
                "melhoria_tempo_horas": round(melhoria_tempo, 2),
                "total_chamados": len(chamados),
                "percentual_automatico": round(len(chamados_auto) / len(chamados) * 100, 2)
                if chamados
                else 0,
            }

        except Exception as e:
            logger.exception("Erro ao analisar atribuição: %s", e)
            return {}

    # ========== INSIGHTS E RECOMENDAÇÕES ==========

    def obter_insights(
        self,
        metricas_supervisores: list[dict[str, Any]] | None = None,
        metricas_areas: list[dict[str, Any]] | None = None,
        metricas_gerais: dict[str, Any] | None = None,
    ) -> list[dict[str, str]]:
        """Gera insights e recomendações baseado nos dados.

        Se forem passados metricas_supervisores, metricas_areas ou metricas_gerais,
        usa esses dados em vez de recalcular (recomendado ao chamar de obter_relatorio_completo).

        Exemplos:
        - "Supervisor X está sobrecarregado (15 chamados abertos)"
        - "Taxa de resolução aumentou 5% em relação ao mês passado"
        - "Área Y precisa de mais supervisores"
        """
        try:
            insights = []

            if metricas_supervisores is None:
                metricas_supervisores = self.obter_metricas_supervisores()

            # Insight SLA (usa metricas_gerais já calculadas no relatório; sem query extra)
            if metricas_gerais is not None:
                pct = metricas_gerais.get("percentual_dentro_sla")
                if pct is not None:
                    if pct >= 80:
                        insights.append(
                            {
                                "tipo": "sucesso",
                                "titulo_key": "insight_sla_ok_title",
                                "mensagem_key": "insight_sla_ok_msg",
                                "mensagem_params": {"pct": pct},
                                "metrica_key": "insight_sla_metric",
                                "metrica_params": {"pct": pct},
                            }
                        )
                    elif pct < 60:
                        insights.append(
                            {
                                "tipo": "aviso",
                                "titulo_key": "insight_sla_low_title",
                                "mensagem_key": "insight_sla_low_msg",
                                "mensagem_params": {"pct": pct},
                                "metrica_key": "insight_sla_metric",
                                "metrica_params": {"pct": pct},
                            }
                        )

            # Insight 1: Supervisor sobrecarregado
            metricas_sups = metricas_supervisores
            if metricas_sups:
                sup_maior_carga = max(metricas_sups, key=lambda x: x["carga_atual"])
                if sup_maior_carga["carga_atual"] > 10:
                    insights.append(
                        {
                            "tipo": "aviso",
                            "titulo_key": "insight_overloaded_title",
                            "mensagem_key": "insight_overloaded_msg",
                            "mensagem_params": {
                                "nome": sup_maior_carga["supervisor_nome"],
                                "carga": sup_maior_carga["carga_atual"],
                            },
                            "supervisor": sup_maior_carga["supervisor_nome"],
                        }
                    )

                # Insight 2: Supervisor com alta taxa de resolução
                sup_melhor = max(metricas_sups, key=lambda x: x["taxa_resolucao_percentual"])
                insights.append(
                    {
                        "tipo": "sucesso",
                        "titulo_key": "insight_best_perf_title",
                        "mensagem_key": "insight_best_perf_msg",
                        "mensagem_params": {
                            "nome": sup_melhor["supervisor_nome"],
                            "taxa": sup_melhor["taxa_resolucao_percentual"],
                        },
                        "supervisor": sup_melhor["supervisor_nome"],
                    }
                )

            # Insight 3: Área com menor performance
            if metricas_areas is None:
                metricas_areas = self.obter_metricas_areas()
            if metricas_areas:
                area_menor = min(metricas_areas, key=lambda x: x["taxa_resolucao_percentual"])
                if area_menor["taxa_resolucao_percentual"] < 40:
                    insights.append(
                        {
                            "tipo": "aviso",
                            "titulo_key": "insight_low_area_title",
                            "mensagem_key": "insight_low_area_msg",
                            "mensagem_params": {
                                "area": area_menor["area"],
                                "taxa": area_menor["taxa_resolucao_percentual"],
                            },
                            "area": area_menor["area"],
                        }
                    )

            return insights

        except Exception as e:
            logger.exception("Erro ao gerar insights: %s", e)
            return []

    # ========== MÉTRICAS DE COMPARAÇÃO (DELTA) ==========

    def obter_metricas_periodo_anterior(
        self, chamados_pre_carregados: list | None = None, dias: int = 30
    ) -> dict[str, Any]:
        """Métricas do período anterior (mesma duração de `dias`, imediatamente
        antes do período atual) para calcular deltas comparativos. Ex.: dias=30
        compara com os 30-60 dias atrás; dias=7 compara com os 7-14 dias atrás.

        Se chamados_pre_carregados for fornecido, filtra por data em Python —
        nenhuma query ao banco é feita.
        """
        cache_key = f"analytics_periodo_anterior_{dias}"
        if chamados_pre_carregados is None:
            try:
                from app.cache import cache_get

                cached = cache_get(cache_key)
                if cached is not None:
                    return cached
            except Exception as e:
                logger.debug("Cache indisponível (analytics): %s", e)
        try:
            agora = datetime.now(UTC)
            data_inicio = agora - timedelta(days=dias * 2)
            data_fim = agora - timedelta(days=dias)

            if chamados_pre_carregados is not None:
                todos_chamados = [
                    c
                    for c in chamados_pre_carregados
                    if (
                        (_to_datetime(c.get("data_abertura")) or _DATETIME_MIN_UTC) >= data_inicio
                        and (_to_datetime(c.get("data_abertura")) or _DATETIME_MIN_UTC) < data_fim
                    )
                ]
            else:
                todos_chamados = self._buscar_chamados_dicts(
                    data_abertura_gte=data_inicio, data_abertura_lt=data_fim
                )

            total = len(todos_chamados)
            concluidos = sum(1 for c in todos_chamados if c.get("status") == "Concluído")
            taxa_resolucao = (concluidos / total * 100) if total > 0 else 0

            tempos_resolucao = []
            concluidos_dentro_sla = 0
            concluidos_fora_sla = 0
            for chamado in todos_chamados:
                if chamado.get("status") == "Concluído" and chamado.get("data_conclusao"):
                    dt_ab = _to_datetime(chamado.get("data_abertura"))
                    dt_con = _to_datetime(chamado.get("data_conclusao"))
                    if dt_ab and dt_con:
                        tempo = (dt_con - dt_ab).total_seconds() / 3600
                        tempos_resolucao.append(tempo)
                    dentro = _dentro_sla(
                        chamado.get("data_abertura"),
                        chamado.get("data_conclusao"),
                        chamado.get("categoria") or "",
                        chamado.get("sla_dias"),
                    )
                    if dentro is True:
                        concluidos_dentro_sla += 1
                    elif dentro is False:
                        concluidos_fora_sla += 1

            tempo_medio = mean(tempos_resolucao) if tempos_resolucao else 0
            total_concluidos_sla = concluidos_dentro_sla + concluidos_fora_sla
            percentual_dentro_sla = (
                round((concluidos_dentro_sla / total_concluidos_sla * 100), 2)
                if total_concluidos_sla > 0
                else None
            )

            resultado = {
                "total_chamados": total,
                "concluidos": concluidos,
                "taxa_resolucao_percentual": round(taxa_resolucao, 2),
                "percentual_dentro_sla": percentual_dentro_sla,
                "tempo_medio_resolucao_horas": round(tempo_medio, 2),
            }
            if chamados_pre_carregados is None:
                try:
                    from app.cache import cache_set

                    cache_set(cache_key, resultado, _ANALYTICS_QUERY_TTL_SEC)
                except Exception as e:
                    logger.debug("Cache indisponível (analytics): %s", e)
            return resultado
        except Exception as e:
            logger.exception("Erro ao obter métricas do período anterior: %s", e)
            return {}

    @staticmethod
    def _calcular_deltas(atual: dict[str, Any], anterior: dict[str, Any]) -> dict[str, Any]:
        """Retorna delta (atual - anterior) para as métricas comparáveis. None quando não calculável."""
        # "abertos"/"em_andamento" não entram aqui de propósito: seriam a
        # contagem de chamados AINDA nesse status hoje, comparando coortes de
        # idades diferentes (abertos há 0-30 dias vs 30-60 dias) — tickets
        # mais antigos tiveram mais tempo pra ser resolvidos, então a
        # comparação tende sempre a cair, independente de desempenho real.
        # "concluidos" já é uma comparação justa (throughput no período).
        campos = [
            "total_chamados",
            "concluidos",
            "taxa_resolucao_percentual",
            "percentual_dentro_sla",
            "tempo_medio_resolucao_horas",
        ]
        deltas: dict[str, Any] = {}
        for campo in campos:
            val_atual = atual.get(campo)
            val_anterior = anterior.get(campo)
            if val_atual is not None and val_anterior is not None:
                deltas[f"{campo}_delta"] = round(val_atual - val_anterior, 2)
            else:
                deltas[f"{campo}_delta"] = None
        return deltas

    # ========== CARGA UNIFICADA DE CHAMADOS ==========

    def _carregar_chamados_analytics(self) -> list[dict[str, Any]]:
        """Carrega todos os chamados do banco com cache (TTL: _RELATORIO_CACHE_TTL_SEC).

        Centraliza a única query a 'chamados' para que obter_relatorio_completo possa
        distribuir o mesmo conjunto de dados para todas as funções de métricas.
        """
        cache_key = "analytics_todos_chamados"
        try:
            from app.cache import cache_get

            cached = cache_get(cache_key)
            if cached is not None:
                return cached
        except Exception as e:
            logger.debug("Cache indisponível (analytics): %s", e)
        chamados = self._buscar_chamados_dicts()
        try:
            from app.cache import cache_set

            cache_set(cache_key, chamados, _RELATORIO_CACHE_TTL_SEC)
        except Exception as e:
            logger.debug("Cache indisponível (analytics): %s", e)
        return chamados

    # ========== RELATÓRIOS DETALHADOS ==========

    def obter_relatorio_completo(
        self, usar_cache: bool = True, dias: int = 30, areas: list[str] | None = None
    ) -> dict[str, Any]:
        """Retorna um relatório completo consolidado.

        `dias` controla o período da Visão Geral (métricas gerais, gráficos e
        resumo de SLA) — as tabelas de supervisores/áreas continuam all-time,
        sem filtro de período.

        `areas`: quando não-None, restringe TODO o relatório (visão geral,
        supervisores e áreas) aos chamados dessas áreas — usado pelo Gestor do
        Setor (nivel_gestao='gestor_setor'), que só pode ver a própria área.
        Uma lista vazia é um escopo válido (usuário sem área associada) e não
        cai para a visão company-wide — só `areas=None` (padrão) faz isso.

        Com usar_cache=True (padrão), reutiliza resultado por 5 minutos (Redis ou memória),
        evitando várias queries pesadas ao banco.
        """
        escopo_area = areas is not None
        areas_norm = sorted({a for a in areas if a}) if areas else []
        cache_key = f"relatorio_completo_{dias}_{'|'.join(areas_norm) if escopo_area else 'all'}"
        try:
            if usar_cache:
                try:
                    from app.cache import cache_get, cache_set

                    cached = cache_get(cache_key)
                    if cached is not None:
                        logger.debug("Relatório servido do cache (Redis/memória)")
                        return cached
                except Exception as e:
                    logger.debug("Cache get ignorado: %s", e)
                # Fallback: cache em memória local
                now = time.time()
                cache_mem = _RELATORIO_CACHE.get(cache_key)
                if cache_mem and (now < cache_mem.get("expires", 0)):
                    logger.debug("Relatório servido do cache em memória")
                    return cache_mem["data"]

            # Carrega todos os chamados UMA vez (com cache Redis/memória) e distribui
            # para todas as funções de métricas — elimina múltiplas queries a 'chamados'.
            chamados_cache = self._carregar_chamados_analytics()
            if escopo_area:
                areas_set = set(areas_norm)
                chamados_cache = [c for c in chamados_cache if c.get("area") in areas_set]

            metricas_gerais = self.obter_metricas_gerais(
                dias=dias, chamados_pre_carregados=chamados_cache
            )
            metricas_periodo_anterior = self.obter_metricas_periodo_anterior(
                chamados_pre_carregados=chamados_cache, dias=dias
            )
            metricas_delta = self._calcular_deltas(metricas_gerais, metricas_periodo_anterior)

            metricas_supervisores = self.obter_metricas_supervisores(
                chamados_pre_carregados=chamados_cache
            )
            metricas_areas = self.obter_metricas_areas(chamados_pre_carregados=chamados_cache)
            if escopo_area:
                areas_set = set(areas_norm)
                metricas_supervisores = [
                    m for m in metricas_supervisores if m.get("area") in areas_set
                ]
                metricas_areas = [m for m in metricas_areas if m.get("area") in areas_set]
            insights = self.obter_insights(
                metricas_supervisores=metricas_supervisores,
                metricas_areas=metricas_areas,
                metricas_gerais=metricas_gerais,
            )
            relatorio = {
                "data_geracao": datetime.now().isoformat(),
                "metricas_gerais": metricas_gerais,
                "metricas_delta": metricas_delta,
                "metricas_supervisores": metricas_supervisores,
                "metricas_areas": metricas_areas,
                "insights": insights,
            }
            if usar_cache:
                try:
                    from app.cache import cache_set

                    cache_set(cache_key, relatorio, _RELATORIO_CACHE_TTL_SEC)
                except Exception as e:
                    logger.debug("Cache set ignorado: %s", e)
                _RELATORIO_CACHE[cache_key] = {
                    "data": relatorio,
                    "expires": time.time() + _RELATORIO_CACHE_TTL_SEC,
                }
            return relatorio
        except Exception as e:
            logger.exception("Erro ao gerar relatório completo: %s", e)
            return {
                "data_geracao": None,
                "metricas_gerais": {},
                "metricas_supervisores": [],
                "metricas_areas": [],
                "insights": [],
            }


# Instância global
analisador = AnalisadorChamados()
