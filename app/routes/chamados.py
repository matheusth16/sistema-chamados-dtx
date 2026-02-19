"""Rotas de criação e listagem de chamados (solicitante)."""
import logging
from flask import render_template, request, redirect, url_for, Response, flash, current_app
from flask_login import current_user
from app.routes import main
from app.limiter import limiter
from app.decoradores import requer_solicitante
from app.database import db
from app.models import Chamado
from app.models_usuario import Usuario
from app.models_historico import Historico
from app.utils import gerar_numero_chamado
from app.services.validators import validar_novo_chamado
from app.services.upload import salvar_anexo
from app.services.assignment import atribuidor
from app.services.notifications import notificar_aprovador_novo_chamado, notificar_solicitante_status
from app.services.notifications_inapp import criar_notificacao
from app.services.webpush_service import enviar_webpush_usuario

logger = logging.getLogger(__name__)


@main.route('/', methods=['GET', 'POST'])
@requer_solicitante
@limiter.limit("10 per hour")
def index() -> Response:
    """GET: formulário de novo chamado. POST: processa e salva no Firestore."""
    if request.method != 'POST':
        return render_template('formulario.html')

    lista_erros = validar_novo_chamado(request.form, request.files.get('anexo'))
    if lista_erros:
        for erro in lista_erros:
            flash(erro, 'danger')
        return render_template('formulario.html')

    categoria = request.form.get('categoria')
    rl_codigo = request.form.get('rl_codigo')
    tipo = request.form.get('tipo')
    descricao = request.form.get('descricao')
    impacto = request.form.get('impacto')
    gate = request.form.get('gate')
    caminho_anexo = salvar_anexo(request.files.get('anexo'))
    numero_chamado = gerar_numero_chamado()
    solicitante_nome = current_user.nome
    solicitante_id = current_user.id
    area_solicitante = current_user.area

    resultado_atribuicao = atribuidor.atribuir(
        area=area_solicitante or 'Geral',
        categoria=categoria,
        prioridade=0 if categoria == 'Projetos' else 1
    )

    if resultado_atribuicao['sucesso']:
        responsavel = resultado_atribuicao['supervisor']['nome']
        responsavel_id = resultado_atribuicao['supervisor']['id']
        motivo_atribuicao = f"Atribuído automaticamente a {responsavel}"
        logger.info(f"Atribuição automática bem-sucedida: {responsavel}")
    else:
        responsavel = solicitante_nome
        responsavel_id = solicitante_id
        motivo_atribuicao = f"Aguardando atribuição manual: {resultado_atribuicao['motivo']}"
        flash(f"⚠️ {resultado_atribuicao['motivo']}", 'warning')

    novo_chamado = Chamado(
        numero_chamado=numero_chamado,
        categoria=categoria,
        rl_codigo=rl_codigo if categoria == 'Projetos' else None,
        tipo_solicitacao=tipo,
        gate=gate,
        impacto=impacto,
        descricao=descricao,
        anexo=caminho_anexo,
        responsavel=responsavel,
        responsavel_id=responsavel_id,
        motivo_atribuicao=motivo_atribuicao,
        solicitante_id=solicitante_id,
        solicitante_nome=solicitante_nome,
        area=area_solicitante,
        status='Aberto'
    )

    try:
        doc_ref = db.collection('chamados').add(novo_chamado.to_dict())
        chamado_id = doc_ref[1].id
        Historico(chamado_id=chamado_id, usuario_id=solicitante_id, usuario_nome=solicitante_nome, acao='criacao').save()

        try:
            responsavel_usuario = Usuario.get_by_id(responsavel_id) if responsavel_id else None
            descricao_resumo = (descricao or '')[:500]
            notificar_aprovador_novo_chamado(
                chamado_id=chamado_id,
                numero_chamado=numero_chamado,
                categoria=categoria,
                tipo_solicitacao=tipo,
                descricao_resumo=descricao_resumo,
                area=area_solicitante or 'Geral',
                solicitante_nome=solicitante_nome,
                responsavel_usuario=responsavel_usuario,
            )
            if responsavel_id:
                criar_notificacao(
                    usuario_id=responsavel_id,
                    chamado_id=chamado_id,
                    numero_chamado=numero_chamado,
                    titulo=f"Novo chamado: {numero_chamado}",
                    mensagem=f"{categoria} · Solicitante: {solicitante_nome}",
                    tipo='novo_chamado',
                )
            if responsavel_id:
                base_url = current_app.config.get('APP_BASE_URL', '').rstrip('/')
                url_chamado = f"{base_url}/chamado/{chamado_id}/historico" if base_url else None
                try:
                    enviar_webpush_usuario(
                        responsavel_id,
                        titulo=f"Novo chamado: {numero_chamado}",
                        corpo=f"{categoria} · {solicitante_nome}",
                        url=url_chamado,
                    )
                except Exception as wp_e:
                    logger.debug(f"Web Push não enviado: {wp_e}")
        except Exception as e:
            logger.warning(f"Notificação ao aprovador não enviada: {e}")

        logger.info(f"Chamado criado: {numero_chamado} (ID: {chamado_id})")
        flash('Chamado criado com sucesso!', 'success')
        return redirect(url_for('main.index'))
    except Exception as e:
        logger.exception(f"Erro ao salvar chamado no Firestore: {str(e)}")
        flash('Não foi possível salvar o chamado. Tente novamente.', 'danger')
        return redirect(url_for('main.index'))
