from datetime import datetime
from firebase_admin import firestore
from app.database import db

class Historico:
    """Representação do histórico de alterações em um chamado"""
    
    def __init__(self,
                 chamado_id: str,
                 usuario_id: str,
                 usuario_nome: str,
                 acao: str,  # 'criacao', 'alteracao_status', 'alteracao_dados'
                 campo_alterado: str = None,
                 valor_anterior = None,
                 valor_novo = None,
                 data_acao = None,
                 id: str = None):
        
        self.id = id
        self.chamado_id = chamado_id
        self.usuario_id = usuario_id
        self.usuario_nome = usuario_nome
        self.acao = acao
        self.campo_alterado = campo_alterado
        self.valor_anterior = valor_anterior
        self.valor_novo = valor_novo
        self.data_acao = data_acao or firestore.SERVER_TIMESTAMP
    
    def to_dict(self):
        """Converte para dicionário para salvar no Firestore"""
        return {
            'chamado_id': self.chamado_id,
            'usuario_id': self.usuario_id,
            'usuario_nome': self.usuario_nome,
            'acao': self.acao,
            'campo_alterado': self.campo_alterado,
            'valor_anterior': self.valor_anterior,
            'valor_novo': self.valor_novo,
            'data_acao': self.data_acao
        }
    
    @classmethod
    def from_dict(cls, data: dict, id: str = None):
        """Cria um objeto Historico a partir de um dicionário do Firestore"""
        return cls(
            id=id,
            chamado_id=data.get('chamado_id'),
            usuario_id=data.get('usuario_id'),
            usuario_nome=data.get('usuario_nome'),
            acao=data.get('acao'),
            campo_alterado=data.get('campo_alterado'),
            valor_anterior=data.get('valor_anterior'),
            valor_novo=data.get('valor_novo'),
            data_acao=data.get('data_acao')
        )
    
    def save(self):
        """Salva o histórico no Firestore"""
        try:
            db.collection('historico').add(self.to_dict())
            return True
        except Exception as e:
            print(f'Erro ao salvar histórico: {e}')
            return False
    
    @classmethod
    def get_by_chamado_id(cls, chamado_id: str):
        """Busca histórico de um chamado específico"""
        try:
            docs = db.collection('historico').where('chamado_id', '==', chamado_id).order_by('data_acao', direction=firestore.Query.DESCENDING).stream()
            historico = []
            for doc in docs:
                data = doc.to_dict()
                historico.append(cls.from_dict(data, doc.id))
            return historico
        except Exception as e:
            print(f'Erro ao buscar histórico: {e}')
            return []
    
    def _converter_timestamp(self, ts):
        """Converte timestamp do Firestore para datetime ou string"""
        if ts is None or ts == firestore.SERVER_TIMESTAMP:
            return None
        if isinstance(ts, datetime):
            return ts
        if hasattr(ts, 'to_pydatetime'):
            return ts.to_pydatetime()
        return ts
    
    def data_acao_formatada(self):
        """Retorna data_acao formatada como string"""
        dt = self._converter_timestamp(self.data_acao)
        if dt and isinstance(dt, datetime):
            return dt.strftime('%d/%m/%Y %H:%M:%S')
        return '-'
    
    def __repr__(self):
        return f'<Historico {self.chamado_id} - {self.acao}>'
