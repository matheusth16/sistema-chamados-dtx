"""
Validação de dados de chamados e formulários.

Centraliza regras de negócio para criação/edição de chamados:
- Campos obrigatórios (descrição, tipo, categoria)
- Regra DTX: Projetos exigem código RL (letras, números e caracteres; 1 a 100 caracteres)
- Extensões e tamanho de anexos (via config)
"""
import re

# Lista de extensões permitidas no sistema
EXTENSOES_PERMITIDAS = {'png', 'jpg', 'jpeg', 'pdf', 'xlsx'}


def _arquivo_permitido(filename: str) -> bool:
    """Verifica se a extensão do arquivo é válida (permitidas: png, jpg, jpeg, pdf, xlsx)."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in EXTENSOES_PERMITIDAS


def validar_novo_chamado(form, arquivo=None):
    """
    Valida dados do formulário de novo chamado. Blindagem antes de persistir no Firestore.

    Args:
        form: Dict-like com campos do formulário (descricao, tipo, categoria, rl_codigo, etc.)
        arquivo: FileStorage opcional (request.files.get('anexo')).

    Returns:
        Lista de mensagens de erro. Lista vazia indica que os dados são válidos.

    Regras:
        - Descrição obrigatória, mínimo 3 caracteres.
        - Setor/Tipo obrigatório.
        - Categoria Projetos exige rl_codigo preenchido (letras, números e caracteres; 1 a 100 caracteres).
        - Anexo: apenas extensões em EXTENSOES_PERMITIDAS (tamanho máximo em config).
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
    # Para Projetos: código RL obrigatório — letras, números e caracteres (1 a 100)
    if categoria == 'Projetos':
        rl_codigo = form.get('rl_codigo', '').strip()
        if not rl_codigo:
            erros.append("Para Projetos, o código RL é obrigatório.")
        elif len(rl_codigo) > 100:
            erros.append("O código RL deve ter no máximo 100 caracteres.")
        # Caracteres permitidos: letras, números, espaços e símbolos comuns (evita controle/injeção)
        elif not re.match(r'^[\w\s\-./(),]+$', rl_codigo, re.UNICODE):
            erros.append("O código RL permite letras, números e os caracteres: espaço, - _ . / ( ) ,")

    # 3. Validação de Arquivo (Se houver upload)
    if arquivo and arquivo.filename != '':
        if not _arquivo_permitido(arquivo.filename):
            erros.append(f"Formato de arquivo inválido. Permitidos: {', '.join(EXTENSOES_PERMITIDAS)}")

    return erros