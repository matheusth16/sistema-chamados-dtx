"""
Serviço de rastreamento de tentativas de login para prevenir força bruta.
Mantém histórico de tentativas falhas por IP/email.
"""
import logging
from datetime import datetime
from app.cache import cache_get, cache_set, cache_delete
from app.utils import get_client_ip

logger = logging.getLogger(__name__)

# Configuração de tentativas
MAX_LOGIN_ATTEMPTS = 5  # Máximo de tentativas permitidas
LOCKOUT_DURATION = 900  # Duração do bloqueio em segundos (15 minutos)
ATTEMPT_WINDOW = 300  # Janela de tempo para contar tentativas (5 minutos)


class LoginAttemptTracker:
    """Rastreia tentativas de login falhas por IP e email."""
    
    @staticmethod
    def get_attempt_count(identifier: str) -> int:
        """
        Obtém o contador de tentativas falhas para um identificador (IP ou email).
        
        Args:
            identifier: Chave única (IP ou email)
            
        Returns:
            Número de tentativas falhas nos últimos ATTEMPT_WINDOW segundos
        """
        cache_key = f'login_attempt:{identifier}'
        count = cache_get(cache_key)
        return count if count is not None else 0
    
    @staticmethod
    def increment_attempt(identifier: str) -> int:
        """
        Incrementa o contador de tentativas falhas.
        
        Args:
            identifier: Chave única (IP ou email)
            
        Returns:
            Novo contador após incremento
        """
        cache_key = f'login_attempt:{identifier}'
        count = LoginAttemptTracker.get_attempt_count(identifier)
        new_count = count + 1
        
        # Se ainda não existe, define com TTL; se existe, atualiza
        cache_set(cache_key, new_count, ttl_seconds=ATTEMPT_WINDOW)
        
        return new_count
    
    @staticmethod
    def is_locked_out(identifier: str) -> bool:
        """
        Verifica se o identificador está bloqueado por muitas tentativas falhas.
        
        Args:
            identifier: Chave única (IP ou email)
            
        Returns:
            True se bloqueado, False caso contrário
        """
        cache_key = f'login_lockout:{identifier}'
        lockout = cache_get(cache_key)
        return lockout is not None  # Se existir chave de lockout, está bloqueado
    
    @staticmethod
    def apply_lockout(identifier: str) -> None:
        """
        Aplica bloqueio temporário após muitas tentativas falhas.
        
        Args:
            identifier: Chave única (IP ou email)
        """
        cache_key = f'login_lockout:{identifier}'
        cache_set(cache_key, True, ttl_seconds=LOCKOUT_DURATION)
        logger.warning(
            f"Bloqueio de login aplicado para {identifier} "
            f"por {LOCKOUT_DURATION} segundos"
        )
    
    @staticmethod
    def reset_attempts(identifier: str) -> None:
        """
        Limpa o contador de tentativas e bloqueio (após login bem-sucedido).
        
        Args:
            identifier: Chave única (IP ou email)
        """
        cache_delete(f'login_attempt:{identifier}')
        cache_delete(f'login_lockout:{identifier}')
        logger.info(f"Tentativas de login resetadas para {identifier}")
    
    @staticmethod
    def log_failed_attempt(email: str, ip_address: str, reason: str = "credenciais inválidas") -> None:
        """
        Registra uma tentativa de login falha com detalhes.
        
        Args:
            email: Email da tentativa de login
            ip_address: Endereço IP do cliente
            reason: Motivo da falha (credenciais inválidas, conta bloqueada, etc)
        """
        logger.warning(
            "Falha de login",
            extra={
                "email": email,
                "ip_address": ip_address,
                "reason": reason,
                "timestamp": datetime.now().isoformat(),
                "attempts_for_ip": LoginAttemptTracker.get_attempt_count(ip_address),
                "attempts_for_email": LoginAttemptTracker.get_attempt_count(email),
            }
        )
    
    @staticmethod
    def log_success_attempt(email: str, ip_address: str, perfil: str) -> None:
        """
        Registra um login bem-sucedido e reseta tentativas falhas.
        
        Args:
            email: Email do usuário
            ip_address: Endereço IP do cliente
            perfil: Perfil/role do usuário (solicitante, supervisor, admin)
        """
        # Reseta tentativas ao fazer login bem-sucedido
        LoginAttemptTracker.reset_attempts(ip_address)
        LoginAttemptTracker.reset_attempts(email)
        
        logger.info(
            "Login bem-sucedido",
            extra={
                "email": email,
                "ip_address": ip_address,
                "perfil": perfil,
                "timestamp": datetime.now().isoformat(),
            }
        )
