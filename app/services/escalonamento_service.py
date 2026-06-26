"""Serviço de escalonamento: transferir_area, escalonar_colega, incluir_participantes,
concluir_minha_parte (Fase 4).

Regras de negócio (ADR-004 / Fases 3–4):
- Só o owner (responsavel_id == usuario.id) ou admin pode executar transferências/inclusões.
- supervisor_id destino é obrigatório (invariante anti-órfão).
- motivo obrigatório e não vazio (após strip).
- Após qualquer mutação: recalcular supervisor_ids_com_acesso.
- Registrar histórico auditável em Historico.
- Owner não pode concluir globalmente enquanto houver participante com status != 'concluido'.
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app.database import db
from app.firebase_retry import execute_with_retry
from app.models import Chamado
from app.models_historico import Historico
from app.models_usuario import Usuario
from app.services.permissions import calcular_supervisor_ids_com_acesso
from config import Config

logger = logging.getLogger(__name__)


# ── Helpers Fase 4 ─────────────────────────────────────────────────────────────


def pode_concluir_global(chamado: Chamado) -> bool:
    """True se lista de participantes vazia OU todos com status='concluido'."""
    participantes = chamado.participantes or []
    return all(p.get("status") == "concluido" for p in participantes)


def todos_participantes_concluidos(chamado: Chamado) -> bool:
    """True se todos participantes têm status='concluido' (lista não vazia)."""
    participantes = chamado.participantes or []
    return bool(participantes) and all(p.get("status") == "concluido" for p in participantes)


def transferir_area(
    chamado_id: str,
    area: str,
    supervisor_id: str | None,
    motivo: str,
    usuario,
) -> dict:
    """Transfere o chamado para outra área com novo responsável obrigatório.

    Args:
        chamado_id: ID do documento no Firestore.
        area: Área destino (não vazia).
        supervisor_id: ID do supervisor destino — obrigatório (anti-órfão).
        motivo: Razão da transferência — obrigatório e não vazio.
        usuario: Usuário que executa a ação (owner ou admin).

    Returns:
        {"sucesso": True, "dados": {...}} ou {"sucesso": False, "erro": "..."}.

    Raises:
        ValueError: Para campos obrigatórios nulos/vazios (supervisor_id, motivo, area).
    """
    # ── validações de input (ValueError — capturado pela rota como 400) ──────
    if not supervisor_id:
        raise ValueError("supervisor_id obrigatório")

    motivo = (motivo or "").strip()
    if not motivo:
        raise ValueError("motivo obrigatório")

    area = (area or "").strip()
    if not area:
        raise ValueError("área obrigatória")

    # ── carrega chamado ──────────────────────────────────────────────────────
    doc = db.collection("chamados").document(chamado_id).get()
    if not doc.exists:
        return {"sucesso": False, "erro": "Chamado não encontrado"}

    dados = doc.to_dict() or {}
    chamado = Chamado.from_dict(dados, chamado_id)

    # ── verifica permissão (owner ou admin) ──────────────────────────────────
    if not (chamado.responsavel_id == usuario.id or usuario.is_admin_or_above):
        logger.warning(
            "transferir_area negado: usuário %s não é owner do chamado %s",
            usuario.id,
            chamado_id,
        )
        return {"sucesso": False, "erro": "Sem permissão para transferir este chamado"}

    # ── valida supervisor destino na área destino ────────────────────────────
    supervisores_destino = Usuario.get_supervisores_por_area(area)
    sup_destino = next((s for s in supervisores_destino if s.id == supervisor_id), None)
    if not sup_destino:
        return {
            "sucesso": False,
            "erro": "Supervisor destino não encontrado ou não pertence à área destino",
        }

    # ── recalcula supervisor_ids_com_acesso ──────────────────────────────────
    novos_ids = calcular_supervisor_ids_com_acesso(area, supervisor_id, chamado.participantes)

    area_anterior = chamado.area

    # ── update atômico ───────────────────────────────────────────────────────
    execute_with_retry(
        db.collection("chamados").document(chamado_id).update,
        {
            "area": area,
            "responsavel_id": supervisor_id,
            "responsavel": sup_destino.nome,
            "motivo_ultima_escalacao": motivo[:500],
            "supervisor_ids_com_acesso": novos_ids,
        },
        max_retries=3,
    )

    # ── histórico ────────────────────────────────────────────────────────────
    hist = Historico(
        chamado_id=chamado_id,
        usuario_id=usuario.id,
        usuario_nome=usuario.nome,
        acao="transferencia_area",
        campo_alterado="area",
        valor_anterior=area_anterior,
        valor_novo=area,
        detalhe=f"Transferido para {area} — {motivo[:500]}",
    )
    hist.save()

    logger.info(
        "Chamado %s transferido de '%s' para '%s' por %s",
        chamado_id,
        area_anterior,
        area,
        usuario.id,
    )
    return {"sucesso": True, "dados": {"area": area, "responsavel_id": supervisor_id}}


def escalonar_colega(
    chamado_id: str,
    supervisor_id: str | None,
    motivo: str,
    usuario,
) -> dict:
    """Escala o chamado para um colega da mesma área sem alterar a área.

    Args:
        chamado_id: ID do documento no Firestore.
        supervisor_id: ID do colega destino — obrigatório.
        motivo: Razão do escalonamento — obrigatório e não vazio.
        usuario: Usuário que executa a ação (owner ou admin).

    Returns:
        {"sucesso": True, "dados": {...}} ou {"sucesso": False, "erro": "..."}.

    Raises:
        ValueError: Para campos obrigatórios nulos/vazios.
    """
    # ── validações de input ──────────────────────────────────────────────────
    if not supervisor_id:
        raise ValueError("supervisor_id obrigatório")

    motivo = (motivo or "").strip()
    if not motivo:
        raise ValueError("motivo obrigatório")

    # ── carrega chamado ──────────────────────────────────────────────────────
    doc = db.collection("chamados").document(chamado_id).get()
    if not doc.exists:
        return {"sucesso": False, "erro": "Chamado não encontrado"}

    dados = doc.to_dict() or {}
    chamado = Chamado.from_dict(dados, chamado_id)

    # ── verifica permissão (owner ou admin) ──────────────────────────────────
    if not (chamado.responsavel_id == usuario.id or usuario.is_admin_or_above):
        logger.warning(
            "escalonar_colega negado: usuário %s não é owner do chamado %s",
            usuario.id,
            chamado_id,
        )
        return {"sucesso": False, "erro": "Sem permissão para escalonar este chamado"}

    # ── destino ≠ owner atual ────────────────────────────────────────────────
    if supervisor_id == chamado.responsavel_id:
        return {
            "sucesso": False,
            "erro": "Destino igual ao responsável atual — selecione um colega diferente",
        }

    # ── valida colega na mesma área ──────────────────────────────────────────
    supervisores_area = Usuario.get_supervisores_por_area(chamado.area)
    colega = next((s for s in supervisores_area if s.id == supervisor_id), None)
    if not colega:
        return {
            "sucesso": False,
            "erro": "Supervisor destino não pertence à área do chamado",
        }

    # ── recalcula supervisor_ids_com_acesso ──────────────────────────────────
    novos_ids = calcular_supervisor_ids_com_acesso(
        chamado.area, supervisor_id, chamado.participantes
    )

    responsavel_anterior = chamado.responsavel_id

    # ── update atômico (área inalterada) ─────────────────────────────────────
    execute_with_retry(
        db.collection("chamados").document(chamado_id).update,
        {
            "responsavel_id": supervisor_id,
            "responsavel": colega.nome,
            "motivo_ultima_escalacao": motivo[:500],
            "supervisor_ids_com_acesso": novos_ids,
        },
        max_retries=3,
    )

    # ── histórico ────────────────────────────────────────────────────────────
    hist = Historico(
        chamado_id=chamado_id,
        usuario_id=usuario.id,
        usuario_nome=usuario.nome,
        acao="escalonamento_colega",
        campo_alterado="responsavel_id",
        valor_anterior=responsavel_anterior,
        valor_novo=supervisor_id,
        detalhe=f"Escalado para {colega.nome} — {motivo[:500]}",
    )
    hist.save()

    logger.info(
        "Chamado %s escalado de '%s' para '%s' por %s",
        chamado_id,
        responsavel_anterior,
        supervisor_id,
        usuario.id,
    )
    return {"sucesso": True, "dados": {"responsavel_id": supervisor_id}}


# ── Fase 4: incluir_participantes ─────────────────────────────────────────────


def incluir_participantes(
    chamado_id: str,
    participantes_novos: list,
    usuario,
) -> dict:
    """Adiciona colaboradores paralelos em participantes[].

    Validações:
    - Usuário é owner (responsavel_id) ou admin.
    - Lista não vazia.
    - Cada item: supervisor_id + area obrigatórios.
    - supervisor_id existe e pertence à área informada.
    - Não duplica supervisor_id já presente.
    - Owner não pode ser adicionado como participante.

    Returns:
        {"sucesso": True, "dados": {"participantes": [...], "adicionados": [...]}}
        ou {"sucesso": False, "erro": "..."}.
    """
    if not participantes_novos:
        return {"sucesso": False, "erro": "Lista de participantes não pode ser vazia"}

    doc = db.collection("chamados").document(chamado_id).get()
    if not doc.exists:
        return {"sucesso": False, "erro": "Chamado não encontrado"}

    dados = doc.to_dict() or {}
    chamado = Chamado.from_dict(dados, chamado_id)

    if not (chamado.responsavel_id == usuario.id or usuario.is_admin_or_above):
        logger.warning(
            "incluir_participantes negado: usuário %s não é owner do chamado %s",
            usuario.id,
            chamado_id,
        )
        return {"sucesso": False, "erro": "Sem permissão para incluir participantes neste chamado"}

    participantes_atuais = list(chamado.participantes or [])
    ids_existentes = {p["supervisor_id"] for p in participantes_atuais}
    adicionados = []

    for item in participantes_novos:
        sup_id = (item.get("supervisor_id") or "").strip()
        area = (item.get("area") or "").strip()

        if not sup_id:
            return {"sucesso": False, "erro": "supervisor_id é obrigatório em cada participante"}
        if not area:
            return {"sucesso": False, "erro": "area é obrigatória em cada participante"}

        if sup_id == chamado.responsavel_id:
            return {
                "sucesso": False,
                "erro": "Owner (responsável) não pode ser adicionado como participante",
            }

        supervisores_area = Usuario.get_supervisores_por_area(area)
        sup_obj = next((s for s in supervisores_area if s.id == sup_id), None)
        if not sup_obj:
            return {
                "sucesso": False,
                "erro": f"Supervisor {sup_id} não encontrado ou não pertence à área {area}",
            }

        if sup_id in ids_existentes:
            continue

        participantes_atuais.append(
            {
                "supervisor_id": sup_id,
                "area": area,
                "status": "pendente",
                "concluido_em": None,
            }
        )
        ids_existentes.add(sup_id)
        adicionados.append({"supervisor_id": sup_id, "area": area, "nome": sup_obj.nome})

    if not adicionados:
        return {
            "sucesso": False,
            "erro": "Nenhum participante novo para incluir — todos já são participantes do chamado",
        }

    novos_ids = calcular_supervisor_ids_com_acesso(
        chamado.area, chamado.responsavel_id, participantes_atuais
    )

    execute_with_retry(
        db.collection("chamados").document(chamado_id).update,
        {
            "participantes": participantes_atuais,
            "supervisor_ids_com_acesso": novos_ids,
        },
        max_retries=3,
    )

    nomes_adicionados = (
        ", ".join(f"{a['nome']} ({a['area']})" for a in adicionados) or "nenhum novo"
    )
    hist = Historico(
        chamado_id=chamado_id,
        usuario_id=usuario.id,
        usuario_nome=usuario.nome,
        acao="inclusao_participantes",
        campo_alterado="participantes",
        valor_anterior=str(len(chamado.participantes or [])),
        valor_novo=str(len(participantes_atuais)),
        detalhe=f"Participantes incluídos: {nomes_adicionados}",
    )
    hist.save()

    logger.info(
        "Chamado %s: %d participante(s) incluído(s) por %s",
        chamado_id,
        len(adicionados),
        usuario.id,
    )
    return {
        "sucesso": True,
        "dados": {
            "participantes": participantes_atuais,
            "adicionados": adicionados,
        },
    }


# ── Fase 4: concluir_minha_parte ─────────────────────────────────────────────


def concluir_minha_parte(chamado_id: str, usuario) -> dict:
    """Marca a parte do participante como concluída.

    Validações:
    - usuario.id está em participantes[*].supervisor_id com status != 'concluido'.

    Returns:
        {"sucesso": True, "dados": {"pode_concluir_global": bool}}
        ou {"sucesso": False, "erro": "..."}.
    """
    doc = db.collection("chamados").document(chamado_id).get()
    if not doc.exists:
        return {"sucesso": False, "erro": "Chamado não encontrado"}

    dados = doc.to_dict() or {}
    chamado = Chamado.from_dict(dados, chamado_id)

    participantes = list(chamado.participantes or [])
    idx = next(
        (i for i, p in enumerate(participantes) if p.get("supervisor_id") == usuario.id),
        None,
    )

    if idx is None:
        return {"sucesso": False, "erro": "Usuário não é participante deste chamado"}

    if participantes[idx].get("status") == "concluido":
        return {"sucesso": False, "erro": "Você já concluiu sua parte neste chamado"}

    agora = datetime.now(ZoneInfo(Config.SLA_TIMEZONE))
    participantes[idx] = {**participantes[idx], "status": "concluido", "concluido_em": agora}

    execute_with_retry(
        db.collection("chamados").document(chamado_id).update,
        {"participantes": participantes},
        max_retries=3,
    )

    hist = Historico(
        chamado_id=chamado_id,
        usuario_id=usuario.id,
        usuario_nome=usuario.nome,
        acao="conclusao_parte_participante",
        campo_alterado="participantes",
        valor_anterior="pendente",
        valor_novo="concluido",
        detalhe=f"Participante {usuario.nome} concluiu sua parte",
    )
    hist.save()

    chamado_atualizado = Chamado.from_dict({**dados, "participantes": participantes}, chamado_id)
    todos_ok = pode_concluir_global(chamado_atualizado)

    logger.info(
        "Chamado %s: participante %s concluiu sua parte (pode_concluir_global=%s)",
        chamado_id,
        usuario.id,
        todos_ok,
    )
    return {"sucesso": True, "dados": {"pode_concluir_global": todos_ok}}
