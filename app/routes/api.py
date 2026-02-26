"""Rotas de API (JSON) e service worker: status, notificações, push, paginação, disponibilidade."""
import os
import logging
from flask import request, redirect, url_for, send_from_directory, current_app, jsonify
from flask_login import login_required, current_user
from firebase_admin import firestore
from app.routes import main
from app.limiter import limiter
from app.database import db
from app.models import Chamado
from app.models_usuario import Usuario
from app.models_historico import Historico
from app.services.filters import aplicar_filtros_dashboard_com_paginacao
from app.services.notifications import notificar_solicitante_status
from app.services.notifications_inapp import listar_para_usuario, contar_nao_lidas, marcar_como_lida, marcar_todas_como_lidas
from app.services.webpush_service import salvar_inscricao
from app.services.assignment import atribuidor
from app.services.upload import salvar_anexo
from app.services.status_service import atualizar_status_chamado
from app.services.permissions import usuario_pode_ver_chamado
from app.services.analytics import obter_sla_para_exibicao
from app.firebase_retry import execute_with_retry

logger = logging.getLogger(__name__)

# Mensagem genérica em respostas 500 para não expor detalhes internos em produção
ERRO_INTERNO_MSG = "Erro interno. Tente novamente."


@main.route('/health', methods=['GET'])
def health():
    """Health check para load balancer e monitoramento. Retorna 200 quando a aplicação está no ar."""
    return jsonify({'status': 'ok'}), 200


@main.route('/api/atualizar-status', methods=['POST'])
@login_required
def atualizar_status_ajax():
    """Atualiza status do chamado via JSON. Requer CSRF; o frontend deve enviar o token no header X-CSRFToken (ex.: valor da meta tag csrf-token)."""
    try:
        dados = request.get_json()
        if not dados:
            return jsonify({'sucesso': False, 'erro': 'JSON inválido ou vazio'}), 400
        chamado_id = (dados.get('chamado_id') or '').strip()
        novo_status = (dados.get('novo_status') or '').strip()
        if not chamado_id:
            return jsonify({'sucesso': False, 'erro': 'chamado_id é obrigatório'}), 400
        if not novo_status:
            return jsonify({'sucesso': False, 'erro': 'novo_status é obrigatório'}), 400
        if novo_status not in ['Aberto', 'Em Atendimento', 'Concluído']:
            return jsonify({'sucesso': False, 'erro': f'Status inválido "{novo_status}"'}), 400

        resultado = atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status=novo_status,
            usuario_id=current_user.id,
            usuario_nome=current_user.nome,
        )
        if resultado['sucesso']:
            return jsonify({'sucesso': True, 'mensagem': resultado['mensagem'], 'novo_status': novo_status}), 200
        else:
            return jsonify({'sucesso': False, 'erro': resultado.get('erro', 'Erro desconhecido')}), 404 if resultado.get('erro') == 'Chamado não encontrado' else 500
    except Exception as e:
        logger.exception("Erro em atualizar_status_ajax: %s", e)
        return jsonify({'sucesso': False, 'erro': ERRO_INTERNO_MSG}), 500


@main.route('/api/editar-chamado', methods=['POST'])
@login_required
def api_editar_chamado():
    """Edita chamado de forma completa via FormData (incluindo arquivo, status, responsavel, descricao). Apenas supervisor/admin."""
    if current_user.perfil not in ('supervisor', 'admin'):
        return jsonify({'sucesso': False, 'erro': 'Acesso negado'}), 403

    try:
        chamado_id = request.form.get('chamado_id')
        novo_status = request.form.get('novo_status')
        nova_descricao = request.form.get('nova_descricao')
        novo_responsavel_id = request.form.get('novo_responsavel_id')
        arquivo_anexo = request.files.get('anexo')

        if not chamado_id:
            return jsonify({'sucesso': False, 'erro': 'ID do chamado é obrigatório'}), 400

        doc_chamado = db.collection('chamados').document(chamado_id).get()
        if not doc_chamado.exists:
            return jsonify({'sucesso': False, 'erro': 'Chamado não encontrado'}), 404

        data_chamado = doc_chamado.to_dict()
        
        # Validar permissão da área (Supervisor só edita chamados de sua área, a menos que seja admin)
        if current_user.perfil == 'supervisor':
            responsavel_atual_obj = Usuario.get_by_id(data_chamado.get('responsavel_id')) if data_chamado.get('responsavel_id') else None
            tem_area_comum = bool(set(responsavel_atual_obj.areas) & set(current_user.areas)) if responsavel_atual_obj else False
            if not (data_chamado.get('area') in current_user.areas or data_chamado.get('responsavel_id') == current_user.id or tem_area_comum):
                return jsonify({'sucesso': False, 'erro': 'Você só pode editar chamados da sua área'}), 403

        update_data = {}

        # Status (atualização via serviço centralizado — já faz o update no Firestore)
        if novo_status and novo_status in ['Aberto', 'Em Atendimento', 'Concluído'] and novo_status != data_chamado.get('status'):
            resultado_status = atualizar_status_chamado(
                chamado_id=chamado_id,
                novo_status=novo_status,
                usuario_id=current_user.id,
                usuario_nome=current_user.nome,
                data_chamado=data_chamado,
            )
            if not resultado_status['sucesso']:
                return jsonify({'sucesso': False, 'erro': resultado_status.get('erro', 'Erro ao atualizar status')}), 500

        # Responsável (reatribuição)
        novo_responsavel_nome = None
        if novo_responsavel_id and novo_responsavel_id != data_chamado.get('responsavel_id'):
            novo_resp_obj = Usuario.get_by_id(novo_responsavel_id)
            if novo_resp_obj:
                novo_responsavel_nome = novo_resp_obj.nome
                update_data['responsavel_id'] = novo_responsavel_id
                update_data['responsavel'] = novo_responsavel_nome
                # Chamado guarda uma única área; usa a primeira do responsável se houver várias
                update_data['area'] = (novo_resp_obj.areas[0] if getattr(novo_resp_obj, 'areas', None) else novo_resp_obj.area)

                Historico(
                    chamado_id=chamado_id,
                    usuario_id=current_user.id,
                    usuario_nome=current_user.nome,
                    acao='alteracao_dados',
                    campo_alterado='responsável',
                    valor_anterior=data_chamado.get('responsavel'),
                    valor_novo=novo_responsavel_nome
                ).save()

        # Descrição
        if nova_descricao and nova_descricao.strip() != data_chamado.get('descricao', '').strip():
            update_data['descricao'] = nova_descricao.strip()
            Historico(
                chamado_id=chamado_id,
                usuario_id=current_user.id,
                usuario_nome=current_user.nome,
                acao='alteracao_dados',
                campo_alterado='descrição',
                valor_anterior='(Texto anterior)',
                valor_novo='(Novo texto)'
            ).save()

        # Anexo (Adicionando múltiplos anexos)
        if arquivo_anexo and arquivo_anexo.filename:
            caminho_anexo = salvar_anexo(arquivo_anexo)
            if caminho_anexo:
                # Recarrega anexos existentes e adiciona o novo
                anexos_existentes = data_chamado.get('anexos', [])
                anexo_principal = data_chamado.get('anexo')
                
                # Garante que o anexo principal original também está na lista
                if anexo_principal and anexo_principal not in anexos_existentes:
                    anexos_existentes.insert(0, anexo_principal)
                
                anexos_existentes.append(caminho_anexo)
                update_data['anexos'] = anexos_existentes
                
                # Se ainda não tinha anexo principal, define este como tal
                if not anexo_principal:
                    update_data['anexo'] = caminho_anexo
                
                Historico(
                    chamado_id=chamado_id,
                    usuario_id=current_user.id,
                    usuario_nome=current_user.nome,
                    acao='alteracao_dados',
                    campo_alterado='novo anexo',
                    valor_anterior='-',
                    valor_novo=caminho_anexo
                ).save()

        if update_data:
            # Atualiza documento com retry automático
            execute_with_retry(
                db.collection('chamados').document(chamado_id).update,
                update_data,
                max_retries=3
            )
            return jsonify({'sucesso': True, 'mensagem': 'Chamado atualizado com sucesso', 'dados': update_data}), 200
        else:
            return jsonify({'sucesso': True, 'mensagem': 'Nenhuma alteração foi feita'}), 200

    except Exception as e:
        logger.exception("Erro em api_editar_chamado: %s", e)
        return jsonify({'sucesso': False, 'erro': ERRO_INTERNO_MSG}), 500

@main.route('/api/bulk-status', methods=['POST'])
@login_required
@limiter.limit("20 per minute")
def bulk_atualizar_status():
    """Atualiza status de múltiplos chamados em lote. Apenas supervisor/admin."""
    if current_user.perfil not in ('supervisor', 'admin'):
        return jsonify({'sucesso': False, 'erro': 'Acesso negado'}), 403
    try:
        dados = request.get_json()
        if not dados:
            return jsonify({'sucesso': False, 'erro': 'JSON inválido ou vazio'}), 400
        ids = dados.get('chamado_ids')
        if not isinstance(ids, list):
            return jsonify({'sucesso': False, 'erro': 'chamado_ids deve ser uma lista'}), 400
        novo_status = (dados.get('novo_status') or '').strip()
        if novo_status not in ('Aberto', 'Em Atendimento', 'Concluído'):
            return jsonify({'sucesso': False, 'erro': 'novo_status inválido'}), 400
        ids = [str(i).strip() for i in ids if i][:50]
        if not ids:
            return jsonify({'sucesso': False, 'erro': 'Nenhum chamado informado'}), 400

        atualizados = 0
        erros = []
        update_data = {'status': novo_status}
        if novo_status == 'Concluído':
            update_data['data_conclusao'] = firestore.SERVER_TIMESTAMP
        for chamado_id in ids:
            try:
                doc = db.collection('chamados').document(chamado_id).get()
                if not doc.exists:
                    erros.append({'id': chamado_id, 'erro': 'Não encontrado'})
                    continue
                data = doc.to_dict()
                if current_user.perfil == 'supervisor':
                    chamado_area = data.get('area')
                    if (chamado_area not in current_user.areas) and data.get('responsavel_id') != current_user.id:
                        erros.append({'id': chamado_id, 'erro': 'Sem permissão para este chamado'})
                        continue
                # Atualiza status com retry automático
                execute_with_retry(
                    db.collection('chamados').document(chamado_id).update,
                    update_data,
                    max_retries=3
                )
                if data.get('status') != novo_status:
                    Historico(
                        chamado_id=chamado_id,
                        usuario_id=current_user.id,
                        usuario_nome=current_user.nome,
                        acao='alteracao_status',
                        campo_alterado='status',
                        valor_anterior=data.get('status'),
                        valor_novo=novo_status,
                    ).save()
                atualizados += 1
            except Exception as e:
                logger.warning("Bulk status: falha em %s: %s", chamado_id, e)
                erros.append({'id': chamado_id, 'erro': str(e)})
        return jsonify({
            'sucesso': True,
            'atualizados': atualizados,
            'total_solicitados': len(ids),
            'erros': erros,
        }), 200
    except Exception as e:
        logger.exception("Erro em bulk_atualizar_status: %s", e)
        return jsonify({'sucesso': False, 'erro': ERRO_INTERNO_MSG}), 500


@main.route('/api/notificacoes', methods=['GET'])
@login_required
def api_notificacoes_listar():
    """Lista notificações do usuário (sino)."""
    try:
        apenas_nao_lidas = request.args.get('nao_lidas') == '1'
        lista = listar_para_usuario(current_user.id, limite=30, apenas_nao_lidas=apenas_nao_lidas)
        total_nao_lidas = contar_nao_lidas(current_user.id)
        return jsonify({'notificacoes': lista, 'total_nao_lidas': total_nao_lidas}), 200
    except Exception as e:
        logger.exception("Erro ao listar notificações: %s", e)
        return jsonify({'notificacoes': [], 'total_nao_lidas': 0}), 200


@main.route('/api/notificacoes/<notificacao_id>/ler', methods=['POST'])
@login_required
def api_notificacoes_marcar_lida(notificacao_id):
    """Marca notificação como lida."""
    try:
        ok = marcar_como_lida(notificacao_id, current_user.id)
        return jsonify({'sucesso': ok}), 200
    except Exception as e:
        logger.exception("Erro ao marcar notificação: %s", e)
        return jsonify({'sucesso': False}), 500


@main.route('/api/notificacoes/ler-todas', methods=['POST'])
@login_required
def api_notificacoes_ler_todas():
    """Marca todas as notificações do usuário como lidas."""
    try:
        qtd = marcar_todas_como_lidas(current_user.id)
        return jsonify({'sucesso': True, 'marcadas': qtd}), 200
    except Exception as e:
        logger.exception("Erro ao marcar todas notificações: %s", e)
        return jsonify({'sucesso': False}), 500


@main.route('/sw.js')
def service_worker_js():
    """Serve o service worker na raiz (scope do app)."""
    return send_from_directory(
        os.path.join(current_app.root_path, 'static'),
        'sw.js',
        mimetype='application/javascript'
    )


@main.route('/api/push-vapid-public')
@login_required
def api_push_vapid_public():
    """Retorna chave pública VAPID para Web Push."""
    key = current_app.config.get('VAPID_PUBLIC_KEY') or ''
    return jsonify({'vapid_public_key': key}), 200


@main.route('/api/push-subscribe', methods=['POST'])
@login_required
def api_push_subscribe():
    """Salva inscrição Web Push do navegador."""
    try:
        data = request.get_json() or {}
        subscription = data.get('subscription')
        if not subscription or not subscription.get('endpoint'):
            return jsonify({'sucesso': False, 'erro': 'subscription inválida'}), 400
        ok = salvar_inscricao(current_user.id, subscription)
        return jsonify({'sucesso': ok}), 200
    except Exception as e:
        logger.exception("Erro ao salvar inscrição push: %s", e)
        return jsonify({'sucesso': False}), 500


@main.route('/api/chamado/<chamado_id>', methods=['GET'])
@login_required
@limiter.limit("60 per minute")
def api_chamado_por_id(chamado_id: str):
    """Retorna um chamado por ID para atualização da linha na Gestão (após fechar aba de detalhes)."""
    try:
        doc = db.collection('chamados').document(chamado_id).get()
        if not doc or not doc.exists:
            return jsonify({'sucesso': False, 'erro': 'Chamado não encontrado'}), 404
        data = doc.to_dict()
        c = Chamado.from_dict(data, doc.id)
        if current_user.perfil == 'solicitante':
            if c.solicitante_id != current_user.id:
                return jsonify({'sucesso': False, 'erro': 'Acesso negado'}), 403
        else:
            if not usuario_pode_ver_chamado(current_user, c):
                return jsonify({'sucesso': False, 'erro': 'Acesso negado'}), 403
        c.sla_info = obter_sla_para_exibicao(c)
        return jsonify({
            'sucesso': True,
            'chamado': {
                'id': c.id,
                'numero_chamado': c.numero_chamado,
                'rl_codigo': c.rl_codigo or None,
                'categoria': c.categoria,
                'tipo_solicitacao': c.tipo_solicitacao,
                'gate': c.gate or '',
                'responsavel': c.responsavel or '',
                'descricao': c.descricao or '',
                'data_abertura': c.data_abertura_formatada(),
                'status': c.status or 'Aberto',
                'sla_info': c.sla_info,
            }
        }), 200
    except Exception as e:
        logger.exception("Erro ao buscar chamado %s: %s", chamado_id, e)
        return jsonify({'sucesso': False, 'erro': ERRO_INTERNO_MSG}), 500


@main.route('/api/chamados/paginar', methods=['GET'])
@login_required
@limiter.limit("60 per minute")
def api_chamados_paginar():
    """Paginação com cursor para chamados."""
    try:
        limite = request.args.get('limite', 50, type=int)
        cursor = request.args.get('cursor')
        if limite < 1 or limite > 100:
            limite = 50
        chamados_ref = db.collection('chamados')
        resultado = aplicar_filtros_dashboard_com_paginacao(
            chamados_ref, request.args, limite=limite, cursor=cursor
        )
        chamados_dict = []
        for doc in resultado['docs']:
            data = doc.to_dict()
            c = Chamado.from_dict(data, doc.id)
            chamados_dict.append({
                'id': doc.id,
                'numero': c.numero_chamado,
                'categoria': c.categoria,
                'rl_codigo': c.rl_codigo or '-',
                'tipo': c.tipo_solicitacao,
                'responsavel': c.responsavel,
                'status': c.status,
                'prioridade': c.prioridade,
                'descricao_resumida': c.descricao[:100] + '...' if len(c.descricao) > 100 else c.descricao,
                'data_abertura': c.data_abertura_formatada(),
                'data_conclusao': c.data_conclusao_formatada()
            })
        return jsonify({
            'sucesso': True,
            'chamados': chamados_dict,
            'paginacao': {
                'cursor_proximo': resultado['proximo_cursor'],
                'tem_proxima': resultado['tem_proxima'],
                'total_pagina': len(chamados_dict),
                'limite': limite
            }
        }), 200
    except Exception as e:
        logger.exception("Erro em api_chamados_paginar: %s", e)
        return jsonify({'sucesso': False, 'erro': ERRO_INTERNO_MSG}), 500


@main.route('/api/carregar-mais', methods=['POST'])
@login_required
@limiter.limit("60 per minute")
def carregar_mais():
    """Carregar mais chamados (infinite scroll)."""
    try:
        dados = request.get_json() or {}
        cursor = dados.get('cursor')
        limite = min(dados.get('limite', 20), 50)
        chamados_ref = db.collection('chamados')
        resultado = aplicar_filtros_dashboard_com_paginacao(
            chamados_ref, request.args, limite=limite, cursor=cursor
        )
        chamados_dict = []
        for doc in resultado['docs']:
            data = doc.to_dict()
            c = Chamado.from_dict(data, doc.id)
            chamados_dict.append({
                'id': doc.id,
                'numero': c.numero_chamado,
                'categoria': c.categoria,
                'status': c.status,
                'responsavel': c.responsavel,
                'data_abertura': c.data_abertura_formatada()
            })
        return jsonify({
            'sucesso': True,
            'chamados': chamados_dict,
            'cursor_proximo': resultado['proximo_cursor'],
            'tem_proxima': resultado['tem_proxima']
        }), 200
    except Exception as e:
        logger.exception("Erro em carregar_mais: %s", e)
        return jsonify({'sucesso': False, 'erro': ERRO_INTERNO_MSG}), 500


@main.route('/api/supervisores/disponibilidade', methods=['GET'])
@login_required
@limiter.limit("30 per minute")
def api_disponibilidade_supervisores():
    """Disponibilidade de supervisores por área."""
    try:
        area = request.args.get('area', 'Geral')
        disponibilidade = atribuidor.obter_disponibilidade(area)
        return jsonify({'sucesso': True, **disponibilidade}), 200
    except Exception as e:
        logger.exception("Erro ao obter disponibilidade: %s", e)
        return jsonify({'sucesso': False, 'erro': ERRO_INTERNO_MSG}), 500
