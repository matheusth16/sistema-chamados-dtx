from datetime import datetime
import pytz
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
                 detalhe: str = None,
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
        self.detalhe = detalhe  # ex: nome do arquivo anexado para exibição

    def to_dict(self):
        """Converte para dicionário para salvar no Firestore"""
        d = {
            'chamado_id': self.chamado_id,
            'usuario_id': self.usuario_id,
            'usuario_nome': self.usuario_nome,
            'acao': self.acao,
            'campo_alterado': self.campo_alterado,
            'valor_anterior': self.valor_anterior,
            'valor_novo': self.valor_novo,
            'data_acao': self.data_acao
        }
        if self.detalhe is not None:
            d['detalhe'] = self.detalhe
        return d

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
            data_acao=data.get('data_acao'),
            detalhe=data.get('detalhe')
        )
    
    def save(self):
        """Salva o histórico no Firestore"""
        try:
            import logging
            logger = logging.getLogger(__name__)
            hist_dict = self.to_dict()
            logger.info(f"Salvando histórico: {hist_dict}")
            doc_ref = db.collection('historico').add(hist_dict)
            logger.info(f"Histórico salvo com ID: {doc_ref[1].id}")
            return True
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f'Erro ao salvar histórico: {e}', exc_info=True)
            print(f'Erro ao salvar histórico: {e}')
            return False
    
    @classmethod
    def get_by_chamado_id(cls, chamado_id: str):
        """Busca histórico de um chamado específico"""
        try:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Buscando histórico para chamado_id: {chamado_id}")
            
            # Tenta buscar com ordenação (requer índice)
            try:
                docs = db.collection('historico').where('chamado_id', '==', chamado_id).order_by('data_acao', direction=firestore.Query.DESCENDING).stream()
                historico = []
                for doc in docs:
                    data = doc.to_dict()
                    logger.debug(f"Histórico encontrado: {doc.id} - {data}")
                    historico.append(cls.from_dict(data, doc.id))
                logger.info(f"✅ Total de {len(historico)} registros encontrados (com ordenação)")
                return historico
            except Exception as index_error:
                # Se falhar (índice em construção), busca sem ordenação e ordena manualmente
                if "index" in str(index_error).lower() or "building" in str(index_error).lower():
                    logger.warning(f"⚠️ Índice ainda em construção, buscando sem ordenação: {index_error}")
                    docs = db.collection('historico').where('chamado_id', '==', chamado_id).stream()
                    historico = []
                    for doc in docs:
                        data = doc.to_dict()
                        logger.debug(f"Histórico encontrado (sem ordem): {doc.id} - {data}")
                        historico.append(cls.from_dict(data, doc.id))
                    
                    # Ordena manualmente por data_acao (mais recente primeiro)
                    historico.sort(key=lambda h: h.data_acao if h.data_acao else '', reverse=True)
                    logger.info(f"✅ Total de {len(historico)} registros encontrados (ordenação manual)")
                    return historico
                else:
                    raise index_error
                    
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f'❌ Erro ao buscar histórico: {e}', exc_info=True)
            print(f'Erro ao buscar histórico: {e}')
            return []
    
    def _converter_timestamp(self, ts):
        """Converte timestamp do Firestore para datetime em horário de Brasília"""
        if ts is None or ts == firestore.SERVER_TIMESTAMP:
            return None
        if isinstance(ts, datetime):
            # Se não tiver timezone, assume UTC e converte para Brasília
            if ts.tzinfo is None:
                ts = pytz.utc.localize(ts)
            return ts.astimezone(pytz.timezone('America/Sao_Paulo'))
        if hasattr(ts, 'to_pydatetime'):
            dt = ts.to_pydatetime()
            # Firestore timestamps são UTC, então convertemos para Brasília
            if dt.tzinfo is None:
                dt = pytz.utc.localize(dt)
            return dt.astimezone(pytz.timezone('America/Sao_Paulo'))
        return ts
    
    def data_acao_formatada(self):
        """Retorna data_acao formatada como string"""
        dt = self._converter_timestamp(self.data_acao)
        if dt and isinstance(dt, datetime):
            return dt.strftime('%d/%m/%Y %H:%M:%S')
        return '-'
    
    def __repr__(self):
        return f'<Historico {self.chamado_id} - {self.acao}>'
