"""
Serviço de Permissões: verifica se um usuário pode ver/editar um chamado.

Centraliza a lógica de permissão que estava duplicada em 4+ locais.
"""

from app.models_usuario import Usuario


def usuario_pode_ver_chamado(user, chamado) -> bool:
    """Verifica se o usuário tem permissão para ver/editar o chamado.
    
    Admin: pode ver tudo.
    Supervisor: pode ver se:
        - A área do chamado está nas suas áreas, OU
        - O chamado está atribuído a ele, OU
        - O responsável atual do chamado tem área em comum com o supervisor.
    
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
    
    # 1. Área do chamado está nas áreas do supervisor
    if chamado.area in user.areas:
        return True
    
    # 2. Chamado está atribuído diretamente ao supervisor
    if chamado.responsavel_id == user.id:
        return True
    
    # 3. Responsável atual tem área em comum com o supervisor
    if chamado.responsavel_id:
        responsavel_obj = Usuario.get_by_id(chamado.responsavel_id)
        if responsavel_obj and bool(set(responsavel_obj.areas) & set(user.areas)):
            return True
    
    return False


def usuario_pode_ver_chamado_otimizado(user, chamado, cache_usuarios: dict = None) -> bool:
    """Versão otimizada que aceita um cache de usuários pré-carregados.
    
    Evita queries N+1 ao Firestore quando chamada em loop.
    
    Args:
        user: Objeto Usuario (current_user)
        chamado: Objeto Chamado
        cache_usuarios: Dict {user_id: Usuario} pré-carregado
    
    Returns:
        True se pode ver, False caso contrário.
    """
    if user.perfil == 'admin':
        return True
    
    if user.perfil != 'supervisor':
        return False
    
    if chamado.area in user.areas:
        return True
    
    if chamado.responsavel_id == user.id:
        return True
    
    if chamado.responsavel_id and cache_usuarios:
        responsavel_obj = cache_usuarios.get(chamado.responsavel_id)
        if responsavel_obj and bool(set(responsavel_obj.areas) & set(user.areas)):
            return True
    
    return False
