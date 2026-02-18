import os
from dotenv import load_dotenv

# 1. Define a "Raiz" do projeto de forma absoluta (C:\Users\Matheus...\sistema_chamados)
basedir = os.path.abspath(os.path.dirname(__file__))

# Carrega as variáveis do arquivo .env
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    """Configuração base da aplicação"""
    SECRET_KEY = os.getenv('SECRET_KEY')
    
    # 2. Caminho ABSOLUTO para a pasta de uploads (Evita erros no Windows/OneDrive)
    UPLOAD_FOLDER = os.path.join(basedir, 'app', 'static', 'uploads')
    
    # 3. Segurança: Limita o tamanho do arquivo a 16MB (Padrão Flask)
    # Se passar disso, o sistema rejeita automaticamente.
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    
    # 4. Paginação
    ITENS_POR_PAGINA = 10
    
    # 5. Rate Limiting (limite de requisições por janela de tempo)
    RATELIMIT_ENABLED = True
    RATELIMIT_DEFAULT = "200 per day, 50 per hour"  # Limite global padrão
    RATELIMIT_STORAGE_URL = "memory://"  # Storage em memória (simples)
    
    # 6. Segurança CSRF
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None  # Sem limite de tempo para tokens CSRF
    
    # 7. Session Security
    PERMANENT_SESSION_LIFETIME = 86400  # 24 horas em segundos
    SESSION_COOKIE_SECURE = True  # Apenas HTTPS em produção
    SESSION_COOKIE_HTTPONLY = True  # Não acessível via JavaScript
    SESSION_COOKIE_SAMESITE = 'Lax'  # Proteção contra CSRF
    
    # 8. Validação de Entrada
    MAX_DESCRICAO_CHARS = 5000
    MIN_DESCRICAO_CHARS = 3
    EXTENSOES_UPLOAD_PERMITIDAS = {'png', 'jpg', 'jpeg', 'pdf', 'xlsx'}
    
    # Firebase: Será inicializado em app/database.py
    # As credenciais vão em credentials.json na raiz do projeto