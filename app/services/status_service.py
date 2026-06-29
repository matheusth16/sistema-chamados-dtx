"""
Serviço centralizado de atualização de status de chamados.

Consolida a lógica que estava repetida em 3 locais:
- admin.py (POST form)
- api.py atualizar_status_ajax()
- api.py api_editar_chamado()
"""

import logging
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from firebase_admin import firestore
from flask import current_app, session

from app.database import db
from app.firebase_retry import execute_with_retry
from app.i18n import get_translated_status, get_translation
from app.models_historico import Historico
from app.models_usuario import Usuario
from app.services.gamification_service import GamificationService
from app.services.notifications import (
    notificar_solicitante_confirmacao_pendente,
    notificar_solicitante_status,
)
from app.services.permissions import calcular_supervisor_ids_com_acesso
from config import Config

logger = logging.getLogger(__name__)


STATUS_VALIDOS = ("Aberto", "Em Atendimento", "Concluído", "Cancelado")

TRANSICOES_VALIDAS: dict[str, set[str]] = {
    "Aberto": {"Em Atendimento", "Cancelado", "Concluído"},
    "Em Atendimento": {"Concluído", "Cancelado", "Aberto"},
    "Concluído": {"Aberto", "Cancelado"},
    "Cancelado": {"Aberto", "Em Atendimento"},
}


def atualizar_status_chamado(
    chamado_id: str,
    novo_status: str,
    usuario_id: str,
    usuario_nome: str,
    data_chamado: dict = None,
    motivo_cancelamento: str = None,
    motivo_reabertura: str = None,
    usuario=None,
) -> dict:
    """Atualiza o status de um chamado, registra histórico e envia notificação.

    Para status 'Cancelado', motivo_cancelamento é obrigatório.

    Args:
        chamado_id: ID do chamado no Firestore
        novo_status: Novo status ('Aberto', 'Em Atendimento', 'Concluído', 'Cancelado')
        usuario_id: ID do usuário que está fazendo a alteração
        usuario_nome: Nome do usuário que está fazendo a alteração
        data_chamado: Dict do chamado (opcional, busca se não informado)
        motivo_cancelamento: Obrigatório quando novo_status == 'Cancelado'

    Returns:
        dict com:
            'sucesso': bool
            'mensagem': str
            'erro': str (se falhar)
    """
    try:
        if novo_status not in STATUS_VALIDOS:
            return {"sucesso": False, "erro": f"Status inválido: {novo_status}"}

        if novo_status == "Cancelado":
            motivo = (motivo_cancelamento or "").strip()
            if not motivo:
                return {"sucesso": False, "erro": "Motivo do cancelamento é obrigatório"}

        # Busca dados do chamado se não fornecidos
        if data_chamado is None:
            doc = db.collection("chamados").document(chamado_id).get()
            if not doc.exists:
                return {"sucesso": False, "erro": "Chamado não encontrado"}
            data_chamado = doc.to_dict()

        status_anterior = data_chamado.get("status")

        # Valida transição de status
        if (
            status_anterior
            and status_anterior in TRANSICOES_VALIDAS
            and novo_status != status_anterior
            and novo_status not in TRANSICOES_VALIDAS[status_anterior]
        ):
            return {
                "sucesso": False,
                "erro": f"Transição inválida: {status_anterior} → {novo_status}",
                "codigo": 400,
            }

        # Defesa em profundidade: valida congelamento mesmo em chamadas diretas ao service
        if status_anterior and novo_status != status_anterior:
            _u = usuario
            if _u is None:
                try:
                    _u = Usuario.get_by_id(usuario_id)
                except Exception as exc:
                    logger.debug(
                        "Validação de congelamento ignorada (usuário não carregável): %s", exc
                    )
            if _u is not None:
                from app.services.permission_validation import chamado_aceita_transicao_status

                _pode, _ = chamado_aceita_transicao_status(_u, data_chamado, novo_status)
                if not _pode:
                    return {
                        "sucesso": False,
                        "erro": "Chamado Concluído não permite esta transição de status",
                        "codigo": 403,
                    }

        # Fase 4: bloqueia conclusão global se houver participantes pendentes
        if novo_status == "Concluído":
            participantes = data_chamado.get("participantes") or []
            pendentes = [p for p in participantes if p.get("status") != "concluido"]
            if pendentes:
                return {
                    "sucesso": False,
                    "erro": "Existem participantes pendentes — aguarde 'Concluí minha parte' de todos",
                }

        # Monta dados de atualização
        update_data = {"status": novo_status}
        if novo_status == "Concluído":
            update_data["data_conclusao"] = firestore.SERVER_TIMESTAMP
            update_data["confirmacao_solicitante"] = "pendente"
            # Reseta flags de lembrete para que novo ciclo de 24 h/48 h seja enviado
            # (cobre reconclusão após reabertura manual por admin/supervisor)
            update_data["lembrete_confirmacao_1_enviado"] = False
            update_data["lembrete_confirmacao_2_enviado"] = False
        elif status_anterior == "Concluído":
            # Saindo de Concluído (reabertura) — limpa confirmação e reinicia flags de escalonamento
            update_data["confirmacao_solicitante"] = None
            update_data["escalacao_resolucao_nivel"] = 0
            update_data["alerta_supervisor_50_enviado"] = False
            update_data["alerta_supervisor_80_enviado"] = False
            update_data["lembrete_confirmacao_1_enviado"] = False
            update_data["lembrete_confirmacao_2_enviado"] = False
        elif novo_status == "Cancelado":
            update_data["motivo_cancelamento"] = (motivo_cancelamento or "").strip()
            update_data["data_cancelamento"] = firestore.SERVER_TIMESTAMP

        # Fase 2 — Claim ao 1º Em Atendimento
        if novo_status == "Em Atendimento" and status_anterior == "Aberto":
            responsavel_atual = data_chamado.get("responsavel_id")
            if not responsavel_atual:
                # Claim: atribui ao usuário logado
                update_data["responsavel_id"] = usuario_id
                update_data["responsavel"] = usuario_nome
                responsavel_atual = usuario_id
            update_data["data_em_atendimento"] = datetime.now(ZoneInfo(Config.SLA_TIMEZONE))
            # Recalcula IDs com acesso após claim
            area = data_chamado.get("area", "")
            participantes = data_chamado.get("participantes") or []
            update_data["supervisor_ids_com_acesso"] = calcular_supervisor_ids_com_acesso(
                area, responsavel_atual, participantes
            )
            # Fase 7 — Escada B: reset dos campos ao iniciar atendimento
            update_data["escalacao_resolucao_nivel"] = 0
            update_data["alerta_supervisor_50_enviado"] = False
            update_data["alerta_supervisor_80_enviado"] = False

        # Atualiza no Firestore com retry
        execute_with_retry(
            db.collection("chamados").document(chamado_id).update, update_data, max_retries=3
        )

        # Registra histórico se houve mudança
        if status_anterior != novo_status:
            Historico(
                chamado_id=chamado_id,
                usuario_id=usuario_id,
                usuario_nome=usuario_nome,
                acao="alteracao_status",
                campo_alterado="status",
                valor_anterior=status_anterior,
                valor_novo=novo_status,
            ).save()
            if novo_status == "Cancelado" and (motivo_cancelamento or "").strip():
                Historico(
                    chamado_id=chamado_id,
                    usuario_id=usuario_id,
                    usuario_nome=usuario_nome,
                    acao="alteracao_dados",
                    campo_alterado="motivo_cancelamento",
                    valor_anterior="-",
                    valor_novo=(motivo_cancelamento or "").strip()[:500],
                ).save()
            if novo_status == "Aberto" and status_anterior == "Concluído":
                motivo = (motivo_reabertura or "Reabertura administrativa").strip()
                Historico(
                    chamado_id=chamado_id,
                    usuario_id=usuario_id,
                    usuario_nome=usuario_nome,
                    acao="reabertura",
                    campo_alterado="status",
                    valor_anterior="Concluído",
                    valor_novo="Aberto",
                    detalhe=motivo[:500],
                ).save()

        # Envia notificação ao solicitante em background (não para Cancelado)
        if novo_status in ("Em Atendimento", "Concluído"):
            try:
                _app = current_app._get_current_object()
                _cid = chamado_id
                _data = data_chamado
                _status = novo_status

                def _notif():
                    with _app.app_context():
                        _notificar_solicitante(_cid, _data, _status)

                threading.Thread(target=_notif, daemon=True).start()
            except RuntimeError:
                # Fora de contexto Flask (testes) — notifica de forma síncrona
                _notificar_solicitante(chamado_id, data_chamado, novo_status)

        # Gamificação: apenas para Em Atendimento / Concluído (não para Cancelado)
        if status_anterior != novo_status:
            if novo_status == "Concluído":
                GamificationService.avaliar_resolucao_chamado(usuario_id, data_chamado)
            elif novo_status == "Em Atendimento":
                GamificationService.avaliar_atendimento_inicial(usuario_id)

        try:
            lang = session.get("language", "en")
        except RuntimeError:
            lang = "en"
        status_traduzido = get_translated_status(novo_status, lang)
        mensagem = get_translation("status_changed_to", lang, status=status_traduzido)
        return {"sucesso": True, "mensagem": mensagem, "novo_status": novo_status}

    except Exception as e:
        logger.exception("Erro ao atualizar status do chamado %s: %s", chamado_id, e)
        return {"sucesso": False, "erro": "Erro interno. Tente novamente.", "codigo": 500}


def _notificar_solicitante(chamado_id: str, data_chamado: dict, novo_status: str):
    """Notifica o solicitante sobre a mudança de status."""
    try:
        sid = data_chamado.get("solicitante_id")
        solicitante = Usuario.get_by_id(sid) if sid else None
        numero = data_chamado.get("numero_chamado") or "N/A"
        categoria = data_chamado.get("categoria") or "Chamado"

        # Concluído: e-mail específico pedindo confirmação; demais: notificação genérica
        if novo_status == "Concluído":
            notificar_solicitante_confirmacao_pendente(
                chamado_id=chamado_id,
                numero_chamado=numero,
                categoria=categoria,
                solicitante_usuario=solicitante,
            )
        else:
            notificar_solicitante_status(
                chamado_id=chamado_id,
                numero_chamado=numero,
                novo_status=novo_status,
                categoria=categoria,
                solicitante_usuario=solicitante,
            )

        if sid:
            from app.services.webpush_service import enviar_webpush_usuario

            base_url = current_app.config.get("APP_BASE_URL", "").rstrip("/")
            url_chamado = f"{base_url}/chamado/{chamado_id}/historico" if base_url else None
            enviar_webpush_usuario(
                sid,
                titulo=f"Chamado {numero}: {novo_status}",
                corpo=categoria,
                url=url_chamado,
            )

            # Notificação in-app (sino) — falha não interrompe e-mail/webpush
            try:
                from app.services.notifications_inapp import criar_notificacao_solicitante

                tipo_inapp = (
                    "status_concluido_confirmar"
                    if novo_status == "Concluído"
                    else "status_em_atendimento"
                )
                criar_notificacao_solicitante(
                    solicitante_id=sid,
                    chamado_id=chamado_id,
                    numero_chamado=numero,
                    categoria=categoria,
                    tipo=tipo_inapp,
                )
            except Exception as e_inapp:
                logger.warning("Notificação in-app ao solicitante não criada: %s", e_inapp)

    except Exception as e:
        logger.warning("Notificação ao solicitante não enviada: %s", e)
