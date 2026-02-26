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
from app.models_categorias import CategoriaSetor, CategoriaImpacto
from app.utils import gerar_numero_chamado
from app.services.validators import validar_novo_chamado
from app.services.upload import salvar_anexo
from app.services.assignment import atribuidor
from app.services.notifications import notificar_aprovador_novo_chamado, notificar_solicitante_status
from app.services.notifications_inapp import criar_notificacao
from app.services.webpush_service import enviar_webpush_usuario
from app.firebase_retry import execute_with_retry

logger = logging.getLogger(__name__)


@main.route('/', methods=['GET', 'POST'])
@requer_solicitante
@limiter.limit("10 per hour")
def index() -> Response:
    """GET: formulário de novo chamado. POST: processa e salva no Firestore."""
    if request.method != 'POST':
        setores = CategoriaSetor.get_all()
        impactos = CategoriaImpacto.get_all()

        # Contagem de chamados do solicitante para o mini resumo
        status_counts = {'Aberto': 0, 'Em Atendimento': 0, 'Concluído': 0}
        try:
            docs = db.collection('chamados').where(
                'solicitante_id', '==', current_user.id
            ).stream()
            for doc in docs:
                st = doc.to_dict().get('status', 'Aberto')
                if st in status_counts:
                    status_counts[st] += 1
        except Exception as e:
            logger.warning(f"Erro ao contar chamados do solicitante: {e}")

        return render_template(
            'formulario.html',
            setores=setores,
            impactos=impactos,
            status_counts=status_counts,
        )

    lista_erros = validar_novo_chamado(request.form, request.files.get('anexo'))
    if lista_erros:
        for erro in lista_erros:
            flash(erro, 'danger')
        setores = CategoriaSetor.get_all()
        impactos = CategoriaImpacto.get_all()
        return render_template(
            'formulario.html',
            setores=setores,
            impactos=impactos,
        )

    categoria = request.form.get('categoria')
    rl_codigo = request.form.get('rl_codigo')
    tipo = request.form.get('tipo')
    descricao = request.form.get('descricao')
    impacto = request.form.get('impacto')
    gate = request.form.get('gate')
    caminho_anexo = salvar_anexo(request.files.get('anexo'))
    solicitante_nome = current_user.nome
    solicitante_id = current_user.id
    area_solicitante = current_user.area

    # Se o solicitante escolheu um responsável no formulário (lista de supervisores), usa esse
    responsavel_id_form = request.form.get('responsavel_id', '').strip()
    responsavel_nome_form = request.form.get('responsavel_nome', '').strip()
    if responsavel_id_form and responsavel_nome_form:
        usuario_escolhido = Usuario.get_by_id(responsavel_id_form)
        if usuario_escolhido and usuario_escolhido.perfil in ('supervisor', 'admin'):
            responsavel = responsavel_nome_form
            responsavel_id = responsavel_id_form
            motivo_atribuicao = f"Escolhido pelo solicitante: {responsavel}"
            logger.info(f"Responsável escolhido no formulário: {responsavel}")
        else:
            responsavel_id_form = None
            responsavel_nome_form = None

    if not responsavel_id_form or not responsavel_nome_form:
        resultado_atribuicao = atribuidor.atribuir(
            area=tipo or area_solicitante or 'Geral',
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

    # Área do chamado: setor solicitado (tipo) ou área do solicitante (uma única string)
    area_chamado = tipo or (area_solicitante if area_solicitante else 'Geral')

    try:
        # ✅ Gera o número APENAS aqui, pouco antes de salvar, garantindo que se algo falhar antes, o número não é consumido
        numero_chamado = gerar_numero_chamado()
        
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
            area=area_chamado,
            status='Aberto'
        )

        # Adiciona novo chamado com retry automático em caso de falha de conexão
        doc_ref = execute_with_retry(
            db.collection('chamados').add,
            novo_chamado.to_dict(),
            max_retries=3
        )
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


@main.route('/meus-chamados')
@requer_solicitante
@limiter.limit("30 per minute")
def meus_chamados() -> Response:
    """GET: lista de chamados criados pelo solicitante."""
    try:
        # Buscar todos os chamados do solicitante
        chamados_ref = db.collection('chamados').where('solicitante_id', '==', current_user.id)
        docs = chamados_ref.stream()
        
        chamados = []
        for doc in docs:
            data = doc.to_dict()
            c = Chamado.from_dict(data, doc.id)
            chamados.append(c)
        
        # Filtro por status (opcional)
        status_filtro = request.args.get('status', '')
        if status_filtro:
            chamados = [c for c in chamados if c.status == status_filtro]
        
        # Ordenar por data de abertura (mais recente primeiro)
        chamados_ordenados = sorted(chamados, key=lambda c: c.data_abertura or '', reverse=True)
        
        # Paginação
        pagina = request.args.get('pagina', 1, type=int)
        itens_por_pagina = 10
        total_chamados = len(chamados_ordenados)
        inicio = (pagina - 1) * itens_por_pagina
        fim = inicio + itens_por_pagina
        total_paginas = (total_chamados + itens_por_pagina - 1) // itens_por_pagina
        
        if pagina < 1 or pagina > total_paginas:
            pagina = 1
            chamados_pagina = chamados_ordenados[:itens_por_pagina]
        else:
            chamados_pagina = chamados_ordenados[inicio:fim]
        
        # Contar chamados por status
        status_counts = {
            'Aberto': len([c for c in chamados if c.status == 'Aberto']),
            'Em Atendimento': len([c for c in chamados if c.status == 'Em Atendimento']),
            'Concluído': len([c for c in chamados if c.status == 'Concluído'])
        }
        
        return render_template(
            'meus_chamados.html',
            chamados=chamados_pagina,
            pagina_atual=pagina,
            total_paginas=total_paginas,
            total_chamados=total_chamados,
            itens_por_pagina=itens_por_pagina,
            status_filtro=status_filtro,
            status_counts=status_counts
        )
    except Exception as e:
        logger.exception(f"Erro ao buscar chamados do solicitante: {str(e)}")
        flash('Erro ao carregar seus chamados.', 'danger')
        return redirect(url_for('main.index'))
