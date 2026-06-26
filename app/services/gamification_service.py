import logging
from typing import Any

from app.database import db
from app.models_usuario import Usuario

try:
    from google.cloud.firestore_v1 import Increment
except ImportError:
    Increment = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


class GamificationService:
    """
    Serviço centralizado para gerenciar regras de Gamificação (EXP, Levels, Ranking).
    """

    # Tabela de níveis (Baseada na fórmula: proximo_nivel = nivel_atual * 100)
    # ou podemos usar ranges fixos para simplificar
    LEVEL_ZONES = [
        (1, 0),  # Nível 1: 0 a 99
        (2, 100),  # Nível 2: 100 a 299
        (3, 300),  # Nível 3: 300 a 599
        (4, 600),  # Nível 4: 600 a 999
        (5, 1000),  # Nível 5: 1000 a 1499
        (6, 1500),  # Nível 6: 1500 a 2099
        (7, 2100),  # Nível 7: 2100 a 2799
        (8, 2800),  # Nível 8: 2800 a 3599
        (9, 3600),  # Nível 9: 3600 a 4499
        (10, 4500),  # Nível 10: 4500+ (Master)
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
        for _level, exp_required in GamificationService.LEVEL_ZONES:
            if exp_required > current_exp:
                return exp_required
        # Nível máximo atingido (retorna um limite fictício ou o próprio exp para barra cheia)
        return current_exp

    @staticmethod
    def _verificar_novas_conquistas(
        conquistas_atuais: list,
        motivo: str,
        novo_level: int,
        nova_exp_total: int,
    ) -> list:
        """Retorna IDs das conquistas recém-desbloqueadas."""
        novas = []
        for level_req, badge_id in [(3, "nivel_3"), (5, "nivel_5"), (10, "nivel_10")]:
            if novo_level >= level_req and badge_id not in conquistas_atuais:
                novas.append(badge_id)
        if "Concluído" in motivo and "primeira_resolucao" not in conquistas_atuais:
            novas.append("primeira_resolucao")
        if (
            nova_exp_total >= 250
            and "Concluído" in motivo
            and "cinco_resolucoes" not in conquistas_atuais
        ):
            novas.append("cinco_resolucoes")
        return novas

    @staticmethod
    def _adicionar_exp(usuario_id: str, pontos: int, motivo: str) -> bool:
        """Método interno para adicionar EXP a um usuário e checar level up.

        exp_total e exp_semanal usam Increment(pontos) para evitar race condition (F-14):
        sem Increment, dois requests simultâneos podem ler o mesmo valor e ambos
        escreverem o mesmo total — perdendo um dos incrementos.
        level e conquistas são calculados otimisticamente a partir do valor pré-leitura.
        """
        try:
            usuario = Usuario.get_by_id(usuario_id)
            if not usuario:
                return False

            # Cálculo otimístico para level e conquistas (aceitável — são valores de exibição)
            nova_exp_total = usuario.exp_total + pontos
            novo_level = GamificationService.get_level_for_exp(nova_exp_total)

            novas_conquistas = GamificationService._verificar_novas_conquistas(
                conquistas_atuais=list(usuario.conquistas or []),
                motivo=motivo,
                novo_level=novo_level,
                nova_exp_total=nova_exp_total,
            )
            conquistas_atualizadas = list(usuario.conquistas or []) + novas_conquistas

            # Increment(pontos) aplica o delta atomicamente no servidor Firestore,
            # eliminando o race condition de read-then-write (F-14).
            db.collection("usuarios").document(usuario_id).update(
                {
                    "exp_total": Increment(pontos),
                    "exp_semanal": Increment(pontos),
                    "level": novo_level,
                    "conquistas": conquistas_atualizadas,
                }
            )

            logger.info(
                "Usuário %s ganhou %s EXP (%s). Novo nível: %s.",
                usuario_id,
                pontos,
                motivo,
                novo_level,
            )
            if novas_conquistas:
                logger.info("Usuário %s desbloqueou conquistas: %s", usuario_id, novas_conquistas)

            return True

        except Exception as e:
            logger.exception("Erro ao adicionar EXP para o usuário %s: %s", usuario_id, e)
            return False

    @staticmethod
    def avaliar_resolucao_chamado(usuario_id: str, chamado_data: dict[str, Any]) -> None:
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

            atrasado = chamado_data.get(
                "atrasado", False
            )  # Supondo que você tem lógica de atraso no sistema

            if atrasado:
                pontos = 15
                motivo = "Chamado Concluído (Atrasado)"
            else:
                pontos = 50
                motivo = "Chamado Concluído no Prazo"

            GamificationService._adicionar_exp(usuario_id, pontos, motivo)

        except Exception as e:
            logger.exception("Erro ao avaliar resolução de chamado para Gamificação: %s", e)

    @staticmethod
    def resetar_ranking_semanal() -> bool:
        """Zera exp_semanal de todos os usuários. Chamado pelo APScheduler toda segunda-feira.

        Usa batch Firestore (máx 500 ops/batch) para minimizar round-trips.
        Pula usuários com exp_semanal == 0 para evitar writes desnecessários.
        """
        try:
            usuarios_ref = db.collection("usuarios")
            docs = usuarios_ref.stream()
            batch = db.batch()
            atualizados = 0
            batch_count = 0
            for doc in docs:
                data = doc.to_dict()
                if (data.get("exp_semanal") or 0) > 0:
                    batch.update(usuarios_ref.document(doc.id), {"exp_semanal": 0})
                    atualizados += 1
                    batch_count += 1
                    if batch_count >= 500:
                        batch.commit()
                        logger.info("Batch comitado: %d usuários", batch_count)
                        batch = db.batch()
                        batch_count = 0
            if batch_count > 0:
                batch.commit()
            logger.info("Reset semanal concluído: %d usuários zerados.", atualizados)
            return True
        except Exception:
            logger.exception("Falha ao resetar ranking semanal.")
            return False

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
