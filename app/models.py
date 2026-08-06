import logging
from contextlib import contextmanager
from datetime import datetime

import pytz
from sqlalchemy import delete, select

from app import db as db_module
from app.db.models.chamado import ChamadoObservadorRow, ChamadoParticipanteRow, ChamadoRow
from app.exceptions import ValidacaoChamadoError

logger = logging.getLogger(__name__)


class Chamado:
    """Representação de um chamado (linha da tabela `chamados` no Postgres)."""

    def __init__(
        self,
        categoria: str,
        tipo_solicitacao: str,
        descricao: str,
        responsavel: str,
        solicitante_id: str = None,
        solicitante_nome: str = None,
        area: str = None,
        rl_codigo: str = None,
        gate: str = None,
        impacto: str = None,
        anexo: str = None,
        anexos: list = None,
        numero_chamado: str = None,
        prioridade: int = 1,
        status: str = "Aberto",
        data_abertura=None,
        data_conclusao=None,
        responsavel_id: str = None,
        motivo_atribuicao: str = None,
        setores_adicionais: list = None,
        motivo_cancelamento: str = None,
        data_cancelamento=None,
        grupo_rl_id: str = None,
        sla_dias: int = None,
        confirmacao_solicitante: str = None,
        id: str = None,
        # Fase 2 — Escalonamento SLA
        supervisor_ids_com_acesso: list = None,
        data_em_atendimento=None,
        escalacao_resposta_nivel: int = 0,
        participantes: list = None,
        # Fase 3 — Transferência e escalada
        motivo_ultima_escalacao: str = None,
        # Fase 7 — Escada B (resolução)
        escalacao_resolucao_nivel: int = 0,
        alerta_supervisor_50_enviado: bool = False,
        alerta_supervisor_80_enviado: bool = False,
        # Lembretes de confirmação de resolução (24h/48h após Concluído)
        lembrete_confirmacao_1_enviado: bool = False,
        lembrete_confirmacao_2_enviado: bool = False,
        alerta_prazo_24h_enviado_em=None,
        reaberturas_solicitante_count: int = 0,
        # Nível 1 — Observadores (em cópia, read-only)
        observadores: list = None,
        # Previsão de atendimento — suspende e-mails de escalonamento (Escada A/B) até a data
        previsao_atendimento=None,
        motivo_previsao_atendimento: str = None,
    ):
        self.id = id
        self.numero_chamado = numero_chamado
        self.categoria = categoria
        self.setores_adicionais = (
            setores_adicionais or []
        )  # Setores adicionados pelo supervisor (ex.: Material, Engenharia)
        self.motivo_cancelamento = motivo_cancelamento  # Obrigatório quando status == 'Cancelado'
        self.data_cancelamento = data_cancelamento
        self.rl_codigo = rl_codigo
        self.grupo_rl_id = grupo_rl_id  # Referência ao grupo lógico de RL (coleção grupos_rl)
        self.sla_dias = sla_dias  # SLA personalizado em dias (None = padrão por categoria)
        self.confirmacao_solicitante = (
            confirmacao_solicitante  # None | "pendente" | "confirmado" | "reaberto"
        )
        # Prioridade centralizada: AOG = -1 (acima de tudo), Projetos = 0, demais = informado ou 1
        self.prioridade = (
            -1
            if categoria == "AOG"
            else 0
            if categoria == "Projetos"
            else (prioridade if prioridade is not None else 1)
        )
        self.tipo_solicitacao = tipo_solicitacao
        self.gate = gate
        self.impacto = impacto
        self.descricao = descricao
        self.anexo = anexo
        self.anexos = anexos or []
        self.responsavel = responsavel
        self.responsavel_id = responsavel_id  # ID do responsável (supervisor ou solicitante)
        self.motivo_atribuicao = motivo_atribuicao  # Como foi atribuído (automático/manual)
        self.solicitante_id = solicitante_id  # ID do usuário que criou o chamado
        self.solicitante_nome = solicitante_nome  # Nome do solicitante para rastreamento
        self.area = area  # Área/setor para filtragem de supervisores
        self.status = status
        # Sem valor: server_default=func.now() na coluna Postgres cobre o timestamp
        # de criação — não precisa de um sentinel aqui como na era Firestore.
        self.data_abertura = data_abertura
        self.data_conclusao = data_conclusao
        # Fase 2 — Escalonamento SLA
        self.supervisor_ids_com_acesso = supervisor_ids_com_acesso or []
        self.data_em_atendimento = data_em_atendimento
        self.escalacao_resposta_nivel = (
            escalacao_resposta_nivel if escalacao_resposta_nivel is not None else 0
        )
        self.participantes = participantes or []
        # Fase 3 — Transferência e escalada
        self.motivo_ultima_escalacao = motivo_ultima_escalacao
        # Fase 7 — Escada B (resolução)
        self.escalacao_resolucao_nivel = (
            escalacao_resolucao_nivel if escalacao_resolucao_nivel is not None else 0
        )
        self.alerta_supervisor_50_enviado = bool(alerta_supervisor_50_enviado)
        self.alerta_supervisor_80_enviado = bool(alerta_supervisor_80_enviado)
        self.lembrete_confirmacao_1_enviado = bool(lembrete_confirmacao_1_enviado)
        self.lembrete_confirmacao_2_enviado = bool(lembrete_confirmacao_2_enviado)
        self.alerta_prazo_24h_enviado_em = alerta_prazo_24h_enviado_em
        self.reaberturas_solicitante_count = (
            reaberturas_solicitante_count if reaberturas_solicitante_count is not None else 0
        )
        # Nível 1 — Observadores (em cópia, read-only): [{usuario_id, nome, email}]
        self.observadores = observadores if isinstance(observadores, list) else []
        # Previsão de atendimento — suspende e-mails de escalonamento (Escada A/B) até a data
        self.previsao_atendimento = previsao_atendimento
        self.motivo_previsao_atendimento = motivo_previsao_atendimento

    def _converter_timestamp(self, ts):
        """Converte timestamp (datetime, ou qualquer objeto tipo-Timestamp com
        .to_pydatetime()) para datetime em horário de Brasília. Tolera tipos
        inesperados (string, etc.) e retorna None em caso de falha.
        """
        if ts is None:
            return None
        try:
            # Se já for datetime, retorna
            if isinstance(ts, datetime):
                # Se não tiver timezone, assume UTC e converte para Brasília
                if ts.tzinfo is None:
                    ts = pytz.utc.localize(ts)
                return ts.astimezone(pytz.timezone("America/Sao_Paulo"))
            # Objetos tipo-Timestamp (ex.: pandas.Timestamp) expõem to_pydatetime()
            if hasattr(ts, "to_pydatetime"):
                dt = ts.to_pydatetime()
                # Assume UTC quando o objeto não carrega timezone
                if dt.tzinfo is None:
                    dt = pytz.utc.localize(dt)
                return dt.astimezone(pytz.timezone("America/Sao_Paulo"))
            return None
        except Exception:
            return None

    def data_abertura_formatada(self):
        """Retorna data_abertura formatada como string"""
        dt = self._converter_timestamp(self.data_abertura)
        if dt and isinstance(dt, datetime):
            return dt.strftime("%d/%m/%Y %H:%M")
        return "-"

    def data_conclusao_formatada(self):
        """Retorna data_conclusao formatada como string"""
        dt = self._converter_timestamp(self.data_conclusao)
        if dt and isinstance(dt, datetime):
            return dt.strftime("%d/%m/%Y %H:%M")
        return "-"

    def data_cancelamento_formatada(self):
        """Retorna data_cancelamento formatada como string"""
        dt = self._converter_timestamp(self.data_cancelamento)
        if dt and isinstance(dt, datetime):
            return dt.strftime("%d/%m/%Y %H:%M")
        return "-"

    def previsao_atendimento_formatada(self):
        """Retorna previsao_atendimento formatada como string"""
        dt = self._converter_timestamp(self.previsao_atendimento)
        if dt and isinstance(dt, datetime):
            return dt.strftime("%d/%m/%Y %H:%M")
        return "-"

    def to_dict(self):
        """Converte para dicionário (serialização para templates, notificações, exports)."""
        return {
            "numero_chamado": self.numero_chamado,
            "categoria": self.categoria,
            "rl_codigo": self.rl_codigo,
            "prioridade": self.prioridade,
            "tipo_solicitacao": self.tipo_solicitacao,
            "gate": self.gate,
            "impacto": self.impacto,
            "descricao": self.descricao,
            "anexo": self.anexo,
            "anexos": self.anexos,
            "responsavel": self.responsavel,
            "responsavel_id": self.responsavel_id,
            "motivo_atribuicao": self.motivo_atribuicao,
            "solicitante_id": self.solicitante_id,
            "solicitante_nome": self.solicitante_nome,
            "area": self.area,
            "status": self.status,
            "data_abertura": self.data_abertura,
            "data_conclusao": self.data_conclusao,
            "setores_adicionais": self.setores_adicionais,
            "motivo_cancelamento": self.motivo_cancelamento,
            "data_cancelamento": self.data_cancelamento,
            "grupo_rl_id": self.grupo_rl_id,
            "sla_dias": self.sla_dias,
            "confirmacao_solicitante": self.confirmacao_solicitante,
            # Fase 2 — Escalonamento SLA
            "supervisor_ids_com_acesso": self.supervisor_ids_com_acesso,
            "data_em_atendimento": self.data_em_atendimento,
            "escalacao_resposta_nivel": self.escalacao_resposta_nivel,
            "participantes": self.participantes,
            # Fase 3 — Transferência e escalada
            "motivo_ultima_escalacao": self.motivo_ultima_escalacao,
            # Fase 7 — Escada B (resolução)
            "escalacao_resolucao_nivel": self.escalacao_resolucao_nivel,
            "alerta_supervisor_50_enviado": self.alerta_supervisor_50_enviado,
            "alerta_supervisor_80_enviado": self.alerta_supervisor_80_enviado,
            "lembrete_confirmacao_1_enviado": self.lembrete_confirmacao_1_enviado,
            "lembrete_confirmacao_2_enviado": self.lembrete_confirmacao_2_enviado,
            "alerta_prazo_24h_enviado_em": self.alerta_prazo_24h_enviado_em,
            "reaberturas_solicitante_count": self.reaberturas_solicitante_count,
            # Nível 1 — Observadores (em cópia)
            "observadores": self.observadores,
            # Previsão de atendimento
            "previsao_atendimento": self.previsao_atendimento,
            "motivo_previsao_atendimento": self.motivo_previsao_atendimento,
        }

    @classmethod
    def from_dict(cls, data: dict, id: str = None):
        """Cria um objeto Chamado a partir de um dicionário (ver to_dict()).
        Usa valores padrão para campos ausentes (registros antigos ou migrados).
        Raises:
            ValidacaoChamadoError: Se dados estiverem vazios.
        """
        if not data:
            raise ValidacaoChamadoError("Dados do chamado estão vazios")

        # Garante strings para campos usados em exibição (evita None em templates)
        def _str(v):
            return v if v is not None else ""

        return cls(
            id=id,
            numero_chamado=data.get("numero_chamado"),
            categoria=_str(data.get("categoria")),
            rl_codigo=_str(data.get("rl_codigo")),
            prioridade=data.get("prioridade", 1),
            tipo_solicitacao=_str(data.get("tipo_solicitacao")),
            gate=data.get("gate"),
            impacto=data.get("impacto"),
            descricao=_str(data.get("descricao")),
            anexo=data.get("anexo"),
            anexos=data.get("anexos") if isinstance(data.get("anexos"), list) else [],
            responsavel=_str(data.get("responsavel")),
            responsavel_id=data.get("responsavel_id"),
            motivo_atribuicao=data.get("motivo_atribuicao"),
            solicitante_id=data.get("solicitante_id"),
            solicitante_nome=data.get("solicitante_nome"),
            area=data.get("area"),
            status=data.get("status", "Aberto"),
            data_abertura=data.get("data_abertura"),
            data_conclusao=data.get("data_conclusao"),
            setores_adicionais=data.get("setores_adicionais")
            if isinstance(data.get("setores_adicionais"), list)
            else [],
            motivo_cancelamento=data.get("motivo_cancelamento"),
            data_cancelamento=data.get("data_cancelamento"),
            grupo_rl_id=data.get("grupo_rl_id"),
            sla_dias=data.get("sla_dias"),
            confirmacao_solicitante=data.get("confirmacao_solicitante"),
            # Fase 2 — Escalonamento SLA
            supervisor_ids_com_acesso=data.get("supervisor_ids_com_acesso")
            if isinstance(data.get("supervisor_ids_com_acesso"), list)
            else [],
            data_em_atendimento=data.get("data_em_atendimento"),
            escalacao_resposta_nivel=data.get("escalacao_resposta_nivel", 0),
            participantes=data.get("participantes")
            if isinstance(data.get("participantes"), list)
            else [],
            # Fase 3 — Transferência e escalada
            motivo_ultima_escalacao=data.get("motivo_ultima_escalacao"),
            # Fase 7 — Escada B (resolução)
            escalacao_resolucao_nivel=data.get("escalacao_resolucao_nivel", 0),
            alerta_supervisor_50_enviado=data.get("alerta_supervisor_50_enviado", False),
            alerta_supervisor_80_enviado=data.get("alerta_supervisor_80_enviado", False),
            lembrete_confirmacao_1_enviado=data.get("lembrete_confirmacao_1_enviado", False),
            lembrete_confirmacao_2_enviado=data.get("lembrete_confirmacao_2_enviado", False),
            alerta_prazo_24h_enviado_em=data.get("alerta_prazo_24h_enviado_em"),
            reaberturas_solicitante_count=data.get("reaberturas_solicitante_count", 0),
            # Nível 1 — Observadores (em cópia)
            observadores=data.get("observadores")
            if isinstance(data.get("observadores"), list)
            else [],
            # Previsão de atendimento
            previsao_atendimento=data.get("previsao_atendimento"),
            motivo_previsao_atendimento=data.get("motivo_previsao_atendimento"),
        )

    def to_row_kwargs(self) -> dict:
        """Campos escalares pra insert/update em ChamadoRow — participantes/
        observadores são sincronizados à parte (tabela-junção, ver salvar())."""
        return {
            "numero_chamado": self.numero_chamado,
            "categoria": self.categoria,
            "tipo_solicitacao": self.tipo_solicitacao,
            "descricao": self.descricao,
            "responsavel": self.responsavel,
            "responsavel_id": self.responsavel_id,
            "motivo_atribuicao": self.motivo_atribuicao,
            "solicitante_id": self.solicitante_id,
            "solicitante_nome": self.solicitante_nome,
            "area": self.area,
            "rl_codigo": self.rl_codigo,
            "grupo_rl_id": self.grupo_rl_id,
            "gate": self.gate,
            "impacto": self.impacto,
            "anexo": self.anexo,
            "anexos": self.anexos,
            "setores_adicionais": self.setores_adicionais,
            "supervisor_ids_com_acesso": self.supervisor_ids_com_acesso,
            "prioridade": self.prioridade,
            "status": self.status,
            "data_conclusao": self.data_conclusao,
            "data_cancelamento": self.data_cancelamento,
            "data_em_atendimento": self.data_em_atendimento,
            "previsao_atendimento": self.previsao_atendimento,
            "motivo_previsao_atendimento": self.motivo_previsao_atendimento,
            "motivo_cancelamento": self.motivo_cancelamento,
            "motivo_ultima_escalacao": self.motivo_ultima_escalacao,
            "sla_dias": self.sla_dias,
            "confirmacao_solicitante": self.confirmacao_solicitante,
            "escalacao_resposta_nivel": self.escalacao_resposta_nivel,
            "escalacao_resolucao_nivel": self.escalacao_resolucao_nivel,
            "alerta_supervisor_50_enviado": self.alerta_supervisor_50_enviado,
            "alerta_supervisor_80_enviado": self.alerta_supervisor_80_enviado,
            "lembrete_confirmacao_1_enviado": self.lembrete_confirmacao_1_enviado,
            "lembrete_confirmacao_2_enviado": self.lembrete_confirmacao_2_enviado,
            "alerta_prazo_24h_enviado_em": self.alerta_prazo_24h_enviado_em,
            "reaberturas_solicitante_count": self.reaberturas_solicitante_count,
        }

    @classmethod
    def _from_row(cls, row: ChamadoRow, participantes=None, observadores=None) -> "Chamado":
        return cls(
            id=row.id,
            numero_chamado=row.numero_chamado,
            categoria=row.categoria,
            tipo_solicitacao=row.tipo_solicitacao,
            descricao=row.descricao,
            responsavel=row.responsavel,
            responsavel_id=row.responsavel_id,
            motivo_atribuicao=row.motivo_atribuicao,
            solicitante_id=row.solicitante_id,
            solicitante_nome=row.solicitante_nome,
            area=row.area,
            rl_codigo=row.rl_codigo,
            grupo_rl_id=row.grupo_rl_id,
            gate=row.gate,
            impacto=row.impacto,
            anexo=row.anexo,
            anexos=list(row.anexos or []),
            prioridade=row.prioridade,
            status=row.status,
            data_abertura=row.data_abertura,
            data_conclusao=row.data_conclusao,
            setores_adicionais=list(row.setores_adicionais or []),
            motivo_cancelamento=row.motivo_cancelamento,
            data_cancelamento=row.data_cancelamento,
            sla_dias=row.sla_dias,
            confirmacao_solicitante=row.confirmacao_solicitante,
            supervisor_ids_com_acesso=list(row.supervisor_ids_com_acesso or []),
            data_em_atendimento=row.data_em_atendimento,
            escalacao_resposta_nivel=row.escalacao_resposta_nivel,
            participantes=participantes or [],
            motivo_ultima_escalacao=row.motivo_ultima_escalacao,
            escalacao_resolucao_nivel=row.escalacao_resolucao_nivel,
            alerta_supervisor_50_enviado=row.alerta_supervisor_50_enviado,
            alerta_supervisor_80_enviado=row.alerta_supervisor_80_enviado,
            lembrete_confirmacao_1_enviado=row.lembrete_confirmacao_1_enviado,
            lembrete_confirmacao_2_enviado=row.lembrete_confirmacao_2_enviado,
            alerta_prazo_24h_enviado_em=row.alerta_prazo_24h_enviado_em,
            reaberturas_solicitante_count=row.reaberturas_solicitante_count,
            observadores=observadores or [],
            previsao_atendimento=row.previsao_atendimento,
            motivo_previsao_atendimento=row.motivo_previsao_atendimento,
        )

    @staticmethod
    def _carregar_participantes(session, chamado_id: int) -> list[dict]:
        rows = (
            session.execute(
                select(ChamadoParticipanteRow).where(
                    ChamadoParticipanteRow.chamado_id == chamado_id
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "supervisor_id": r.supervisor_id,
                "area": r.area,
                "status": r.status,
                "concluido_em": r.concluido_em,
            }
            for r in rows
        ]

    @staticmethod
    def _carregar_observadores(session, chamado_id: int) -> list[dict]:
        rows = (
            session.execute(
                select(ChamadoObservadorRow).where(ChamadoObservadorRow.chamado_id == chamado_id)
            )
            .scalars()
            .all()
        )
        return [{"usuario_id": r.usuario_id, "nome": r.nome, "email": r.email} for r in rows]

    @classmethod
    def get_by_id(cls, chamado_id) -> "Chamado | None":
        """Busca um chamado pelo ID, com participantes/observadores carregados."""
        try:
            cid = int(chamado_id)
        except (TypeError, ValueError):
            return None
        try:
            with db_module.SessionLocal() as session:
                row = session.get(ChamadoRow, cid)
                if row is None:
                    return None
                participantes = cls._carregar_participantes(session, cid)
                observadores = cls._carregar_observadores(session, cid)
                return cls._from_row(row, participantes, observadores)
        except Exception as e:
            logger.exception("Erro ao buscar chamado %s: %s", chamado_id, e)
            return None

    @classmethod
    @contextmanager
    def editar_com_lock(cls, chamado_id):
        """Carrega o chamado travando a linha (SELECT ... FOR UPDATE) e, ao sair
        do bloco `with` sem exceção, persiste os campos + participantes/
        observadores dentro da MESMA transação.

        Serializa mutações concorrentes no mesmo chamado (ex: um participante
        chamando concluir_minha_parte enquanto o owner chama incluir_participantes)
        — sem isso, salvar() fazia delete-all+reinsert de participantes/observadores
        a partir de um snapshot Python já desatualizado, e a escrita que committasse
        por último apagava silenciosamente a mudança da outra (achado em auditoria,
        2026-08-05). Em caso de exceção dentro do bloco, a transação é revertida e
        nada é persistido.

        Uso:
            with Chamado.editar_com_lock(chamado_id) as chamado:
                if chamado is None:
                    ...  # não encontrado
                chamado.participantes = [...]
        """
        try:
            cid = int(chamado_id)
        except (TypeError, ValueError):
            yield None
            return
        with db_module.SessionLocal() as session, session.begin():
            row = session.execute(
                select(ChamadoRow).where(ChamadoRow.id == cid).with_for_update()
            ).scalar_one_or_none()
            if row is None:
                yield None
                return
            participantes = cls._carregar_participantes(session, cid)
            observadores = cls._carregar_observadores(session, cid)
            chamado = cls._from_row(row, participantes, observadores)
            yield chamado
            for k, v in chamado.to_row_kwargs().items():
                setattr(row, k, v)
            chamado._sincronizar_participantes(session)
            chamado._sincronizar_observadores(session)

    def _sincronizar_participantes(self, session) -> None:
        """Substitui todos os participantes do chamado pelo estado atual de
        self.participantes (delete-all + reinsert — a lista é sempre o
        estado completo desejado, não um delta)."""
        session.execute(
            delete(ChamadoParticipanteRow).where(ChamadoParticipanteRow.chamado_id == self.id)
        )
        for p in self.participantes:
            session.add(
                ChamadoParticipanteRow(
                    chamado_id=self.id,
                    supervisor_id=p["supervisor_id"],
                    area=p.get("area"),
                    status=p.get("status") or "pendente",
                    concluido_em=p.get("concluido_em"),
                )
            )

    def _sincronizar_observadores(self, session) -> None:
        """Substitui todos os observadores do chamado pelo estado atual de
        self.observadores (delete-all + reinsert)."""
        session.execute(
            delete(ChamadoObservadorRow).where(ChamadoObservadorRow.chamado_id == self.id)
        )
        for o in self.observadores:
            session.add(
                ChamadoObservadorRow(
                    chamado_id=self.id,
                    usuario_id=o["usuario_id"],
                    nome=o.get("nome") or "",
                    email=o.get("email") or "",
                )
            )

    def salvar(self) -> int | None:
        """Insere (sem id) ou atualiza (com id) o chamado, sincronizando
        participantes/observadores pro estado atual do objeto Python.
        Retorna o id (novo ou existente), ou None em falha."""
        try:
            with db_module.SessionLocal() as session, session.begin():
                if self.id:
                    row = session.get(ChamadoRow, self.id)
                    if row is None:
                        raise ValueError(f"Chamado {self.id} não encontrado")
                else:
                    row = ChamadoRow()
                    session.add(row)
                for k, v in self.to_row_kwargs().items():
                    setattr(row, k, v)
                session.flush()
                self.id = row.id
                if row.data_abertura:
                    self.data_abertura = row.data_abertura
                self._sincronizar_participantes(session)
                self._sincronizar_observadores(session)
            return self.id
        except Exception as e:
            logger.exception("Erro ao salvar chamado %s: %s", self.id, e)
            return None

    def atualizar_campos(self, **kwargs) -> bool:
        """Atualiza campos escalares específicos (equivalente ao antigo
        db.collection('chamados').document(id).update(...)). Não mexe em
        participantes/observadores — use salvar() ou os métodos dedicados."""
        if not self.id:
            return False
        campos_validos = set(self.to_row_kwargs().keys())
        alteracoes = {k: v for k, v in kwargs.items() if k in campos_validos}
        if not alteracoes:
            return False
        try:
            with db_module.SessionLocal() as session, session.begin():
                row = session.get(ChamadoRow, self.id)
                if row is None:
                    return False
                for k, v in alteracoes.items():
                    setattr(row, k, v)
                    setattr(self, k, v)
            return True
        except Exception as e:
            logger.exception("Erro ao atualizar chamado %s: %s", self.id, e)
            return False

    def deletar(self) -> bool:
        """Remove o chamado (participantes/observadores somem via ON DELETE CASCADE)."""
        try:
            with db_module.SessionLocal() as session, session.begin():
                row = session.get(ChamadoRow, self.id)
                if row is not None:
                    session.delete(row)
            return True
        except Exception as e:
            logger.exception("Erro ao deletar chamado %s: %s", self.id, e)
            return False

    def __repr__(self):
        return f"<Chamado {self.id} - {self.categoria}>"
