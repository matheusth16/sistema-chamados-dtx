"""Serviço para centralizar a lógica de edição de chamados (dashboard e API)."""

import logging
import threading

from flask import current_app, session

from app.i18n import get_translation
from app.models import Chamado
from app.models_historico import Historico
from app.models_usuario import Usuario
from app.services.notifications import notificar_setores_adicionais_chamado
from app.services.permissions import calcular_supervisor_ids_com_acesso
from app.services.status_service import atualizar_status_chamado
from app.services.upload import salvar_anexo

logger = logging.getLogger(__name__)


def processar_edicao_chamado(
    usuario_atual,
    chamado_id: str,
    novo_status: str,
    motivo_cancelamento: str,
    nova_descricao: str,
    novo_responsavel_id: str,
    novo_sla_str: str,
    arquivos_novos: list,
    setores_adicionais_lista: list,
) -> dict:
    """
    Processa a edição completa de um chamado, registrando histórico e notificações.
    Retorna: {'sucesso': bool, 'mensagem': str, 'erro': str, 'dados': dict}
    """
    try:
        _lang = session.get("language", "en")
    except RuntimeError:
        _lang = "en"

    def _t(key, **kwargs):
        return get_translation(key, _lang, **kwargs)

    if not chamado_id:
        return {"sucesso": False, "erro": _t("field_ticket_id_required")}

    from app.services.permissoes_edicao_chamado import usuario_pode_mutar_chamado

    pode_mutar, msg_erro = usuario_pode_mutar_chamado(usuario_atual)
    if not pode_mutar:
        return {"sucesso": False, "erro": _t(msg_erro), "codigo": 403}

    chamado_obj = Chamado.get_by_id(chamado_id)
    if chamado_obj is None:
        return {"sucesso": False, "erro": _t("ticket_not_found"), "codigo": 404}

    data_chamado = chamado_obj.to_dict()

    # Validação de Permissão de ESCRITA — mais restritiva que a de leitura usada pra
    # exibir o chamado. Leitura (usuario_pode_ver_chamado) libera dono/responsável/
    # fila-da-área/participante/observador; um supervisor que só enxerga o chamado
    # como observador (cc) não deve poder editá-lo, só acompanhar.
    from app.services.permissoes_edicao_chamado import supervisor_pode_alterar_chamado

    if not supervisor_pode_alterar_chamado(usuario_atual, chamado_obj.area, chamado_obj):
        return {
            "sucesso": False,
            "erro": _t("ticket_out_of_area_no_permission"),
            "codigo": 403,
        }

    update_data = {}
    mensagens = []
    historico_pendente = []  # acumula Historico para batch write único

    # Congelamento: Chamado Concluído é read-only para edição operacional.
    # Reabertura deve ser feita via /api/atualizar-status com chamado_aceita_transicao_status.
    from app.services.permissoes_edicao_chamado import chamado_aceita_edicao_operacional

    _pode_op, _msg_key = chamado_aceita_edicao_operacional(usuario_atual, chamado_obj)
    if not _pode_op:
        return {
            "sucesso": False,
            "erro": _t(_msg_key or "error_ticket_frozen_no_edit"),
            "codigo": 403,
        }

    try:
        import html

        import bleach

        # 1. Status
        if (
            novo_status
            and novo_status in ("Aberto", "Em Atendimento", "Concluído", "Cancelado")
            and novo_status != data_chamado.get("status")
        ):
            if motivo_cancelamento:
                # bleach.clean() já devolve texto HTML-escapado (ex.: ">" vira "&gt;") — sem
                # desfazer aqui, o autoescape do Jinja na renderização escapa de novo e o
                # usuário vê "&gt;" literal na tela em vez de ">".
                motivo_cancelamento = html.unescape(
                    bleach.clean(motivo_cancelamento, tags=[], strip=True)
                )
            if novo_status == "Cancelado" and not motivo_cancelamento:
                return {
                    "sucesso": False,
                    "erro": _t("cancellation_reason_required_for_status"),
                }

            resultado_status = atualizar_status_chamado(
                chamado_id=chamado_id,
                novo_status=novo_status,
                usuario_id=usuario_atual.id,
                usuario_nome=usuario_atual.nome,
                data_chamado=data_chamado,
                motivo_cancelamento=motivo_cancelamento if novo_status == "Cancelado" else None,
            )
            if not resultado_status.get("sucesso"):
                return {
                    "sucesso": False,
                    "erro": resultado_status.get("erro") or _t("error_updating_status_generic"),
                }
            mensagens.append(resultado_status.get("mensagem", _t("status_updated")))

        # 2. Responsável
        if novo_responsavel_id and novo_responsavel_id != data_chamado.get("responsavel_id"):
            novo_resp = Usuario.get_by_id(novo_responsavel_id)
            if novo_resp:
                update_data["responsavel_id"] = novo_resp.id
                update_data["responsavel"] = novo_resp.nome
                update_data["area"] = (
                    novo_resp.areas[0]
                    if getattr(novo_resp, "areas", None)
                    else novo_resp.area or data_chamado.get("area")
                )

                historico_pendente.append(
                    Historico(
                        chamado_id=chamado_id,
                        usuario_id=usuario_atual.id,
                        usuario_nome=usuario_atual.nome,
                        acao="alteracao_dados",
                        campo_alterado="responsável",
                        valor_anterior=data_chamado.get("responsavel"),
                        valor_novo=novo_resp.nome,
                    )
                )
                area_final = update_data.get("area") or data_chamado.get("area", "")
                participantes = data_chamado.get("participantes") or []
                update_data["supervisor_ids_com_acesso"] = calcular_supervisor_ids_com_acesso(
                    area_final, update_data.get("responsavel_id"), participantes
                )

        # 3. Descrição — texto original do solicitante. Só admin/admin_global pode
        # sobrescrever (válvula de escape administrativa); supervisor nunca altera
        # o que o solicitante escreveu, só acompanha e escala.
        if nova_descricao and nova_descricao.strip() != data_chamado.get("descricao", "").strip():
            if not getattr(usuario_atual, "is_admin_or_above", False):
                return {
                    "sucesso": False,
                    "erro": _t("cannot_edit_solicitante_description"),
                    "codigo": 403,
                }
            nova_descricao = html.unescape(
                bleach.clean(nova_descricao.strip(), tags=[], strip=True)
            )[:3000]
            descricao_anterior = (data_chamado.get("descricao") or "").strip()
            update_data["descricao"] = nova_descricao
            max_len = 3000

            historico_pendente.append(
                Historico(
                    chamado_id=chamado_id,
                    usuario_id=usuario_atual.id,
                    usuario_nome=usuario_atual.nome,
                    acao="alteracao_dados",
                    campo_alterado="descrição",
                    valor_anterior=(
                        descricao_anterior[:max_len]
                        + ("..." if len(descricao_anterior) > max_len else "")
                    )
                    or "(Vazio)",
                    valor_novo=(
                        nova_descricao[:max_len] + ("..." if len(nova_descricao) > max_len else "")
                    ),
                )
            )

        # 4. SLA
        if novo_sla_str != "":
            sla_atual = data_chamado.get("sla_dias")
            if novo_sla_str == "0":
                novo_sla = None
            else:
                try:
                    novo_sla = int(novo_sla_str)
                    if novo_sla < 1 or novo_sla > 365:
                        raise ValueError()
                except ValueError:
                    return {
                        "sucesso": False,
                        "erro": _t("sla_invalid_range"),
                    }

            if novo_sla != sla_atual:
                update_data["sla_dias"] = novo_sla
                historico_pendente.append(
                    Historico(
                        chamado_id=chamado_id,
                        usuario_id=usuario_atual.id,
                        usuario_nome=usuario_atual.nome,
                        acao="alteracao_dados",
                        campo_alterado="sla_dias",
                        valor_anterior=str(sla_atual) if sla_atual is not None else "padrão",
                        valor_novo=str(novo_sla) if novo_sla is not None else "padrão",
                    )
                )

        # 5. Anexos (suporta múltiplos arquivos)
        arquivos_validos = [a for a in (arquivos_novos or []) if getattr(a, "filename", "")]
        if arquivos_validos:
            anexos_existentes = list(data_chamado.get("anexos") or [])
            anexo_principal = data_chamado.get("anexo")
            if anexo_principal and anexo_principal not in anexos_existentes:
                anexos_existentes.insert(0, anexo_principal)

            for arq in arquivos_validos:
                try:
                    caminho_anexo = salvar_anexo(arq)
                except ValueError as e:
                    return {"sucesso": False, "erro": str(e)}

                if caminho_anexo is None and current_app.config.get("ENV") == "production":
                    mensagens.append(_t("file_save_error_production"))
                    continue

                if caminho_anexo:
                    anexos_existentes.append(caminho_anexo)
                    historico_pendente.append(
                        Historico(
                            chamado_id=chamado_id,
                            usuario_id=usuario_atual.id,
                            usuario_nome=usuario_atual.nome,
                            acao="alteracao_dados",
                            campo_alterado="novo anexo",
                            valor_anterior="-",
                            valor_novo=caminho_anexo,
                            detalhe=arq.filename,
                        )
                    )

            update_data["anexos"] = anexos_existentes
            if not anexo_principal and anexos_existentes:
                update_data["anexo"] = anexos_existentes[0]

        # 6. Setores adicionais
        setores_atuais = data_chamado.get("setores_adicionais") or []
        if not isinstance(setores_atuais, list):
            setores_atuais = []

        setores_novos_lista = [
            str(s).strip() for s in setores_adicionais_lista if s and str(s).strip()
        ]
        setores_novos_para_notificar = [s for s in setores_novos_lista if s not in setores_atuais]

        if setores_novos_lista != setores_atuais:
            update_data["setores_adicionais"] = setores_novos_lista

            if setores_novos_para_notificar:
                _app = current_app._get_current_object()
                _kwargs = {
                    "chamado_id": chamado_id,
                    "numero_chamado": data_chamado.get("numero_chamado")
                    or chamado_obj.numero_chamado,
                    "setores_novos": setores_novos_para_notificar,
                    "categoria": data_chamado.get("categoria") or chamado_obj.categoria,
                    "tipo_solicitacao": data_chamado.get("tipo_solicitacao")
                    or chamado_obj.tipo_solicitacao,
                    "descricao_resumo": (data_chamado.get("descricao") or "")[:500],
                    "solicitante_nome": data_chamado.get("solicitante_nome")
                    or chamado_obj.solicitante_nome
                    or "—",
                    "quem_adicionou_nome": usuario_atual.nome,
                }

                def _notificar_setores():
                    with _app.app_context():
                        try:
                            notificar_setores_adicionais_chamado(**_kwargs)
                        except Exception as e:
                            logger.exception("Erro ao notificar setores adicionais: %s", e)

                threading.Thread(target=_notificar_setores, daemon=True).start()

            historico_pendente.append(
                Historico(
                    chamado_id=chamado_id,
                    usuario_id=usuario_atual.id,
                    usuario_nome=usuario_atual.nome,
                    acao="alteracao_dados",
                    campo_alterado="setores adicionais",
                    valor_anterior=", ".join(setores_atuais) if setores_atuais else "-",
                    valor_novo=", ".join(setores_novos_lista) if setores_novos_lista else "-",
                )
            )

        # Persiste histórico em lote único (N writes → 1 round-trip)
        if historico_pendente:
            Historico.salvar_lote(historico_pendente)

        # Efetivar as alterações de Dados
        if update_data:
            if not chamado_obj.atualizar_campos(**update_data):
                return {"sucesso": False, "erro": _t("internal_error_saving_changes")}
            mensagens.insert(0, _t("changes_saved"))
            return {"sucesso": True, "mensagem": " ".join(mensagens), "dados": update_data}
        else:
            if not mensagens:
                return {"sucesso": True, "mensagem": _t("no_changes_made"), "dados": {}}
            else:
                return {"sucesso": True, "mensagem": " ".join(mensagens), "dados": {}}

    except Exception as e:
        logger.exception("Erro processando edição do chamado %s: %s", chamado_id, e)
        return {"sucesso": False, "erro": _t("internal_error_saving_changes")}


def responder_chamado_supervisor(chamado_id: str, mensagem: str, usuario) -> dict:
    """Resposta em texto livre do responsável (supervisor/admin) ao solicitante —
    via inversa de responder_chamado_solicitante (solicitante_edicao_service.py),
    que só cobre o solicitante respondendo ao responsável. Mesma permissão de
    escrita usada em processar_edicao_chamado (área + não congelado).

    Bloqueio em 'Cancelado' alinhado com o lado solicitante
    (solicitante_edicao_service._STATUS_PERMITIDOS_RESPOSTA): sem isso, o
    responsável podia mandar mensagem num chamado cancelado sem o solicitante
    ter como responder de volta — achado em auditoria, 2026-08-12."""
    try:
        _lang = session.get("language", "en")
    except RuntimeError:
        _lang = "en"

    def _t(key, **kwargs):
        return get_translation(key, _lang, **kwargs)

    if not chamado_id:
        return {"sucesso": False, "erro": _t("field_ticket_id_required")}

    chamado_obj = Chamado.get_by_id(chamado_id)
    if chamado_obj is None:
        return {"sucesso": False, "erro": _t("ticket_not_found"), "codigo": 404}

    from app.services.permissoes_edicao_chamado import (
        chamado_aceita_edicao_operacional,
        supervisor_pode_alterar_chamado,
    )

    if not supervisor_pode_alterar_chamado(usuario, chamado_obj.area, chamado_obj):
        return {
            "sucesso": False,
            "erro": _t("ticket_out_of_area_no_permission"),
            "codigo": 403,
        }

    if chamado_obj.status == "Cancelado":
        return {
            "sucesso": False,
            "erro": _t("cannot_reply_status", status=chamado_obj.status),
            "codigo": 403,
        }

    pode_op, msg_key = chamado_aceita_edicao_operacional(usuario, chamado_obj)
    if not pode_op:
        return {
            "sucesso": False,
            "erro": _t(msg_key or "error_ticket_frozen_no_edit"),
            "codigo": 403,
        }

    mensagem = (mensagem or "").strip()
    if len(mensagem) < 2:
        return {
            "sucesso": False,
            "erro": _t("reply_message_required", min_chars=2),
            "codigo": 400,
        }

    data_chamado = chamado_obj.to_dict()

    try:
        Historico(
            chamado_id=chamado_id,
            usuario_id=usuario.id,
            usuario_nome=usuario.nome,
            acao="resposta_responsavel",
            campo_alterado="mensagem",
            valor_anterior=None,
            valor_novo=mensagem,
        ).save()

        _notificar_resposta_supervisor(
            chamado_id=chamado_id,
            dados=data_chamado,
            usuario=usuario,
            mensagem=mensagem,
        )

        return {"sucesso": True}

    except Exception as exc:
        logger.exception(
            "Erro ao registrar resposta do responsável no chamado %s: %s", chamado_id, exc
        )
        return {"sucesso": False, "erro": _t("internal_error_saving_reply"), "codigo": 500}


def _notificar_resposta_supervisor(chamado_id: str, dados: dict, usuario, mensagem: str) -> None:
    """Dispara notificação de resposta do responsável em thread background."""
    app = current_app._get_current_object()  # noqa: SLF001
    usuario_nome = usuario.nome  # captura antes da thread — ver _notificar_resposta_solicitante

    def _run():
        with app.app_context():
            try:
                from app.services.chamado_notificacao_service import (
                    notificar_resposta_supervisor_chamado,
                )

                notificar_resposta_supervisor_chamado(
                    chamado_id=chamado_id,
                    numero_chamado=dados.get("numero_chamado") or "N/A",
                    categoria=dados.get("categoria") or "Chamado",
                    respondente_nome=usuario_nome,
                    mensagem=mensagem,
                    dados_chamado=dados,
                )
            except Exception as exc:
                logger.warning("Notificação de resposta do responsável não enviada: %s", exc)

    threading.Thread(target=_run, daemon=True).start()
