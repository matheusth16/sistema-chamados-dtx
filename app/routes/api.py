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
from app.services.notifications import notificar_solicitante_status, notificar_setores_adicionais_chamado
from app.services.notifications_inapp import listar_para_usuario, contar_nao_lidas, marcar_como_lida, marcar_todas_como_lidas
from app.services.webpush_service import salvar_inscricao
from app.services.assignment import atribuidor
from app.utils_areas import setor_para_area
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
        if novo_status not in ['Aberto', 'Em Atendimento', 'Concluído', 'Cancelado']:
            return jsonify({'sucesso': False, 'erro': f'Status inválido "{novo_status}"'}), 400
        motivo_cancelamento = (dados.get('motivo_cancelamento') or '').strip()
        if novo_status == 'Cancelado' and not motivo_cancelamento:
            return jsonify({'sucesso': False, 'erro': 'Motivo do cancelamento é obrigatório'}), 400

        doc_chamado = db.collection('chamados').document(chamado_id).get()
        if not doc_chamado.exists:
            return jsonify({'sucesso': False, 'erro': 'Chamado não encontrado'}), 404
        
        chamado_obj = Chamado.from_dict(doc_chamado.to_dict(), chamado_id)
        
        if current_user.perfil == 'solicitante':
            if chamado_obj.solicitante_id != current_user.id:
                return jsonify({'sucesso': False, 'erro': 'Acesso negado: Você só pode atualizar seus próprios chamados'}), 403
            if novo_status != 'Cancelado':
                return jsonify({'sucesso': False, 'erro': 'Acesso negado: Solicitantes só podem Cancelar chamados'}), 403
        elif current_user.perfil == 'supervisor':
            from app.services.permissions import usuario_pode_ver_chamado
            if not usuario_pode_ver_chamado(current_user, chamado_obj):
                return jsonify({'sucesso': False, 'erro': 'Acesso negado: Sem permissão ou fora da sua área'}), 403

        resultado = atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status=novo_status,
            usuario_id=current_user.id,
            usuario_nome=current_user.nome,
            motivo_cancelamento=motivo_cancelamento if novo_status == 'Cancelado' else None,
            data_chamado=doc_chamado.to_dict()
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
        motivo_cancelamento = (request.form.get('motivo_cancelamento') or '').strip()
        if not motivo_cancelamento and request.get_json(silent=True):
            motivo_cancelamento = (request.get_json() or {}).get('motivo_cancelamento') or ''
            motivo_cancelamento = str(motivo_cancelamento).strip()
        nova_descricao = request.form.get('nova_descricao')
        novo_responsavel_id = request.form.get('novo_responsavel_id')
        arquivo_anexo = request.files.get('anexo')

        if not chamado_id:
            return jsonify({'sucesso': False, 'erro': 'ID do chamado é obrigatório'}), 400

        from app.services.edicao_chamado_service import processar_edicao_chamado
        
        setores_adicionais_form = request.form.getlist('setores_adicionais')
        if not setores_adicionais_form and request.get_json(silent=True):
            setores_adicionais_form = (request.get_json(silent=True) or {}).get('setores_adicionais') or []
            
        resultado = processar_edicao_chamado(
            usuario_atual=current_user,
            chamado_id=chamado_id,
            novo_status=novo_status,
            motivo_cancelamento=motivo_cancelamento,
            nova_descricao=nova_descricao,
            novo_responsavel_id=novo_responsavel_id,
            novo_sla_str=(request.form.get('sla_dias') or '').strip(),
            arquivo_anexo=arquivo_anexo,
            setores_adicionais_lista=setores_adicionais_form
        )
        
        if resultado.get('sucesso'):
            return jsonify({'sucesso': True, 'mensagem': resultado.get('mensagem'), 'dados': resultado.get('dados', {})}), 200
        else:
            http_code = resultado.get('codigo', 400)
            return jsonify({'sucesso': False, 'erro': resultado.get('erro')}), http_code

    except Exception as e:
        logger.exception("Erro em api_editar_chamado: %s", e)
        return jsonify({'sucesso': False, 'erro': ERRO_INTERNO_MSG}), 500

@main.route('/api/bulk-status', methods=['POST'])
@login_required
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


@main.route('/api/notificacoes/contar', methods=['GET'])
@login_required
def api_notificacoes_contar():
    """Retorna apenas o total de notificações não lidas (sem transferir os documentos)."""
    try:
        total = contar_nao_lidas(current_user.id)
        return jsonify({'total_nao_lidas': total}), 200
    except Exception as e:
        logger.exception("Erro ao contar notificações: %s", e)
        return jsonify({'total_nao_lidas': 0}), 200


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
        count = marcar_todas_como_lidas(current_user.id)
        return jsonify({'sucesso': True, 'atualizadas': count}), 200
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
def api_chamado_por_id(chamado_id: str):
    """Retorna um chamado por ID (JSON). Usado pelo dashboard para atualizar a linha após fechar o modal/aba de detalhes."""
    try:
        doc_chamado = db.collection('chamados').document(chamado_id).get()
        if not doc_chamado.exists:
            return jsonify({'sucesso': False, 'erro': 'Chamado não encontrado'}), 404
        chamado = Chamado.from_dict(doc_chamado.to_dict(), chamado_id)
        if current_user.perfil == 'solicitante':
            if chamado.solicitante_id != current_user.id:
                return jsonify({'sucesso': False, 'erro': 'Sem permissão'}), 403
        else:
            if not usuario_pode_ver_chamado(current_user, chamado):
                return jsonify({'sucesso': False, 'erro': 'Sem permissão'}), 403
        sla_info = obter_sla_para_exibicao(chamado)
        chamado_dict = {
            'id': chamado_id,
            'numero_chamado': chamado.numero_chamado,
            'rl_codigo': chamado.rl_codigo,
            'categoria': chamado.categoria,
            'tipo_solicitacao': chamado.tipo_solicitacao,
            'gate': chamado.gate,
            'responsavel': chamado.responsavel,
            'descricao': chamado.descricao,
            'data_abertura': chamado.data_abertura_formatada(),
            'status': chamado.status,
            'sla_info': sla_info,
        }
        return jsonify({'sucesso': True, 'chamado': chamado_dict}), 200
    except Exception as e:
        logger.exception("Erro ao buscar chamado %s: %s", chamado_id, e)
        return jsonify({'sucesso': False, 'erro': ERRO_INTERNO_MSG}), 500


@main.route('/api/chamados/paginar', methods=['GET'])
@login_required
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


@main.route('/api/onboarding/avancar', methods=['POST'])
@login_required
def api_onboarding_avancar():
    """Salva o passo atual do tour de onboarding."""
    try:
        dados = request.get_json() or {}
        passo = dados.get('passo')
        if passo is None or not isinstance(passo, int) or passo < 0:
            return jsonify({'sucesso': False, 'erro': 'passo inválido'}), 400
        from app.services.onboarding_service import avancar_passo
        ok = avancar_passo(current_user.id, passo)
        return jsonify({'sucesso': ok}), 200
    except Exception as e:
        logger.exception("Erro em api_onboarding_avancar: %s", e)
        return jsonify({'sucesso': False, 'erro': ERRO_INTERNO_MSG}), 500


@main.route('/api/onboarding/concluir', methods=['POST'])
@login_required
def api_onboarding_concluir():
    """Marca o onboarding como concluído."""
    try:
        from app.services.onboarding_service import concluir_onboarding
        ok = concluir_onboarding(current_user.id)
        return jsonify({'sucesso': ok}), 200
    except Exception as e:
        logger.exception("Erro em api_onboarding_concluir: %s", e)
        return jsonify({'sucesso': False, 'erro': ERRO_INTERNO_MSG}), 500


@main.route('/api/onboarding/pular', methods=['POST'])
@login_required
def api_onboarding_pular():
    """Pula o tour e marca onboarding como concluído."""
    try:
        from app.services.onboarding_service import concluir_onboarding
        ok = concluir_onboarding(current_user.id)
        return jsonify({'sucesso': ok}), 200
    except Exception as e:
        logger.exception("Erro em api_onboarding_pular: %s", e)
        return jsonify({'sucesso': False, 'erro': ERRO_INTERNO_MSG}), 500


@main.route('/api/supervisores/lista', methods=['GET'])
@login_required
def api_lista_supervisores():
    """Lista simples de supervisores por área para o formulário (rápida, sem contar carga)."""
    area = request.args.get('area', '').strip() or 'Geral'
    try:
        area_resolvida = setor_para_area(area) or area
        supervisores = Usuario.get_supervisores_por_area(area_resolvida)
        dados = [
            {
                'id': u.id,
                'nome': u.nome,
                'email': u.email,
            }
            for u in supervisores
        ]
        return jsonify({
            'sucesso': True,
            'area': area_resolvida,
            'supervisores': dados,
        }), 200
    except Exception as e:
        logger.exception("Erro ao listar supervisores: %s", e)
        return jsonify({
            'sucesso': False,
            'area': area,
            'supervisores': [],
            'erro': ERRO_INTERNO_MSG,
        }), 200
