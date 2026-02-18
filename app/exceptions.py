"""
Exceções customizadas para o sistema de chamados.

Define exceções específicas para melhor tratamento de erros
e mensagens mais claras ao usuário.
"""


class ChamadoError(Exception):
    """Exceção base para erros relacionados a chamados"""
    pass


class ChamadoNaoEncontradoError(ChamadoError):
    """Levantada quando um chamado não é encontrado no banco de dados"""
    
    def __init__(self, chamado_id: str):
        self.chamado_id = chamado_id
        super().__init__(f"Chamado {chamado_id} não encontrado")


class ValidacaoChamadoError(ChamadoError):
    """Levantada quando validação de dados falha"""
    
    def __init__(self, mensagem: str, erros: list = None):
        self.erros = erros or []
        self.mensagem = mensagem
        super().__init__(mensagem)


class UsuarioError(Exception):
    """Exceção base para erros de usuário"""
    pass


class UsuarioNaoEncontradoError(UsuarioError):
    """Levantada quando um usuário não é encontrado"""
    
    def __init__(self, email: str):
        self.email = email
        super().__init__(f"Usuário {email} não encontrado")


class AutenticacaoError(UsuarioError):
    """Levantada quando falha a autenticação"""
    
    def __init__(self, mensagem: str = "Email ou senha incorretos"):
        super().__init__(mensagem)


class PermissaoNegadaError(UsuarioError):
    """Levantada quando usuário não tem permissão"""
    
    def __init__(self, mensagem: str = "Você não tem permissão para esta ação"):
        super().__init__(mensagem)


class FirestoreError(Exception):
    """Exceção base para erros do Firestore"""
    pass


class DocumentoNaoEncontradoError(FirestoreError):
    """Levantada quando documento não existe"""
    
    def __init__(self, colecao: str, doc_id: str):
        self.colecao = colecao
        self.doc_id = doc_id
        super().__init__(f"Documento {doc_id} não encontrado em {colecao}")


class ErroTransacaoError(FirestoreError):
    """Levantada quando transação Firestore falha"""
    
    def __init__(self, mensagem: str):
        super().__init__(f"Erro em transação Firestore: {mensagem}")


class UploadError(Exception):
    """Exceção base para erros de upload"""
    pass


class ArquivoNaoPermitidoError(UploadError):
    """Levantada quando arquivo tem extensão não permitida"""
    
    def __init__(self, extensao: str, permitidas: list):
        self.extensao = extensao
        self.permitidas = permitidas
        super().__init__(
            f"Extensão .{extensao} não permitida. "
            f"Permitidas: {', '.join(permitidas)}"
        )


class TamanhoArquivoExcedidoError(UploadError):
    """Levantada quando arquivo excede tamanho máximo"""
    
    def __init__(self, tamanho_mb: float, maximo_mb: float):
        self.tamanho_mb = tamanho_mb
        self.maximo_mb = maximo_mb
        super().__init__(
            f"Arquivo de {tamanho_mb:.2f}MB excede máximo de {maximo_mb}MB"
        )
