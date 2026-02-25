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
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from firebase_admin import firestore
from statistics import mean, stdev

logger = logging.getLogger(__name__)

# Cache em memória (fallback quando Redis não está configurado)
_RELATORIO_CACHE: Dict[str, Any] = {}
_RELATORIO_CACHE_TTL_SEC = 300  # 5 minutos

# SLA por categoria (dias para conclusão): Projetos 2 dias, demais 3 dias
SLA_DIAS_PROJETOS = 2
SLA_DIAS_PADRAO = 3


def _sla_dias_por_categoria(categoria: str) -> int:
    """Retorna o prazo em dias do SLA para a categoria."""
    return SLA_DIAS_PROJETOS if (categoria or '').strip() == 'Projetos' else SLA_DIAS_PADRAO


def _to_datetime(ts: Any) -> Optional[datetime]:
    """Converte valor do Firestore (Timestamp/datetime) para datetime. Evita queries extras."""
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts
    if hasattr(ts, 'to_pydatetime'):
        return ts.to_pydatetime()
    return None


def _dentro_sla(data_abertura, data_conclusao, categoria: str) -> Optional[bool]:
    """True se concluído dentro do SLA, False se fora. None se não for possível calcular."""
    dt_abertura = _to_datetime(data_abertura)
    dt_conclusao = _to_datetime(data_conclusao)
    if not dt_abertura or not dt_conclusao:
        return None
    dias = _sla_dias_por_categoria(categoria or '')
    limite = dt_abertura + timedelta(days=dias)
    return dt_conclusao <= limite


def obter_sla_para_exibicao(chamado: Any) -> Optional[Dict[str, Any]]:
    """Retorna dict para exibir SLA na Gestão (dashboard). Sem leituras ao Firestore.
    chamado: objeto com .data_abertura, .data_conclusao, .categoria, .status
    Retorno: {'label': 'No prazo'|'Atrasado'|'Em risco', 'dentro_prazo': bool|None, 'em_risco': bool} ou None."""
    data_abertura = getattr(chamado, 'data_abertura', None)
    data_conclusao = getattr(chamado, 'data_conclusao', None)
    categoria = getattr(chamado, 'categoria', None) or ''
    status = getattr(chamado, 'status', None) or 'Aberto'
    dt_abertura = _to_datetime(data_abertura)
    if not dt_abertura:
        return None
    dias = _sla_dias_por_categoria(categoria)
    limite = dt_abertura + timedelta(days=dias)
    # Comparação consistente: ambos naive ou ambos aware (evita TypeError)
    if limite.tzinfo is not None:
        now = datetime.now(timezone.utc)
    else:
        now = datetime.utcnow()
    if status == 'Concluído':
        dt_conclusao = _to_datetime(data_conclusao)
        if not dt_conclusao:
            return None
        dentro = dt_conclusao <= limite
        return {
            'label': 'No prazo' if dentro else 'Atrasado',
            'dentro_prazo': dentro,
            'em_risco': False,
        }
    # Aberto ou Em Atendimento
    if now > limite:
        return {'label': 'Atrasado', 'dentro_prazo': False, 'em_risco': False}
    um_dia = timedelta(days=1)
    if (limite - now) <= um_dia:
        return {'label': 'Em risco', 'dentro_prazo': None, 'em_risco': True}
    return {'label': 'No prazo', 'dentro_prazo': True, 'em_risco': False}


class AnalisadorChamados:
    """Análise de performance e insights dos chamados"""
    
    def __init__(self):
        self.db = None
    
    def get_db(self):
        """Retorna o cliente Firestore (lazy initialization)."""
        if self.db is None:
            self.db = firestore.client()
        return self.db
    
    # ========== MÉTRICAS GERAIS ==========
    
    def obter_metricas_gerais(self, dias: int = 30) -> Dict[str, Any]:
        """Retorna métricas gerais dos últimos N dias
        
        Incluindo:
        - Total de chamados
        - Abertos vs Concluídos
        - Taxa de resolução
        - Tempo médio de resolução
        """
        try:
            data_limite = datetime.now() - timedelta(days=dias)
            
            # Query todos os chamados no período
            chamados_ref = self.get_db().collection('chamados')\
                .where('data_abertura', '>=', data_limite)
            
            chamados = list(chamados_ref.stream())
            
            total = len(chamados)
            abertos = sum(1 for doc in chamados if doc.to_dict().get('status') == 'Aberto')
            concluidos = sum(1 for doc in chamados if doc.to_dict().get('status') == 'Concluído')
            em_andamento = sum(1 for doc in chamados if doc.to_dict().get('status') == 'Em Atendimento')
            
            # Taxa de resolução
            taxa_resolucao = (concluidos / total * 100) if total > 0 else 0
            
            # Tempo médio de resolução e SLA (apenas concluídos; mesma iteração, zero query extra)
            tempos_resolucao = []
            concluidos_dentro_sla = 0
            concluidos_fora_sla = 0
            for doc in chamados:
                chamado = doc.to_dict()
                if chamado.get('status') == 'Concluído' and chamado.get('data_conclusao'):
                    data_abertura = chamado.get('data_abertura')
                    data_conclusao = chamado.get('data_conclusao')
                    categoria = chamado.get('categoria') or ''
                    # Tempo em horas
                    dt_ab = _to_datetime(data_abertura)
                    dt_con = _to_datetime(data_conclusao)
                    if dt_ab and dt_con:
                        tempo = (dt_con - dt_ab).total_seconds() / 3600
                        tempos_resolucao.append(tempo)
                    # SLA (Projetos 2d, demais 3d)
                    dentro = _dentro_sla(data_abertura, data_conclusao, categoria)
                    if dentro is True:
                        concluidos_dentro_sla += 1
                    elif dentro is False:
                        concluidos_fora_sla += 1
            
            tempo_medio_resolucao = mean(tempos_resolucao) if tempos_resolucao else 0
            total_concluidos_sla = concluidos_dentro_sla + concluidos_fora_sla
            percentual_dentro_sla = round(
                (concluidos_dentro_sla / total_concluidos_sla * 100), 2
            ) if total_concluidos_sla > 0 else None
            
            # Contagem por prioridade e por categoria
            prioridades = {}
            categorias = {}
            em_risco_count = 0
            atrasado_abertos = 0
            um_dia = timedelta(days=1)

            for doc in chamados:
                chamado = doc.to_dict()
                prio = chamado.get('prioridade', 'Indefinido')
                prioridades[prio] = prioridades.get(prio, 0) + 1
                cat = chamado.get('categoria') or 'Indefinido'
                categorias[cat] = categorias.get(cat, 0) + 1

                # SLA para abertos/em atendimento: em risco (vence em <= 1 dia) ou atrasado
                if chamado.get('status') not in ('Concluído',):
                    data_abertura = chamado.get('data_abertura')
                    categoria = chamado.get('categoria') or ''
                    dt_ab = _to_datetime(data_abertura)
                    if dt_ab is not None:
                        dias_sla = _sla_dias_por_categoria(categoria)
                        limite = dt_ab + timedelta(days=dias_sla)
                        if limite.tzinfo is not None:
                            now = datetime.now(timezone.utc)
                        else:
                            now = datetime.utcnow()
                        if now > limite:
                            atrasado_abertos += 1
                        elif (limite - now) <= um_dia:
                            em_risco_count += 1

            resumo_sla = {
                'no_prazo': concluidos_dentro_sla,
                'atrasado': concluidos_fora_sla + atrasado_abertos,
                'em_risco': em_risco_count,
            }

            return {
                'periodo_dias': dias,
                'total_chamados': total,
                'abertos': abertos,
                'em_andamento': em_andamento,
                'concluidos': concluidos,
                'taxa_resolucao_percentual': round(taxa_resolucao, 2),
                'tempo_medio_resolucao_horas': round(tempo_medio_resolucao, 2),
                'concluidos_dentro_sla': concluidos_dentro_sla,
                'concluidos_fora_sla': concluidos_fora_sla,
                'percentual_dentro_sla': percentual_dentro_sla,
                'distribuicao_prioridade': prioridades,
                'distribuicao_categoria': categorias,
                'resumo_sla': resumo_sla,
            }
        
        except Exception as e:
            logger.exception(f"Erro ao obter métricas gerais: {str(e)}")
            return {}
    
    # ========== MÉTRICAS POR SUPERVISOR ==========
    
    def obter_metricas_supervisores(self) -> List[Dict[str, Any]]:
        """Retorna métricas de desempenho de cada supervisor
        
        Incluindo:
        - Nome e email
        - Chamados atribuídos
        - Abertos e concluídos
        - Taxa de resolução
        - Tempo médio de resolução
        - Carga atual
        """
        try:
            from app.models_usuario import Usuario
            from app.services.assignment import atribuidor
            
            supervisores = Usuario.get_all()
            # Apenas supervisores (admin do sistema não entra nas métricas de atendimento)
            supervisores_ativos = [u for u in supervisores if u.perfil == 'supervisor']
            
            metricas = []
            
            for sup in supervisores_ativos:
                # Chamados atribuídos a este supervisor
                chamados_ref = self.get_db().collection('chamados')\
                    .where('responsavel_id', '==', sup.id)
                
                chamados = list(chamados_ref.stream())
                total = len(chamados)
                abertos = sum(1 for doc in chamados if doc.to_dict().get('status') == 'Aberto')
                concluidos = sum(1 for doc in chamados if doc.to_dict().get('status') == 'Concluído')
                em_andamento = sum(1 for doc in chamados if doc.to_dict().get('status') == 'Em Atendimento')
                
                # Taxa de resolução
                taxa_resolucao = (concluidos / total * 100) if total > 0 else 0
                
                # Tempo médio de resolução e SLA (mesma iteração, zero query extra)
                tempos_resolucao = []
                dentro_sla = 0
                fora_sla = 0
                for doc in chamados:
                    chamado = doc.to_dict()
                    if chamado.get('status') == 'Concluído' and chamado.get('data_conclusao'):
                        data_abertura = chamado.get('data_abertura')
                        data_conclusao = chamado.get('data_conclusao')
                        categoria = chamado.get('categoria') or ''
                        dt_ab = _to_datetime(data_abertura)
                        dt_con = _to_datetime(data_conclusao)
                        if dt_ab and dt_con:
                            tempo = (dt_con - dt_ab).total_seconds() / 3600
                            tempos_resolucao.append(tempo)
                        d = _dentro_sla(data_abertura, data_conclusao, categoria)
                        if d is True:
                            dentro_sla += 1
                        elif d is False:
                            fora_sla += 1
                
                tempo_medio = mean(tempos_resolucao) if tempos_resolucao else 0
                total_sla = dentro_sla + fora_sla
                percentual_dentro_sla = round(
                    (dentro_sla / total_sla * 100), 2
                ) if total_sla > 0 else None
                
                # Distribuição por categoria
                categorias = {}
                for doc in chamados:
                    chamado = doc.to_dict()
                    cat = chamado.get('categoria', 'Indefinido')
                    categorias[cat] = categorias.get(cat, 0) + 1
                
                # Carga atual (chamados não concluídos)
                carga_atual = abertos + em_andamento
                
                metricas.append({
                    'supervisor_id': sup.id,
                    'supervisor_nome': sup.nome,
                    'supervisor_email': sup.email,
                    'area': sup.area or 'Não definida',
                    'total_chamados': total,
                    'abertos': abertos,
                    'em_andamento': em_andamento,
                    'concluidos': concluidos,
                    'carga_atual': carga_atual,
                    'taxa_resolucao_percentual': round(taxa_resolucao, 2),
                    'tempo_medio_resolucao_horas': round(tempo_medio, 2),
                    'percentual_dentro_sla': percentual_dentro_sla,
                    'distribuicao_categoria': categorias
                })
            
            # Ordenar por carga (decrescente)
            metricas.sort(key=lambda x: x['carga_atual'], reverse=True)
            
            return metricas
        
        except Exception as e:
            logger.exception(f"Erro ao obter métricas de supervisores: {str(e)}")
            return []
    
    # ========== MÉTRICAS POR ÁREA ==========
    
    def obter_metricas_areas(self) -> List[Dict[str, Any]]:
        """Retorna métricas de desempenho por área
        
        Incluindo:
        - Chamados por área
        - Taxa de resolução
        - Supervisores alocados
        - Performance média da área
        """
        try:
            # Um único passe nos usuários: áreas únicas + contagem de supervisores por área
            # (considera 'areas' array e legado 'area' string, igual ao modelo Usuario)
            usuarios_ref = self.get_db().collection('usuarios').stream()
            areas_uniques = set()
            area_to_supervisor_ids = defaultdict(set)
            for doc in usuarios_ref:
                usuario = doc.to_dict()
                if usuario.get('perfil') != 'supervisor':
                    continue
                areas_list = usuario.get('areas') or []
                if not areas_list and usuario.get('area'):
                    areas_list = [usuario.get('area')]
                for a in areas_list:
                    areas_uniques.add(a)
                    area_to_supervisor_ids[a].add(doc.id)
            metricas = []

            for area in sorted(areas_uniques):
                # Chamados criados por solicitantes dessa área
                chamados_ref = self.get_db().collection('chamados')\
                    .where('area', '==', area)
                
                chamados = list(chamados_ref.stream())
                total = len(chamados)
                abertos = sum(1 for doc in chamados if doc.to_dict().get('status') == 'Aberto')
                concluidos = sum(1 for doc in chamados if doc.to_dict().get('status') == 'Concluído')
                
                # Taxa de resolução
                taxa_resolucao = (concluidos / total * 100) if total > 0 else 0
                
                # Supervisores alocados à área (já contados no passe único, suporta 'areas' e 'area')
                num_supervisores = len(area_to_supervisor_ids.get(area, set()))
                
                # Análise de atribuição automática vs manual
                atribuidos_auto = sum(1 for doc in chamados 
                    if 'Atribuído automaticamente' in doc.to_dict().get('motivo_atribuicao', ''))
                atribuidos_manual = total - atribuidos_auto

                # Tempo médio de resolução (horas) para concluídos da área
                tempos_resolucao = []
                for doc in chamados:
                    c = doc.to_dict()
                    if c.get('status') == 'Concluído' and c.get('data_conclusao') and c.get('data_abertura'):
                        dt_ab = _to_datetime(c.get('data_abertura'))
                        dt_con = _to_datetime(c.get('data_conclusao'))
                        if dt_ab and dt_con:
                            tempos_resolucao.append((dt_con - dt_ab).total_seconds() / 3600)
                tempo_medio = round(mean(tempos_resolucao), 2) if tempos_resolucao else 0
                
                metricas.append({
                    'area': area,
                    'total_chamados': total,
                    'abertos': abertos,
                    'concluidos': concluidos,
                    'taxa_resolucao_percentual': round(taxa_resolucao, 2),
                    'tempo_medio_resolucao_horas': tempo_medio,
                    'supervisores_alocados': num_supervisores,
                    'chamados_por_supervisor': round(total / num_supervisores, 2) if num_supervisores > 0 else 0,
                    'atribuidos_automaticamente': atribuidos_auto,
                    'atribuidos_manualmente': atribuidos_manual,
                    'taxa_automacao_percentual': round(atribuidos_auto / total * 100, 2) if total > 0 else 0
                })
            
            return metricas
        
        except Exception as e:
            logger.exception(f"Erro ao obter métricas de áreas: {str(e)}")
            return []
    
    # ========== ANÁLISE DE ATRIBUIÇÃO ==========
    
    def obter_analise_atribuicao(self, dias: int = 180) -> Dict[str, Any]:
        """Análise da performance da atribuição automática
        
        Comparando:
        - Taxa de resolução: Automática vs Manual
        - Tempo médio de resolução: Automática vs Manual
        - Distribuição de carga após atribuição
        
        Limita aos últimos `dias` para evitar carregar todo o histórico (performance).
        """
        try:
            data_limite = datetime.now() - timedelta(days=dias)
            chamados_ref = self.get_db().collection('chamados')\
                .where('data_abertura', '>=', data_limite)
            chamados = list(chamados_ref.stream())
            
            # Separar automáticos e manuais
            chamados_auto = [doc for doc in chamados 
                if 'Atribuído automaticamente' in doc.to_dict().get('motivo_atribuicao', '')]
            chamados_manual = [doc for doc in chamados 
                if 'Atribuído automaticamente' not in doc.to_dict().get('motivo_atribuicao', '')]
            
            def calcular_stats(docs):
                """Helper para calcular estatísticas"""
                if not docs:
                    return {
                        'total': 0,
                        'concluidos': 0,
                        'taxa_resolucao': 0,
                        'tempo_medio_resolucao_horas': 0
                    }
                
                total = len(docs)
                concluidos = sum(1 for doc in docs if doc.to_dict().get('status') == 'Concluído')
                taxa = (concluidos / total * 100) if total > 0 else 0
                
                tempos = []
                for doc in docs:
                    chamado = doc.to_dict()
                    if chamado.get('status') == 'Concluído' and chamado.get('data_conclusao'):
                        data_abertura = chamado.get('data_abertura', datetime.now())
                        data_conclusao = chamado.get('data_conclusao', datetime.now())
                        
                        if isinstance(data_abertura, datetime) and isinstance(data_conclusao, datetime):
                            tempo = (data_conclusao - data_abertura).total_seconds() / 3600
                            tempos.append(tempo)
                
                tempo_medio = mean(tempos) if tempos else 0
                
                return {
                    'total': total,
                    'concluidos': concluidos,
                    'taxa_resolucao': round(taxa, 2),
                    'tempo_medio_resolucao_horas': round(tempo_medio, 2)
                }
            
            stats_auto = calcular_stats(chamados_auto)
            stats_manual = calcular_stats(chamados_manual)
            
            # Calcular melhoria
            melhoria_taxa = stats_auto['taxa_resolucao'] - stats_manual['taxa_resolucao']
            melhoria_tempo = stats_manual['tempo_medio_resolucao_horas'] - stats_auto['tempo_medio_resolucao_horas']
            
            return {
                'atribuicao_automatica': stats_auto,
                'atribuicao_manual': stats_manual,
                'melhoria_taxa_percentual': round(melhoria_taxa, 2),
                'melhoria_tempo_horas': round(melhoria_tempo, 2),
                'total_chamados': len(chamados),
                'percentual_automatico': round(len(chamados_auto) / len(chamados) * 100, 2) if chamados else 0
            }
        
        except Exception as e:
            logger.exception(f"Erro ao analisar atribuição: {str(e)}")
            return {}
    
    # ========== INSIGHTS E RECOMENDAÇÕES ==========
    
    def obter_insights(
        self,
        metricas_supervisores: Optional[List[Dict[str, Any]]] = None,
        metricas_areas: Optional[List[Dict[str, Any]]] = None,
        metricas_gerais: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, str]]:
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
                pct = metricas_gerais.get('percentual_dentro_sla')
                if pct is not None:
                    if pct >= 80:
                        insights.append({
                            'tipo': 'sucesso',
                            'titulo_key': 'insight_sla_ok_title',
                            'mensagem_key': 'insight_sla_ok_msg',
                            'mensagem_params': {'pct': pct},
                            'metrica_key': 'insight_sla_metric',
                            'metrica_params': {'pct': pct},
                        })
                    elif pct < 60:
                        insights.append({
                            'tipo': 'aviso',
                            'titulo_key': 'insight_sla_low_title',
                            'mensagem_key': 'insight_sla_low_msg',
                            'mensagem_params': {'pct': pct},
                            'metrica_key': 'insight_sla_metric',
                            'metrica_params': {'pct': pct},
                        })
            
            # Insight 1: Supervisor sobrecarregado
            metricas_sups = metricas_supervisores
            if metricas_sups:
                sup_maior_carga = max(metricas_sups, key=lambda x: x['carga_atual'])
                if sup_maior_carga['carga_atual'] > 10:
                    insights.append({
                        'tipo': 'aviso',
                        'titulo_key': 'insight_overloaded_title',
                        'mensagem_key': 'insight_overloaded_msg',
                        'mensagem_params': {'nome': sup_maior_carga['supervisor_nome'], 'carga': sup_maior_carga['carga_atual']},
                        'supervisor': sup_maior_carga['supervisor_nome']
                    })
                
                # Insight 2: Supervisor com alta taxa de resolução
                sup_melhor = max(metricas_sups, key=lambda x: x['taxa_resolucao_percentual'])
                insights.append({
                    'tipo': 'sucesso',
                    'titulo_key': 'insight_best_perf_title',
                    'mensagem_key': 'insight_best_perf_msg',
                    'mensagem_params': {'nome': sup_melhor['supervisor_nome'], 'taxa': sup_melhor['taxa_resolucao_percentual']},
                    'supervisor': sup_melhor['supervisor_nome']
                })
            
            # Insight 3: Área com menor performance
            if metricas_areas is None:
                metricas_areas = self.obter_metricas_areas()
            if metricas_areas:
                area_menor = min(metricas_areas, key=lambda x: x['taxa_resolucao_percentual'])
                if area_menor['taxa_resolucao_percentual'] < 40:
                    insights.append({
                        'tipo': 'aviso',
                        'titulo_key': 'insight_low_area_title',
                        'mensagem_key': 'insight_low_area_msg',
                        'mensagem_params': {'area': area_menor['area'], 'taxa': area_menor['taxa_resolucao_percentual']},
                        'area': area_menor['area']
                    })
            
            return insights
        
        except Exception as e:
            logger.exception(f"Erro ao gerar insights: {str(e)}")
            return []
    
    # ========== RELATÓRIOS DETALHADOS ==========
    
    def obter_relatorio_completo(self, usar_cache: bool = True) -> Dict[str, Any]:
        """Retorna um relatório completo consolidado.
        
        Com usar_cache=True (padrão), reutiliza resultado por 5 minutos (Redis ou memória),
        evitando várias queries pesadas ao Firestore.
        """
        try:
            if usar_cache:
                try:
                    from app.cache import cache_get, cache_set
                    cached = cache_get('relatorio_completo')
                    if cached is not None:
                        logger.debug("Relatório servido do cache (Redis/memória)")
                        return cached
                except Exception as e:
                    logger.debug("Cache get ignorado: %s", e)
                # Fallback: cache em memória local
                now = time.time()
                if _RELATORIO_CACHE and (now < _RELATORIO_CACHE.get('expires', 0)):
                    logger.debug("Relatório servido do cache em memória")
                    return _RELATORIO_CACHE['data']

            metricas_gerais = self.obter_metricas_gerais(dias=30)
            metricas_supervisores = self.obter_metricas_supervisores()
            metricas_areas = self.obter_metricas_areas()
            insights = self.obter_insights(
                metricas_supervisores=metricas_supervisores,
                metricas_areas=metricas_areas,
                metricas_gerais=metricas_gerais,
            )
            relatorio = {
                'data_geracao': datetime.now().isoformat(),
                'metricas_gerais': metricas_gerais,
                'metricas_supervisores': metricas_supervisores,
                'metricas_areas': metricas_areas,
                'insights': insights,
            }
            if usar_cache:
                try:
                    from app.cache import cache_set
                    cache_set('relatorio_completo', relatorio, _RELATORIO_CACHE_TTL_SEC)
                except Exception as e:
                    logger.debug("Cache set ignorado: %s", e)
                _RELATORIO_CACHE['data'] = relatorio
                _RELATORIO_CACHE['expires'] = time.time() + _RELATORIO_CACHE_TTL_SEC
            return relatorio
        except Exception as e:
            logger.exception(f"Erro ao gerar relatório completo: {str(e)}")
            return {}


# Instância global
analisador = AnalisadorChamados()
