import os
import logging
import traceback
from flask import Blueprint, render_template, request, redirect, url_for, send_file, current_app, flash, Response, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from config import Config
from app.database import db
from app.models import Chamado
from app.models_usuario import Usuario
from app.models_historico import Historico
from app.services.validators import validar_novo_chamado
from app.services.filters import aplicar_filtros_dashboard, aplicar_filtros_dashboard_com_paginacao
from app.services.pagination import PaginadorFirestore, OptimizadorQuery
from app.services.upload import salvar_anexo
from datetime import datetime
from firebase_admin import firestore
import pandas as pd
import io
from typing import List, Optional, Any, Tuple, Dict

# Logger estruturado
logger = logging.getLogger(__name__)

# Rate Limiter para rotas sensíveis (será injetado em __init__.py)
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)


def _formatar_data_para_excel(val: Any) -> str:
    """Converte data (datetime, Firestore Timestamp ou str) para string no formato do Excel."""
    if val is None:
        return '-'
    if isinstance(val, str):
        return val
    if hasattr(val, 'strftime'):
        return val.strftime('%d/%m/%Y %H:%M')
    # Firestore Timestamp (google.cloud.firestore_v1)
    if hasattr(val, 'to_pydatetime'):
        return val.to_pydatetime().strftime('%d/%m/%Y %H:%M')
    if hasattr(val, 'timestamp'):
        return datetime.fromtimestamp(val.timestamp()).strftime('%d/%m/%Y %H:%M')
    return '-'


def _extrair_numero_chamado(numero_str: Optional[str]) -> int:
    """Extrai número de 'CHM-XXXX' para ordenação numérica"""
    if not numero_str:
        return float('inf')
    try:
        return int(numero_str.replace('CHM-', ''))
    except (ValueError, AttributeError):
        return float('inf')


def _gerar_numero_chamado() -> str:
    """Gera o próximo número de chamado sequencial no formato CHM-XXXX
    
    Usa transação atômica com documento contador para evitar duplicatas
    e escalabilidade com grande volume de chamados.
    """
    try:
        contador_ref = db.collection('_sistema').document('contador_chamados')
        
        @firestore.transactional
        def atualizar_contador(transaction):
            """Incrementa contador de forma atômica"""
            doc = transaction.get(contador_ref)
            
            if doc.exists:
                proximo_numero = doc.get('proximo_numero') + 1
            else:
                # Primeira vez: inicializa com 1
                proximo_numero = 1
            
            transaction.update(contador_ref, {'proximo_numero': proximo_numero})
            return proximo_numero
        
        transaction = db.transaction()
        novo_numero = atualizar_contador(transaction)
        return f'CHM-{novo_numero:04d}'
    except Exception as e:
        current_app.logger.exception('Erro ao gerar número de chamado via transação')
        # Fallback: usa timestamp como número
        timestamp_num = int(datetime.now().timestamp()) % 10000
        return f'CHM-{timestamp_num:04d}'


# Cria um "agrupamento" de rotas chamado 'main'
main = Blueprint('main', __name__)


# --- ROTA 0: LOGIN/LOGOUT ---
@main.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")  # Máximo 5 tentativas de login por minuto por IP
def login() -> Response:
    """Rota de autenticação de usuários
    
    GET: Retorna formulário de login
    POST: Valida credenciais e cria sessão
    """
    # Se já está logado, redireciona para admin
    if current_user.is_authenticated:
        logger.info(f"Usuário {current_user.email} já autenticado, redirecionando para admin")
        return redirect(url_for('main.admin'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        senha = request.form.get('senha', '')
        
        logger.debug(f"Tentativa de login com email: {email}")
        
        if not email or not senha:
            logger.warning(f"Tentativa de login com dados incompletos: email={bool(email)}, senha={bool(senha)}")
            flash('Email e senha são obrigatórios', 'danger')
            return redirect(url_for('main.login'))
        
        # Busca usuário no Firestore
        usuario = Usuario.get_by_email(email)
        
        if usuario and usuario.check_password(senha):
            login_user(usuario, remember=True)
            logger.info(f"Login bem-sucedido: {usuario.email} ({usuario.nome})")
            flash(f'Bem-vindo, {usuario.nome}!', 'success')
            return redirect(url_for('main.admin'))
        else:
            logger.warning(f"Falha de autenticação: email {email} ou senha incorretos")
            flash('Email ou senha incorretos', 'danger')
            return redirect(url_for('main.login'))
    
    return render_template('login.html')


@main.route('/logout')
@login_required
def logout() -> Response:
    """Finaliza a sessão do usuário autenticado"""
    email = current_user.email
    logout_user()
    logger.info(f"Logout: {email}")
    flash('Você foi desconectado com sucesso!', 'info')
    return redirect(url_for('main.login'))


# --- ROTA 1: O FORMULÁRIO (Home) ---
@main.route('/', methods=['GET', 'POST'])
@limiter.limit("10 per hour")  # Máximo 10 chamados por hora por IP
def index() -> Response:
    """Rota para criação de novo chamado
    
    GET: Retorna formulário de criação
    POST: Processa novo chamado com validações e salva no Firestore
    """
    if request.method == 'POST':
        # 1. BLINDAGEM DE DADOS
        lista_erros = validar_novo_chamado(request.form, request.files.get('anexo'))
        if lista_erros:
            logger.warning(f"Validação falhou: {lista_erros}")
            for erro in lista_erros:
                flash(erro, 'danger')
            return render_template('formulario.html')

        # 2. Captura os dados
        categoria = request.form.get('categoria')
        rl_codigo = request.form.get('rl_codigo')
        tipo = request.form.get('tipo')
        descricao = request.form.get('descricao')
        impacto = request.form.get('impacto')
        gate = request.form.get('gate')
        
        # 3. UPLOAD DE ANEXO (serviço centralizado em app/services/upload.py)
        caminho_anexo = salvar_anexo(request.files.get('anexo'))

        # 4. Gera o número do chamado
        numero_chamado = _gerar_numero_chamado()

        # 5. Pega o usuário autenticado, ou 'Sistema' se não houver
        responsavel = current_user.nome if current_user.is_authenticated else 'Sistema'
        usuario_id = current_user.id if current_user.is_authenticated else 'sistema'

        # 6. Salva no Firestore (prioridade é definida no modelo conforme categoria)
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
            status='Aberto'
        )

        try:
            doc_ref = db.collection('chamados').add(novo_chamado.to_dict())
            chamado_id = doc_ref[1].id
            
            # Registra a criação no histórico
            historico = Historico(
                chamado_id=chamado_id,
                usuario_id=usuario_id,
                usuario_nome=responsavel,
                acao='criacao'
            )
            historico.save()
            
            logger.info(f"Chamado criado: {numero_chamado} (ID: {chamado_id}, Categoria: {categoria}, Responsável: {responsavel})")
            flash('Chamado criado com sucesso!', 'success')
            return redirect(url_for('main.index'))
        except Exception as e:
            logger.exception(f"Erro ao salvar chamado no Firestore: {str(e)}")
            flash('Não foi possível salvar o chamado. Tente novamente.', 'danger')
            return redirect(url_for('main.index'))

    return render_template('formulario.html')


# --- ROTA 2: O PAINEL DO GESTOR (Admin) ---
@main.route('/admin', methods=['GET', 'POST'])
@login_required
@limiter.limit("30 per minute")  # Máximo 30 ações por minuto
def admin() -> Response:
    """Rota do painel administrativo
    
    GET: Retorna dashboard com chamados paginados e filtrados
    POST: Processa alteração de status de chamado
    """
    # --- AÇÃO: Alterar status ---
    if request.method == 'POST':
        chamado_id = request.form.get('chamado_id')
        novo_status = request.form.get('novo_status')
        
        logger.debug(f"Tentativa de alterar status: chamado_id={chamado_id}, novo_status={novo_status}, usuário={current_user.email}")
        
        try:
            # Busca o chamado anterior para registrar alteração
            doc_anterior = db.collection('chamados').document(chamado_id).get()
            status_anterior = doc_anterior.to_dict().get('status') if doc_anterior.exists else None
            
            chamado_ref = db.collection('chamados').document(chamado_id)
            update_data = {'status': novo_status}
            
            if novo_status == 'Concluído':
                update_data['data_conclusao'] = firestore.SERVER_TIMESTAMP
            
            chamado_ref.update(update_data)
            
            # Registra a alteração no histórico
            if status_anterior != novo_status:
                historico = Historico(
                    chamado_id=chamado_id,
                    usuario_id=current_user.id,
                    usuario_nome=current_user.nome,
                    acao='alteracao_status',
                    campo_alterado='status',
                    valor_anterior=status_anterior,
                    valor_novo=novo_status
                )
                historico.save()
            
            logger.info(f"Status alterado: chamado_id={chamado_id}, {status_anterior} → {novo_status}, usuário={current_user.email}")
            flash(f'Status alterado para {novo_status}', 'success')
            return redirect(url_for('main.admin', **request.args))
        except Exception as e:
            logger.exception(f"Erro ao atualizar chamado {chamado_id}: {str(e)}")
            flash(f'Erro ao atualizar: {str(e)}', 'danger')
            return redirect(url_for('main.admin', **request.args))

    # --- LEITURA: Buscar e paginar ---
    # --- 1. PREPARA A QUERY BASE ---
    chamados_ref = db.collection('chamados')
    
    # --- 2. APLICA OS FILTROS INTELIGENTES ---
    docs = aplicar_filtros_dashboard(chamados_ref, request.args)
    
    # --- 3. CONVERTE DOCUMENTOS EM OBJETOS CHAMADO ---
    chamados = []
    for doc in docs:
        data = doc.to_dict()
        chamado = Chamado.from_dict(data, doc.id)
        chamados.append(chamado)
    
    # --- 4. ORDENAÇÃO ---
    def _chave_ordenacao(c):
        concluido = c.status == 'Concluído'
        num_id = _extrair_numero_chamado(c.numero_chamado)
        if concluido:
            return (True, 0, num_id)
        prioridade_cat = 0 if c.categoria == 'Projetos' else 1
        return (False, prioridade_cat, num_id)

    chamados_ordenados = sorted(chamados, key=_chave_ordenacao)

    # --- 5. PAGINAÇÃO (otimizada com constante de config) ---
    pagina = request.args.get('pagina', 1, type=int)
    itens_por_pagina = Config.ITENS_POR_PAGINA
    total_chamados = len(chamados_ordenados)
    
    # Calcula o índice de início e fim
    inicio = (pagina - 1) * itens_por_pagina
    fim = inicio + itens_por_pagina
    
    chamados_pagina = chamados_ordenados[inicio:fim]
    
    # Calcula total de páginas
    total_paginas = (total_chamados + itens_por_pagina - 1) // itens_por_pagina
    
    # Sanitiza o número de página
    if pagina < 1 or pagina > total_paginas:
        pagina = 1
        chamados_pagina = chamados_ordenados[:itens_por_pagina]

    return render_template('dashboard.html', 
                         chamados=chamados_pagina,
                         pagina_atual=pagina,
                         total_paginas=total_paginas,
                         total_chamados=total_chamados,
                         itens_por_pagina=itens_por_pagina)


# --- ROTA 3: VISUALIZAR HISTÓRICO DE UM CHAMADO ---
@main.route('/chamado/<chamado_id>/historico')
@login_required
def visualizar_historico(chamado_id: str) -> Response:
    """Retorna histórico de alterações de um chamado
    
    Args:
        chamado_id: ID do documento no Firestore
        
    Returns:
        HTML com histórico ou redirecionamento em caso de erro
    """
    try:
        logger.debug(f"Buscando histórico: chamado_id={chamado_id}, usuário={current_user.email}")
        
        # Busca o chamado
        doc_chamado = db.collection('chamados').document(chamado_id).get()
        if not doc_chamado.exists:
            logger.warning(f"Chamado não encontrado: {chamado_id}")
            flash('Chamado não encontrado', 'danger')
            return redirect(url_for('main.admin'))
        
        chamado_data = doc_chamado.to_dict()
        chamado = Chamado.from_dict(chamado_data, chamado_id)
        
        # Busca o histórico
        historico = Historico.get_by_chamado_id(chamado_id)
        
        logger.info(f"Histórico consultado: {chamado_id} ({len(historico) if historico else 0} registros)")
        return render_template('historico.html', chamado=chamado, historico=historico)
    except Exception as e:
        logger.exception(f"Erro ao buscar histórico de {chamado_id}: {str(e)}")
        flash('Erro ao buscar histórico', 'danger')
        return redirect(url_for('main.admin'))


# --- ROTA 3.5: ATUALIZAR STATUS VIA AJAX (OTIMIZADO) ---
@main.route('/api/atualizar-status', methods=['POST'])
@login_required
def atualizar_status_ajax():
    """
    OTIMIZAÇÃO 4: Atualizar status SEM recarregar a página
    
    Problema anterior:
    - Atualizava no Firestore
    - Redirecionava (recarregava toda a página)
    - Recarregava TODOS os chamados do Firestore
    
    Nova abordagem:
    - Atualiza no Firestore (1 operação)
    - Retorna JSON (não recarrega)
    - Frontend atualiza apenas a linha alterada
    - Economiza: ~10 leituras de documentos por ação
    
    Recebe: JSON com chamado_id e novo_status
    Retorna: JSON com sucesso/erro
    """
    try:
        # ========== RECEBER E VALIDAR DADOS ==========
        dados = request.get_json()
        logger.debug(f"🔍 DEBUG - Dados recebidos brutos: {dados}")
        logger.debug(f"🔍 DEBUG - Content-Type: {request.content_type}")
        
        if not dados:
            logger.error('❌ Dados JSON vazios ou inválidos')
            return jsonify({'sucesso': False, 'erro': 'JSON inválido ou vazio'}), 400
        
        chamado_id = (dados.get('chamado_id') or '').strip()
        novo_status = (dados.get('novo_status') or '').strip()
        
        logger.debug(f"🔍 DEBUG - Valores extraídos: chamado_id='{chamado_id}' | novo_status='{novo_status}'")
        
        # Validação detalhada
        if not chamado_id:
            logger.warning(f'❌ chamado_id vazio. Dados completos: {dados}')
            return jsonify({'sucesso': False, 'erro': 'chamado_id é obrigatório'}), 400
        
        if not novo_status:
            logger.warning(f'❌ novo_status vazio. Dados completos: {dados}')
            return jsonify({'sucesso': False, 'erro': 'novo_status é obrigatório'}), 400
        
        # Valida o status
        status_validos = ['Aberto', 'Em Atendimento', 'Concluído']
        if novo_status not in status_validos:
            logger.warning(f'❌ Status inválido: "{novo_status}". Válidos: {status_validos}')
            return jsonify({'sucesso': False, 'erro': f'Status inválido "{novo_status}". Use um de: {", ".join(status_validos)}'}), 400
        
        logger.debug(f"✅ Validação OK: {chamado_id} → {novo_status}, usuário={current_user.email}")
        
        # ========== ATUALIZAR DOCUMENTO ==========
        doc_anterior = db.collection('chamados').document(chamado_id).get()
        if not doc_anterior.exists:
            logger.warning(f'❌ Chamado não encontrado: {chamado_id}')
            return jsonify({'sucesso': False, 'erro': 'Chamado não encontrado'}), 404
        
        status_anterior = doc_anterior.to_dict().get('status')
        
        # Atualiza no Firestore
        chamado_ref = db.collection('chamados').document(chamado_id)
        update_data = {'status': novo_status}
        
        if novo_status == 'Concluído':
            update_data['data_conclusao'] = firestore.SERVER_TIMESTAMP
        
        chamado_ref.update(update_data)
        logger.debug(f"✅ Firestore atualizado: {chamado_id}")
        
        # Registra no histórico
        if status_anterior != novo_status:
            historico = Historico(
                chamado_id=chamado_id,
                usuario_id=current_user.id,
                usuario_nome=current_user.nome,
                acao='alteracao_status',
                campo_alterado='status',
                valor_anterior=status_anterior,
                valor_novo=novo_status
            )
            historico.save()
            logger.debug(f"✅ Histórico registrado: {status_anterior} → {novo_status}")
        
        logger.info(f"✅ SUCCESS: Status alterado: {chamado_id}, {status_anterior} → {novo_status}, usuário={current_user.email}")
        
        return jsonify({
            'sucesso': True,
            'mensagem': f'Status alterado para {novo_status}',
            'novo_status': novo_status
        }), 200
    
    except Exception as e:
        logger.exception(f"❌ ERROR em atualizar_status_ajax: {str(e)}")
        logger.error(f"Stack trace: {traceback.format_exc()}")
        return jsonify({'sucesso': False, 'erro': f'Erro no servidor: {str(e)}'}), 500


# --- ROTA 4: EXPORTAR PARA EXCEL ---
@main.route('/exportar')
@login_required
@limiter.limit("5 per hour")  # Máximo 5 exportações por hora
def exportar() -> Response:
    """Exporta chamados filtrados para arquivo Excel
    
    Returns:
        Arquivo Excel (.xlsx) com os chamados
    """
    try:
        logger.debug(f"Iniciando exportação de chamados: filtros={dict(request.args)}, usuário={current_user.email}")
        
        # Busca todos os chamados com filtros aplicados
        chamados_ref = db.collection('chamados')
        docs = aplicar_filtros_dashboard(chamados_ref, request.args)
        
        dados: List[Dict[str, Any]] = []
        for doc in docs:
            c_data = doc.to_dict()
            c = Chamado.from_dict(c_data, doc.id)
            
            dados.append({
                'Chamado': c.numero_chamado,
                'Categoria': c.categoria,
                'RL': c.rl_codigo or '-',
                'Tipo': c.tipo_solicitacao,
                'Gate': c.gate or '-',
                'Responsável': c.responsavel,
                'Status': c.status,
                'Anexo': c.anexo or '-',
                'Abertura': _formatar_data_para_excel(c.data_abertura),
                'Conclusão': _formatar_data_para_excel(c.data_conclusao),
                'Descrição': c.descricao
            })
        
        df = pd.DataFrame(dados)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Chamados')
        
        output.seek(0)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        logger.info(f"Exportação concluída: {len(dados)} chamados exportados, usuário={current_user.email}")
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'relatorio_chamados_{timestamp}.xlsx'
        )
    except Exception as e:
        logger.exception(f"Erro ao exportar chamados: {str(e)}")
        flash('Erro ao exportar dados. Tente novamente.', 'danger')
        return redirect(url_for('main.admin'))


# --- ROTA 5: API OTIMIZADA DE PAGINAÇÃO ---
@main.route('/api/chamados/paginar', methods=['GET'])
@login_required
@limiter.limit("60 per minute")  # API pode ter mais requisições
def api_chamados_paginar():
    """
    OTIMIZAÇÃO: API de paginação com cursor
    
    Endpoints anterior era problema porque:
    - Carregava TODOS os documentos
    - Depois paginava em memória
    
    Novo endpoint:
    - Busca apenas limite + 1 documentos
    - Usa cursor para saber por onde começar
    - Muito mais eficiente em grandes volumes
    
    Query params:
    - cursor: ID do último documento da página anterior
    - limite: Quantos documentos buscar (padrão 50)
    - status, categoria, gate, search: Filtros
    
    Returns:
        {
            'sucesso': True,
            'chamados': [...],
            'paginacao': {
                'cursor_proximo': 'id123',
                'tem_proxima': True,
                'total_pagina': 50,
                'limite': 50
            }
        }
    """
    try:
        # Parâmetros
        limite = request.args.get('limite', 50, type=int)
        cursor = request.args.get('cursor')  # ID do último doc da página anterior
        
        # Validação
        if limite < 1 or limite > 100:
            limite = 50  # Limite máximo: 100
        
        logger.debug(f"API de paginação: limite={limite}, cursor={cursor}, usuário={current_user.email}")
        
        # Busca com paginação por cursor
        chamados_ref = db.collection('chamados')
        resultado = aplicar_filtros_dashboard_com_paginacao(
            chamados_ref, 
            request.args, 
            limite=limite,
            cursor=cursor
        )
        
        # Converte para dicts
        chamados_dict = []
        for doc in resultado['docs']:
            data = doc.to_dict()
            chamado = Chamado.from_dict(data, doc.id)
            chamados_dict.append({
                'id': doc.id,
                'numero': chamado.numero_chamado,
                'categoria': chamado.categoria,
                'rl_codigo': chamado.rl_codigo or '-',
                'tipo': chamado.tipo_solicitacao,
                'responsavel': chamado.responsavel,
                'status': chamado.status,
                'prioridade': chamado.prioridade,
                'descricao_resumida': chamado.descricao[:100] + '...' if len(chamado.descricao) > 100 else chamado.descricao,
                'data_abertura': chamado.data_abertura_formatada(),
                'data_conclusao': chamado.data_conclusao_formatada()
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
        return jsonify({
            'sucesso': False,
            'erro': str(e)
        }), 500


# --- ROTA 6: CARREGAR MAIS (Infinite Scroll) ---
@main.route('/api/carregar-mais', methods=['POST'])
@login_required
@limiter.limit("60 per minute")
def carregar_mais():
    """
    OTIMIZAÇÃO: Carregar mais chamados sem recarregar a página
    
    Usada para:
    - "Carregar mais" button
    - Infinite scroll
    - Alternativa leve à paginação
    
    Recebe:
    - cursor: ID do último documento carregado
    - limite: Quantos carregar (padrão 20)
    
    Returns uma lista de novos chamados
    """
    try:
        dados = request.get_json()
        cursor = dados.get('cursor')
        limite = min(dados.get('limite', 20), 50)  # Max 50
        
        logger.debug(f"Carregar mais: cursor={cursor}, limite={limite}, usuário={current_user.email}")
        
        chamados_ref = db.collection('chamados')
        resultado = aplicar_filtros_dashboard_com_paginacao(
            chamados_ref,
            request.args,
            limite=limite,
            cursor=cursor
        )
        
        # Converte
        chamados_dict = []
        for doc in resultado['docs']:
            data = doc.to_dict()
            chamado = Chamado.from_dict(data, doc.id)
            chamados_dict.append({
                'id': doc.id,
                'numero': chamado.numero_chamado,
                'categoria': chamado.categoria,
                'status': chamado.status,
                'responsavel': chamado.responsavel,
                'data_abertura': chamado.data_abertura_formatada()
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


# --- ROTA 7: ÍNDICES FIRESTORE (Documentação) ---
@main.route('/admin/indices-firestore')
@login_required
def indices_firestore():
    """
    OTIMIZAÇÃO: Documentação dos índices necessários
    
    Mostra quais índices devem ser criados no Firestore para
    melhor performance com filtros compostos.
    """
    try:
        logger.debug(f"Acessando page de índices: usuário={current_user.email}")
        
        indices = OptimizadorQuery.INDICES_RECOMENDADOS
        script = OptimizadorQuery.gerar_script_indices()
        
        return render_template(
            'indices_firestore.html',
            indices=indices,
            script=script
        )
    
    except Exception as e:
        logger.exception(f"Erro ao exibir índices: {str(e)}")
        flash('Erro ao carregar informações de índices', 'danger')
        return redirect(url_for('main.admin'))