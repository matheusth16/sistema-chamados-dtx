import logging
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.database import db
from app.firebase_retry import firebase_retry
from app.cache import cache_get, cache_set

logger = logging.getLogger(__name__)

CACHE_KEY_USUARIOS = 'usuarios_lista'
CACHE_TTL_USUARIOS = 300  # 5 minutos
CACHE_KEY_SUPERVISORES_VERSION = 'usuarios_supervisores_version'
CACHE_TTL_SUPERVISORES = 300  # 5 minutos
CACHE_TTL_VERSION = 86400  # 1 dia (só para a chave de versão)
CACHE_TTL_USUARIO_BY_ID = 120  # 2 minutos para get_by_id


class Usuario(UserMixin):
    """Representação de um usuário do sistema"""
    
    def __init__(self, id: str, email: str, nome: str, perfil: str = 'solicitante', areas: list = None):
        self.id = id
        self.email = email
        self.nome = nome
        self.perfil = perfil  # 'solicitante', 'supervisor' ou 'admin'
        self.areas = areas or []  # Lista de setores/departamentos
        self.senha_hash = None
    
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
            'senha_hash': self.senha_hash
        }
    
    @classmethod
    def from_dict(cls, data: dict, id: str = None):
        """Cria um objeto Usuario a partir de um dicionário do Firestore"""
        areas = data.get('areas', [])
        # Migração: se tem area string mas não tem areas array
        if not areas and data.get('area'):
            areas = [data.get('area')]
            
        usuario = cls(
            id=id,
            email=data.get('email'),
            nome=data.get('nome'),
            perfil=data.get('perfil', 'solicitante'),
            areas=areas
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
        """Busca usuário por ID (com cache de 2 min)."""
        try:
            cache_key = f'usuario_{user_id}'
            cached = cache_get(cache_key)
            if cached is not None:
                return cls.from_dict({k: v for k, v in cached.items() if k != '_id'}, cached['_id'])
            doc = db.collection('usuarios').document(user_id).get()
            if not doc.exists:
                return None
            data = doc.to_dict()
            usuario = cls.from_dict(data, doc.id)
            cache_set(cache_key, {"_id": doc.id, **data}, ttl_seconds=CACHE_TTL_USUARIO_BY_ID)
            return usuario
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
        """Retorna lista de todos os usuários (ordenada por nome, com cache de 5 min)."""
        try:
            cached = cache_get(CACHE_KEY_USUARIOS)
            if cached is not None:
                return [cls.from_dict({k: v for k, v in d.items() if k != '_id'}, d['_id']) for d in cached]
            docs = list(db.collection('usuarios').order_by('nome').stream())
            lista = [{"_id": doc.id, **doc.to_dict()} for doc in docs]
            cache_set(CACHE_KEY_USUARIOS, lista, ttl_seconds=CACHE_TTL_USUARIOS)
            return [cls.from_dict(doc.to_dict(), doc.id) for doc in docs]
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
        """Retorna supervisores de uma área específica (e admins da mesma área), com cache de 5 min."""
        try:
            version = cache_get(CACHE_KEY_SUPERVISORES_VERSION) or 0
            cache_key = f'usuarios_supervisores_area_{area}_{version}'
            cached = cache_get(cache_key)
            if cached is not None:
                return [cls.from_dict({k: v for k, v in d.items() if k != '_id'}, d['_id']) for d in cached]
            usuarios = []
            docs_sup = list(db.collection('usuarios').where('perfil', '==', 'supervisor').stream())
            for doc in docs_sup:
                user_dict = doc.to_dict()
                usuario = cls.from_dict(user_dict, doc.id)
                if area in usuario.areas:
                    usuarios.append(usuario)
            docs_admin = list(db.collection('usuarios').where('perfil', '==', 'admin').stream())
            for doc in docs_admin:
                user_dict = doc.to_dict()
                usuario = cls.from_dict(user_dict, doc.id)
                if area in usuario.areas:
                    usuarios.append(usuario)
            lista = [{"_id": u.id, **u.to_dict()} for u in usuarios]
            cache_set(cache_key, lista, ttl_seconds=CACHE_TTL_SUPERVISORES)
            return usuarios
        except Exception as e:
            logger.exception("Erro ao buscar supervisores: %s", e)
            return []

    @classmethod
    def invalidar_cache_supervisores_por_area(cls):
        """Invalida o cache de supervisores por área (chamar após criar/editar/excluir usuário)."""
        try:
            version = (cache_get(CACHE_KEY_SUPERVISORES_VERSION) or 0) + 1
            cache_set(CACHE_KEY_SUPERVISORES_VERSION, version, ttl_seconds=CACHE_TTL_VERSION)
        except Exception as e:
            logger.debug("Invalidação cache supervisores: %s", e)
    
    def __repr__(self):
        return f'<Usuario {self.email} - {self.perfil}>'
