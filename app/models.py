from datetime import datetime
from firebase_admin import firestore

class Chamado:
    """Representação de um documento Chamado no Firestore"""
    
    def __init__(self, 
                 categoria: str,
                 tipo_solicitacao: str,
                 descricao: str,
                 responsavel: str,
                 rl_codigo: str = None,
                 gate: str = None,
                 impacto: str = None,
                 anexo: str = None,
                 numero_chamado: str = None,
                 prioridade: int = 1,
                 status: str = 'Aberto',
                 data_abertura = None,
                 data_conclusao = None,
                 id: str = None):
        
        self.id = id
        self.numero_chamado = numero_chamado
        self.categoria = categoria
        self.rl_codigo = rl_codigo
        # Prioridade centralizada: Projetos = 0, demais = informado ou 1
        self.prioridade = 0 if categoria == 'Projetos' else (prioridade if prioridade is not None else 1)
        self.tipo_solicitacao = tipo_solicitacao
        self.gate = gate
        self.impacto = impacto
        self.descricao = descricao
        self.anexo = anexo
        self.responsavel = responsavel
        self.status = status
        self.data_abertura = data_abertura or firestore.SERVER_TIMESTAMP
        self.data_conclusao = data_conclusao
    
    def _converter_timestamp(self, ts):
        """Converte timestamp do Firestore para datetime ou string"""
        if ts is None or ts == firestore.SERVER_TIMESTAMP:
            return None
        # Se já for datetime, retorna
        if isinstance(ts, datetime):
            return ts
        # Se for Timestamp do Firestore, converte para datetime
        if hasattr(ts, 'to_pydatetime'):
            return ts.to_pydatetime()
        return ts
    
    def data_abertura_formatada(self):
        """Retorna data_abertura formatada como string"""
        dt = self._converter_timestamp(self.data_abertura)
        if dt and isinstance(dt, datetime):
            return dt.strftime('%d/%m/%Y %H:%M')
        return '-'
    
    def data_conclusao_formatada(self):
        """Retorna data_conclusao formatada como string"""
        dt = self._converter_timestamp(self.data_conclusao)
        if dt and isinstance(dt, datetime):
            return dt.strftime('%d/%m/%Y %H:%M')
        return '-'
    
    def to_dict(self):
        """Converte para dicionário para salvar no Firestore"""
        return {
            'numero_chamado': self.numero_chamado,
            'categoria': self.categoria,
            'rl_codigo': self.rl_codigo,
            'prioridade': self.prioridade,
            'tipo_solicitacao': self.tipo_solicitacao,
            'gate': self.gate,
            'impacto': self.impacto,
            'descricao': self.descricao,
            'anexo': self.anexo,
            'responsavel': self.responsavel,
            'status': self.status,
            'data_abertura': self.data_abertura,
            'data_conclusao': self.data_conclusao
        }
    
    @classmethod
    def from_dict(cls, data: dict, id: str = None):
        """Cria um objeto Chamado a partir de um dicionário do Firestore"""
        return cls(
            id=id,
            numero_chamado=data.get('numero_chamado'),
            categoria=data.get('categoria'),
            rl_codigo=data.get('rl_codigo'),
            prioridade=data.get('prioridade', 1),
            tipo_solicitacao=data.get('tipo_solicitacao'),
            gate=data.get('gate'),
            impacto=data.get('impacto'),
            descricao=data.get('descricao'),
            anexo=data.get('anexo'),
            responsavel=data.get('responsavel'),
            status=data.get('status', 'Aberto'),
            data_abertura=data.get('data_abertura'),
            data_conclusao=data.get('data_conclusao')
        )
    
    def __repr__(self):
        return f'<Chamado {self.id} - {self.categoria}>'