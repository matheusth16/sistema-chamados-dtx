"""Serviço para centralizar a lógica de edição de chamados (dashboard e API)."""
import logging
from flask import current_app
from app.database import db
from app.models import Chamado
from app.models_usuario import Usuario
from app.models_historico import Historico
from app.services.status_service import atualizar_status_chamado
from app.services.upload import salvar_anexo
from app.services.notifications import notificar_setores_adicionais_chamado
from app.firebase_retry import execute_with_retry

logger = logging.getLogger(__name__)

def processar_edicao_chamado(
    usuario_atual,
    chamado_id: str,
    novo_status: str,
    motivo_cancelamento: str,
    nova_descricao: str,
    novo_responsavel_id: str,
    novo_sla_str: str,
    arquivo_anexo,
    setores_adicionais_lista: list
) -> dict:
    """
    Processa a edição completa de um chamado, registrando histórico e notificações.
    Retorna: {'sucesso': bool, 'mensagem': str, 'erro': str, 'dados': dict}
    """
    if not chamado_id:
        return {'sucesso': False, 'erro': 'ID do chamado é obrigatório'}

    doc_chamado = db.collection('chamados').document(chamado_id).get()
    if not doc_chamado.exists:
        return {'sucesso': False, 'erro': 'Chamado não encontrado'}

    data_chamado = doc_chamado.to_dict()
    chamado_obj = Chamado.from_dict(data_chamado, chamado_id)

    # Validação de Permissão (exigida para supervisores)
    if usuario_atual.perfil == 'supervisor':
        from app.services.permissions import usuario_pode_ver_chamado
        if not usuario_pode_ver_chamado(usuario_atual, chamado_obj):
            return {'sucesso': False, 'erro': 'Sem permissão para este chamado ou fora da sua área'}

    update_data = {}
    mensagens = []

    try:
        import bleach
        # 1. Status
        if novo_status and novo_status in ('Aberto', 'Em Atendimento', 'Concluído', 'Cancelado') and novo_status != data_chamado.get('status'):
            if motivo_cancelamento:
                motivo_cancelamento = bleach.clean(motivo_cancelamento, tags=[], strip=True)
            if novo_status == 'Cancelado' and not motivo_cancelamento:
                return {'sucesso': False, 'erro': 'Motivo do cancelamento é obrigatório para alterar o status para Cancelado'}
            
            resultado_status = atualizar_status_chamado(
                chamado_id=chamado_id,
                novo_status=novo_status,
                usuario_id=usuario_atual.id,
                usuario_nome=usuario_atual.nome,
                data_chamado=data_chamado,
                motivo_cancelamento=motivo_cancelamento if novo_status == 'Cancelado' else None,
            )
            if not resultado_status.get('sucesso'):
                return {'sucesso': False, 'erro': resultado_status.get('erro', 'Erro ao atualizar status')}
            mensagens.append(resultado_status.get('mensagem', 'Status atualizado.'))

        # 2. Responsável
        if novo_responsavel_id and novo_responsavel_id != data_chamado.get('responsavel_id'):
            novo_resp = Usuario.get_by_id(novo_responsavel_id)
            if novo_resp:
                update_data['responsavel_id'] = novo_resp.id
                update_data['responsavel'] = novo_resp.nome
                update_data['area'] = (novo_resp.areas[0] if getattr(novo_resp, 'areas', None) else novo_resp.area or data_chamado.get('area'))
                
                Historico(
                    chamado_id=chamado_id,
                    usuario_id=usuario_atual.id,
                    usuario_nome=usuario_atual.nome,
                    acao='alteracao_dados',
                    campo_alterado='responsável',
                    valor_anterior=data_chamado.get('responsavel'),
                    valor_novo=novo_resp.nome
                ).save()

        # 3. Descrição
        if nova_descricao and nova_descricao.strip() != data_chamado.get('descricao', '').strip():
            nova_descricao = bleach.clean(nova_descricao.strip(), tags=[], strip=True)
            descricao_anterior = (data_chamado.get('descricao') or '').strip()
            update_data['descricao'] = nova_descricao
            max_len = 3000
            
            Historico(
                chamado_id=chamado_id,
                usuario_id=usuario_atual.id,
                usuario_nome=usuario_atual.nome,
                acao='alteracao_dados',
                campo_alterado='descrição',
                valor_anterior=(descricao_anterior[:max_len] + ('...' if len(descricao_anterior) > max_len else '')) or '(Vazio)',
                valor_novo=(nova_descricao[:max_len] + ('...' if len(nova_descricao) > max_len else ''))
            ).save()

        # 4. SLA 
        if novo_sla_str != '':
            sla_atual = data_chamado.get('sla_dias')
            if novo_sla_str == '0':
                novo_sla = None
            else:
                try:
                    novo_sla = int(novo_sla_str)
                    if novo_sla < 1 or novo_sla > 365:
                        raise ValueError()
                except ValueError:
                    return {'sucesso': False, 'erro': 'SLA inválido. Informe um número entre 1 e 365 dias, ou 0 para redefinir ao padrão.'}
            
            if novo_sla != sla_atual:
                from firebase_admin import firestore as fs_admin
                update_data['sla_dias'] = fs_admin.DELETE_FIELD if novo_sla is None else novo_sla
                Historico(
                    chamado_id=chamado_id,
                    usuario_id=usuario_atual.id,
                    usuario_nome=usuario_atual.nome,
                    acao='alteracao_dados',
                    campo_alterado='sla_dias',
                    valor_anterior=str(sla_atual) if sla_atual is not None else 'padrão',
                    valor_novo=str(novo_sla) if novo_sla is not None else 'padrão',
                ).save()

        # 5. Anexo
        if arquivo_anexo and arquivo_anexo.filename:
            try:
                caminho_anexo = salvar_anexo(arquivo_anexo)
            except ValueError as e:
                return {'sucesso': False, 'erro': str(e)}
            
            if caminho_anexo is None and current_app.config.get('ENV') == 'production':
                mensagens.append("Houve um problema ao salvar o arquivo em produção.")
            elif caminho_anexo:
                anexos_existentes = data_chamado.get('anexos', [])
                anexo_principal = data_chamado.get('anexo')
                
                if anexo_principal and anexo_principal not in anexos_existentes:
                    anexos_existentes.insert(0, anexo_principal)
                
                anexos_existentes.append(caminho_anexo)
                update_data['anexos'] = anexos_existentes
                
                if not anexo_principal:
                    update_data['anexo'] = caminho_anexo
                
                Historico(
                    chamado_id=chamado_id,
                    usuario_id=usuario_atual.id,
                    usuario_nome=usuario_atual.nome,
                    acao='alteracao_dados',
                    campo_alterado='novo anexo',
                    valor_anterior='-',
                    valor_novo=caminho_anexo,
                    detalhe=arquivo_anexo.filename
                ).save()

        # 6. Setores adicionais
        setores_atuais = data_chamado.get('setores_adicionais') or []
        if not isinstance(setores_atuais, list):
            setores_atuais = []
        
        setores_novos_lista = [str(s).strip() for s in setores_adicionais_lista if s and str(s).strip()]
        setores_novos_para_notificar = [s for s in setores_novos_lista if s not in setores_atuais]
        
        if setores_novos_lista != setores_atuais:
            update_data['setores_adicionais'] = setores_novos_lista
            if setores_novos_para_notificar:
                try:
                    notificar_setores_adicionais_chamado(
                        chamado_id=chamado_id,
                        numero_chamado=data_chamado.get('numero_chamado') or chamado_obj.numero_chamado,
                        setores_novos=setores_novos_para_notificar,
                        categoria=data_chamado.get('categoria') or chamado_obj.categoria,
                        tipo_solicitacao=data_chamado.get('tipo_solicitacao') or chamado_obj.tipo_solicitacao,
                        descricao_resumo=(data_chamado.get('descricao') or '')[:500],
                        solicitante_nome=data_chamado.get('solicitante_nome') or chamado_obj.solicitante_nome or '—',
                        quem_adicionou_nome=usuario_atual.nome,
                    )
                except Exception as e:
                    logger.exception("Erro ao notificar setores adicionais: %s", e)
                    mensagens.append("Setores adicionados, mas houve falha ao notificar.")
            
            Historico(
                chamado_id=chamado_id,
                usuario_id=usuario_atual.id,
                usuario_nome=usuario_atual.nome,
                acao='alteracao_dados',
                campo_alterado='setores adicionais',
                valor_anterior=', '.join(setores_atuais) if setores_atuais else '-',
                valor_novo=', '.join(setores_novos_lista) if setores_novos_lista else '-',
            ).save()

        # Efetivar as alterações de Dados
        if update_data:
            execute_with_retry(
                db.collection('chamados').document(chamado_id).update,
                update_data,
                max_retries=3
            )
            mensagens.insert(0, "Alterações salvas.")
            return {'sucesso': True, 'mensagem': " ".join(mensagens), 'dados': update_data}
        else:
            if not mensagens:
                return {'sucesso': True, 'mensagem': "Nenhuma alteração foi feita.", 'dados': {}}
            else:
                return {'sucesso': True, 'mensagem': " ".join(mensagens), 'dados': {}}
            
    except Exception as e:
        logger.exception("Erro processando edição do chamado %s: %s", chamado_id, e)
        return {'sucesso': False, 'erro': "Erro interno ao salvar as modificações."}
