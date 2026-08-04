import logging
from datetime import datetime

import pytz
from sqlalchemy import select

from app import db as db_module
from app.db.models.historico import HistoricoRow

logger = logging.getLogger(__name__)


class Historico:
    """Representação do histórico de alterações em um chamado"""

    def __init__(
        self,
        chamado_id: int,
        usuario_id: str,
        usuario_nome: str,
        acao: str,  # 'criacao', 'alteracao_status', 'alteracao_dados'
        campo_alterado: str = None,
        valor_anterior=None,
        valor_novo=None,
        data_acao=None,
        detalhe: str = None,
        id: int = None,
    ):
        self.id = id
        self.chamado_id = chamado_id
        self.usuario_id = usuario_id
        self.usuario_nome = usuario_nome
        self.acao = acao
        self.campo_alterado = campo_alterado
        self.valor_anterior = valor_anterior
        self.valor_novo = valor_novo
        self.data_acao = data_acao
        self.detalhe = detalhe  # ex: nome do arquivo anexado para exibição

    def to_row_kwargs(self) -> dict:
        """Campos pra insert em HistoricoRow (registro é sempre criado, nunca
        atualizado — histórico é um log de auditoria imutável). chamado_id
        aceita str (rotas Flask/form ainda repassam string em vários call
        sites) — coage pra int aqui, ponto único de conversão."""
        return {
            "chamado_id": int(self.chamado_id),
            "usuario_id": self.usuario_id,
            "usuario_nome": self.usuario_nome,
            "acao": self.acao,
            "campo_alterado": self.campo_alterado,
            "valor_anterior": self.valor_anterior,
            "valor_novo": self.valor_novo,
            "detalhe": self.detalhe,
        }

    @classmethod
    def _from_row(cls, row: HistoricoRow) -> "Historico":
        return cls(
            id=row.id,
            chamado_id=row.chamado_id,
            usuario_id=row.usuario_id,
            usuario_nome=row.usuario_nome,
            acao=row.acao,
            campo_alterado=row.campo_alterado,
            valor_anterior=row.valor_anterior,
            valor_novo=row.valor_novo,
            data_acao=row.data_acao,
            detalhe=row.detalhe,
        )

    def save(self) -> bool:
        """Insere o registro de histórico no Postgres. Retorna True/False."""
        try:
            with db_module.SessionLocal() as session, session.begin():
                row = HistoricoRow(**self.to_row_kwargs())
                session.add(row)
                session.flush()
                self.id = row.id
                if row.data_acao:
                    self.data_acao = row.data_acao
            logger.debug("Histórico salvo: chamado=%s, acao=%s", self.chamado_id, self.acao)
            return True
        except Exception as e:
            logger.exception("Erro ao salvar histórico: %s", e)
            return False

    @classmethod
    def salvar_lote(cls, historicos: list["Historico"]) -> bool:
        """Insere vários registros de histórico numa única transação
        (N writes → 1 round-trip, equivalente ao antigo batch do Firestore).
        Retorna True/False; em falha, nenhum registro é persistido."""
        if not historicos:
            return True
        try:
            with db_module.SessionLocal() as session, session.begin():
                rows = [HistoricoRow(**h.to_row_kwargs()) for h in historicos]
                session.add_all(rows)
                session.flush()
                for h, row in zip(historicos, rows, strict=True):
                    h.id = row.id
                    if row.data_acao:
                        h.data_acao = row.data_acao
            return True
        except Exception as e:
            logger.exception("Erro ao salvar lote de histórico: %s", e)
            return False

    @classmethod
    def get_by_chamado_id(cls, chamado_id) -> list["Historico"]:
        """Busca histórico de um chamado específico, mais recente primeiro."""
        try:
            cid = int(chamado_id)
        except (TypeError, ValueError):
            return []
        try:
            with db_module.SessionLocal() as session:
                rows = (
                    session.execute(
                        select(HistoricoRow)
                        .where(HistoricoRow.chamado_id == cid)
                        .order_by(HistoricoRow.data_acao.desc(), HistoricoRow.id.desc())
                    )
                    .scalars()
                    .all()
                )
                return [cls._from_row(row) for row in rows]
        except Exception as e:
            logger.exception("Erro ao buscar histórico do chamado %s: %s", chamado_id, e)
            return []

    def _converter_timestamp(self, ts):
        """Converte timestamp para datetime em horário de Brasília"""
        if ts is None:
            return None
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                ts = pytz.utc.localize(ts)
            return ts.astimezone(pytz.timezone("America/Sao_Paulo"))
        return ts

    def data_acao_formatada(self):
        """Retorna data_acao formatada como string"""
        dt = self._converter_timestamp(self.data_acao)
        if dt and isinstance(dt, datetime):
            return dt.strftime("%d/%m/%Y %H:%M:%S")
        return "-"

    def __repr__(self):
        return f"<Historico {self.chamado_id} - {self.acao}>"
