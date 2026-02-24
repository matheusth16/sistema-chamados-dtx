"""
Serviço de atribuição automática inteligente de chamados

Oferece múltiplas estratégias de atribuição:
- Load Balancing: Atribui ao supervisor com menos chamados abertos
- Round-Robin: Distribui sequencialmente entre supervisores
- Por Prioridade: Supervisores com menos alerta para prioridades_altas

Uso:
    from app.services.assignment import atribuidor
    supervisor = atribuidor.atribuir(chamado)
"""

import logging
from typing import Optional, Dict, List
from google.cloud.firestore_v1.base_query import FieldFilter, BaseCompositeFilter
from app.database import db
from app.models_usuario import Usuario

logger = logging.getLogger(__name__)


class AtribuidorAutomatico:
    """Gerencia atribuição automática inteligente de chamados"""
    
    # Estratégias disponíveis
    ESTRATEGIAS = {
        'balanceamento_carga': 'Supervisor com menos chamados abertos',
        'round_robin': 'Distribuição sequencial',
        'aleatorio': 'Distribuição aleatória',
    }
    
    def __init__(self, estrategia: str = 'balanceamento_carga'):
        """
        Inicializa atribuidor
        
        Args:
            estrategia: Uma das estratégias em ESTRATEGIAS
        """
        if estrategia not in self.ESTRATEGIAS:
            raise ValueError(f"Estratégia inválida: {estrategia}")
        
        self.estrategia = estrategia
        self.contador_round_robin = {}  # Para rastrear round-robin por área
    
    def atribuir(self, area: str, categoria: str = None, prioridade: int = 1) -> Dict:
        """
        Atribui um chamado a um supervisor automaticamente.
        
        Distribui novo chamado usando a estratégia configurada:
        - **Balanceamento de Carga:** Atribui ao supervisor com menos chamados abertos (padrão)
        - **Round-Robin:** Alterna sequencialmente entre supervisores
        - **Aleatório:** Seleciona supervisor aleatório
        
        Args:
            area (str): Área/departamento do chamado (ex: 'Manutencao', 'Engenharia').
                        Deve corresponder à área de um supervisor.
            categoria (str, optional): Categoria do chamado (ex: 'Projetos'). 
                        Padrão: None. Pode ser usado para priorização futura.
            prioridade (int, optional): Nível de prioridade (0=crítica, 1=alta, 2=média, 3=baixa).
                        Padrão: 1. Pode influenciar em atribuição por prioridade.
        
        Returns:
            dict: Resultado da atribuição com chaves:
                - **sucesso** (bool): True se supervisor foi encontrado e atribuído
                - **supervisor** (dict): Dados do supervisor atribuído:
                    - id (str): ID único do supervisor
                    - nome (str): Nome completo
                    - email (str): Email para notificação
                    - area (str): Área de atuação
                    - chamados_abertos (int): Contagem atual de chamados abertos
                - **motivo** (str): Razão da atribuição ou mensagem de erro
                - **estrategia_usada** (str): Nome da estratégia aplicada
                
        Raises:
            ValueError: Se area for inválida ou vazia
            
        Examples:
            >>> resultado = atribuidor.atribuir('Suporte', 'Manutenção', prioridade=0)
            >>> if resultado['sucesso']:
            ...     print(f"Atribuído para {resultado['supervisor']['nome']}")
            ...     # Enviar e-mail de notificação
            ... else:
            ...     print(f"Erro: {resultado['motivo']}")
        """
        try:
            logger.debug(f"Atribuindo chamado: area={area}, categoria={categoria}, prioridade={prioridade}")
            
            # 1. Busca supervisores da área
            supervisores = Usuario.get_supervisores_por_area(area)
            
            if not supervisores:
                logger.warning(f"Nenhum supervisor encontrado para área: {area}")
                return {
                    'sucesso': False,
                    'supervisor': None,
                    'motivo': f'Nenhum supervisor disponível para a área "{area}"',
                    'estrategia_usada': self.estrategia
                }
            
            logger.debug(f"Encontrados {len(supervisores)} supervisores para área {area}")
            
            # 2. Conta chamados abertos por supervisor
            supervisores_com_carga = self._contar_chamados_abertos(supervisores)
            
            # 3. Aplica estratégia de atribuição
            if self.estrategia == 'balanceamento_carga':
                supervisor_escolhido = self._atribuir_balanceamento(supervisores_com_carga, area)
            elif self.estrategia == 'round_robin':
                supervisor_escolhido = self._atribuir_round_robin(supervisores_com_carga, area)
            else:  # aleatorio
                supervisor_escolhido = supervisores_com_carga[0]  # Sem estratégia específica
            
            if not supervisor_escolhido:
                return {
                    'sucesso': False,
                    'supervisor': None,
                    'motivo': 'Não foi possível selecionar um supervisor',
                    'estrategia_usada': self.estrategia
                }
            
            logger.info(f"Chamado atribuído a {supervisor_escolhido['usuario'].nome} ({supervisor_escolhido['usuario'].email}) - {supervisor_escolhido['chamados_abertos']} chamados abertos")
            
            return {
                'sucesso': True,
                'supervisor': {
                    'id': supervisor_escolhido['usuario'].id,
                    'email': supervisor_escolhido['usuario'].email,
                    'nome': supervisor_escolhido['usuario'].nome,
                    'area': supervisor_escolhido['usuario'].area,
                    'chamados_abertos': supervisor_escolhido['chamados_abertos']
                },
                'motivo': f"Atribuído com sucesso (estratégia: {self.estrategia})",
                'estrategia_usada': self.estrategia
            }
        
        except Exception as e:
            logger.exception(f"Erro ao atribuir chamado: {str(e)}")
            return {
                'sucesso': False,
                'supervisor': None,
                'motivo': f'Erro ao atribuir: {str(e)}',
                'estrategia_usada': self.estrategia
            }
    
    def _contar_chamados_abertos(self, supervisores: List[Usuario]) -> List[Dict]:
        """
        Conta quantos chamados abertos cada supervisor tem
        
        Returns: Lista com dicts contendo usuario e chamados_abertos
        """
        supervisores_com_carga = []
        
        for sup in supervisores:
            try:
                # Conta chamados não concluídos atribuídos ao supervisor
                filtro = BaseCompositeFilter('AND', [
                    FieldFilter('responsavel', '==', sup.nome),
                    FieldFilter('status', '!=', 'Concluído'),
                ])
                docs = db.collection('chamados').where(filter=filtro).stream()
                
                count = sum(1 for _ in docs)
                
                supervisores_com_carga.append({
                    'usuario': sup,
                    'chamados_abertos': count
                })
                
                logger.debug(f"Supervisor {sup.nome}: {count} chamados abertos")
            
            except Exception as e:
                logger.warning(f"Erro ao contar chamados para {sup.nome}: {e}")
                supervisores_com_carga.append({
                    'usuario': sup,
                    'chamados_abertos': 0
                })
        
        return supervisores_com_carga
    
    def _atribuir_balanceamento(self, supervisores_com_carga: List[Dict], area: str) -> Optional[Dict]:
        """
        Estratégia: Atribui ao supervisor com menos chamados abertos
        Garante distribuição equilibrada de carga
        """
        if not supervisores_com_carga:
            return None
        
        # Ordena por menos chamados abertos
        supervisor_escolhido = min(supervisores_com_carga, key=lambda x: x['chamados_abertos'])
        
        logger.debug(f"Balanceamento: {supervisor_escolhido['usuario'].nome} selecionado ({supervisor_escolhido['chamados_abertos']} chamados)")
        
        return supervisor_escolhido
    
    def _atribuir_round_robin(self, supervisores_com_carga: List[Dict], area: str) -> Optional[Dict]:
        """
        Estratégia: Distribui sequencialmente entre supervisores
        Garante que cada supervisor recebe chamados na sequência
        """
        if not supervisores_com_carga:
            return None
        
        # Inicializa contador se não existe para essa área
        if area not in self.contador_round_robin:
            self.contador_round_robin[area] = 0
        
        # Seleciona o próximo supervisor na sequência
        idx = self.contador_round_robin[area] % len(supervisores_com_carga)
        supervisor_escolhido = supervisores_com_carga[idx]
        
        # Incrementa para próximo
        self.contador_round_robin[area] = (idx + 1) % len(supervisores_com_carga)
        
        logger.debug(f"Round-Robin: {supervisor_escolhido['usuario'].nome} selecionado (índice {idx})")
        
        return supervisor_escolhido
    
    def obter_disponibilidade(self, area: str) -> Dict:
        """
        Retorna informações sobre disponibilidade de supervisores numa área
        
        Útil para dashboard e análises
        """
        try:
            supervisores = Usuario.get_supervisores_por_area(area)
            supervisores_com_carga = self._contar_chamados_abertos(supervisores)
            
            return {
                'area': area,
                'total_supervisores': len(supervisores_com_carga),
                'supervisores': [
                    {
                        'id': sup['usuario'].id,
                        'nome': sup['usuario'].nome,
                        'email': sup['usuario'].email,
                        'chamados_abertos': sup['chamados_abertos'],
                        'disponivel': sup['chamados_abertos'] < 10  # Threshold: 10 chamados
                    }
                    for sup in supervisores_com_carga
                ],
                'carga_total': sum(sup['chamados_abertos'] for sup in supervisores_com_carga),
                'carga_media': sum(sup['chamados_abertos'] for sup in supervisores_com_carga) / len(supervisores_com_carga) if supervisores_com_carga else 0
            }
        
        except Exception as e:
            logger.exception(f"Erro ao obter disponibilidade: {str(e)}")
            return {
                'area': area,
                'total_supervisores': 0,
                'supervisores': [],
                'carga_total': 0,
                'carga_media': 0
            }


# Instância global do atribuidor
atribuidor = AtribuidorAutomatico(estrategia='balanceamento_carga')
