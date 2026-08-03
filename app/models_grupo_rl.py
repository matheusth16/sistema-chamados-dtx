import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app import db as db_module
from app.db.models.grupo_rl import GrupoRLRow

logger = logging.getLogger(__name__)


class GrupoRL:
    """
    Representa um grupo lógico de chamados ligados a um mesmo código RL.

    Fase 2: armazenamento migrado de Firestore para PostgreSQL. rl_codigo é
    UNIQUE no banco — get_or_create() usa upsert atômico (ON CONFLICT DO
    NOTHING), eliminando a race condition do antigo check-then-act.
    """

    def __init__(
        self,
        rl_codigo: str,
        criado_em=None,
        criado_por_id: str | None = None,
        area: str | None = None,
        id: int | None = None,
    ):
        self.id = int(id) if id is not None else None
        self.rl_codigo = (rl_codigo or "").strip()
        self.criado_em = criado_em
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
    def from_dict(cls, data: dict, id: int | None = None) -> "GrupoRL":
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
    def _from_row(cls, row: GrupoRLRow) -> "GrupoRL":
        return cls(
            id=row.id,
            rl_codigo=row.rl_codigo,
            criado_em=row.criado_em,
            criado_por_id=row.criado_por_id,
            area=row.area,
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
            with db_module.SessionLocal() as session:
                row = session.execute(
                    select(GrupoRLRow).where(GrupoRLRow.rl_codigo == rl)
                ).scalar_one_or_none()
                return cls._from_row(row) if row is not None else None
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
        Obtém (ou cria) um GrupoRL para o código RL informado — atômico.

        - rl_codigo é UNIQUE no banco: usa INSERT ... ON CONFLICT DO NOTHING
          + SELECT se não houve insert, sem janela de corrida entre "checar
          se existe" e "criar" (o antigo comportamento no Firestore).
        - Se já existir, retorna o grupo existente SEM atualizar seus dados
          (criado_por_id/area do request atual são ignorados nesse caso).
        """
        rl = (rl_codigo or "").strip()
        if not rl:
            raise ValueError("rl_codigo é obrigatório para criar GrupoRL")

        try:
            with db_module.SessionLocal() as session, session.begin():
                stmt = (
                    pg_insert(GrupoRLRow)
                    .values(rl_codigo=rl, criado_por_id=criado_por_id, area=area)
                    .on_conflict_do_nothing(index_elements=["rl_codigo"])
                    .returning(GrupoRLRow)
                )
                row = session.execute(stmt).scalar_one_or_none()
                if row is None:
                    row = session.execute(
                        select(GrupoRLRow).where(GrupoRLRow.rl_codigo == rl)
                    ).scalar_one()
                grupo = cls._from_row(row)
            logger.info("GrupoRL obtido/criado para RL %s (id=%s)", rl, grupo.id)
            return grupo
        except Exception as e:
            logger.exception("Erro ao criar/obter GrupoRL para rl_codigo %s: %s", rl, e)
            # Em caso de erro, não bloqueia o fluxo de criação do chamado;
            # apenas propaga a exceção para tratamento na camada chamadora.
            raise
