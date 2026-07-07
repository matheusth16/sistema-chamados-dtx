import logging
from datetime import datetime

from flask_login import UserMixin
from google.cloud.firestore_v1.base_query import FieldFilter
from werkzeug.security import check_password_hash, generate_password_hash

from app.database import db
from app.firebase_retry import firebase_retry
from app.services.pii_encryption import (
    email_lookup_hash,
    is_pii_encryption_enabled,
    maybe_decrypt,
    maybe_encrypt,
)

logger = logging.getLogger(__name__)

# Chave de cache para lista de usuários (usada em cache_delete nas rotas)
CACHE_KEY_USUARIOS = "usuarios_list"

# Valores válidos de nivel_gestao — lista fechada
NIVEIS_GESTAO_VALIDOS = frozenset({"gestor_setor", "gerente_producao", "assistente_gm", "gm"})

# Valores válidos de auth_provider — lista fechada
AUTH_PROVIDERS_VALIDOS = frozenset({"local", "microsoft"})

# Perfis válidos — usado para validar onboarding_perfis_vistos
PERFIS_VALIDOS = frozenset({"solicitante", "supervisor", "admin", "admin_global"})


class Usuario(UserMixin):
    """Representação de um usuário do sistema"""

    def __init__(
        self,
        id: str,
        email: str,
        nome: str,
        perfil: str = "solicitante",
        areas: list = None,
        exp_total: int = 0,
        exp_semanal: int = 0,
        level: int = 1,
        conquistas: list = None,
        must_change_password: bool = False,
        password_changed_at=None,
        onboarding_perfis_vistos: list | None = None,
        onboarding_passo: int = 0,
        ativo: bool = True,
        nivel_gestao: str | None = None,
        mfa_enabled: bool = False,
        mfa_secret: str | None = None,
        mfa_backup_codes: list | None = None,
        auth_provider: str = "local",
    ):
        self.id = id
        self.email = email
        self.nome = nome
        self.perfil = perfil  # 'solicitante', 'supervisor', 'admin' ou 'admin_global'
        self.areas = areas or []  # Lista de setores/departamentos
        self.senha_hash = None
        self.ativo = ativo  # False bloqueia login e invalida sessão ativa

        # Controle de senha
        self.must_change_password = must_change_password
        self.password_changed_at = password_changed_at

        # Sistemas de Gamificação
        self.exp_total = exp_total
        self.exp_semanal = exp_semanal
        self.level = level
        self.conquistas = conquistas or []

        # Onboarding: perfis para os quais o tour já foi visto/pulado — não repete
        # o tour de um perfil já visto (ex.: rebaixado de volta a um perfil anterior)
        self.onboarding_perfis_vistos: list[str] = [
            p for p in (onboarding_perfis_vistos or []) if p in PERFIS_VALIDOS
        ]
        self.onboarding_passo = onboarding_passo

        # Gestão (Fase 5): valor fora da lista fechada → None (fail-safe)
        self.nivel_gestao: str | None = (
            nivel_gestao if nivel_gestao in NIVEIS_GESTAO_VALIDOS else None
        )

        # MFA (TOTP + códigos de backup)
        self.mfa_enabled = mfa_enabled
        self.mfa_secret = mfa_secret
        self.mfa_backup_codes = mfa_backup_codes or []

        # SSO: como o usuário autentica ('local' ou 'microsoft') — auditoria/exibição,
        # nunca usado para controle de acesso (login por e-mail existente vale para os dois)
        self.auth_provider: str = (
            auth_provider if auth_provider in AUTH_PROVIDERS_VALIDOS else "local"
        )

    @property
    def is_admin_or_above(self) -> bool:
        return self.perfil in ("admin", "admin_global")

    @property
    def is_supervisor_or_above(self) -> bool:
        return self.perfil in ("supervisor", "admin", "admin_global")

    @property
    def is_gestor(self) -> bool:
        """True quando nivel_gestao está preenchido com valor válido."""
        return self.nivel_gestao is not None

    @property
    def is_gestor_only(self) -> bool:
        """Gestor sem privilégio admin — visão read-only do painel operacional."""
        return self.is_gestor and not self.is_admin_or_above

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
        """Converte para dicionário para salvar no Firestore.

        Quando ENCRYPT_PII_AT_REST=true: criptografa email/nome e inclui email_lookup_hash.
        Quando falso: formato plaintext original (retrocompatível).
        """
        d = {
            "email": maybe_encrypt(self.email),
            "nome": maybe_encrypt(self.nome),
            "perfil": self.perfil,
            "areas": self.areas,
            "senha_hash": self.senha_hash,
            "must_change_password": self.must_change_password,
            "password_changed_at": self.password_changed_at.isoformat()
            if self.password_changed_at
            else None,
            "exp_total": self.exp_total,
            "exp_semanal": self.exp_semanal,
            "level": self.level,
            "conquistas": self.conquistas,
            "onboarding_perfis_vistos": self.onboarding_perfis_vistos,
            "onboarding_passo": self.onboarding_passo,
            "ativo": self.ativo,
            "nivel_gestao": self.nivel_gestao,
            "mfa_enabled": self.mfa_enabled,
            "mfa_secret": maybe_encrypt(self.mfa_secret) if self.mfa_secret else None,
            "mfa_backup_codes": self.mfa_backup_codes,
            "auth_provider": self.auth_provider,
        }
        if is_pii_encryption_enabled():
            d["email_lookup_hash"] = email_lookup_hash(self.email)
        return d

    def to_public_dict(self) -> dict:
        """Serialização segura para respostas HTTP — sem senha_hash."""
        return {
            "id": self.id,
            "email": self.email,
            "nome": self.nome,
            "perfil": self.perfil,
            "areas": self.areas,
            "exp_total": self.exp_total,
            "level": self.level,
            "onboarding_perfis_vistos": self.onboarding_perfis_vistos,
        }

    @classmethod
    def from_dict(cls, data: dict, id: str = None):
        """Cria um objeto Usuario a partir de um dicionário do Firestore"""
        areas = data.get("areas", [])
        # Migração: se tem area string mas não tem areas array
        if not areas and data.get("area"):
            areas = [data.get("area")]

        # Processar password_changed_at
        password_changed_at = data.get("password_changed_at")
        if password_changed_at and isinstance(password_changed_at, str):
            try:
                password_changed_at = datetime.fromisoformat(password_changed_at)
            except ValueError:
                password_changed_at = None

        perfil = data.get("perfil", "solicitante")

        # Retrocompat: docs antigos tinham só onboarding_completo (bool), sem a lista
        # por perfil. Se a lista nova não existe mas o antigo flag era True, assume
        # que o usuário já viu o tour do perfil atual (evita reaparecer do nada).
        onboarding_perfis_vistos = data.get("onboarding_perfis_vistos")
        if onboarding_perfis_vistos is None:
            onboarding_perfis_vistos = [perfil] if data.get("onboarding_completo") else []

        usuario = cls(
            id=id,
            email=maybe_decrypt(data.get("email") or ""),
            nome=maybe_decrypt(data.get("nome") or ""),
            perfil=perfil,
            areas=areas,
            exp_total=data.get("exp_total", 0),
            exp_semanal=data.get("exp_semanal", 0),
            level=data.get("level", 1),
            conquistas=data.get("conquistas", []),
            must_change_password=data.get("must_change_password", False),
            password_changed_at=password_changed_at,
            onboarding_perfis_vistos=onboarding_perfis_vistos,
            onboarding_passo=data.get("onboarding_passo", 0),
            # Docs sem campo ativo (legado) tratados como ativos — retrocompat.
            ativo=data.get("ativo", True),
            # Fase 5: nivel_gestao — valores inválidos normalizados para None pelo __init__
            nivel_gestao=data.get("nivel_gestao"),
            mfa_enabled=data.get("mfa_enabled", False),
            mfa_secret=(maybe_decrypt(data["mfa_secret"]) if data.get("mfa_secret") else None),
            mfa_backup_codes=data.get("mfa_backup_codes", []),
            auth_provider=data.get("auth_provider", "local"),
        )
        usuario.senha_hash = data.get("senha_hash")
        return usuario

    @classmethod
    def _stream_by_email_lookup(cls, email: str):
        """Query Firestore por email_lookup_hash (email normalizado)."""
        lookup = email_lookup_hash(email)
        return (
            db.collection("usuarios")
            .where(filter=FieldFilter("email_lookup_hash", "==", lookup))
            .stream()
        )

    @classmethod
    def get_by_email(cls, email: str):
        """Busca usuário por email.

        Quando encryption ON: consulta email_lookup_hash (sha256 do email normalizado).
        Quando encryption OFF: consulta campo email plaintext; se vazio, fallback
        por hash (docs já migrados com email criptografado no Firestore).
        """
        email_norm = (email or "").strip().lower()
        if not email_norm:
            return None
        try:
            if is_pii_encryption_enabled():
                docs = cls._stream_by_email_lookup(email_norm)
            else:
                docs = (
                    db.collection("usuarios")
                    .where(filter=FieldFilter("email", "==", email_norm))
                    .stream()
                )
                first = next(iter(docs), None)
                if first is not None:
                    return cls.from_dict(first.to_dict(), first.id)
                # Docs migrados: email no Firestore é fernet:v1:… — usar hash
                docs = cls._stream_by_email_lookup(email_norm)

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
            doc = db.collection("usuarios").document(user_id).get()
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
            db.collection("usuarios").document(self.id).set(self.to_dict())
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
            if "email" in kwargs:
                self.email = kwargs["email"]
                update_data["email"] = maybe_encrypt(kwargs["email"])
                if is_pii_encryption_enabled():
                    update_data["email_lookup_hash"] = email_lookup_hash(kwargs["email"])

            if "nome" in kwargs:
                self.nome = kwargs["nome"]
                update_data["nome"] = maybe_encrypt(kwargs["nome"])

            if "perfil" in kwargs:
                self.perfil = kwargs["perfil"]
                update_data["perfil"] = kwargs["perfil"]

            if "areas" in kwargs:
                self.areas = kwargs["areas"]
                update_data["areas"] = kwargs["areas"]

            if "senha" in kwargs and kwargs["senha"]:
                self.set_password(kwargs["senha"])
                update_data["senha_hash"] = self.senha_hash

            if "must_change_password" in kwargs:
                self.must_change_password = kwargs["must_change_password"]
                update_data["must_change_password"] = kwargs["must_change_password"]

            if "password_changed_at" in kwargs:
                self.password_changed_at = kwargs["password_changed_at"]
                update_data["password_changed_at"] = (
                    kwargs["password_changed_at"].isoformat()
                    if kwargs["password_changed_at"]
                    else None
                )

            if "onboarding_perfis_vistos" in kwargs:
                valor = [
                    p for p in (kwargs["onboarding_perfis_vistos"] or []) if p in PERFIS_VALIDOS
                ]
                self.onboarding_perfis_vistos = valor
                update_data["onboarding_perfis_vistos"] = valor

            if "onboarding_passo" in kwargs:
                self.onboarding_passo = kwargs["onboarding_passo"]
                update_data["onboarding_passo"] = kwargs["onboarding_passo"]

            if "ativo" in kwargs:
                self.ativo = kwargs["ativo"]
                update_data["ativo"] = kwargs["ativo"]

            if "nivel_gestao" in kwargs:
                raw = kwargs["nivel_gestao"]
                valor = raw if raw in NIVEIS_GESTAO_VALIDOS else None
                self.nivel_gestao = valor
                update_data["nivel_gestao"] = valor

            if "mfa_enabled" in kwargs:
                self.mfa_enabled = kwargs["mfa_enabled"]
                update_data["mfa_enabled"] = kwargs["mfa_enabled"]

            if "mfa_secret" in kwargs:
                self.mfa_secret = kwargs["mfa_secret"]
                update_data["mfa_secret"] = (
                    maybe_encrypt(kwargs["mfa_secret"]) if kwargs["mfa_secret"] else None
                )

            if "mfa_backup_codes" in kwargs:
                self.mfa_backup_codes = kwargs["mfa_backup_codes"] or []
                update_data["mfa_backup_codes"] = self.mfa_backup_codes

            if "auth_provider" in kwargs:
                raw = kwargs["auth_provider"]
                valor = raw if raw in AUTH_PROVIDERS_VALIDOS else "local"
                self.auth_provider = valor
                update_data["auth_provider"] = valor

            if "gamification" in kwargs:
                g_data = kwargs["gamification"]
                if "exp_total" in g_data:
                    self.exp_total = g_data["exp_total"]
                    update_data["exp_total"] = g_data["exp_total"]
                if "exp_semanal" in g_data:
                    self.exp_semanal = g_data["exp_semanal"]
                    update_data["exp_semanal"] = g_data["exp_semanal"]
                if "level" in g_data:
                    self.level = g_data["level"]
                    update_data["level"] = g_data["level"]
                if "conquistas" in g_data:
                    self.conquistas = g_data["conquistas"]
                    update_data["conquistas"] = g_data["conquistas"]

            if update_data:
                db.collection("usuarios").document(self.id).update(update_data)
                return True

            return False
        except Exception as e:
            logger.exception("Erro ao atualizar usuário: %s", e)
            return False

    @firebase_retry(max_retries=3)
    def delete(self):
        """Deleta o usuário do Firestore com retry automático"""
        try:
            db.collection("usuarios").document(self.id).delete()
            return True
        except Exception as e:
            logger.exception("Erro ao deletar usuário: %s", e)
            return False

    @classmethod
    def get_by_ids(cls, ids: list[str]) -> dict[str, "Usuario"]:
        """
        Busca múltiplos usuários em um único round-trip via batch read do Firestore.

        Substitui o loop com N chamadas a get_by_id, reduzindo queries N+1.

        Returns:
            Dict {user_id: Usuario} com apenas os IDs encontrados.
        """
        if not ids:
            return {}
        try:
            refs = [db.collection("usuarios").document(uid) for uid in ids]
            snapshots = db.get_all(refs)
            result = {}
            for snap in snapshots:
                if snap.exists:
                    result[snap.id] = cls.from_dict(snap.to_dict(), snap.id)
            return result
        except Exception as e:
            logger.exception("Erro ao buscar usuários em lote: %s", e)
            return {}

    @classmethod
    def get_all(cls):
        """Retorna lista de todos os usuários ordenada por nome.

        Quando encryption ON: Firestore não pode ordenar por campo criptografado,
        então faz stream() sem order_by e ordena em Python após decrypt.
        Quando encryption OFF: usa order_by("nome") do Firestore (comportamento legado).
        """
        try:
            if is_pii_encryption_enabled():
                docs = db.collection("usuarios").stream()
                usuarios = [cls.from_dict(doc.to_dict(), doc.id) for doc in docs]
                return sorted(usuarios, key=lambda u: (u.nome or "").lower())
            else:
                docs = db.collection("usuarios").order_by("nome").stream()
                return [cls.from_dict(doc.to_dict(), doc.id) for doc in docs]
        except Exception as e:
            logger.exception("Erro ao buscar usuários: %s", e)
            return []

    @classmethod
    def email_existe(cls, email: str, id_atual: str = None) -> bool:
        """Verifica se um email já existe (excluindo é um ID específico).

        Quando encryption ON: consulta email_lookup_hash.
        Quando encryption OFF: consulta campo email diretamente.
        """
        email_norm = (email or "").strip().lower()
        if not email_norm:
            return False
        try:
            if is_pii_encryption_enabled():
                docs = cls._stream_by_email_lookup(email_norm)
            else:
                docs = (
                    db.collection("usuarios")
                    .where(filter=FieldFilter("email", "==", email_norm))
                    .stream()
                )
                if any(id_atual is None or doc.id != id_atual for doc in docs):
                    return True
                docs = cls._stream_by_email_lookup(email_norm)
            return any(id_atual is None or doc.id != id_atual for doc in docs)
        except Exception as e:
            logger.exception("Erro ao verificar email: %s", e)
            return False

    @classmethod
    def invalidar_cache_supervisores_por_area(cls):
        """Invalida cache de supervisores por área (no-op se não houver cache)."""
        pass

    @classmethod
    def buscar_ativos(cls, q: str) -> list["Usuario"]:
        """Busca usuários ativos cujo nome ou e-mail contém q (case-insensitive).

        Usa get_all() com filtragem em Python para compatibilidade com PII encryption.
        Máximo 200 candidatos lidos — busca interna de baixo volume.
        """
        q_low = (q or "").strip().lower()
        if not q_low:
            return []
        try:
            todos = cls.get_all()
            resultado = []
            for u in todos:
                if not getattr(u, "ativo", True):
                    continue
                nome_low = (getattr(u, "nome", "") or "").lower()
                email_low = (getattr(u, "email", "") or "").lower()
                if q_low in nome_low or q_low in email_low:
                    resultado.append(u)
            return resultado
        except Exception as exc:
            logger.exception("Erro em buscar_ativos('%s'): %s", q, exc)
            return []

    @classmethod
    def get_supervisores_por_area(cls, area: str):
        """Retorna supervisores e admins de uma área específica.

        Usa array_contains no campo areas[] (1 query vs 2 full-scans anteriores).
        O índice single-field em areas[] é criado automaticamente pelo Firestore.
        """
        try:
            usuarios = []
            docs = (
                db.collection("usuarios")
                .where(filter=FieldFilter("areas", "array_contains", area))
                .stream()
            )
            for doc in docs:
                usuario = cls.from_dict(doc.to_dict(), doc.id)
                if usuario.perfil in ("supervisor", "admin"):
                    usuarios.append(usuario)
            return usuarios
        except Exception as e:
            logger.exception("Erro ao buscar supervisores: %s", e)
            return []

    def __repr__(self):
        return f"<Usuario {self.email} - {self.perfil}>"
