"""Decisão atômica do solicitante sobre uma resolução concluída."""

from app.i18n import get_translation_session
from app.models import Chamado
from app.models_historico import Historico


def _t(key, **kwargs):
    return get_translation_session(key, **kwargs)


def processar_confirmacao_solicitante(
    chamado_id: str,
    *,
    acao: str,
    motivo: str,
    usuario,
    limite_reaberturas: int,
) -> dict:
    chamado = Chamado.get_by_id(chamado_id)
    if chamado is None:
        return {"sucesso": False, "erro": _t("ticket_not_found"), "codigo": 404}

    dados = chamado.to_dict()
    if dados.get("solicitante_id") != usuario.id:
        return {"sucesso": False, "erro": _t("access_denied_generic"), "codigo": 403}
    if dados.get("status") != "Concluído" or dados.get("confirmacao_solicitante") != "pendente":
        return {
            "sucesso": False,
            "erro": _t("ticket_not_awaiting_confirmation"),
            "codigo": 400,
        }

    if acao == "reabrir":
        contador = int(dados.get("reaberturas_solicitante_count") or 0)
        if contador >= limite_reaberturas:
            return {
                "sucesso": False,
                "erro": _t("reopen_limit_reached", limite=limite_reaberturas),
                "codigo": 403,
            }
        alteracoes = {
            "status": "Aberto",
            "confirmacao_solicitante": "reaberto",
            "data_conclusao": None,
            "escalacao_nivel": 0,
            "escalacao_proximo_tick_em": None,
            "escalacao_pre_aviso_nivel_enviado": None,
            "alerta_supervisor_50_enviado": False,
            "alerta_supervisor_80_enviado": False,
            "lembrete_confirmacao_1_enviado": False,
            "lembrete_confirmacao_2_enviado": False,
        }
        incrementos = {"reaberturas_solicitante_count": 1}
    else:
        alteracoes = {"confirmacao_solicitante": "confirmado"}
        incrementos = None

    venceu = chamado.atualizar_campos_cas(
        precondicoes={
            "status": "Concluído",
            "confirmacao_solicitante": "pendente",
            "solicitante_id": usuario.id,
        },
        incrementos=incrementos,
        **alteracoes,
    )
    if not venceu:
        return {
            "sucesso": False,
            "erro": _t("ticket_not_awaiting_confirmation"),
            "codigo": 409,
        }

    if acao == "confirmar":
        Historico(
            chamado_id=chamado_id,
            usuario_id=usuario.id,
            usuario_nome=usuario.nome,
            acao="confirmacao_resolucao",
            campo_alterado="confirmacao_solicitante",
            valor_anterior="pendente",
            valor_novo="confirmado",
        ).save()
    else:
        Historico(
            chamado_id=chamado_id,
            usuario_id=usuario.id,
            usuario_nome=usuario.nome,
            acao="reabertura",
            campo_alterado="status",
            valor_anterior="Concluído",
            valor_novo="Aberto",
            detalhe=motivo[:500],
        ).save()

    return {
        "sucesso": True,
        "dados": dados,
        "acao": acao,
        "motivo": motivo,
    }
