import logging
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.database import db

logger = logging.getLogger(__name__)


class Usuario(UserMixin):
    """Representação de um usuário do sistema"""
    
    def __init__(self, id: str, email: str, nome: str, perfil: str = 'solicitante', area: str = None):
        self.id = id
        self.email = email
        self.nome = nome
        self.perfil = perfil  # 'solicitante', 'supervisor' ou 'admin'
        self.area = area  # Setor/departamento (ex: Manutencao, Engenharia, etc)
        self.senha_hash = None
    
    def set_password(self, senha: str):
        """Define a senha com hash"""
        self.senha_hash = generate_password_hash(senha)
    
    def check_password(self, senha: str) -> bool:
        """Verifica se a senha está correta"""
        return check_password_hash(self.senha_hash, senha) if self.senha_hash else False
    
    def to_dict(self):
        """Converte para dicionário para salvar no Firestore"""
        return {
            'email': self.email,
            'nome': self.nome,
            'perfil': self.perfil,
            'area': self.area,
            'senha_hash': self.senha_hash
        }
    
    @classmethod
    def from_dict(cls, data: dict, id: str = None):
        """Cria um objeto Usuario a partir de um dicionário do Firestore"""
        usuario = cls(
            id=id,
            email=data.get('email'),
            nome=data.get('nome'),
            perfil=data.get('perfil', 'solicitante'),
            area=data.get('area')
        )
        usuario.senha_hash = data.get('senha_hash')
        return usuario
    
    @classmethod
    def get_by_email(cls, email: str):
        """Busca usuário por email"""
        try:
            docs = db.collection('usuarios').where('email', '==', email).stream()
            for doc in docs:
                data = doc.to_dict()
                return cls.from_dict(data, doc.id)
        except Exception as e:
            logger.exception("Erro ao buscar usuário por email: %s", e)
        return None
    
    @classmethod
    def get_by_id(cls, user_id: str):
        """Busca usuário por ID"""
        try:
            doc = db.collection('usuarios').document(user_id).get()
            if doc.exists:
                data = doc.to_dict()
                return cls.from_dict(data, doc.id)
        except Exception as e:
            logger.exception("Erro ao buscar usuário por ID: %s", e)
        return None
    
    def save(self):
        """Salva o usuário no Firestore"""
        try:
            db.collection('usuarios').document(self.id).set(self.to_dict())
            return True
        except Exception as e:
            logger.exception("Erro ao salvar usuário: %s", e)
            return False
    
    def update(self, **kwargs):
        """Atualiza campos específicos do usuário no Firestore
        
        Args:
            **kwargs: Campos a atualizar (email, nome, perfil, area, senha)
        """
        try:
            update_data = {}
            
            # Aceita atualizações de campos específicos
            if 'email' in kwargs:
                self.email = kwargs['email']
                update_data['email'] = kwargs['email']
            
            if 'nome' in kwargs:
                self.nome = kwargs['nome']
                update_data['nome'] = kwargs['nome']
            
            if 'perfil' in kwargs:
                self.perfil = kwargs['perfil']
                update_data['perfil'] = kwargs['perfil']
            
            if 'area' in kwargs:
                self.area = kwargs['area']
                update_data['area'] = kwargs['area']
            
            if 'senha' in kwargs and kwargs['senha']:
                self.set_password(kwargs['senha'])
                update_data['senha_hash'] = self.senha_hash
            
            if update_data:
                db.collection('usuarios').document(self.id).update(update_data)
                return True
            
            return False
        except Exception as e:
            logger.exception("Erro ao atualizar usuário: %s", e)
            return False
    
    def delete(self):
        """Deleta o usuário do Firestore"""
        try:
            db.collection('usuarios').document(self.id).delete()
            return True
        except Exception as e:
            logger.exception("Erro ao deletar usuário: %s", e)
            return False
    
    @classmethod
    def get_all(cls):
        """Retorna lista de todos os usuários"""
        try:
            docs = db.collection('usuarios').order_by('nome').stream()
            usuarios = []
            for doc in docs:
                data = doc.to_dict()
                usuario = cls.from_dict(data, doc.id)
                usuarios.append(usuario)
            return usuarios
        except Exception as e:
            logger.exception("Erro ao buscar usuários: %s", e)
            return []
    
    @classmethod
    def email_existe(cls, email: str, id_atual: str = None) -> bool:
        """Verifica se um email já existe (excluindo é um ID específico)
        
        Args:
            email: Email a verificar
            id_atual: ID do usuário atual (para validação de atualização)
        """
        try:
            docs = db.collection('usuarios').where('email', '==', email).stream()
            for doc in docs:
                if id_atual is None or doc.id != id_atual:
                    return True
            return False
        except Exception as e:
            logger.exception("Erro ao verificar email: %s", e)
            return False
    
    @classmethod
    def get_supervisores_por_area(cls, area: str):
        """Retorna supervisores de uma área específica (e admins da mesma área, para sugestão de responsável)."""
        try:
            # Supervisores da área
            docs_sup = db.collection('usuarios')\
                .where('perfil', '==', 'supervisor')\
                .where('area', '==', area)\
                .stream()
            usuarios = [cls.from_dict(doc.to_dict(), doc.id) for doc in docs_sup]
            # Admins da área também podem ser sugeridos como responsáveis
            docs_admin = db.collection('usuarios')\
                .where('perfil', '==', 'admin')\
                .where('area', '==', area)\
                .stream()
            for doc in docs_admin:
                usuarios.append(cls.from_dict(doc.to_dict(), doc.id))
            return usuarios
        except Exception as e:
            logger.exception("Erro ao buscar supervisores: %s", e)
            return []
    
    def __repr__(self):
        return f'<Usuario {self.email} - {self.perfil}>'
