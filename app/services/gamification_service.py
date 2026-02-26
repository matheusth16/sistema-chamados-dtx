import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from app.models_usuario import Usuario
from app.models_historico import Historico

logger = logging.getLogger(__name__)

class GamificationService:
    """
    Serviço centralizado para gerenciar regras de Gamificação (EXP, Levels, Ranking).
    """
    
    # Tabela de níveis (Baseada na fórmula: proximo_nivel = nivel_atual * 100)
    # ou podemos usar ranges fixos para simplificar
    LEVEL_ZONES = [
        (1, 0),         # Nível 1: 0 a 99
        (2, 100),       # Nível 2: 100 a 299
        (3, 300),       # Nível 3: 300 a 599
        (4, 600),       # Nível 4: 600 a 999
        (5, 1000),      # Nível 5: 1000 a 1499
        (6, 1500),      # Nível 6: 1500 a 2099
        (7, 2100),      # Nível 7: 2100 a 2799
        (8, 2800),      # Nível 8: 2800 a 3599
        (9, 3600),      # Nível 9: 3600 a 4499
        (10, 4500)      # Nível 10: 4500+ (Master)
    ]
    
    @staticmethod
    def get_level_for_exp(exp: int) -> int:
        """Calcula o nível baseado no EXP total."""
        current_level = 1
        for level, exp_required in GamificationService.LEVEL_ZONES:
            if exp >= exp_required:
                current_level = level
            else:
                break
        return current_level

    @staticmethod
    def get_exp_for_next_level(current_exp: int) -> int:
        """Calcula quanto EXP falta para o próximo nível."""
        for level, exp_required in GamificationService.LEVEL_ZONES:
            if exp_required > current_exp:
                return exp_required
        # Nível máximo atingido (retorna um limite fictício ou o próprio exp para barra cheia)
        return current_exp 

    @staticmethod
    def _adicionar_exp(usuario_id: str, pontos: int, motivo: str) -> bool:
        """Método interno para adicionar EXP a um usuário e checar level up."""
        try:
            usuario = Usuario.get_by_id(usuario_id)
            if not usuario:
                return False
                
            nova_exp_total = usuario.exp_total + pontos
            nova_exp_semanal = usuario.exp_semanal + pontos
            novo_level = GamificationService.get_level_for_exp(nova_exp_total)
            
            # TODO: Podemos aqui adicionar lógicas de "Conquistas" pro array usuario.conquistas
            # Ex: if novo_level > usuario.level: usuario.conquistas.append(f"Alcançou Nível {novo_level}")

            gamification_data = {
                'exp_total': nova_exp_total,
                'exp_semanal': nova_exp_semanal,
                'level': novo_level,
                'conquistas': usuario.conquistas
            }
            
            sucesso = usuario.update(gamification=gamification_data)
            
            if sucesso:
                logger.info(f"Usuário {usuario_id} ganhou {pontos} EXP ({motivo}). Novo nível: {novo_level}.")
                
            return sucesso
            
        except Exception as e:
            logger.exception(f"Erro ao adicionar EXP para o usuário {usuario_id}: {e}")
            return False

    @staticmethod
    def avaliar_resolucao_chamado(usuario_id: str, chamado_data: Dict[str, Any]) -> None:
        """
        Avalia a resolução de um chamado e concede EXP ao técnico/responsável.
        Deve ser chamado no momento em que o status muda para 'Concluído'.
        """
        try:
            # Regras da avaliação
            # 1. Padrão ao fechar o chamado
            # 2. Bônus se foi resolvido dentro do SLA previsto (se houver campo de prazo)
            # Como ainda não temos campo de 'prazo_final' explicito no model base que sabemos
            # Usaremos as regras:
            # +50 por fechamento, +15 se ele tá fechando algo que não é dele?
            
            # Vamos adotar a lógica sugerida no plano: 
            # Como a verificação de "No Prazo" requer que o Chamado tenha campo de prazo ou prioridade,
            # vamos implementar uma versão baseline. Se tiver um campo de atraso a gente adapta depois.
            
            atrasado = chamado_data.get('atrasado', False) # Supondo que você tem lógica de atraso no sistema
            
            if atrasado:
                pontos = 15
                motivo = "Chamado Concluído (Atrasado)"
            else:
                pontos = 50
                motivo = "Chamado Concluído no Prazo"
                
            GamificationService._adicionar_exp(usuario_id, pontos, motivo)
            
        except Exception as e:
            logger.exception(f"Erro ao avaliar resolução de chamado para Gamificação: {e}")

    @staticmethod
    def avaliar_atendimento_inicial(usuario_id: str) -> None:
        """
        Avalia o momento que o técnico pega o chamado para 'Em Atendimento'.
        Se for muito rápido (ex: em menos de 1h) ganhava +20 EXP, mas como 
        a data_abertura pode exigir um fetch extra, simplificamos para dar sempre 
        algum incentivo ao iniciar um atendimento, ou fazer o calculo extra aqui.
        """
        # Exemplo simples:
        pontos = 10
        motivo = "Iniciou Atendimento de Chamado"
        GamificationService._adicionar_exp(usuario_id, pontos, motivo)
