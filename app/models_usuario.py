import logging
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.database import db
from app.firebase_retry import firebase_retry

logger = logging.getLogger(__name__)


def _encrypt_nome_if_enabled(nome: str):
    """Criptografa o nome para armazenamento se ENCRYPT_PII_AT_REST estiver ativo."""
    try:
        from flask import current_app
        if current_app.config.get('ENCRYPT_PII_AT_REST') and nome:
            from app.services.crypto import encrypt_at_rest
            return encrypt_at_rest(nome)
    except RuntimeError:
        pass  # fora do contexto de aplicação
    return nome


def _decrypt_nome_if_encrypted(valor):
    """Descriptografa o nome ao ler do banco, se for payload criptografado."""
    if not valor:
        return valor
    try:
        from app.services.crypto import decrypt_at_rest
        return decrypt_at_rest(valor)
    except Exception:
        return valor

# Chave de cache para lista de usuários (usada em app/routes/usuarios.py)
CACHE_KEY_USUARIOS = 'usuarios_list'


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
        """Converte para dicionário para salvar no Firestore (nome pode ser criptografado se ENCRYPT_PII_AT_REST)."""
        nome_armazenar = _encrypt_nome_if_enabled(self.nome) if self.nome else self.nome
        return {
            'email': self.email,
            'nome': nome_armazenar,
            'perfil': self.perfil,
            'areas': self.areas,
            'senha_hash': self.senha_hash
        }
    
    @classmethod
    def from_dict(cls, data: dict, id: str = None):
        """Cria um objeto Usuario a partir de um dicionário do Firestore (nome descriptografado se criptografado)."""
        areas = data.get('areas', [])
        # Migração: se tem area string mas não tem areas array
        if not areas and data.get('area'):
            areas = [data.get('area')]
        nome_raw = data.get('nome')
        nome = _decrypt_nome_if_encrypted(nome_raw) if nome_raw else nome_raw
        usuario = cls(
            id=id,
            email=data.get('email'),
            nome=nome,
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
        """Retorna lista de todos os usuários (ordenada por nome). Com criptografia PII, ordenação é em memória."""
        try:
            try:
                from flask import current_app
                use_encrypt = current_app.config.get('ENCRYPT_PII_AT_REST')
            except RuntimeError:
                use_encrypt = False
            if use_encrypt:
                # Nome criptografado: não ordenar no Firestore; ordenar após descriptografar
                docs = db.collection('usuarios').stream()
                usuarios = [cls.from_dict(doc.to_dict(), doc.id) for doc in docs]
                usuarios.sort(key=lambda u: (u.nome or '').upper())
                return usuarios
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

    @classmethod
    def invalidar_cache_supervisores_por_area(cls):
        """Invalida cache de supervisores por área (se existir). No-op se não houver cache."""
        try:
            from app.cache import cache_delete
            cache_delete('supervisores_por_area')
        except Exception:
            pass

    def __repr__(self):
        return f'<Usuario {self.email} - {self.perfil}>'
