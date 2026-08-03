import logging
from datetime import datetime

from flask_login import UserMixin
from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash

from app import db as db_module
from app.db.models.usuario import UsuarioRow
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

# Teto de segurança para get_all() — evita ler a tabela inteira sem limite
MAX_USUARIOS_GET_ALL = 2000


class Usuario(UserMixin):
    """Representação de um usuário do sistema.

    Fase 2: armazenamento migrado de Firestore para PostgreSQL. id continua
    string (não vira serial) — referenciado por várias coleções ainda não
    migradas (chamados.solicitante_id, historico_usuarios.admin_id, etc.).
    """

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
        """Gestor "puro" (sem perfil operacional) — visão read-only do painel operacional.

        Quem acumula perfil=supervisor + nivel_gestao (ex.: gestor_setor) mantém a
        capacidade de operar chamados do próprio setor — só vira 100% read-only quem
        não tem perfil operacional nenhum.
        """
        return self.is_gestor and not self.is_admin_or_above and self.perfil != "supervisor"

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
        """Converte para dicionário (compatibilidade com callers existentes).

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
        """Cria um objeto Usuario a partir de um dicionário (Firestore legado)."""
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
            ativo=data.get("ativo", True),
            nivel_gestao=data.get("nivel_gestao"),
            mfa_enabled=data.get("mfa_enabled", False),
            mfa_secret=(maybe_decrypt(data["mfa_secret"]) if data.get("mfa_secret") else None),
            mfa_backup_codes=data.get("mfa_backup_codes", []),
            auth_provider=data.get("auth_provider", "local"),
        )
        usuario.senha_hash = data.get("senha_hash")
        return usuario

    @classmethod
    def _from_row(cls, row: UsuarioRow) -> "Usuario":
        usuario = cls(
            id=row.id,
            email=maybe_decrypt(row.email or ""),
            nome=maybe_decrypt(row.nome or ""),
            perfil=row.perfil,
            areas=list(row.areas or []),
            exp_total=row.exp_total,
            exp_semanal=row.exp_semanal,
            level=row.level,
            conquistas=list(row.conquistas or []),
            must_change_password=row.must_change_password,
            password_changed_at=row.password_changed_at,
            onboarding_perfis_vistos=list(row.onboarding_perfis_vistos or []),
            onboarding_passo=row.onboarding_passo,
            ativo=row.ativo,
            nivel_gestao=row.nivel_gestao,
            mfa_enabled=row.mfa_enabled,
            mfa_secret=(maybe_decrypt(row.mfa_secret) if row.mfa_secret else None),
            mfa_backup_codes=list(row.mfa_backup_codes or []),
            auth_provider=row.auth_provider,
        )
        usuario.senha_hash = row.senha_hash
        return usuario

    def _preencher_row(self, row: UsuarioRow) -> None:
        """Aplica o estado atual do objeto num UsuarioRow (insert ou update)."""
        row.email = maybe_encrypt(self.email)
        row.nome = maybe_encrypt(self.nome)
        row.email_lookup_hash = (
            email_lookup_hash(self.email) if is_pii_encryption_enabled() else None
        )
        row.perfil = self.perfil
        row.areas = self.areas
        row.senha_hash = self.senha_hash
        row.must_change_password = self.must_change_password
        row.password_changed_at = self.password_changed_at
        row.exp_total = self.exp_total
        row.exp_semanal = self.exp_semanal
        row.level = self.level
        row.conquistas = self.conquistas
        row.onboarding_perfis_vistos = self.onboarding_perfis_vistos
        row.onboarding_passo = self.onboarding_passo
        row.ativo = self.ativo
        row.nivel_gestao = self.nivel_gestao
        row.mfa_enabled = self.mfa_enabled
        row.mfa_secret = maybe_encrypt(self.mfa_secret) if self.mfa_secret else None
        row.mfa_backup_codes = self.mfa_backup_codes
        row.auth_provider = self.auth_provider

    @classmethod
    def _buscar_por_email_lookup(cls, session, email_norm: str) -> UsuarioRow | None:
        lookup = email_lookup_hash(email_norm)
        return session.execute(
            select(UsuarioRow).where(UsuarioRow.email_lookup_hash == lookup)
        ).scalar_one_or_none()

    @classmethod
    def get_by_email(cls, email: str):
        """Busca usuário por email.

        Quando encryption ON: consulta email_lookup_hash (sha256 do email normalizado).
        Quando encryption OFF: consulta campo email plaintext; se vazio, fallback
        por hash (linhas já migradas com email criptografado).
        """
        email_norm = (email or "").strip().lower()
        if not email_norm:
            return None
        try:
            with db_module.SessionLocal() as session:
                if is_pii_encryption_enabled():
                    row = cls._buscar_por_email_lookup(session, email_norm)
                else:
                    row = session.execute(
                        select(UsuarioRow).where(UsuarioRow.email == email_norm)
                    ).scalar_one_or_none()
                    if row is None:
                        row = cls._buscar_por_email_lookup(session, email_norm)
                return cls._from_row(row) if row is not None else None
        except Exception as e:
            logger.exception("Erro ao buscar usuário por email: %s", e)
        return None

    @classmethod
    def get_by_id(cls, user_id: str):
        """Busca usuário por ID"""
        try:
            with db_module.SessionLocal() as session:
                row = session.get(UsuarioRow, user_id)
                return cls._from_row(row) if row is not None else None
        except Exception as e:
            logger.exception("Erro ao buscar usuário por ID: %s", e)
        return None

    def save(self):
        """Salva o usuário no Postgres (upsert — mesma semântica do antigo
        Firestore .set(), que sempre sobrescreve o documento inteiro)."""
        try:
            with db_module.SessionLocal() as session, session.begin():
                row = session.get(UsuarioRow, self.id)
                if row is None:
                    row = UsuarioRow(id=self.id)
                    session.add(row)
                self._preencher_row(row)
            return True
        except Exception as e:
            logger.exception("Erro ao salvar usuário: %s", e)
            return False

    def update(self, **kwargs):
        """Atualiza campos específicos do usuário no Postgres.

        Args:
            **kwargs: Campos a atualizar (email, nome, perfil, areas, senha, ...)
        """
        try:
            with db_module.SessionLocal() as session, session.begin():
                row = session.get(UsuarioRow, self.id)
                if row is None:
                    return False

                atualizou = False

                if "email" in kwargs:
                    self.email = kwargs["email"]
                    row.email = maybe_encrypt(kwargs["email"])
                    if is_pii_encryption_enabled():
                        row.email_lookup_hash = email_lookup_hash(kwargs["email"])
                    atualizou = True

                if "nome" in kwargs:
                    self.nome = kwargs["nome"]
                    row.nome = maybe_encrypt(kwargs["nome"])
                    atualizou = True

                if "perfil" in kwargs:
                    self.perfil = kwargs["perfil"]
                    row.perfil = kwargs["perfil"]
                    atualizou = True

                if "areas" in kwargs:
                    self.areas = kwargs["areas"]
                    row.areas = kwargs["areas"]
                    atualizou = True

                if "senha" in kwargs and kwargs["senha"]:
                    self.set_password(kwargs["senha"])
                    row.senha_hash = self.senha_hash
                    atualizou = True

                if "must_change_password" in kwargs:
                    self.must_change_password = kwargs["must_change_password"]
                    row.must_change_password = kwargs["must_change_password"]
                    atualizou = True

                if "password_changed_at" in kwargs:
                    self.password_changed_at = kwargs["password_changed_at"]
                    row.password_changed_at = kwargs["password_changed_at"]
                    atualizou = True

                if "onboarding_perfis_vistos" in kwargs:
                    valor = [
                        p for p in (kwargs["onboarding_perfis_vistos"] or []) if p in PERFIS_VALIDOS
                    ]
                    self.onboarding_perfis_vistos = valor
                    row.onboarding_perfis_vistos = valor
                    atualizou = True

                if "onboarding_passo" in kwargs:
                    self.onboarding_passo = kwargs["onboarding_passo"]
                    row.onboarding_passo = kwargs["onboarding_passo"]
                    atualizou = True

                if "ativo" in kwargs:
                    self.ativo = kwargs["ativo"]
                    row.ativo = kwargs["ativo"]
                    atualizou = True

                if "nivel_gestao" in kwargs:
                    raw = kwargs["nivel_gestao"]
                    valor = raw if raw in NIVEIS_GESTAO_VALIDOS else None
                    self.nivel_gestao = valor
                    row.nivel_gestao = valor
                    atualizou = True

                if "mfa_enabled" in kwargs:
                    self.mfa_enabled = kwargs["mfa_enabled"]
                    row.mfa_enabled = kwargs["mfa_enabled"]
                    atualizou = True

                if "mfa_secret" in kwargs:
                    self.mfa_secret = kwargs["mfa_secret"]
                    row.mfa_secret = (
                        maybe_encrypt(kwargs["mfa_secret"]) if kwargs["mfa_secret"] else None
                    )
                    atualizou = True

                if "mfa_backup_codes" in kwargs:
                    self.mfa_backup_codes = kwargs["mfa_backup_codes"] or []
                    row.mfa_backup_codes = self.mfa_backup_codes
                    atualizou = True

                if "auth_provider" in kwargs:
                    raw = kwargs["auth_provider"]
                    valor = raw if raw in AUTH_PROVIDERS_VALIDOS else "local"
                    self.auth_provider = valor
                    row.auth_provider = valor
                    atualizou = True

                if "gamification" in kwargs:
                    g_data = kwargs["gamification"]
                    if "exp_total" in g_data:
                        self.exp_total = g_data["exp_total"]
                        row.exp_total = g_data["exp_total"]
                        atualizou = True
                    if "exp_semanal" in g_data:
                        self.exp_semanal = g_data["exp_semanal"]
                        row.exp_semanal = g_data["exp_semanal"]
                        atualizou = True
                    if "level" in g_data:
                        self.level = g_data["level"]
                        row.level = g_data["level"]
                        atualizou = True
                    if "conquistas" in g_data:
                        self.conquistas = g_data["conquistas"]
                        row.conquistas = g_data["conquistas"]
                        atualizou = True

                return atualizou
        except Exception as e:
            logger.exception("Erro ao atualizar usuário: %s", e)
            return False

    def delete(self):
        """Deleta o usuário do Postgres."""
        try:
            with db_module.SessionLocal() as session, session.begin():
                row = session.get(UsuarioRow, self.id)
                if row is not None:
                    session.delete(row)
            return True
        except Exception as e:
            logger.exception("Erro ao deletar usuário: %s", e)
            return False

    @classmethod
    def get_by_ids(cls, ids: list[str]) -> dict[str, "Usuario"]:
        """
        Busca múltiplos usuários em um único round-trip (WHERE id IN (...)).

        Substitui o loop com N chamadas a get_by_id, reduzindo queries N+1.

        Returns:
            Dict {user_id: Usuario} com apenas os IDs encontrados.
        """
        if not ids:
            return {}
        try:
            with db_module.SessionLocal() as session:
                rows = (
                    session.execute(select(UsuarioRow).where(UsuarioRow.id.in_(ids)))
                    .scalars()
                    .all()
                )
                return {row.id: cls._from_row(row) for row in rows}
        except Exception as e:
            logger.exception("Erro ao buscar usuários em lote: %s", e)
            return {}

    @classmethod
    def get_all(cls):
        """Retorna lista de todos os usuários ordenada por nome.

        Quando encryption ON: Postgres não pode ordenar por campo criptografado,
        então busca sem order_by e ordena em Python após decrypt.
        Quando encryption OFF: usa ORDER BY nome nativo do Postgres.
        """
        try:
            with db_module.SessionLocal() as session:
                if is_pii_encryption_enabled():
                    rows = (
                        session.execute(select(UsuarioRow).limit(MAX_USUARIOS_GET_ALL))
                        .scalars()
                        .all()
                    )
                    usuarios = [cls._from_row(row) for row in rows]
                    if len(usuarios) >= MAX_USUARIOS_GET_ALL:
                        logger.warning(
                            "Usuario.get_all() atingiu o teto de segurança (%d) — resultado pode estar incompleto",
                            MAX_USUARIOS_GET_ALL,
                        )
                    return sorted(usuarios, key=lambda u: (u.nome or "").lower())
                else:
                    rows = (
                        session.execute(
                            select(UsuarioRow).order_by(UsuarioRow.nome).limit(MAX_USUARIOS_GET_ALL)
                        )
                        .scalars()
                        .all()
                    )
                    usuarios = [cls._from_row(row) for row in rows]
                    if len(usuarios) >= MAX_USUARIOS_GET_ALL:
                        logger.warning(
                            "Usuario.get_all() atingiu o teto de segurança (%d) — resultado pode estar incompleto",
                            MAX_USUARIOS_GET_ALL,
                        )
                    return usuarios
        except Exception as e:
            logger.exception("Erro ao buscar usuários: %s", e)
            return []

    @classmethod
    def email_existe(cls, email: str, id_atual: str = None) -> bool:
        """Verifica se um email já existe (excluindo um ID específico).

        Quando encryption ON: consulta email_lookup_hash.
        Quando encryption OFF: consulta campo email diretamente.
        """
        email_norm = (email or "").strip().lower()
        if not email_norm:
            return False
        try:
            with db_module.SessionLocal() as session:
                if is_pii_encryption_enabled():
                    row = cls._buscar_por_email_lookup(session, email_norm)
                    return row is not None and (id_atual is None or row.id != id_atual)
                row = session.execute(
                    select(UsuarioRow).where(UsuarioRow.email == email_norm)
                ).scalar_one_or_none()
                if row is not None:
                    return id_atual is None or row.id != id_atual
                # Linhas migradas: email no Postgres é fernet:v1:… — usar hash
                row = cls._buscar_por_email_lookup(session, email_norm)
                return row is not None and (id_atual is None or row.id != id_atual)
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

        Usa o operador de contenção de array (ARRAY @> ARRAY[area]) — 1 query,
        aproveitando o índice GIN em areas[].
        """
        try:
            usuarios = []
            with db_module.SessionLocal() as session:
                rows = (
                    session.execute(select(UsuarioRow).where(UsuarioRow.areas.contains([area])))
                    .scalars()
                    .all()
                )
                for row in rows:
                    usuario = cls._from_row(row)
                    if usuario.perfil in ("supervisor", "admin"):
                        usuarios.append(usuario)
            return usuarios
        except Exception as e:
            logger.exception("Erro ao buscar supervisores: %s", e)
            return []

    def __repr__(self):
        return f"<Usuario {self.email} - {self.perfil}>"
