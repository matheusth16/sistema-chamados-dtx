"""
Validação de permissões de acesso a chamados.

Centraliza blocos de verificação (supervisor → areas) que apareciam
duplicados em rotas do dashboard.
"""

from typing import Any


def supervisor_pode_alterar_chamado(usuario: Any, chamado_area: str) -> bool:
    """Verifica se o usuário tem permissão de ESCRITA no chamado.

    Admin pode sempre. Supervisor somente se a área do chamado
    estiver nas suas áreas (regra mais restritiva que a de leitura).

    Args:
        usuario: current_user (com .perfil e .areas)
        chamado_area: campo area do chamado

    Returns:
        True se pode alterar, False caso contrário.
    """
    if usuario.perfil == "admin":
        return True
    if usuario.perfil != "supervisor":
        return False
    return chamado_area in getattr(usuario, "areas", [])


def verificar_permissao_mudanca_status(
    usuario: Any, chamado: Any, novo_status: str
) -> tuple[bool, str | None]:
    """Verifica se o usuário pode alterar o chamado para novo_status.

    Regras:
    - Admin: sempre pode.
    - Supervisor: apenas se usuário_pode_ver_chamado() (área).
    - Solicitante: apenas o próprio chamado, e somente para "Cancelado".

    Args:
        usuario: current_user (com .perfil, .id, .areas)
        chamado: objeto Chamado (com .solicitante_id, .area)
        novo_status: status desejado

    Returns:
        (permitido, mensagem_erro) — mensagem_erro é None quando permitido.
    """
    from app.services.permissions import usuario_pode_ver_chamado

    if usuario.perfil == "solicitante":
        if chamado.solicitante_id != usuario.id:
            return False, "Acesso negado: Você só pode atualizar seus próprios chamados"
        if novo_status != "Cancelado":
            return False, "Acesso negado: Solicitantes só podem Cancelar chamados"
    elif usuario.perfil == "supervisor":
        if not usuario_pode_ver_chamado(usuario, chamado):
            return False, "Acesso negado: Sem permissão ou fora da sua área"
    return True, None


def filtrar_supervisores_por_area(usuario: Any, supervisores: list) -> list:
    """Filtra lista de supervisores para mostrar apenas os da mesma área do usuário.

    Supervisor vê somente supervisores que compartilham pelo menos uma área.
    Admin vê todos.

    Args:
        usuario: current_user (com .perfil e .areas)
        supervisores: lista de objetos Usuario com perfil supervisor

    Returns:
        Lista filtrada (ou original, se admin).
    """
    if usuario.perfil != "supervisor" or not getattr(usuario, "areas", None):
        return supervisores
    user_areas = set(usuario.areas)
    return [u for u in supervisores if user_areas & set(getattr(u, "areas", []))]
