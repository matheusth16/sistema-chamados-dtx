"""
Serviço de Permissões: verifica se um usuário pode fazer MUTAÇÃO num chamado
(escrita — transição de status, janela de edição, flags de UI). Para regras de
VISIBILIDADE — quem pode apenas VER o chamado —, ver app/services/permissions.py.

Centraliza blocos de verificação (supervisor → areas) que apareciam
duplicados em rotas do dashboard.
"""

import logging
from typing import Any

from app.services.solicitante_edicao_service import segundos_restantes_janela_edicao

logger = logging.getLogger(__name__)


def supervisor_pode_alterar_chamado(usuario: Any, chamado_area: str, chamado: Any = None) -> bool:
    """Verifica se o usuário tem permissão de ESCRITA no chamado.

    Admin pode sempre. Supervisor somente se a área do chamado
    estiver nas suas áreas (regra mais restritiva que a de leitura).
    Gestor read-only (is_gestor_only=True) nunca pode escrever.

    Quando `chamado` é informado e o usuário é gestor_setor (Nível 3), aplica
    também a restrição de posse: a leitura ampliada de gestor_setor sobre chamado
    de colega da própria área não vira permissão de escrita — só dono/fila/
    participante/quem abriu (ver usuario_pode_operar_chamado).

    Dono do chamado (responsavel_id == usuario.id) sempre pode alterar,
    mesmo que a área do chamado não esteja mais nas áreas cadastradas do
    supervisor — bug real, auditoria 2026-08-13, achado em dado vivo do
    banco de dev: renomear/editar o cadastro de área de um supervisor (ou a
    área do próprio chamado) depois da atribuição não é uma FK, não
    propaga (ver feedback_verificar_dado_vivo_antes_hardcode), e sem essa
    checagem o responsável de fato ficava sem NENHUM controle na tela —
    nem trocar status, nem responder ao solicitante — no chamado que ele
    mesmo estava tratando.

    Args:
        usuario: current_user (com .perfil e .areas)
        chamado_area: campo area do chamado
        chamado: objeto Chamado completo (opcional — habilita a checagem de posse)

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
    if chamado_area not in getattr(usuario, "areas", []):
        return chamado is not None and getattr(chamado, "responsavel_id", None) == usuario.id
    if chamado is not None and getattr(usuario, "nivel_gestao", None) == "gestor_setor":
        from app.services.permissions import usuario_pode_operar_chamado

        return usuario_pode_operar_chamado(usuario, chamado)
    return True


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
    from app.services.permissions import usuario_pode_operar_chamado

    # Gestor read-only: bloqueio antes de qualquer outra verificação
    if getattr(usuario, "is_gestor_only", None) is True:
        return False, "access_denied_gestor_readonly"

    if usuario.perfil == "solicitante":
        if chamado.solicitante_id != usuario.id:
            return False, "access_denied_own_tickets_only"
        if novo_status != "Cancelado":
            return False, "access_denied_requester_cancel_only"
    elif usuario.perfil == "supervisor":
        # usuario_pode_operar_chamado (não usuario_pode_ver_chamado): a leitura
        # ampliada de gestor_setor sobre chamado de colega não pode virar escrita
        # (Nível 3 — enxergar não é igual a poder editar).
        if not usuario_pode_operar_chamado(usuario, chamado):
            return False, "access_denied_out_of_area"
    return True, None


def usuario_pode_mutar_chamado(usuario: Any, chamado=None) -> tuple[bool, str | None]:
    """Verifica se o usuário pode realizar qualquer mutação em chamados.

    Gestor read-only (is_gestor_only=True) nunca pode escrever, mesmo se for
    owner ou participante — EXCETO gestor_setor agindo via Ações de
    Escalonamento num chamado da própria área (chamado informado + área bate),
    decisão de escopo 2026-08-20 (ver usuario_gestor_setor_pode_escalonar).
    Admin sempre pode. Supervisor comum pode (verificações de área ficam a
    cargo dos callers).

    Args:
        usuario: current_user
        chamado: quando informado, habilita a exceção de gestor_setor acima —
            sem ele, gestor read-only continua bloqueado (fail-closed)

    Returns:
        (permitido, mensagem_erro) — mensagem_erro é None quando permitido.
    """
    if getattr(usuario, "is_gestor_only", None) is True:
        if chamado is not None:
            from app.services.permissions import usuario_gestor_setor_pode_escalonar

            if usuario_gestor_setor_pode_escalonar(usuario, chamado):
                return True, None
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


def montar_flags_detalhe_chamado(usuario: Any, chamado: Any) -> dict:
    """Calcula as flags de permissão/estado da tela de detalhe do chamado
    (visualizar_chamado.html): o que pode ser editado e a janela de
    ações do solicitante dono (edição de descrição, cancelamento, anexo tardio).

    Extraído de visualizar_detalhe_chamado (app/routes/dashboard.py) — a rota
    calculava essas ~10 regras direto no controller, misturando lógica de
    negócio com montagem de resposta HTTP (achado em auditoria, 2026-08-05).
    """
    status_com_janela_solicitante = {"Aberto", "Em Atendimento", "Aguardando Informação"}

    nivel = nivel_congelamento_chamado(chamado)
    # Escrita é mais restritiva que leitura: usuario_pode_ver_chamado (checado
    # pelo caller antes de chamar esta função) libera dono/responsável/fila/
    # participante/observador, mas só quem tem a área do chamado (ou admin)
    # pode de fato editar — supervisor que só enxerga como observador (cc)
    # fica read-only. supervisor_pode_alterar_chamado já bloqueia gestor_only.
    pode_editar_base = supervisor_pode_alterar_chamado(usuario, chamado.area, chamado)
    # Chamado Concluído (qualquer nível) bloqueia edição operacional no formulário
    pode_editar = pode_editar_base and nivel is None
    # Descrição é texto do solicitante — só admin pode sobrescrever (ver
    # edicao_chamado_service.py); supervisor nunca edita o que foi escrito.
    pode_editar_descricao = pode_editar and usuario.is_admin_or_above

    eh_dono_do_chamado = chamado.solicitante_id == usuario.id and not getattr(
        usuario, "is_gestor_only", False
    )
    segundos_restantes = 0
    pode_editar_descricao_solicitante = False
    if eh_dono_do_chamado and chamado.status == "Aberto":
        dt_ab = chamado._converter_timestamp(chamado.data_abertura)
        if dt_ab:
            segundos_restantes = segundos_restantes_janela_edicao(dt_ab)
            pode_editar_descricao_solicitante = segundos_restantes > 0
    pode_cancelar_solicitante = eh_dono_do_chamado and chamado.status in (
        status_com_janela_solicitante
    )
    pode_anexo_tardio_solicitante = eh_dono_do_chamado and chamado.status in (
        status_com_janela_solicitante
    )

    return {
        "nivel_congelamento": nivel,
        "pode_editar_base": pode_editar_base,
        "pode_editar": pode_editar,
        "pode_editar_descricao": pode_editar_descricao,
        "pode_editar_descricao_solicitante": pode_editar_descricao_solicitante,
        "segundos_restantes_edicao": segundos_restantes,
        "pode_cancelar_solicitante": pode_cancelar_solicitante,
        "pode_anexo_tardio_solicitante": pode_anexo_tardio_solicitante,
    }


def montar_anexos_para_exibicao(chamado: Any, historico: list) -> list[dict]:
    """Anexos do chamado deduplicados, anotados com quem anexou cada um, e
    ordenados com os do solicitante primeiro (pra visualizar_chamado.html).

    chamado.anexos é uma lista simples (só o caminho/chave do arquivo) — não
    guarda quem anexou. Cruza contra o Histórico, que registra isso nos dois
    fluxos que adicionam anexo DEPOIS da criação: edição do responsável
    (acao="alteracao_dados", campo_alterado="novo anexo") e anexo tardio do
    solicitante (acao="anexo_tardio"). Um caminho sem entrada correspondente
    veio da abertura do chamado — sempre pelo solicitante.
    """
    anexos_brutos = (
        chamado.anexos
        if (chamado.anexos and len(chamado.anexos) > 0)
        else ([chamado.anexo] if chamado.anexo and chamado.anexo != "None" else [])
    )
    vistos: set = set()
    anexos_unicos = []
    for a in anexos_brutos:
        if a and a != "None" and a not in vistos:
            vistos.add(a)
            anexos_unicos.append(a)

    origem_por_caminho = {}
    for evento in historico:
        eh_anexo_responsavel = (
            evento.acao == "alteracao_dados" and evento.campo_alterado == "novo anexo"
        )
        eh_anexo_tardio_solicitante = evento.acao == "anexo_tardio"
        if (eh_anexo_responsavel or eh_anexo_tardio_solicitante) and evento.valor_novo:
            origem_por_caminho.setdefault(evento.valor_novo, evento)

    itens = []
    for caminho in anexos_unicos:
        evento = origem_por_caminho.get(caminho)
        eh_solicitante = evento is None or evento.usuario_id == chamado.solicitante_id
        itens.append(
            {
                "caminho": caminho,
                "eh_solicitante": eh_solicitante,
                "usuario_id": None if eh_solicitante else evento.usuario_id,
                "usuario_nome": None if eh_solicitante else evento.usuario_nome,
            }
        )

    # Sort estável: solicitante primeiro, mantendo ordem relativa original dentro de cada grupo
    itens.sort(key=lambda item: 0 if item["eh_solicitante"] else 1)
    return itens


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
