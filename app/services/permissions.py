"""
Serviço de Permissões: verifica se um usuário pode ver/editar um chamado.

Centraliza a lógica de permissão que estava duplicada em 4+ locais.
"""

from typing import Any

from app.models_usuario import Usuario


def usuario_pode_ver_chamado(user: Usuario, chamado: Any) -> bool:
    """Verifica se o usuário tem permissão para ver/editar o chamado.

    Admin: pode ver tudo.
    Supervisor: pode ver se (1) a ÁREA DO CHAMADO está nas suas áreas,
    ou (2) ele é o solicitante (abriu o chamado para outra pessoa).
    Assim, na aba "Meus Chamados", o supervisor consegue visualizar detalhes,
    escrever e adicionar anexos nos chamados que abriu.

    Args:
        user: Objeto Usuario (current_user)
        chamado: Objeto Chamado (com .area, .responsavel_id, .solicitante_id)

    Returns:
        True se pode ver, False caso contrário.
    """
    if user.perfil == "admin":
        return True

    if user.perfil != "supervisor":
        return False

    # Supervisor vê chamados da sua área ou que ele mesmo abriu (solicitante)
    if getattr(chamado, "solicitante_id", None) == user.id:
        return True
    return chamado.area in getattr(user, "areas", [])


def usuario_pode_ver_chamado_otimizado(
    user: Usuario,
    chamado: Any,
    cache_usuarios: dict | None = None,
) -> bool:
    """Versão otimizada: mesma regra de usuario_pode_ver_chamado.

    Supervisor vê chamados da sua área ou que ele abriu (solicitante_id).
    cache_usuarios é ignorado nesta regra (mantido por compatibilidade de assinatura).
    """
    if user.perfil == "admin":
        return True

    if user.perfil != "supervisor":
        return False

    if getattr(chamado, "solicitante_id", None) == user.id:
        return True
    return chamado.area in getattr(user, "areas", [])
