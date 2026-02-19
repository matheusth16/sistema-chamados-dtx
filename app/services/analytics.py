"""
Serviço de Análise e Relatórios
Fornece métricas de performance, insights e análises dos chamados
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from firebase_admin import firestore
from statistics import mean, stdev

logger = logging.getLogger(__name__)

# Cache em memória para o relatório completo (evita queries pesadas a cada acesso)
_RELATORIO_CACHE: Dict[str, Any] = {}
_RELATORIO_CACHE_TTL_SEC = 300  # 5 minutos


class AnalisadorChamados:
    """Análise de performance e insights dos chamados"""
    
    def __init__(self):
        self.db = None
    
    def get_db(self):
        """Lazy initialization do Firestore"""
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
            em_andamento = sum(1 for doc in chamados if doc.to_dict().get('status') == 'Em Andamento')
            
            # Taxa de resolução
            taxa_resolucao = (concluidos / total * 100) if total > 0 else 0
            
            # Tempo médio de resolução (apenas concluídos)
            tempos_resolucao = []
            for doc in chamados:
                chamado = doc.to_dict()
                if chamado.get('status') == 'Concluído' and chamado.get('data_conclusao'):
                    data_abertura = chamado.get('data_abertura', datetime.now())
                    data_conclusao = chamado.get('data_conclusao', datetime.now())
                    
                    if isinstance(data_abertura, datetime) and isinstance(data_conclusao, datetime):
                        tempo = (data_conclusao - data_abertura).total_seconds() / 3600  # em horas
                        tempos_resolucao.append(tempo)
            
            tempo_medio_resolucao = mean(tempos_resolucao) if tempos_resolucao else 0
            
            # Contagem por prioridade
            prioridades = {}
            for doc in chamados:
                chamado = doc.to_dict()
                prio = chamado.get('prioridade', 'Indefinido')
                prioridades[prio] = prioridades.get(prio, 0) + 1
            
            return {
                'periodo_dias': dias,
                'total_chamados': total,
                'abertos': abertos,
                'em_andamento': em_andamento,
                'concluidos': concluidos,
                'taxa_resolucao_percentual': round(taxa_resolucao, 2),
                'tempo_medio_resolucao_horas': round(tempo_medio_resolucao, 2),
                'distribuicao_prioridade': prioridades
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
            supervisores_ativos = [u for u in supervisores if u.perfil in ['supervisor', 'admin']]
            
            metricas = []
            
            for sup in supervisores_ativos:
                # Chamados atribuídos a este supervisor
                chamados_ref = self.get_db().collection('chamados')\
                    .where('responsavel_id', '==', sup.id)
                
                chamados = list(chamados_ref.stream())
                total = len(chamados)
                abertos = sum(1 for doc in chamados if doc.to_dict().get('status') == 'Aberto')
                concluidos = sum(1 for doc in chamados if doc.to_dict().get('status') == 'Concluído')
                em_andamento = sum(1 for doc in chamados if doc.to_dict().get('status') == 'Em Andamento')
                
                # Taxa de resolução
                taxa_resolucao = (concluidos / total * 100) if total > 0 else 0
                
                # Tempo médio de resolução
                tempos_resolucao = []
                for doc in chamados:
                    chamado = doc.to_dict()
                    if chamado.get('status') == 'Concluído' and chamado.get('data_conclusao'):
                        data_abertura = chamado.get('data_abertura', datetime.now())
                        data_conclusao = chamado.get('data_conclusao', datetime.now())
                        
                        if isinstance(data_abertura, datetime) and isinstance(data_conclusao, datetime):
                            tempo = (data_conclusao - data_abertura).total_seconds() / 3600
                            tempos_resolucao.append(tempo)
                
                tempo_medio = mean(tempos_resolucao) if tempos_resolucao else 0
                
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
            # Buscar todas as áreas
            usuarios_ref = self.get_db().collection('usuarios').stream()
            areas_uniques = set()
            
            for doc in usuarios_ref:
                usuario = doc.to_dict()
                if usuario.get('area'):
                    areas_uniques.add(usuario['area'])
            
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
                
                # Supervisores da área
                supervs_area = self.get_db().collection('usuarios')\
                    .where('area', '==', area)\
                    .where('perfil', '==', 'supervisor').stream()
                
                num_supervisores = len(list(supervs_area))
                
                # Análise de atribuição automática vs manual
                atribuidos_auto = sum(1 for doc in chamados 
                    if 'Atribuído automaticamente' in doc.to_dict().get('motivo_atribuicao', ''))
                atribuidos_manual = total - atribuidos_auto
                
                metricas.append({
                    'area': area,
                    'total_chamados': total,
                    'abertos': abertos,
                    'concluidos': concluidos,
                    'taxa_resolucao_percentual': round(taxa_resolucao, 2),
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
        analise_atribuicao: Optional[Dict[str, Any]] = None,
        metricas_areas: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, str]]:
        """Gera insights e recomendações baseado nos dados.
        
        Se forem passados metricas_supervisores, analise_atribuicao ou metricas_areas,
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
            
            # Insight 1: Supervisor sobrecarregado
            metricas_sups = metricas_supervisores
            if metricas_sups:
                sup_maior_carga = max(metricas_sups, key=lambda x: x['carga_atual'])
                if sup_maior_carga['carga_atual'] > 10:
                    insights.append({
                        'tipo': 'aviso',
                        'titulo': 'Supervisor Sobrecarregado',
                        'mensagem': f"{sup_maior_carga['supervisor_nome']} tem {sup_maior_carga['carga_atual']} chamados abertos. Considere redistribuição.",
                        'supervisor': sup_maior_carga['supervisor_nome']
                    })
                
                # Insight 2: Supervisor com alta taxa de resolução
                sup_melhor = max(metricas_sups, key=lambda x: x['taxa_resolucao_percentual'])
                insights.append({
                    'tipo': 'sucesso',
                    'titulo': 'Melhor Performance',
                    'mensagem': f"{sup_melhor['supervisor_nome']} tem a melhor taxa de resolução ({sup_melhor['taxa_resolucao_percentual']}%)",
                    'supervisor': sup_melhor['supervisor_nome']
                })
            
            # Insight 3: Análise de atribuição automática
            if analise_atribuicao is None:
                analise_atribuicao = self.obter_analise_atribuicao()
            analise_attr = analise_atribuicao
            if analise_attr.get('melhoria_taxa_percentual', 0) > 0:
                insights.append({
                    'tipo': 'info',
                    'titulo': 'Atribuição Automática Eficaz',
                    'mensagem': f"A atribuição automática tem +{analise_attr['melhoria_taxa_percentual']}% de taxa de resolução comparado ao manual.",
                    'metrica': f"{analise_attr['percentual_automatico']}% dos chamados são automáticos"
                })
            
            # Insight 4: Área com menor performance
            if metricas_areas is None:
                metricas_areas = self.obter_metricas_areas()
            if metricas_areas:
                area_menor = min(metricas_areas, key=lambda x: x['taxa_resolucao_percentual'])
                if area_menor['taxa_resolucao_percentual'] < 40:
                    insights.append({
                        'tipo': 'aviso',
                        'titulo': 'Área com Baixa Performance',
                        'mensagem': f"A área {area_menor['area']} tem taxa de resolução de {area_menor['taxa_resolucao_percentual']}%. Investigação recomendada.",
                        'area': area_menor['area']
                    })
            
            return insights
        
        except Exception as e:
            logger.exception(f"Erro ao gerar insights: {str(e)}")
            return []
    
    # ========== RELATÓRIOS DETALHADOS ==========
    
    def obter_relatorio_completo(self, usar_cache: bool = True) -> Dict[str, Any]:
        """Retorna um relatório completo consolidado.
        
        Com usar_cache=True (padrão), reutiliza resultado por 5 minutos,
        evitando várias queries pesadas ao Firestore a cada acesso à página.
        """
        try:
            now = time.time()
            if usar_cache and _RELATORIO_CACHE and (now < _RELATORIO_CACHE.get('expires', 0)):
                logger.debug("Relatório servido do cache")
                return _RELATORIO_CACHE['data']
            
            metricas_gerais = self.obter_metricas_gerais(dias=30)
            metricas_supervisores = self.obter_metricas_supervisores()
            metricas_areas = self.obter_metricas_areas()
            analise_atribuicao = self.obter_analise_atribuicao(dias=180)
            insights = self.obter_insights(
                metricas_supervisores=metricas_supervisores,
                analise_atribuicao=analise_atribuicao,
                metricas_areas=metricas_areas,
            )
            
            relatorio = {
                'data_geracao': datetime.now().isoformat(),
                'metricas_gerais': metricas_gerais,
                'metricas_supervisores': metricas_supervisores,
                'metricas_areas': metricas_areas,
                'analise_atribuicao': analise_atribuicao,
                'insights': insights,
            }
            
            if usar_cache:
                _RELATORIO_CACHE['data'] = relatorio
                _RELATORIO_CACHE['expires'] = now + _RELATORIO_CACHE_TTL_SEC
            
            return relatorio
        except Exception as e:
            logger.exception(f"Erro ao gerar relatório completo: {str(e)}")
            return {}


# Instância global
analisador = AnalisadorChamados()
