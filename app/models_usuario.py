from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.database import db

class Usuario(UserMixin):
    """Representação de um usuário do sistema"""
    
    def __init__(self, id: str, email: str, nome: str, perfil: str = 'gestor'):
        self.id = id
        self.email = email
        self.nome = nome
        self.perfil = perfil  # 'admin' ou 'gestor'
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
            'senha_hash': self.senha_hash
        }
    
    @classmethod
    def from_dict(cls, data: dict, id: str = None):
        """Cria um objeto Usuario a partir de um dicionário do Firestore"""
        usuario = cls(
            id=id,
            email=data.get('email'),
            nome=data.get('nome'),
            perfil=data.get('perfil', 'gestor')
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
            print(f'Erro ao buscar usuário: {e}')
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
            print(f'Erro ao buscar usuário por ID: {e}')
        return None
    
    def save(self):
        """Salva o usuário no Firestore"""
        try:
            db.collection('usuarios').document(self.id).set(self.to_dict())
            return True
        except Exception as e:
            print(f'Erro ao salvar usuário: {e}')
            return False
    
    def __repr__(self):
        return f'<Usuario {self.email} - {self.perfil}>'
