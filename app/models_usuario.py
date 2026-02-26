import logging
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.database import db
from app.firebase_retry import firebase_retry

logger = logging.getLogger(__name__)

# Chave de cache para lista de usuários (usada em cache_delete nas rotas)
CACHE_KEY_USUARIOS = 'usuarios_list'


class Usuario(UserMixin):
    """Representação de um usuário do sistema"""
    
    def __init__(self, id: str, email: str, nome: str, perfil: str = 'solicitante', areas: list = None,
                 exp_total: int = 0, exp_semanal: int = 0, level: int = 1, conquistas: list = None,
                 must_change_password: bool = False, password_changed_at=None):
        self.id = id
        self.email = email
        self.nome = nome
        self.perfil = perfil  # 'solicitante', 'supervisor' ou 'admin'
        self.areas = areas or []  # Lista de setores/departamentos
        self.senha_hash = None
        
        # Controle de senha
        self.must_change_password = must_change_password
        self.password_changed_at = password_changed_at
        
        # Sistemas de Gamificação
        self.exp_total = exp_total
        self.exp_semanal = exp_semanal
        self.level = level
        self.conquistas = conquistas or []
    
    @property
    def area(self):
        """Property de compatibilidade: retorna áreas separadas por vírgula"""
        return ", ".join(self.areas) if self.areas else None
    
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
            'areas': self.areas,
            'senha_hash': self.senha_hash,
            'must_change_password': self.must_change_password,
            'password_changed_at': self.password_changed_at.isoformat() if self.password_changed_at else None,
            'exp_total': self.exp_total,
            'exp_semanal': self.exp_semanal,
            'level': self.level,
            'conquistas': self.conquistas
        }
    
    @classmethod
    def from_dict(cls, data: dict, id: str = None):
        """Cria um objeto Usuario a partir de um dicionário do Firestore"""
        areas = data.get('areas', [])
        # Migração: se tem area string mas não tem areas array
        if not areas and data.get('area'):
            areas = [data.get('area')]
            
        # Processar password_changed_at
        password_changed_at = data.get('password_changed_at')
        if password_changed_at and isinstance(password_changed_at, str):
            try:
                password_changed_at = datetime.fromisoformat(password_changed_at)
            except:
                password_changed_at = None
        
        usuario = cls(
            id=id,
            email=data.get('email'),
            nome=data.get('nome'),
            perfil=data.get('perfil', 'solicitante'),
            areas=areas,
            exp_total=data.get('exp_total', 0),
            exp_semanal=data.get('exp_semanal', 0),
            level=data.get('level', 1),
            conquistas=data.get('conquistas', []),
            must_change_password=data.get('must_change_password', False),
            password_changed_at=password_changed_at
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
    
    @firebase_retry(max_retries=3)
    def save(self):
        """Salva o usuário no Firestore com retry automático"""
        try:
            db.collection('usuarios').document(self.id).set(self.to_dict())
            return True
        except Exception as e:
            logger.exception("Erro ao salvar usuário: %s", e)
            return False
    
    @firebase_retry(max_retries=3)
    def update(self, **kwargs):
        """Atualiza campos específicos do usuário no Firestore com retry automático
        
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
            
            if 'areas' in kwargs:
                self.areas = kwargs['areas']
                update_data['areas'] = kwargs['areas']
            
            if 'senha' in kwargs and kwargs['senha']:
                self.set_password(kwargs['senha'])
                update_data['senha_hash'] = self.senha_hash
            
            if 'must_change_password' in kwargs:
                self.must_change_password = kwargs['must_change_password']
                update_data['must_change_password'] = kwargs['must_change_password']
            
            if 'password_changed_at' in kwargs:
                self.password_changed_at = kwargs['password_changed_at']
                update_data['password_changed_at'] = kwargs['password_changed_at'].isoformat() if kwargs['password_changed_at'] else None
            
            if 'gamification' in kwargs:
                g_data = kwargs['gamification']
                if 'exp_total' in g_data:
                    self.exp_total = g_data['exp_total']
                    update_data['exp_total'] = g_data['exp_total']
                if 'exp_semanal' in g_data:
                    self.exp_semanal = g_data['exp_semanal']
                    update_data['exp_semanal'] = g_data['exp_semanal']
                if 'level' in g_data:
                    self.level = g_data['level']
                    update_data['level'] = g_data['level']
                if 'conquistas' in g_data:
                    self.conquistas = g_data['conquistas']
                    update_data['conquistas'] = g_data['conquistas']
            
            if update_data:
                db.collection('usuarios').document(self.id).update(update_data)
                return True
            
            return False
        except Exception as e:
            logger.exception("Erro ao atualizar usuário: %s", e)
            return False
    
    @firebase_retry(max_retries=3)
    def delete(self):
        """Deleta o usuário do Firestore com retry automático"""
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
    def invalidar_cache_supervisores_por_area(cls):
        """Invalida cache de supervisores por área (no-op se não houver cache)."""
        pass

    @classmethod
    def get_supervisores_por_area(cls, area: str):
        """Retorna supervisores de uma área específica (e admins da mesma área, para sugestão de responsável)."""
        try:
            usuarios = []
            
            # Buscar todos os supervisores e filtrar por área em Python
            # (Firestore tem limitações em queries compostas com array_contains)
            docs_sup = db.collection('usuarios').where('perfil', '==', 'supervisor').stream()
            for doc in docs_sup:
                user_dict = doc.to_dict()
                # Precisamos criar o objeto Usuario primeiro para que from_dict
                # faça a conversão de 'area' (string) para 'areas' (array)
                usuario = cls.from_dict(user_dict, doc.id)
                # Agora verificar se a área desejada está nas áreas do usuário
                if area in usuario.areas:
                    usuarios.append(usuario)
            
            # Buscar todos os admins e filtrar por área
            docs_admin = db.collection('usuarios').where('perfil', '==', 'admin').stream()
            for doc in docs_admin:
                user_dict = doc.to_dict()
                usuario = cls.from_dict(user_dict, doc.id)
                if area in usuario.areas:
                    usuarios.append(usuario)
            
            return usuarios
        except Exception as e:
            logger.exception("Erro ao buscar supervisores: %s", e)
            return []
    
    def __repr__(self):
        return f'<Usuario {self.email} - {self.perfil}>'
