"""
Modelo para Categorias do Sistema (Setores, Gates, Impactos).
Cada categoria é traduzida automaticamente para PT, EN e ES.
"""

import logging
from datetime import datetime

import pytz
from google.cloud.firestore_v1.base_query import FieldFilter

from app.database import db
from app.firebase_retry import firebase_retry
from app.services.translation_service import traduzir_categoria

logger = logging.getLogger(__name__)

# Chaves de cache para listas de categorias (usadas em cache_delete nas rotas)
CACHE_KEY_SETORES = "categorias_setores_list"
CACHE_KEY_GATES = "categorias_gates_list"

# Teto de segurança para stream() sem filtro — evita leitura sem limite em produção
MAX_CATEGORIAS = 1000
CACHE_KEY_IMPACTOS = "categorias_impactos_list"

# Chaves do static_cache usadas em chamados.py / __init__.py
STATIC_CACHE_KEY_SETORES = "categorias_setor"
STATIC_CACHE_KEY_GATES = "categorias_gate"
STATIC_CACHE_KEY_IMPACTOS = "categorias_impacto"


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
    ):
        self.id = id
        self.nome_pt = nome_pt
        self.nome_en = nome_en or traduzir_categoria(nome_pt)["en"]
        self.nome_es = nome_es or traduzir_categoria(nome_pt)["es"]
        self.descricao_pt = descricao_pt
        self.descricao_en = descricao_en
        self.descricao_es = descricao_es
        self.ativo = ativo
        self.data_criacao = datetime.now(pytz.timezone("America/Sao_Paulo"))

    def to_dict(self):
        """Converte para dicionário para salvar no Firestore"""
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
        )

    @firebase_retry(max_retries=3)
    def save(self):
        """Salva o setor no Firestore com retry automático"""
        try:
            if self.id:
                db.collection("categorias_setores").document(self.id).update(self.to_dict())
            else:
                self.id = db.collection("categorias_setores").add(self.to_dict())[1].id
            logger.info("Setor %s salvo com sucesso", self.nome_pt)
            return self.id
        except Exception as e:
            logger.error("Erro ao salvar setor: %s", e)
            raise

    @firebase_retry(max_retries=3)
    def delete(self):
        """Deleta o setor do Firestore com retry automático"""
        try:
            db.collection("categorias_setores").document(self.id).delete()
            return True
        except Exception as e:
            logger.error("Erro ao deletar setor: %s", e)
            return False

    @classmethod
    def get_all(cls):
        """Retorna todos os setores ativos (para formulários e seletores)."""
        try:
            docs = (
                db.collection("categorias_setores")
                .where(filter=FieldFilter("ativo", "==", True))
                .stream()
            )
            return [cls.from_dict(doc.to_dict(), doc.id) for doc in docs]
        except Exception as e:
            logger.error("Erro ao buscar setores: %s", e)
            return []

    @classmethod
    def get_all_incluindo_inativos(cls):
        """Retorna todos os setores (ativos e inativos). Para a interface de administração."""
        try:
            docs = db.collection("categorias_setores").limit(MAX_CATEGORIAS).stream()
            return [cls.from_dict(doc.to_dict(), doc.id) for doc in docs]
        except Exception as e:
            logger.error("Erro ao buscar setores (incluindo inativos): %s", e)
            return []

    @classmethod
    def get_by_id(cls, setor_id: str):
        """Busca um setor pelo ID"""
        try:
            doc = db.collection("categorias_setores").document(setor_id).get()
            if doc.exists:
                return cls.from_dict(doc.to_dict(), doc.id)
            return None
        except Exception as e:
            logger.error("Erro ao buscar setor: %s", e)
            return None

    @classmethod
    def nome_existe(cls, nome_pt: str, id_atual: str = None) -> bool:
        """Verifica se já existe outro setor com esse nome (case-insensitive, ativo ou não).

        Args:
            nome_pt: nome a verificar
            id_atual: ID do setor sendo editado, pra não comparar consigo mesmo
        """
        nome_norm = (nome_pt or "").strip().lower()
        if not nome_norm:
            return False
        try:
            docs = db.collection("categorias_setores").limit(MAX_CATEGORIAS).stream()
            for doc in docs:
                if id_atual and doc.id == id_atual:
                    continue
                if (doc.to_dict().get("nome_pt") or "").strip().lower() == nome_norm:
                    return True
            return False
        except Exception as e:
            logger.error("Erro ao verificar nome do setor: %s", e)
            return False


class CategoriaGate:
    """Representa um Gate do sistema (gate pai + sub-etapa).

    Valor canônico em nome_pt: 'Gate 1 - Desmontagem' (usado no formulário e no Firestore).
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
    ):
        self.id = id
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
        self.data_criacao = datetime.now(pytz.timezone("America/Sao_Paulo"))

    def to_dict(self):
        """Converte para dicionário para salvar no Firestore"""
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
        )

    @firebase_retry(max_retries=3)
    def save(self):
        """Salva o gate no Firestore com retry automático"""
        try:
            if self.id:
                db.collection("categorias_gates").document(self.id).update(self.to_dict())
            else:
                self.id = db.collection("categorias_gates").add(self.to_dict())[1].id
            logger.info("Gate %s salvo com sucesso", self.nome_pt)
            return self.id
        except Exception as e:
            logger.error("Erro ao salvar gate: %s", e)
            raise

    @firebase_retry(max_retries=3)
    def delete(self):
        """Deleta o gate do Firestore com retry automático"""
        try:
            db.collection("categorias_gates").document(self.id).delete()
            return True
        except Exception as e:
            logger.error("Erro ao deletar gate: %s", e)
            return False

    @classmethod
    def get_all(cls):
        """Retorna todos os gates ordenados por gate_pai + ordem (admin: inclui inativos)"""
        try:
            docs = db.collection("categorias_gates").limit(MAX_CATEGORIAS).stream()
            gates = [cls.from_dict(doc.to_dict(), doc.id) for doc in docs]
            return sorted(gates, key=lambda x: (x.gate_pai or "", x.ordem))
        except Exception as e:
            logger.error("Erro ao buscar gates: %s", e)
            return []

    @classmethod
    def get_all_ativos(cls):
        """Retorna apenas gates ativos, ordenados por gate_pai + ordem (para o formulário)"""
        try:
            docs = (
                db.collection("categorias_gates")
                .where(filter=FieldFilter("ativo", "==", True))
                .stream()
            )
            gates = [cls.from_dict(doc.to_dict(), doc.id) for doc in docs]
            return sorted(gates, key=lambda x: (x.gate_pai or "", x.ordem))
        except Exception as e:
            logger.error("Erro ao buscar gates ativos: %s", e)
            return []

    @classmethod
    def get_by_id(cls, gate_id: str):
        """Busca um gate pelo ID"""
        try:
            doc = db.collection("categorias_gates").document(gate_id).get()
            if doc.exists:
                return cls.from_dict(doc.to_dict(), doc.id)
            return None
        except Exception as e:
            logger.error("Erro ao buscar gate: %s", e)
            return None

    @classmethod
    def nome_existe(cls, nome_pt: str, id_atual: str = None) -> bool:
        """Verifica se já existe outro gate com esse nome_pt (case-insensitive, ativo ou não).

        nome_pt aqui é o valor composto "{gate_pai} - {etapa}" — duas combinações
        gate_pai/etapa iguais resultam no mesmo nome_pt, então checar nome_pt já
        cobre a checagem de duplicidade da combinação.
        """
        nome_norm = (nome_pt or "").strip().lower()
        if not nome_norm:
            return False
        try:
            docs = db.collection("categorias_gates").limit(MAX_CATEGORIAS).stream()
            for doc in docs:
                if id_atual and doc.id == id_atual:
                    continue
                if (doc.to_dict().get("nome_pt") or "").strip().lower() == nome_norm:
                    return True
            return False
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
    ):
        self.id = id
        self.nome_pt = nome_pt
        self.nome_en = nome_en or traduzir_categoria(nome_pt)["en"]
        self.nome_es = nome_es or traduzir_categoria(nome_pt)["es"]
        self.descricao_pt = descricao_pt
        self.descricao_en = descricao_en
        self.descricao_es = descricao_es
        self.nivel = nivel  # Ordem de severidade
        self.cor = cor  # Cor CSS válida para exibição (ex: red, orange, yellow, green, #808080)
        self.ativo = ativo
        self.data_criacao = datetime.now(pytz.timezone("America/Sao_Paulo"))

    def to_dict(self):
        """Converte para dicionário para salvar no Firestore"""
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
        )

    @firebase_retry(max_retries=3)
    def save(self):
        """Salva o impacto no Firestore"""
        try:
            if self.id:
                db.collection("categorias_impactos").document(self.id).update(self.to_dict())
            else:
                self.id = db.collection("categorias_impactos").add(self.to_dict())[1].id
            logger.info("Impacto %s salvo com sucesso", self.nome_pt)
            return self.id
        except Exception as e:
            logger.error("Erro ao salvar impacto: %s", e)
            raise

    @firebase_retry(max_retries=3)
    def delete(self):
        """Deleta o impacto do Firestore com retry automático"""
        try:
            db.collection("categorias_impactos").document(self.id).delete()
            return True
        except Exception as e:
            logger.error("Erro ao deletar impacto: %s", e)
            return False

    @classmethod
    def get_all(cls):
        """Retorna todos os impactos ativos (para formulários e seletores)."""
        try:
            docs = (
                db.collection("categorias_impactos")
                .where(filter=FieldFilter("ativo", "==", True))
                .stream()
            )
            return [cls.from_dict(doc.to_dict(), doc.id) for doc in docs]
        except Exception as e:
            logger.error("Erro ao buscar impactos: %s", e)
            return []

    @classmethod
    def get_all_incluindo_inativos(cls):
        """Retorna todos os impactos (ativos e inativos). Para a interface de administração."""
        try:
            docs = db.collection("categorias_impactos").limit(MAX_CATEGORIAS).stream()
            return [cls.from_dict(doc.to_dict(), doc.id) for doc in docs]
        except Exception as e:
            logger.error("Erro ao buscar impactos (incluindo inativos): %s", e)
            return []

    @classmethod
    def get_by_id(cls, impacto_id: str):
        """Busca um impacto pelo ID"""
        try:
            doc = db.collection("categorias_impactos").document(impacto_id).get()
            if doc.exists:
                return cls.from_dict(doc.to_dict(), doc.id)
            return None
        except Exception as e:
            logger.error("Erro ao buscar impacto: %s", e)
            return None

    @classmethod
    def nome_existe(cls, nome_pt: str, id_atual: str = None) -> bool:
        """Verifica se já existe outro impacto com esse nome (case-insensitive, ativo ou não).

        Args:
            nome_pt: nome a verificar
            id_atual: ID do impacto sendo editado, pra não comparar consigo mesmo
        """
        nome_norm = (nome_pt or "").strip().lower()
        if not nome_norm:
            return False
        try:
            docs = db.collection("categorias_impactos").limit(MAX_CATEGORIAS).stream()
            for doc in docs:
                if id_atual and doc.id == id_atual:
                    continue
                if (doc.to_dict().get("nome_pt") or "").strip().lower() == nome_norm:
                    return True
            return False
        except Exception as e:
            logger.error("Erro ao verificar nome do impacto: %s", e)
            return False
