"""Rotas de criação e listagem de chamados (solicitante)."""
import logging
from datetime import datetime
from flask import render_template, request, redirect, url_for, Response, flash, current_app
from flask_login import current_user
from firebase_admin import firestore
from app.routes import main
from app.limiter import limiter
from app.decoradores import requer_solicitante
from app.database import db
from app.models import Chamado
from app.services.pagination import obter_total_por_contagem
from app.models_usuario import Usuario
from app.models_historico import Historico
from app.models_categorias import CategoriaSetor, CategoriaImpacto
from app.utils import gerar_numero_chamado
from app.utils_areas import setor_para_area
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
def index() -> Response:
    """GET: formulário de novo chamado. POST: processa e salva no Firestore."""
    if request.method != 'POST':
        setores = CategoriaSetor.get_all()
        impactos = CategoriaImpacto.get_all()

        # Contagem por agregação (count) — sem ler documentos
        status_counts = {'Aberto': 0, 'Em Atendimento': 0, 'Concluído': 0}
        try:
            for st in ('Aberto', 'Em Atendimento', 'Concluído'):
                q = db.collection('chamados').where(
                    'solicitante_id', '==', current_user.id
                ).where('status', '==', st)
                c = obter_total_por_contagem(q)
                status_counts[st] = c if c is not None else 0
        except Exception as e:
            logger.warning("Erro ao contar chamados do solicitante: %s", e)

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
    try:
        caminho_anexo = salvar_anexo(request.files.get('anexo'))
    except ValueError as e:
        flash(str(e), 'danger')
        setores = CategoriaSetor.get_all()
        impactos = CategoriaImpacto.get_all()
        return render_template('formulario.html', setores=setores, impactos=impactos)
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
        area_para_atribuicao = setor_para_area(tipo) if tipo else (area_solicitante or 'Geral')
        resultado_atribuicao = atribuidor.atribuir(
            area=area_para_atribuicao,
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

    # Área do chamado: normalizada para o valor usado no cadastro de usuários (filtro dashboard)
    area_chamado = setor_para_area(tipo) if tipo else (area_solicitante if area_solicitante else 'Geral')

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
                solicitante_email=getattr(current_user, 'email', None) or None,
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


def _eh_erro_indice_firestore(exc: Exception) -> bool:
    """Verifica se a exceção é de índice do Firestore (FAILED_PRECONDITION / index)."""
    msg = (getattr(exc, 'message', '') or str(exc) or '').lower()
    return 'failed_precondition' in msg or 'index' in msg or 'requires an index' in msg


def _meus_chamados_fallback_sem_indice(user_id: str, status_filtro: str, itens_por_pagina: int, pagina_atual: int):
    """
    Fallback quando a query com order_by falha por falta de índice:
    busca só por solicitante_id (não exige índice composto), ordena em memória e pagina.
    """
    q = db.collection('chamados').where('solicitante_id', '==', user_id).limit(500)
    docs = list(q.stream())
    # Filtra por status se pedido
    if status_filtro:
        docs = [d for d in docs if (d.to_dict() or {}).get('status') == status_filtro]
    # Ordena por data_abertura desc (None por último)
    def _data_key(d):
        data = (d.to_dict() or {}).get('data_abertura')
        if data is None or data == firestore.SERVER_TIMESTAMP:
            return None
        if hasattr(data, 'to_pydatetime'):
            return data.to_pydatetime()
        return data
    docs.sort(key=lambda d: (_data_key(d) is None, _data_key(d) or datetime.min), reverse=True)  # mais recentes primeiro
    # Contagens por status
    status_counts = {'Aberto': 0, 'Em Atendimento': 0, 'Concluído': 0}
    for d in docs:
        st = (d.to_dict() or {}).get('status', 'Aberto')
        if st in status_counts:
            status_counts[st] += 1
    total_chamados = len(docs)
    total_paginas = max(1, (total_chamados + itens_por_pagina - 1) // itens_por_pagina)
    pagina_atual = max(1, min(pagina_atual, total_paginas))
    inicio = (pagina_atual - 1) * itens_por_pagina
    fim = inicio + itens_por_pagina
    docs_pagina = docs[inicio:fim]
    chamados = []
    for doc in docs_pagina:
        try:
            data = doc.to_dict()
            if not data:
                continue
            c = Chamado.from_dict(data, doc.id)
            chamados.append(c)
        except Exception as doc_err:
            logger.warning("Chamado %s ignorado (dados inválidos): %s", doc.id, doc_err)
    cursor_next = docs_pagina[-1].id if len(docs_pagina) == itens_por_pagina and fim < total_chamados else None
    cursor_prev = docs_pagina[0].id if inicio > 0 else None
    return {
        'chamados': chamados,
        'pagina_atual': pagina_atual,
        'total_paginas': total_paginas,
        'total_chamados': total_chamados,
        'status_counts': status_counts,
        'cursor_next': cursor_next,
        'cursor_prev': cursor_prev,
    }


@main.route('/meus-chamados')
@requer_solicitante
def meus_chamados() -> Response:
    """GET: lista de chamados do solicitante com paginação por cursor (menos leituras no Firestore)."""
    try:
        if not getattr(current_user, 'id', None):
            logger.warning("meus_chamados: current_user.id ausente")
            flash('Erro ao carregar seus chamados. Sessão inválida.', 'danger')
            return redirect(url_for('main.index'))

        status_filtro = request.args.get('status', '')
        cursor = request.args.get('cursor', '').strip()
        cursor_prev = request.args.get('cursor_prev', '').strip() or None
        pagina_atual = request.args.get('pagina', 1, type=int)
        itens_por_pagina = 10

        # Query base: solicitante + opcional status, ordenado por data_abertura desc
        q = db.collection('chamados').where('solicitante_id', '==', current_user.id)
        if status_filtro:
            q = q.where('status', '==', status_filtro)
        q = q.order_by('data_abertura', direction=firestore.Query.DESCENDING)

        # Total e contagens por status via agregação (count) — sem ler todos os docs
        total_chamados = obter_total_por_contagem(q) or 0
        status_counts = {'Aberto': 0, 'Em Atendimento': 0, 'Concluído': 0}
        try:
            base_ref = db.collection('chamados').where('solicitante_id', '==', current_user.id)
            for st in ('Aberto', 'Em Atendimento', 'Concluído'):
                cq = base_ref.where('status', '==', st)
                c = obter_total_por_contagem(cq)
                status_counts[st] = c if c is not None else 0
        except Exception as e:
            logger.debug("Contagem por status em meus_chamados: %s", e)

        total_paginas = max(1, (total_chamados + itens_por_pagina - 1) // itens_por_pagina)
        if pagina_atual < 1:
            pagina_atual = 1
        if pagina_atual > total_paginas:
            pagina_atual = total_paginas

        # Página de documentos: limit + start_after(cursor)
        if cursor:
            try:
                cursor_doc = db.collection('chamados').document(cursor).get()
                if cursor_doc.exists:
                    q_page = q.start_after(cursor_doc).limit(itens_por_pagina + 1)
                else:
                    q_page = q.limit(itens_por_pagina + 1)
            except Exception as e:
                logger.debug("Cursor inválido em meus_chamados: %s", e)
                q_page = q.limit(itens_por_pagina + 1)
        else:
            q_page = q.limit(itens_por_pagina + 1)

        docs = list(q_page.stream())
        tem_proxima = len(docs) > itens_por_pagina
        if tem_proxima:
            docs = docs[:itens_por_pagina]
        cursor_next = docs[-1].id if docs and tem_proxima else None

        chamados = []
        for doc in docs:
            try:
                data = doc.to_dict()
                if not data:
                    continue
                c = Chamado.from_dict(data, doc.id)
                chamados.append(c)
            except Exception as doc_err:
                logger.warning("Chamado %s ignorado (dados inválidos): %s", doc.id, doc_err)

        return render_template(
            'meus_chamados.html',
            chamados=chamados,
            pagina_atual=pagina_atual,
            total_paginas=total_paginas,
            total_chamados=total_chamados,
            itens_por_pagina=itens_por_pagina,
            status_filtro=status_filtro,
            status_counts=status_counts,
            cursor_next=cursor_next,
            cursor_prev=cursor_prev,
        )
    except Exception as e:
        if _eh_erro_indice_firestore(e):
            logger.warning("Índice Firestore indisponível, usando fallback para meus_chamados: %s", e)
            try:
                resultado = _meus_chamados_fallback_sem_indice(
                    current_user.id, status_filtro, itens_por_pagina, pagina_atual
                )
                return render_template(
                    'meus_chamados.html',
                    itens_por_pagina=itens_por_pagina,
                    status_filtro=status_filtro,
                    **resultado,
                )
            except Exception as fallback_err:
                logger.exception("Fallback meus_chamados também falhou: %s", fallback_err)
                flash('Erro ao carregar seus chamados. Tente novamente.', 'danger')
                return redirect(url_for('main.index'))
        logger.exception("Erro ao buscar chamados do solicitante: %s", e)
        flash('Erro ao carregar seus chamados. Tente novamente ou verifique os logs.', 'danger')
        return redirect(url_for('main.index'))
