"""
Entry point da aplicação Sistema de Chamados.

Configura ambiente e inicia servidor Flask com segurança.
Debug é ativado apenas em desenvolvimento via variável de ambiente.
"""

import os
import logging
from app import create_app

# Logger para mensagens de inicialização
logger = logging.getLogger(__name__)

app = create_app()

if __name__ == '__main__':
    # Determina modo de debug da variável de ambiente
    # Padrão: False (seguro para produção)
    debug_mode = os.getenv('FLASK_ENV', 'production') == 'development'
    
    # Porta padrão: 5000, pode ser alterada via PORT
    port = int(os.getenv('PORT', 5000))
    
    # Host: localhost em dev, 0.0.0.0 em produção (se configurado)
    host = os.getenv('FLASK_HOST', '127.0.0.1' if debug_mode else 'localhost')
    
    # Log de inicialização
    log_level = logging.DEBUG if debug_mode else logging.INFO
    logger.setLevel(log_level)
    
    print(f"\n{'='*60}")
    print("Sistema de Chamados - DTX Aerospace")
    print(f"{'='*60}")
    print(f"Ambiente: {'DESENVOLVIMENTO' if debug_mode else 'PRODUÇÃO'}")
    print(f"Host: {host}:{port}")
    print(f"Debug: {debug_mode}")
    print(f"{'='*60}\n")
    
    # Inicia servidor
    app.run(
        debug=debug_mode,
        host=host,
        port=port,
        use_reloader=debug_mode
    )