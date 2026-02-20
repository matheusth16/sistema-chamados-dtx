"""
Decoradores para controle de acesso baseado em perfil (RBAC)

Uso:
    @requer_perfil('admin')  # Apenas admins
    @requer_perfil(['supervisor', 'admin'])  # Supervisores ou admins
    @requer_supervisor_area  # Supervisor pode ver/editar apenas sua área
"""

from functools import wraps
from flask import redirect, url_for, flash, current_app
from flask_login import current_user
import logging

logger = logging.getLogger(__name__)


def requer_perfil(*perfis_permitidos):
    """
    Decorador que verifica se o usuário tem um dos perfis permitidos
    
    Parâmetros:
        *perfis_permitidos: String ou lista de strings com os perfis permitidos
                            Exemplos: 'admin', 'supervisor', ['admin', 'supervisor']
    
    Exemplo:
        @requer_perfil('admin')
        def rota_admin():
            pass
        
        @requer_perfil('supervisor', 'admin')
        def rota_gestao():
            pass
    """
    def decorador(f):
        @wraps(f)
        def funcao_decorada(*args, **kwargs):
            # Se não está autenticado, redireciona para login
            if not current_user.is_authenticated:
                logger.warning(f"Acesso negado: usuário não autenticado tentou acessar {f.__name__}")
                flash('Você precisa estar logado para acessar essa página.', 'danger')
                return redirect(url_for('main.login'))
            
            # Normaliza perfis_permitidos para uma lista
            perfis_lista = []
            for perfil in perfis_permitidos:
                if isinstance(perfil, (list, tuple)):
                    perfis_lista.extend(perfil)
                else:
                    perfis_lista.append(perfil)
            
            # Verifica se o perfil do usuário está na lista
            if current_user.perfil not in perfis_lista:
                logger.warning(f"Acesso negado: usuário {current_user.email} (perfil {current_user.perfil}) tentou acessar {f.__name__}")
                flash(f'Acesso negado. Você precisa ter um dos seguintes perfis: {", ".join(perfis_lista)}', 'danger')
                
                # Redireciona para a página apropriada conforme o perfil
                if current_user.perfil == 'solicitante':
                    return redirect(url_for('main.index'))
                else:
                    return redirect(url_for('main.admin'))
            
            # Perfil autorizado, executa a função
            return f(*args, **kwargs)
        
        return funcao_decorada
    return decorador


def requer_supervisor_area(f):
    """
    Decorador especial para verificar se é supervisor/admin
    Se for supervisor, adiciona filtro automático por área
    
    Uso:
        @requer_supervisor_area
        def rota_gestao():
            # current_user.area contém a área do supervisor
            # Você já pode usar current_user.area para filtrar
            pass
    """
    @wraps(f)
    def funcao_decorada(*args, **kwargs):
        # Se não está autenticado, redireciona para login
        if not current_user.is_authenticated:
            logger.warning(f"Acesso negado: usuário não autenticado tentou acessar {f.__name__}")
            flash('Você precisa estar logado para acessar essa página.', 'danger')
            return redirect(url_for('main.login'))
        
        # Apenas supervisores e admins podem acessar
        if current_user.perfil not in ['supervisor', 'admin']:
            logger.warning(f"Acesso negado: solicitante {current_user.email} tentou acessar {f.__name__}")
            flash('Acesso negado. Apenas supervisores e admins podem acessar essa página.', 'danger')
            return redirect(url_for('main.index'))
        
        # Se é supervisor, registra a área dele para uso posterior
        if current_user.perfil == 'supervisor':
            current_app.logger.debug(f"Supervisor {current_user.email} acessando {f.__name__} (Área: {current_user.area})")
        
        # Executa a função
        return f(*args, **kwargs)
    
    return funcao_decorada


def requer_solicitante(f):
    """
    Decorador para rotas que só solicitantes podem acessar
    (aqueles que criam chamados)
    """
    @wraps(f)
    def funcao_decorada(*args, **kwargs):
        # Se não está autenticado, redireciona para login
        if not current_user.is_authenticated:
            logger.warning(f"Acesso negado: usuário não autenticado tentou acessar {f.__name__}")
            flash('Você precisa estar logado para acessar essa página.', 'danger')
            return redirect(url_for('main.login'))
        
        # Apenas solicitantes podem acessar
        if current_user.perfil != 'solicitante':
            logger.warning(f"Acesso negado: {current_user.perfil} {current_user.email} tentou acessar rota de solicitante {f.__name__}")
            flash('Acesso negado. Essa página é apenas para solicitantes.', 'danger')
            return redirect(url_for('main.admin'))
        
        # Executa a função
        return f(*args, **kwargs)
    
    return funcao_decorada
