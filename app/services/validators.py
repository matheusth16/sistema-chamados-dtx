import re

# Lista de extensões permitidas no sistema
EXTENSOES_PERMITIDAS = {'png', 'jpg', 'jpeg', 'pdf', 'xlsx'}

def _arquivo_permitido(filename):
    """Verifica se a extensão do arquivo é válida."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in EXTENSOES_PERMITIDAS

def validar_novo_chamado(form, arquivo=None):
    """
    Realiza a blindagem dos dados recebidos do formulário.
    Retorna uma lista de erros. Se a lista estiver vazia, está tudo OK.
    """
    erros = []

    # 1. Validação Básica de Campos Obrigatórios
    descricao = form.get('descricao', '').strip()
    tipo = form.get('tipo')
    categoria = form.get('categoria')

    if not descricao:
        erros.append("A descrição do chamado é obrigatória.")
    elif len(descricao) < 3:
        erros.append("A descrição deve ter no mínimo 3 caracteres.")
    
    if not tipo:
        erros.append("É necessário selecionar um Setor/Tipo.")

    # 2. Validação Específica da DTX (Regra do RL)
    # Se for Projeto, OBRIGATORIAMENTE precisa de um RL de 3 dígitos
    if categoria == 'Projetos':
        rl_codigo = form.get('rl_codigo', '').strip()
        
        # Regex: Verifica se tem exatamente 3 números (ex: 045, 102)
        if not re.match(r'^\d{3}$', rl_codigo):
            erros.append("Para Projetos, o código RL deve conter exatamente 3 dígitos numéricos.")

    # 3. Validação de Arquivo (Se houver upload)
    if arquivo and arquivo.filename != '':
        if not _arquivo_permitido(arquivo.filename):
            erros.append(f"Formato de arquivo inválido. Permitidos: {', '.join(EXTENSOES_PERMITIDAS)}")

    return erros