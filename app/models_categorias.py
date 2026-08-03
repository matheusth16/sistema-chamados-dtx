"""
Modelo para Categorias do Sistema (Setores, Gates, Impactos).
Cada categoria é traduzida automaticamente para PT, EN e ES.

Fase 2: armazenamento migrado de Firestore para PostgreSQL (SQLAlchemy).
"""

import logging
from datetime import datetime

import pytz
from sqlalchemy import func, select

from app import db as db_module
from app.db.models.categoria import CategoriaGateRow, CategoriaImpactoRow, CategoriaSetorRow
from app.services.translation_service import traduzir_categoria

logger = logging.getLogger(__name__)

# Chaves de cache para listas de categorias (usadas em cache_delete nas rotas)
CACHE_KEY_SETORES = "categorias_setores_list"
CACHE_KEY_GATES = "categorias_gates_list"

# Teto de segurança para get_all_incluindo_inativos() sem filtro
MAX_CATEGORIAS = 1000
CACHE_KEY_IMPACTOS = "categorias_impactos_list"

# Chaves do static_cache usadas em chamados.py / __init__.py
STATIC_CACHE_KEY_SETORES = "categorias_setor"
STATIC_CACHE_KEY_GATES = "categorias_gate"
STATIC_CACHE_KEY_IMPACTOS = "categorias_impacto"


def _id_para_int(id_bruto):
    """Converte id (str/int vindo de URL, from_dict, etc.) pra int, ou None."""
    if id_bruto is None:
        return None
    return int(id_bruto)


class CategoriaSetor:
    """Representa um Setor/Departamento do sistema"""

    def __init__(
        self,
        nome_pt: str,
        nome_en: str = None,
        nome_es: str = None,
        descricao_pt: str = None,
        descricao_en: str = None,
        descricao_es: str = None,
        ativo: bool = True,
        id: str = None,
        data_criacao: datetime = None,
    ):
        self.id = _id_para_int(id)
        self.nome_pt = nome_pt
        self.nome_en = nome_en or traduzir_categoria(nome_pt)["en"]
        self.nome_es = nome_es or traduzir_categoria(nome_pt)["es"]
        self.descricao_pt = descricao_pt
        self.descricao_en = descricao_en
        self.descricao_es = descricao_es
        self.ativo = ativo
        self.data_criacao = data_criacao or datetime.now(pytz.timezone("America/Sao_Paulo"))

    def to_dict(self):
        """Converte para dicionário (compatibilidade com callers existentes)."""
        return {
            "nome_pt": self.nome_pt,
            "nome_en": self.nome_en,
            "nome_es": self.nome_es,
            "descricao_pt": self.descricao_pt,
            "descricao_en": self.descricao_en,
            "descricao_es": self.descricao_es,
            "ativo": self.ativo,
            "data_criacao": self.data_criacao,
        }

    @classmethod
    def from_dict(cls, data: dict, id: str = None):
        """Cria um objeto CategoriaSetor a partir de um dicionário"""
        return cls(
            nome_pt=data.get("nome_pt"),
            nome_en=data.get("nome_en"),
            nome_es=data.get("nome_es"),
            descricao_pt=data.get("descricao_pt"),
            descricao_en=data.get("descricao_en"),
            descricao_es=data.get("descricao_es"),
            ativo=data.get("ativo", True),
            id=id,
            data_criacao=data.get("data_criacao"),
        )

    @classmethod
    def _from_row(cls, row: CategoriaSetorRow):
        return cls(
            nome_pt=row.nome_pt,
            nome_en=row.nome_en,
            nome_es=row.nome_es,
            descricao_pt=row.descricao_pt,
            descricao_en=row.descricao_en,
            descricao_es=row.descricao_es,
            ativo=row.ativo,
            id=row.id,
            data_criacao=row.data_criacao,
        )

    def save(self):
        """Salva o setor no Postgres (insert ou update)."""
        try:
            with db_module.SessionLocal() as session, session.begin():
                if self.id:
                    row = session.get(CategoriaSetorRow, self.id)
                    if row is None:
                        raise ValueError(f"Setor {self.id} não encontrado")
                else:
                    row = CategoriaSetorRow()
                    session.add(row)
                row.nome_pt = self.nome_pt
                row.nome_en = self.nome_en
                row.nome_es = self.nome_es
                row.descricao_pt = self.descricao_pt
                row.descricao_en = self.descricao_en
                row.descricao_es = self.descricao_es
                row.ativo = self.ativo
                session.flush()
                self.id = row.id
            logger.info("Setor %s salvo com sucesso", self.nome_pt)
            return self.id
        except Exception as e:
            logger.error("Erro ao salvar setor: %s", e)
            raise

    def delete(self):
        """Deleta o setor do Postgres. Idempotente: sem id ou já removido, retorna True."""
        try:
            if self.id:
                with db_module.SessionLocal() as session, session.begin():
                    row = session.get(CategoriaSetorRow, self.id)
                    if row is not None:
                        session.delete(row)
            return True
        except Exception as e:
            logger.error("Erro ao deletar setor: %s", e)
            return False

    @classmethod
    def get_all(cls):
        """Retorna todos os setores ativos (para formulários e seletores)."""
        try:
            with db_module.SessionLocal() as session:
                rows = (
                    session.execute(
                        select(CategoriaSetorRow).where(CategoriaSetorRow.ativo.is_(True))
                    )
                    .scalars()
                    .all()
                )
                return [cls._from_row(r) for r in rows]
        except Exception as e:
            logger.error("Erro ao buscar setores: %s", e)
            return []

    @classmethod
    def get_all_incluindo_inativos(cls):
        """Retorna todos os setores (ativos e inativos). Para a interface de administração."""
        try:
            with db_module.SessionLocal() as session:
                rows = (
                    session.execute(select(CategoriaSetorRow).limit(MAX_CATEGORIAS)).scalars().all()
                )
                return [cls._from_row(r) for r in rows]
        except Exception as e:
            logger.error("Erro ao buscar setores (incluindo inativos): %s", e)
            return []

    @classmethod
    def get_by_id(cls, setor_id):
        """Busca um setor pelo ID"""
        try:
            with db_module.SessionLocal() as session:
                row = session.get(CategoriaSetorRow, _id_para_int(setor_id))
                return cls._from_row(row) if row is not None else None
        except Exception as e:
            logger.error("Erro ao buscar setor: %s", e)
            return None

    @classmethod
    def nome_existe(cls, nome_pt: str, id_atual=None) -> bool:
        """Verifica se já existe outro setor com esse nome (case-insensitive, ativo ou não).

        Args:
            nome_pt: nome a verificar
            id_atual: ID do setor sendo editado, pra não comparar consigo mesmo
        """
        nome_norm = (nome_pt or "").strip().lower()
        if not nome_norm:
            return False
        try:
            with db_module.SessionLocal() as session:
                stmt = select(CategoriaSetorRow.id).where(
                    func.lower(func.trim(CategoriaSetorRow.nome_pt)) == nome_norm
                )
                if id_atual is not None:
                    stmt = stmt.where(CategoriaSetorRow.id != _id_para_int(id_atual))
                return session.execute(stmt).first() is not None
        except Exception as e:
            logger.error("Erro ao verificar nome do setor: %s", e)
            return False


class CategoriaGate:
    """Representa um Gate do sistema (gate pai + sub-etapa).

    Valor canônico em nome_pt: 'Gate 1 - Desmontagem' (usado no formulário e no banco).
    """

    def __init__(
        self,
        nome_pt: str,
        nome_en: str = None,
        nome_es: str = None,
        descricao_pt: str = None,
        descricao_en: str = None,
        descricao_es: str = None,
        gate_pai: str = None,
        etapa: str = None,
        ordem: int = 0,
        ativo: bool = True,
        id: str = None,
        data_criacao: datetime = None,
    ):
        self.id = _id_para_int(id)
        self.nome_pt = nome_pt
        self.nome_en = nome_en or traduzir_categoria(nome_pt)["en"]
        self.nome_es = nome_es or traduzir_categoria(nome_pt)["es"]
        self.descricao_pt = descricao_pt
        self.descricao_en = descricao_en
        self.descricao_es = descricao_es
        self.gate_pai = gate_pai
        self.etapa = etapa
        self.ordem = ordem
        self.ativo = ativo
        self.data_criacao = data_criacao or datetime.now(pytz.timezone("America/Sao_Paulo"))

    def to_dict(self):
        """Converte para dicionário (compatibilidade com callers existentes)."""
        return {
            "nome_pt": self.nome_pt,
            "nome_en": self.nome_en,
            "nome_es": self.nome_es,
            "descricao_pt": self.descricao_pt,
            "descricao_en": self.descricao_en,
            "descricao_es": self.descricao_es,
            "gate_pai": self.gate_pai,
            "etapa": self.etapa,
            "ordem": self.ordem,
            "ativo": self.ativo,
            "data_criacao": self.data_criacao,
        }

    @classmethod
    def from_dict(cls, data: dict, id: str = None):
        """Cria um objeto CategoriaGate a partir de um dicionário"""
        return cls(
            nome_pt=data.get("nome_pt"),
            nome_en=data.get("nome_en"),
            nome_es=data.get("nome_es"),
            descricao_pt=data.get("descricao_pt"),
            descricao_en=data.get("descricao_en"),
            descricao_es=data.get("descricao_es"),
            gate_pai=data.get("gate_pai"),
            etapa=data.get("etapa"),
            ordem=data.get("ordem", 0),
            ativo=data.get("ativo", True),
            id=id,
            data_criacao=data.get("data_criacao"),
        )

    @classmethod
    def _from_row(cls, row: CategoriaGateRow):
        return cls(
            nome_pt=row.nome_pt,
            nome_en=row.nome_en,
            nome_es=row.nome_es,
            descricao_pt=row.descricao_pt,
            descricao_en=row.descricao_en,
            descricao_es=row.descricao_es,
            gate_pai=row.gate_pai,
            etapa=row.etapa,
            ordem=row.ordem,
            ativo=row.ativo,
            id=row.id,
            data_criacao=row.data_criacao,
        )

    def save(self):
        """Salva o gate no Postgres (insert ou update)."""
        try:
            with db_module.SessionLocal() as session, session.begin():
                if self.id:
                    row = session.get(CategoriaGateRow, self.id)
                    if row is None:
                        raise ValueError(f"Gate {self.id} não encontrado")
                else:
                    row = CategoriaGateRow()
                    session.add(row)
                row.nome_pt = self.nome_pt
                row.nome_en = self.nome_en
                row.nome_es = self.nome_es
                row.descricao_pt = self.descricao_pt
                row.descricao_en = self.descricao_en
                row.descricao_es = self.descricao_es
                row.gate_pai = self.gate_pai
                row.etapa = self.etapa
                row.ordem = self.ordem
                row.ativo = self.ativo
                session.flush()
                self.id = row.id
            logger.info("Gate %s salvo com sucesso", self.nome_pt)
            return self.id
        except Exception as e:
            logger.error("Erro ao salvar gate: %s", e)
            raise

    def delete(self):
        """Deleta o gate do Postgres. Idempotente: sem id ou já removido, retorna True."""
        try:
            if self.id:
                with db_module.SessionLocal() as session, session.begin():
                    row = session.get(CategoriaGateRow, self.id)
                    if row is not None:
                        session.delete(row)
            return True
        except Exception as e:
            logger.error("Erro ao deletar gate: %s", e)
            return False

    @classmethod
    def get_all(cls):
        """Retorna todos os gates ordenados por gate_pai + ordem (admin: inclui inativos)"""
        try:
            with db_module.SessionLocal() as session:
                rows = (
                    session.execute(select(CategoriaGateRow).limit(MAX_CATEGORIAS)).scalars().all()
                )
                gates = [cls._from_row(r) for r in rows]
                return sorted(gates, key=lambda x: (x.gate_pai or "", x.ordem))
        except Exception as e:
            logger.error("Erro ao buscar gates: %s", e)
            return []

    @classmethod
    def get_all_ativos(cls):
        """Retorna apenas gates ativos, ordenados por gate_pai + ordem (para o formulário)"""
        try:
            with db_module.SessionLocal() as session:
                rows = (
                    session.execute(
                        select(CategoriaGateRow).where(CategoriaGateRow.ativo.is_(True))
                    )
                    .scalars()
                    .all()
                )
                gates = [cls._from_row(r) for r in rows]
                return sorted(gates, key=lambda x: (x.gate_pai or "", x.ordem))
        except Exception as e:
            logger.error("Erro ao buscar gates ativos: %s", e)
            return []

    @classmethod
    def get_by_id(cls, gate_id):
        """Busca um gate pelo ID"""
        try:
            with db_module.SessionLocal() as session:
                row = session.get(CategoriaGateRow, _id_para_int(gate_id))
                return cls._from_row(row) if row is not None else None
        except Exception as e:
            logger.error("Erro ao buscar gate: %s", e)
            return None

    @classmethod
    def nome_existe(cls, nome_pt: str, id_atual=None) -> bool:
        """Verifica se já existe outro gate com esse nome_pt (case-insensitive, ativo ou não).

        nome_pt aqui é o valor composto "{gate_pai} - {etapa}" — duas combinações
        gate_pai/etapa iguais resultam no mesmo nome_pt, então checar nome_pt já
        cobre a checagem de duplicidade da combinação.
        """
        nome_norm = (nome_pt or "").strip().lower()
        if not nome_norm:
            return False
        try:
            with db_module.SessionLocal() as session:
                stmt = select(CategoriaGateRow.id).where(
                    func.lower(func.trim(CategoriaGateRow.nome_pt)) == nome_norm
                )
                if id_atual is not None:
                    stmt = stmt.where(CategoriaGateRow.id != _id_para_int(id_atual))
                return session.execute(stmt).first() is not None
        except Exception as e:
            logger.error("Erro ao verificar nome do gate: %s", e)
            return False


class CategoriaImpacto:
    """Representa um Impacto/Severidade do sistema"""

    def __init__(
        self,
        nome_pt: str,
        nome_en: str = None,
        nome_es: str = None,
        descricao_pt: str = None,
        descricao_en: str = None,
        descricao_es: str = None,
        nivel: int = 0,
        cor: str = "gray",
        ativo: bool = True,
        id: str = None,
        data_criacao: datetime = None,
    ):
        self.id = _id_para_int(id)
        self.nome_pt = nome_pt
        self.nome_en = nome_en or traduzir_categoria(nome_pt)["en"]
        self.nome_es = nome_es or traduzir_categoria(nome_pt)["es"]
        self.descricao_pt = descricao_pt
        self.descricao_en = descricao_en
        self.descricao_es = descricao_es
        self.nivel = nivel  # Ordem de severidade
        self.cor = cor  # Cor CSS válida para exibição (ex: red, orange, yellow, green, #808080)
        self.ativo = ativo
        self.data_criacao = data_criacao or datetime.now(pytz.timezone("America/Sao_Paulo"))

    def to_dict(self):
        """Converte para dicionário (compatibilidade com callers existentes)."""
        return {
            "nome_pt": self.nome_pt,
            "nome_en": self.nome_en,
            "nome_es": self.nome_es,
            "descricao_pt": self.descricao_pt,
            "descricao_en": self.descricao_en,
            "descricao_es": self.descricao_es,
            "nivel": self.nivel,
            "cor": self.cor,
            "ativo": self.ativo,
            "data_criacao": self.data_criacao,
        }

    @classmethod
    def from_dict(cls, data: dict, id: str = None):
        """Cria um objeto CategoriaImpacto a partir de um dicionário"""
        return cls(
            nome_pt=data.get("nome_pt"),
            nome_en=data.get("nome_en"),
            nome_es=data.get("nome_es"),
            descricao_pt=data.get("descricao_pt"),
            descricao_en=data.get("descricao_en"),
            descricao_es=data.get("descricao_es"),
            nivel=data.get("nivel", 0),
            cor=data.get("cor", "gray"),
            ativo=data.get("ativo", True),
            id=id,
            data_criacao=data.get("data_criacao"),
        )

    @classmethod
    def _from_row(cls, row: CategoriaImpactoRow):
        return cls(
            nome_pt=row.nome_pt,
            nome_en=row.nome_en,
            nome_es=row.nome_es,
            descricao_pt=row.descricao_pt,
            descricao_en=row.descricao_en,
            descricao_es=row.descricao_es,
            nivel=row.nivel,
            cor=row.cor,
            ativo=row.ativo,
            id=row.id,
            data_criacao=row.data_criacao,
        )

    def save(self):
        """Salva o impacto no Postgres (insert ou update)."""
        try:
            with db_module.SessionLocal() as session, session.begin():
                if self.id:
                    row = session.get(CategoriaImpactoRow, self.id)
                    if row is None:
                        raise ValueError(f"Impacto {self.id} não encontrado")
                else:
                    row = CategoriaImpactoRow()
                    session.add(row)
                row.nome_pt = self.nome_pt
                row.nome_en = self.nome_en
                row.nome_es = self.nome_es
                row.descricao_pt = self.descricao_pt
                row.descricao_en = self.descricao_en
                row.descricao_es = self.descricao_es
                row.nivel = self.nivel
                row.cor = self.cor
                row.ativo = self.ativo
                session.flush()
                self.id = row.id
            logger.info("Impacto %s salvo com sucesso", self.nome_pt)
            return self.id
        except Exception as e:
            logger.error("Erro ao salvar impacto: %s", e)
            raise

    def delete(self):
        """Deleta o impacto do Postgres. Idempotente: sem id ou já removido, retorna True."""
        try:
            if self.id:
                with db_module.SessionLocal() as session, session.begin():
                    row = session.get(CategoriaImpactoRow, self.id)
                    if row is not None:
                        session.delete(row)
            return True
        except Exception as e:
            logger.error("Erro ao deletar impacto: %s", e)
            return False

    @classmethod
    def get_all(cls):
        """Retorna todos os impactos ativos (para formulários e seletores)."""
        try:
            with db_module.SessionLocal() as session:
                rows = (
                    session.execute(
                        select(CategoriaImpactoRow).where(CategoriaImpactoRow.ativo.is_(True))
                    )
                    .scalars()
                    .all()
                )
                return [cls._from_row(r) for r in rows]
        except Exception as e:
            logger.error("Erro ao buscar impactos: %s", e)
            return []

    @classmethod
    def get_all_incluindo_inativos(cls):
        """Retorna todos os impactos (ativos e inativos). Para a interface de administração."""
        try:
            with db_module.SessionLocal() as session:
                rows = (
                    session.execute(select(CategoriaImpactoRow).limit(MAX_CATEGORIAS))
                    .scalars()
                    .all()
                )
                return [cls._from_row(r) for r in rows]
        except Exception as e:
            logger.error("Erro ao buscar impactos (incluindo inativos): %s", e)
            return []

    @classmethod
    def get_by_id(cls, impacto_id):
        """Busca um impacto pelo ID"""
        try:
            with db_module.SessionLocal() as session:
                row = session.get(CategoriaImpactoRow, _id_para_int(impacto_id))
                return cls._from_row(row) if row is not None else None
        except Exception as e:
            logger.error("Erro ao buscar impacto: %s", e)
            return None

    @classmethod
    def nome_existe(cls, nome_pt: str, id_atual=None) -> bool:
        """Verifica se já existe outro impacto com esse nome (case-insensitive, ativo ou não).

        Args:
            nome_pt: nome a verificar
            id_atual: ID do impacto sendo editado, pra não comparar consigo mesmo
        """
        nome_norm = (nome_pt or "").strip().lower()
        if not nome_norm:
            return False
        try:
            with db_module.SessionLocal() as session:
                stmt = select(CategoriaImpactoRow.id).where(
                    func.lower(func.trim(CategoriaImpactoRow.nome_pt)) == nome_norm
                )
                if id_atual is not None:
                    stmt = stmt.where(CategoriaImpactoRow.id != _id_para_int(id_atual))
                return session.execute(stmt).first() is not None
        except Exception as e:
            logger.error("Erro ao verificar nome do impacto: %s", e)
            return False
