"""
Modelo para Categorias do Sistema (Setores, Gates, Impactos).
Cada categoria é traduzida automaticamente para PT, EN e ES.
"""
from datetime import datetime
import pytz
from firebase_admin import firestore
from app.database import db
from app.services.translation_service import traduzir_categoria
from app.firebase_retry import firebase_retry
import logging

logger = logging.getLogger(__name__)

# Chaves de cache usadas em app/routes/categorias.py
CACHE_KEY_SETORES = 'categorias_setores'
CACHE_KEY_GATES = 'categorias_gates'
CACHE_KEY_IMPACTOS = 'categorias_impactos'


class CategoriaSetor:
    """Representa um Setor/Departamento do sistema"""
    
    def __init__(self,
                 nome_pt: str,
                 nome_en: str = None,
                 nome_es: str = None,
                 descricao_pt: str = None,
                 descricao_en: str = None,
                 descricao_es: str = None,
                 ativo: bool = True,
                 id: str = None):
        self.id = id
        self.nome_pt = nome_pt
        self.nome_en = nome_en or traduzir_categoria(nome_pt)['en']
        self.nome_es = nome_es or traduzir_categoria(nome_pt)['es']
        self.descricao_pt = descricao_pt
        self.descricao_en = descricao_en
        self.descricao_es = descricao_es
        self.ativo = ativo
        self.data_criacao = datetime.now(pytz.timezone('America/Sao_Paulo'))
    
    def to_dict(self):
        """Converte para dicionário para salvar no Firestore"""
        return {
            'nome_pt': self.nome_pt,
            'nome_en': self.nome_en,
            'nome_es': self.nome_es,
            'descricao_pt': self.descricao_pt,
            'descricao_en': self.descricao_en,
            'descricao_es': self.descricao_es,
            'ativo': self.ativo,
            'data_criacao': self.data_criacao,
        }
    
    @classmethod
    def from_dict(cls, data: dict, id: str = None):
        """Cria um objeto CategoriaSetor a partir de um dicionário"""
        return cls(
            nome_pt=data.get('nome_pt'),
            nome_en=data.get('nome_en'),
            nome_es=data.get('nome_es'),
            descricao_pt=data.get('descricao_pt'),
            descricao_en=data.get('descricao_en'),
            descricao_es=data.get('descricao_es'),
            ativo=data.get('ativo', True),
            id=id,
        )
    
    @firebase_retry(max_retries=3)
    def save(self):
        """Salva o setor no Firestore com retry automático"""
        try:
            if self.id:
                db.collection('categorias_setores').document(self.id).update(self.to_dict())
            else:
                self.id = db.collection('categorias_setores').add(self.to_dict())[1].id
            logger.info(f"Setor {self.nome_pt} salvo com sucesso")
            return self.id
        except Exception as e:
            logger.error(f"Erro ao salvar setor: {e}")
            raise
    
    @classmethod
    def get_all(cls):
        """Retorna todos os setores"""
        try:
            docs = db.collection('categorias_setores').stream()
            return [cls.from_dict(doc.to_dict(), doc.id) for doc in docs]
        except Exception as e:
            logger.error(f"Erro ao buscar setores: {e}")
            return []
    
    @classmethod
    def get_by_id(cls, setor_id: str):
        """Busca um setor pelo ID"""
        try:
            doc = db.collection('categorias_setores').document(setor_id).get()
            if doc.exists:
                return cls.from_dict(doc.to_dict(), doc.id)
            return None
        except Exception as e:
            logger.error(f"Erro ao buscar setor: {e}")
            return None


class CategoriaGate:
    """Representa um Gate do sistema"""
    
    def __init__(self,
                 nome_pt: str,
                 nome_en: str = None,
                 nome_es: str = None,
                 descricao_pt: str = None,
                 descricao_en: str = None,
                 descricao_es: str = None,
                 ordem: int = 0,
                 ativo: bool = True,
                 id: str = None):
        self.id = id
        self.nome_pt = nome_pt
        self.nome_en = nome_en or traduzir_categoria(nome_pt)['en']
        self.nome_es = nome_es or traduzir_categoria(nome_pt)['es']
        self.descricao_pt = descricao_pt
        self.descricao_en = descricao_en
        self.descricao_es = descricao_es
        self.ordem = ordem
        self.ativo = ativo
        self.data_criacao = datetime.now(pytz.timezone('America/Sao_Paulo'))
    
    def to_dict(self):
        """Converte para dicionário para salvar no Firestore"""
        return {
            'nome_pt': self.nome_pt,
            'nome_en': self.nome_en,
            'nome_es': self.nome_es,
            'descricao_pt': self.descricao_pt,
            'descricao_en': self.descricao_en,
            'descricao_es': self.descricao_es,
            'ordem': self.ordem,
            'ativo': self.ativo,
            'data_criacao': self.data_criacao,
        }
    
    @classmethod
    def from_dict(cls, data: dict, id: str = None):
        """Cria um objeto CategoriaGate a partir de um dicionário"""
        return cls(
            nome_pt=data.get('nome_pt'),
            nome_en=data.get('nome_en'),
            nome_es=data.get('nome_es'),
            descricao_pt=data.get('descricao_pt'),
            descricao_en=data.get('descricao_en'),
            descricao_es=data.get('descricao_es'),
            ordem=data.get('ordem', 0),
            ativo=data.get('ativo', True),
            id=id,
        )
    
    @firebase_retry(max_retries=3)
    def save(self):
        """Salva o gate no Firestore com retry automático"""
        try:
            if self.id:
                db.collection('categorias_gates').document(self.id).update(self.to_dict())
            else:
                self.id = db.collection('categorias_gates').add(self.to_dict())[1].id
            logger.info(f"Gate {self.nome_pt} salvo com sucesso")
            return self.id
        except Exception as e:
            logger.error(f"Erro ao salvar gate: {e}")
            raise
    
    @classmethod
    def get_all(cls):
        """Retorna todos os gates ordenados por ordem"""
        try:
            docs = db.collection('categorias_gates').stream()
            gates = [cls.from_dict(doc.to_dict(), doc.id) for doc in docs]
            # Ordena por ordem no Python (evita problema de índice no Firestore)
            return sorted(gates, key=lambda x: x.ordem)
        except Exception as e:
            logger.error(f"Erro ao buscar gates: {e}")
            return []
    
    @classmethod
    def get_by_id(cls, gate_id: str):
        """Busca um gate pelo ID"""
        try:
            doc = db.collection('categorias_gates').document(gate_id).get()
            if doc.exists:
                return cls.from_dict(doc.to_dict(), doc.id)
            return None
        except Exception as e:
            logger.error(f"Erro ao buscar gate: {e}")
            return None


class CategoriaImpacto:
    """Representa um Impacto/Severidade do sistema"""
    
    def __init__(self,
                 nome_pt: str,
                 nome_en: str = None,
                 nome_es: str = None,
                 descricao_pt: str = None,
                 descricao_en: str = None,
                 descricao_es: str = None,
                 nivel: int = 0,
                 cor: str = '#gray',
                 ativo: bool = True,
                 id: str = None):
        self.id = id
        self.nome_pt = nome_pt
        self.nome_en = nome_en or traduzir_categoria(nome_pt)['en']
        self.nome_es = nome_es or traduzir_categoria(nome_pt)['es']
        self.descricao_pt = descricao_pt
        self.descricao_en = descricao_en
        self.descricao_es = descricao_es
        self.nivel = nivel  # Ordem de severidade
        self.cor = cor  # Cor para exibição (ex: #red, #orange, #yellow, #green)
        self.ativo = ativo
        self.data_criacao = datetime.now(pytz.timezone('America/Sao_Paulo'))
    
    def to_dict(self):
        """Converte para dicionário para salvar no Firestore"""
        return {
            'nome_pt': self.nome_pt,
            'nome_en': self.nome_en,
            'nome_es': self.nome_es,
            'descricao_pt': self.descricao_pt,
            'descricao_en': self.descricao_en,
            'descricao_es': self.descricao_es,
            'nivel': self.nivel,
            'cor': self.cor,
            'ativo': self.ativo,
            'data_criacao': self.data_criacao,
        }
    
    @classmethod
    def from_dict(cls, data: dict, id: str = None):
        """Cria um objeto CategoriaImpacto a partir de um dicionário"""
        return cls(
            nome_pt=data.get('nome_pt'),
            nome_en=data.get('nome_en'),
            nome_es=data.get('nome_es'),
            descricao_pt=data.get('descricao_pt'),
            descricao_en=data.get('descricao_en'),
            descricao_es=data.get('descricao_es'),
            nivel=data.get('nivel', 0),
            cor=data.get('cor', '#gray'),
            ativo=data.get('ativo', True),
            id=id,
        )
    
    def save(self):
        """Salva o impacto no Firestore"""
        try:
            if self.id:
                db.collection('categorias_impactos').document(self.id).update(self.to_dict())
            else:
                self.id = db.collection('categorias_impactos').add(self.to_dict())[1].id
            logger.info(f"Impacto {self.nome_pt} salvo com sucesso")
            return self.id
        except Exception as e:
            logger.error(f"Erro ao salvar impacto: {e}")
            raise
    
    @classmethod
    def get_all(cls):
        """Retorna todos os impactos ativos"""
        try:
            docs = db.collection('categorias_impactos').where('ativo', '==', True).stream()
            return [cls.from_dict(doc.to_dict(), doc.id) for doc in docs]
        except Exception as e:
            logger.error(f"Erro ao buscar impactos: {e}")
            return []
    
    @classmethod
    def get_by_id(cls, impacto_id: str):
        """Busca um impacto pelo ID"""
        try:
            doc = db.collection('categorias_impactos').document(impacto_id).get()
            if doc.exists:
                return cls.from_dict(doc.to_dict(), doc.id)
            return None
        except Exception as e:
            logger.error(f"Erro ao buscar impacto: {e}")
            return None
