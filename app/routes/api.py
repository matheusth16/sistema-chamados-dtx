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
from app.services.notifications_inapp import listar_para_usuario, contar_nao_lidas, marcar_como_lida
from app.services.webpush_service import salvar_inscricao
from app.services.assignment import atribuidor

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
        logger.exception("Erro em atualizar_status_ajax: %s", e)
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
                    if data.get('area') != current_user.area and data.get('responsavel_id') != current_user.id:
                        erros.append({'id': chamado_id, 'erro': 'Sem permissão para este chamado'})
                        continue
                db.collection('chamados').document(chamado_id).update(update_data)
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
