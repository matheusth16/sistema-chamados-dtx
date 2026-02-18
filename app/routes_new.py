import os
from flask import Blueprint, render_template, request, redirect, url_for, send_file, current_app, flash
from flask_login import login_user, logout_user, login_required, current_user
from app.database import db
from app.models import Chamado
from app.models_usuario import Usuario
from app.models_historico import Historico
from app.services.validators import validar_novo_chamado
from app.services.filters import aplicar_filtros_dashboard
from app.services.upload import salvar_anexo
from datetime import datetime
from firebase_admin import firestore
import pandas as pd
import io


def _formatar_data_para_excel(val):
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


def _extrair_numero_chamado(numero_str):
    """Extrai número de 'CHM-XXXX' para ordenação numérica"""
    if not numero_str:
        return float('inf')
    try:
        return int(numero_str.replace('CHM-', ''))
    except (ValueError, AttributeError):
        return float('inf')


def _gerar_numero_chamado():
    """Gera o próximo número de chamado sequencial no formato CHM-XXXX"""
    try:
        # Busca todos os chamados com numero_chamado
        docs = db.collection('chamados').stream()
        numeros = []
        
        for doc in docs:
            data = doc.to_dict()
            numero_str = data.get('numero_chamado', '')
            if numero_str.startswith('CHM-'):
                try:
                    num = int(numero_str.replace('CHM-', ''))
                    numeros.append(num)
                except ValueError:
                    pass
        
        # Pega o maior número e incrementa
        proximo_numero = max(numeros) + 1 if numeros else 1
        return f'CHM-{proximo_numero:04d}'
    except Exception as e:
        current_app.logger.exception('Erro ao gerar número de chamado')
        # Fallback: usa timestamp como número
        return f'CHM-{int(datetime.now().timestamp()) % 10000:04d}'


# Cria um "agrupamento" de rotas chamado 'main'
main = Blueprint('main', __name__)


# --- ROTA 0: LOGIN/LOGOUT ---
@main.route('/login', methods=['GET', 'POST'])
def login():
    # Se já está logado, redireciona para admin
    if current_user.is_authenticated:
        return redirect(url_for('main.admin'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')
        
        if not email or not senha:
            flash('Email e senha são obrigatórios', 'danger')
            return redirect(url_for('main.login'))
        
        # Busca usuário no Firestore
        usuario = Usuario.get_by_email(email)
        
        if usuario and usuario.check_password(senha):
            login_user(usuario, remember=True)
            flash(f'Bem-vindo, {usuario.nome}!', 'success')
            return redirect(url_for('main.admin'))
        else:
            flash('Email ou senha incorretos', 'danger')
            return redirect(url_for('main.login'))
    
    return render_template('login.html')


@main.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você foi desconectado com sucesso!', 'info')
    return redirect(url_for('main.login'))


# --- ROTA 1: O FORMULÁRIO (Home) ---
@main.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # 1. BLINDAGEM DE DADOS
        lista_erros = validar_novo_chamado(request.form, request.files.get('anexo'))
        if lista_erros:
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
            
            # Registra a criação no histórico
            historico = Historico(
                chamado_id=doc_ref[1].id,
                usuario_id=usuario_id,
                usuario_nome=responsavel,
                acao='criacao'
            )
            historico.save()
            
            flash('Chamado criado com sucesso!', 'success')
            return redirect(url_for('main.index'))
        except Exception as e:
            current_app.logger.exception('Erro ao salvar chamado no Firestore')
            flash('Não foi possível salvar o chamado. Tente novamente.', 'danger')
            return redirect(url_for('main.index'))

    return render_template('formulario.html')


# --- ROTA 2: O PAINEL DO GESTOR (Admin) ---
@main.route('/admin', methods=['GET', 'POST'])
@login_required
def admin():
    # --- AÇÃO: Alterar status ---
    if request.method == 'POST':
        chamado_id = request.form.get('chamado_id')
        novo_status = request.form.get('novo_status')
        
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
            
            flash(f'Status alterado para {novo_status}', 'success')
            return redirect(url_for('main.admin', **request.args))
        except Exception as e:
            current_app.logger.exception('Erro ao atualizar chamado')
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

    # --- 5. PAGINAÇÃO ---
    pagina = request.args.get('pagina', 1, type=int)
    itens_por_pagina = 10
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
def visualizar_historico(chamado_id):
    try:
        # Busca o chamado
        doc_chamado = db.collection('chamados').document(chamado_id).get()
        if not doc_chamado.exists:
            flash('Chamado não encontrado', 'danger')
            return redirect(url_for('main.admin'))
        
        chamado_data = doc_chamado.to_dict()
        chamado = Chamado.from_dict(chamado_data, chamado_id)
        
        # Busca o histórico
        historico = Historico.get_by_chamado_id(chamado_id)
        
        return render_template('historico.html', chamado=chamado, historico=historico)
    except Exception as e:
        current_app.logger.exception('Erro ao buscar histórico')
        flash('Erro ao buscar histórico', 'danger')
        return redirect(url_for('main.admin'))


# --- ROTA 4: EXPORTAR PARA EXCEL ---
@main.route('/exportar')
@login_required
def exportar():
    # Busca todos os chamados com filtros aplicados
    chamados_ref = db.collection('chamados')
    docs = aplicar_filtros_dashboard(chamados_ref, request.args)
    
    dados = []
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
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'relatorio_chamados_{datetime.now().strftime("%Y%m%d")}.xlsx'
    )
