import logging

from firebase_admin import firestore

from app.database import db

logger = logging.getLogger(__name__)


class GrupoRL:
    """
    Representa um grupo lógico de chamados ligados a um mesmo código RL.

    Coleção Firestore: grupos_rl
    """

    def __init__(
        self,
        rl_codigo: str,
        criado_em=None,
        criado_por_id: str | None = None,
        area: str | None = None,
        id: str | None = None,
    ):
        self.id = id
        self.rl_codigo = (rl_codigo or "").strip()
        self.criado_em = criado_em or firestore.SERVER_TIMESTAMP
        self.criado_por_id = criado_por_id
        self.area = area

    def to_dict(self) -> dict:
        return {
            "rl_codigo": self.rl_codigo,
            "criado_em": self.criado_em,
            "criado_por_id": self.criado_por_id,
            "area": self.area,
        }

    @classmethod
    def from_dict(cls, data: dict, id: str | None = None) -> "GrupoRL":
        if not data:
            raise ValueError("Dados do GrupoRL estão vazios")
        return cls(
            id=id,
            rl_codigo=data.get("rl_codigo", ""),
            criado_em=data.get("criado_em"),
            criado_por_id=data.get("criado_por_id"),
            area=data.get("area"),
        )

    @classmethod
    def get_by_rl_codigo(cls, rl_codigo: str) -> "GrupoRL | None":
        """
        Busca um grupo existente pelo código RL exato.
        """
        rl = (rl_codigo or "").strip()
        if not rl:
            return None
        try:
            docs = db.collection("grupos_rl").where("rl_codigo", "==", rl).limit(1).stream()
            for doc in docs:
                return cls.from_dict(doc.to_dict(), doc.id)
        except Exception as e:
            logger.exception("Erro ao buscar GrupoRL por rl_codigo %s: %s", rl, e)
        return None

    @classmethod
    def get_or_create(
        cls,
        rl_codigo: str,
        criado_por_id: str | None = None,
        area: str | None = None,
    ) -> "GrupoRL":
        """
        Obtém (ou cria) um GrupoRL para o código RL informado.

        - Usa rl_codigo como chave lógica do grupo (um grupo por RL).
        - Se já existir, apenas retorna o grupo existente.
        - Se não existir, cria um novo documento na coleção grupos_rl.
        """
        rl = (rl_codigo or "").strip()
        if not rl:
            raise ValueError("rl_codigo é obrigatório para criar GrupoRL")

        existente = cls.get_by_rl_codigo(rl)
        if existente:
            return existente

        try:
            grupo = cls(
                rl_codigo=rl,
                criado_em=firestore.SERVER_TIMESTAMP,
                criado_por_id=criado_por_id,
                area=area,
            )
            doc_ref = db.collection("grupos_rl").add(grupo.to_dict())
            grupo.id = doc_ref[1].id
            logger.info("GrupoRL criado para RL %s (id=%s)", rl, grupo.id)
            return grupo
        except Exception as e:
            logger.exception("Erro ao criar GrupoRL para rl_codigo %s: %s", rl, e)
            # Em caso de erro, não bloqueia o fluxo de criação do chamado;
            # apenas propaga a exceção para tratamento na camada chamadora.
            raise
