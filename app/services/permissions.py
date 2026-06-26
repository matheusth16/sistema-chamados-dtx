"""
Serviço de Permissões: verifica se um usuário pode ver/editar um chamado.

Centraliza a lógica de permissão que estava duplicada em 4+ locais.
Ordem fail-closed:
  1. admin/admin_global → True (acesso total)
  2. solicitante → True somente se solicitante_id == user.id (chamado próprio)
  3. supervisor → True se:
       a. abriu o chamado (solicitante_id == user.id)
       b. é o responsável atual (responsavel_id == user.id)
       c. chamado está na fila da área (area in user.areas AND responsavel_id is None)
       d. é participante ativo (user.id in participantes[*].supervisor_id)
  4. qualquer outro perfil → False
"""

from typing import Any

from app.models_usuario import Usuario


def calcular_supervisor_ids_com_acesso(
    area: str,
    responsavel_id: str | None,
    participantes: list | None = None,
) -> list[str]:
    """Calcula a lista desnormalizada de IDs de supervisores com acesso operacional.

    - Com owner: [owner] + participantes ativos
    - Fila (sem owner): todos os supervisores/admins da área + participantes

    Retorna lista deduplicada e ordenada alfabeticamente (estável).
    """
    ids: set[str] = set()

    # Adiciona participantes em qualquer caso
    for p in participantes or []:
        sid = p.get("supervisor_id") if isinstance(p, dict) else getattr(p, "supervisor_id", None)
        if sid:
            ids.add(sid)

    if responsavel_id:
        ids.add(responsavel_id)
    else:
        # Fila sem owner: inclui todos supervisores/admins da área
        try:
            supervisores = Usuario.get_supervisores_por_area(area)
            for sup in supervisores:
                if sup.id:
                    ids.add(sup.id)
        except Exception:
            pass  # fail-open na leitura; permissão real verificada por usuario_pode_ver_chamado

    return sorted(ids)


def usuario_pode_ver_chamado(user: Usuario, chamado: Any) -> bool:
    """Verifica se o usuário tem permissão para ver/editar o chamado.

    Admin: pode ver tudo.
    Solicitante: vê somente os chamados que ele mesmo abriu (solicitante_id == user.id).
    Supervisor: vê chamados:
      - que ele mesmo abriu (solicitante_id == user.id)
      - onde é o responsável atual (responsavel_id == user.id)
      - fila da área sem owner (area in user.areas AND responsavel_id is None)
      - onde é participante ativo

    Args:
        user: Objeto Usuario (current_user)
        chamado: Objeto Chamado (com .area, .responsavel_id, .solicitante_id, .participantes)

    Returns:
        True se pode ver, False caso contrário (fail-closed).
    """
    if user.is_admin_or_above:
        return True

    # Gestor read-only: visão ampliada (vê todos os chamados)
    if getattr(user, "is_gestor", None) is True and not user.is_admin_or_above:
        return True

    if user.perfil == "solicitante":
        return getattr(chamado, "solicitante_id", None) == user.id

    if user.perfil == "supervisor":
        # a) abriu o chamado
        if getattr(chamado, "solicitante_id", None) == user.id:
            return True

        responsavel_id = getattr(chamado, "responsavel_id", None)

        # b) é o responsável atual (owner)
        if responsavel_id and responsavel_id == user.id:
            return True

        # c) fila da área sem owner
        if not responsavel_id and chamado.area in getattr(user, "areas", []):
            return True

        # d) é participante ativo
        participantes = getattr(chamado, "participantes", None) or []
        for p in participantes:
            sid = (
                p.get("supervisor_id") if isinstance(p, dict) else getattr(p, "supervisor_id", None)
            )
            if sid and sid == user.id:
                return True

        return False

    return False


def usuario_pode_ver_chamado_otimizado(
    user: Usuario,
    chamado: Any,
    cache_usuarios: dict | None = None,
) -> bool:
    """Versão otimizada: mesma regra de usuario_pode_ver_chamado.

    cache_usuarios é ignorado nesta regra (mantido por compatibilidade de assinatura).
    """
    return usuario_pode_ver_chamado(user, chamado)
