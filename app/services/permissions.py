"""
Serviço de Permissões: verifica se um usuário pode ver/editar um chamado.

Centraliza a lógica de permissão que estava duplicada em 4+ locais.
"""

from app.models_usuario import Usuario


def usuario_pode_ver_chamado(user, chamado) -> bool:
    """Verifica se o usuário tem permissão para ver/editar o chamado.
    
    Admin: pode ver tudo.
    Supervisor: pode ver apenas se a ÁREA DO CHAMADO está nas suas áreas.
    (Não basta o responsável ser de outro setor que o supervisor também atende;
     cada supervisor vê só os chamados dos setores que ele gerencia.)
    
    Args:
        user: Objeto Usuario (current_user)
        chamado: Objeto Chamado (com .area, .responsavel_id)
    
    Returns:
        True se pode ver, False caso contrário.
    """
    if user.perfil == 'admin':
        return True
    
    if user.perfil != 'supervisor':
        return False
    
    # Supervisor vê apenas chamados cujo setor está nas suas áreas
    return chamado.area in user.areas


def usuario_pode_ver_chamado_otimizado(user, chamado, cache_usuarios: dict = None) -> bool:
    """Versão otimizada: mesma regra de usuario_pode_ver_chamado (por área do chamado).
    
    Supervisor vê apenas chamados cujo setor está nas suas áreas.
    cache_usuarios é ignorado nesta regra (mantido por compatibilidade de assinatura).
    """
    if user.perfil == 'admin':
        return True
    
    if user.perfil != 'supervisor':
        return False
    
    return chamado.area in user.areas
