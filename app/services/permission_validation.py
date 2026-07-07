"""
Validação de permissões de acesso a chamados.

Centraliza blocos de verificação (supervisor → areas) que apareciam
duplicados em rotas do dashboard.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def supervisor_pode_alterar_chamado(usuario: Any, chamado_area: str) -> bool:
    """Verifica se o usuário tem permissão de ESCRITA no chamado.

    Admin pode sempre. Supervisor somente se a área do chamado
    estiver nas suas áreas (regra mais restritiva que a de leitura).
    Gestor read-only (is_gestor_only=True) nunca pode escrever.

    Args:
        usuario: current_user (com .perfil e .areas)
        chamado_area: campo area do chamado

    Returns:
        True se pode alterar, False caso contrário.
    """
    if usuario.is_admin_or_above:
        return True
    # Gestor sem privilégio admin → read-only, sem escrita
    if getattr(usuario, "is_gestor_only", None) is True:
        return False
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

    # Gestor read-only: bloqueio antes de qualquer outra verificação
    if getattr(usuario, "is_gestor_only", None) is True:
        return False, "access_denied_gestor_readonly"

    if usuario.perfil == "solicitante":
        if chamado.solicitante_id != usuario.id:
            return False, "access_denied_own_tickets_only"
        if novo_status != "Cancelado":
            return False, "access_denied_requester_cancel_only"
    elif usuario.perfil == "supervisor":
        if not usuario_pode_ver_chamado(usuario, chamado):
            return False, "access_denied_out_of_area"
    return True, None


def usuario_pode_mutar_chamado(usuario: Any, chamado=None) -> tuple[bool, str | None]:
    """Verifica se o usuário pode realizar qualquer mutação em chamados.

    Gestor read-only (is_gestor_only=True) nunca pode escrever, mesmo se for
    owner ou participante. Admin sempre pode. Supervisor comum pode (verificações
    de área ficam a cargo dos callers).

    Args:
        usuario: current_user
        chamado: ignorado nesta versão; mantido para compatibilidade futura

    Returns:
        (permitido, mensagem_erro) — mensagem_erro é None quando permitido.
    """
    if getattr(usuario, "is_gestor_only", None) is True:
        return False, "access_denied_gestor_readonly"
    return True, None


def nivel_congelamento_chamado(chamado) -> str | None:
    """Retorna None | 'pendente' | 'confirmado' conforme status + confirmacao_solicitante.

    Suporta objeto Chamado (com atributos) ou dict.
    'pendente' = Nível 1 (aguardando confirmação do solicitante).
    'confirmado' = Nível 2 (encerrado e confirmado pelo solicitante).
    None = sem congelamento (chamado não está Concluído, ou está em estado transitório).
    """
    if isinstance(chamado, dict):
        status = chamado.get("status")
        confirmacao = chamado.get("confirmacao_solicitante")
    else:
        status = getattr(chamado, "status", None)
        confirmacao = getattr(chamado, "confirmacao_solicitante", None)

    if status != "Concluído":
        return None
    if confirmacao == "confirmado":
        return "confirmado"
    # "reaberto" + Concluído é estado anômalo (reabertura deveria mudar status para Aberto)
    if confirmacao == "reaberto":
        logger.warning(
            "Chamado Concluído com confirmacao_solicitante='reaberto' — estado anômalo; "
            "tratando como pendente por segurança"
        )
    # None, "", "pendente", "reaberto" ou qualquer outro valor → congela como nível 1 (pendente)
    return "pendente"


def chamado_aceita_edicao_operacional(usuario: Any, chamado: Any) -> tuple[bool, str | None]:
    """False se Concluído (nível 1 ou 2) — bloqueia edição operacional para qualquer perfil.

    Edição operacional: descrição, responsável, anexos, setores, SLA, participantes.
    Para reabrir, use /api/atualizar-status com chamado_aceita_transicao_status.

    Returns:
        (permitido, chave_i18n_erro) — chave_i18n_erro é None quando permitido.
    """
    if nivel_congelamento_chamado(chamado) is not None:
        return False, "error_ticket_frozen_no_edit"
    return True, None


def chamado_aceita_transicao_status(
    usuario: Any, chamado: Any, novo_status: str
) -> tuple[bool, str | None]:
    """Regras de transição de status quando Concluído.

    Nível 1 (pendente):
    - Supervisor ou Admin: Aberto (reabrir) ou Cancelado OK
    - Em Atendimento sempre bloqueado (contornaria confirmação do solicitante)
    - Solicitante: tudo bloqueado (usa /api/chamado/<id>/confirmar-resolucao)

    Nível 2 (confirmado):
    - Admin: apenas → Aberto (reabrir com motivo)
    - Supervisor / Solicitante: tudo bloqueado

    Fora dos níveis (não Concluído): retorna True sem restrição adicional.

    Returns:
        (permitido, chave_i18n_erro) — chave_i18n_erro é None quando permitido.
    """
    nivel = nivel_congelamento_chamado(chamado)
    if nivel is None:
        return True, None

    is_admin = getattr(usuario, "is_admin_or_above", False)
    perfil = getattr(usuario, "perfil", "")

    if nivel == "pendente":
        if (is_admin or perfil == "supervisor") and novo_status in ("Aberto", "Cancelado"):
            return True, None
        return False, "error_ticket_frozen_no_edit"

    if nivel == "confirmado":
        if is_admin and novo_status == "Aberto":
            return True, None
        return False, "error_ticket_frozen_no_edit"

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
