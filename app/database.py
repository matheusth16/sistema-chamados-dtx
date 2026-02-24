"""
Inicialização e Configuração do Firebase/Firestore

Responsável por:
1. Inicializar Firebase Admin SDK com retry automático
2. Fornecer cliente Firestore para toda a aplicação
3. Gerenciar credenciais (arquivo credentials.json ou Cloud credentials)

A inicialização usa exponential backoff com até 3 tentativas.
Em Cloud Run, usa Application Default Credentials (ADC) automaticamente.
Em desenvolvimento local, busca credentials.json na raiz do projeto.
"""

import firebase_admin
from firebase_admin import credentials, firestore
import os
import time
import logging

logger = logging.getLogger(__name__)


def _inicializar_firebase_com_retry(max_tentativas: int = 3, delay_inicial: float = 1.0):
    """
    Inicializa Firebase Admin SDK com retry automático e exponential backoff.
    
    Tenta inicializar Firebase até 3 vezes, aguardando progressivamente mais
    tempo entre cada tentativa em caso de falha.
    
    Args:
        max_tentativas (int): Número máximo de tentativas de inicialização.
                             Padrão: 3 (delays: 1s, 2s, 4s)
        delay_inicial (float): Delay inicial em segundos antes de retry.
                              Padrão: 1.0
    
    Raises:
        Exception: Se todas as tentativas falharem. Registra a falha em log.
        
    Side Effects:
        - Inicializa firebase_admin._apps (app padrão do Firebase)
        - Registra tentativas e resultados no logger
        
    Examples:
        >>> _inicializar_firebase_com_retry(max_tentativas=5)
        # INFO: Tentativa 1/5 para inicializar Firebase...
        # INFO: Firebase inicializado com credentials.json
        
        >>> _inicializar_firebase_com_retry()
        # INFO: Firebase já inicializado
    """
    for tentativa in range(1, max_tentativas + 1):
        try:
            # Verifica se Firebase já foi inicializado
            firebase_admin.get_app()
            logger.info("✓ Firebase já inicializado (app padrão encontrado)")
            return
        except ValueError:
            # Primera inicialização necessária
            pass
        
        try:
            logger.info(f"Tentativa {tentativa}/{max_tentativas} para inicializar Firebase...")
            
            # Caminho para credentials.json
            cert_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), 
                'credentials.json'
            )
            
            if os.path.exists(cert_path):
                # Inicializa com arquivo de credenciais (desenvolvimento local)
                logger.info(f"Carregando credentials.json de: {cert_path}")
                cred = credentials.Certificate(cert_path)
                firebase_admin.initialize_app(cred)
                logger.info("✓ Firebase inicializado com credentials.json (arquivo local)")
            else:
                # Inicializa com Application Default Credentials (Cloud Run/GCP)
                logger.info("credentials.json não encontrado. Usando ADC (Application Default Credentials)")
                firebase_admin.initialize_app()
                logger.info("✓ Firebase inicializado com ADC (Cloud credentials)")
            
            return  # Sucesso - sai da função
            
        except Exception as e:
            logger.warning(
                f"⚠ Tentativa {tentativa}/{max_tentativas} falhou: {type(e).__name__}: {e}"
            )
            
            if tentativa < max_tentativas:
                # Calcula delay com exponential backoff: 1s, 2s, 4s, 8s, ...
                delay = delay_inicial * (2 ** (tentativa - 1))
                logger.info(f"Aguardando {delay}s antes de tentar novamente...")
                time.sleep(delay)
            else:
                # Última tentativa falhou - levanta exceção
                logger.critical(
                    f"✗ Todas as {max_tentativas} tentativas falharam. "
                    f"Firebase não foi inicializado. Verifique credenciais."
                )
                raise


# Executa inicialização com retry
try:
    _inicializar_firebase_com_retry(max_tentativas=3)
except Exception as e:
    logger.critical(
        f"✗ Erro crítico: Firebase não foi inicializado. "
        f"A aplicação não pode funcionar. Detalhes: {e}"
    )
    raise

# Obtém cliente Firestore com verificação
try:
    db = firestore.client()
    logger.info("✓ Cliente Firestore obtido com sucesso. Aplicação pronta.")
except Exception as e:
    logger.critical(
        f"✗ Erro ao obter cliente Firestore: {type(e).__name__}: {e}"
    )
    raise
