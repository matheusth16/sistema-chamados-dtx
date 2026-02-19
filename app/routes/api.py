"""Rotas de API (JSON) e service worker: status, notificações, push, paginação, disponibilidade."""
import os
import logging
import traceback
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
from app.services.notifications_inapp import listar_para_usuario, contar_nao_lidas, marcar_como_lida
from app.services.webpush_service import salvar_inscricao
from app.services.assignment import atribuidor

logger = logging.getLogger(__name__)


@main.route('/api/atualizar-status', methods=['POST'])
@login_required
def atualizar_status_ajax():
    """Atualiza status do chamado via JSON. Isento de CSRF para fetch."""
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

        doc_anterior = db.collection('chamados').document(chamado_id).get()
        if not doc_anterior.exists:
            return jsonify({'sucesso': False, 'erro': 'Chamado não encontrado'}), 404
        status_anterior = doc_anterior.to_dict().get('status')
        update_data = {'status': novo_status}
        if novo_status == 'Concluído':
            update_data['data_conclusao'] = firestore.SERVER_TIMESTAMP
        db.collection('chamados').document(chamado_id).update(update_data)

        if status_anterior != novo_status:
            Historico(
                chamado_id=chamado_id,
                usuario_id=current_user.id,
                usuario_nome=current_user.nome,
                acao='alteracao_status',
                campo_alterado='status',
                valor_anterior=status_anterior,
                valor_novo=novo_status
            ).save()
            if novo_status in ('Em Atendimento', 'Concluído'):
                try:
                    data_anterior = doc_anterior.to_dict()
                    sid = data_anterior.get('solicitante_id')
                    sup = Usuario.get_by_id(sid) if sid else None
                    notificar_solicitante_status(
                        chamado_id=chamado_id,
                        numero_chamado=data_anterior.get('numero_chamado') or 'N/A',
                        novo_status=novo_status,
                        categoria=data_anterior.get('categoria') or 'Chamado',
                        solicitante_usuario=sup,
                    )
                except Exception as e:
                    logger.warning(f"Notificação ao solicitante não enviada: {e}")

        return jsonify({'sucesso': True, 'mensagem': f'Status alterado para {novo_status}', 'novo_status': novo_status}), 200
    except Exception as e:
        logger.exception(f"Erro em atualizar_status_ajax: {str(e)}")
        return jsonify({'sucesso': False, 'erro': str(e)}), 500


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
        logger.exception(f"Erro ao listar notificações: {e}")
        return jsonify({'notificacoes': [], 'total_nao_lidas': 0}), 200


@main.route('/api/notificacoes/<notificacao_id>/ler', methods=['POST'])
@login_required
def api_notificacoes_marcar_lida(notificacao_id):
    """Marca notificação como lida."""
    try:
        ok = marcar_como_lida(notificacao_id, current_user.id)
        return jsonify({'sucesso': ok}), 200
    except Exception as e:
        logger.exception(f"Erro ao marcar notificação: {e}")
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
        logger.exception(f"Erro ao salvar inscrição push: {e}")
        return jsonify({'sucesso': False}), 500


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
        logger.exception(f"Erro em api_chamados_paginar: {str(e)}")
        return jsonify({'sucesso': False, 'erro': str(e)}), 500


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
        logger.exception(f"Erro em carregar_mais: {str(e)}")
        return jsonify({'sucesso': False, 'erro': str(e)}), 500


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
        logger.exception(f"Erro ao obter disponibilidade: {str(e)}")
        return jsonify({'sucesso': False, 'erro': str(e)}), 500
