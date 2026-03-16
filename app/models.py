from datetime import datetime

import pytz
from firebase_admin import firestore

from app.exceptions import ValidacaoChamadoError


class Chamado:
    """Representação de um documento Chamado no Firestore"""

    def __init__(self,
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
                 status: str = 'Aberto',
                 data_abertura = None,
                 data_conclusao = None,
                 responsavel_id: str = None,
                 motivo_atribuicao: str = None,
                 setores_adicionais: list = None,
                 motivo_cancelamento: str = None,
                 data_cancelamento = None,
                 grupo_rl_id: str = None,
                 sla_dias: int = None,
                 id: str = None):

        self.id = id
        self.numero_chamado = numero_chamado
        self.categoria = categoria
        self.setores_adicionais = setores_adicionais or []  # Setores adicionados pelo supervisor (ex.: Material, Engenharia)
        self.motivo_cancelamento = motivo_cancelamento  # Obrigatório quando status == 'Cancelado'
        self.data_cancelamento = data_cancelamento
        self.rl_codigo = rl_codigo
        self.grupo_rl_id = grupo_rl_id  # Referência ao grupo lógico de RL (coleção grupos_rl)
        self.sla_dias = sla_dias  # SLA personalizado em dias (None = padrão por categoria)
        # Prioridade centralizada: Projetos = 0, demais = informado ou 1
        self.prioridade = 0 if categoria == 'Projetos' else (prioridade if prioridade is not None else 1)
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
        self.data_abertura = data_abertura or firestore.SERVER_TIMESTAMP
        self.data_conclusao = data_conclusao

    def _converter_timestamp(self, ts):
        """Converte timestamp do Firestore para datetime em horário de Brasília.
        Tolera tipos inesperados (string, etc.) e retorna None em caso de falha.
        """
        if ts is None or ts == firestore.SERVER_TIMESTAMP:
            return None
        try:
            # Se já for datetime, retorna
            if isinstance(ts, datetime):
                # Se não tiver timezone, assume UTC e converte para Brasília
                if ts.tzinfo is None:
                    ts = pytz.utc.localize(ts)
                return ts.astimezone(pytz.timezone('America/Sao_Paulo'))
            # Se for Timestamp do Firestore, converte para datetime
            if hasattr(ts, 'to_pydatetime'):
                dt = ts.to_pydatetime()
                # Firestore timestamps são UTC, então convertemos para Brasília
                if dt.tzinfo is None:
                    dt = pytz.utc.localize(dt)
                return dt.astimezone(pytz.timezone('America/Sao_Paulo'))
            return None
        except Exception:
            return None

    def data_abertura_formatada(self):
        """Retorna data_abertura formatada como string"""
        dt = self._converter_timestamp(self.data_abertura)
        if dt and isinstance(dt, datetime):
            return dt.strftime('%d/%m/%Y %H:%M')
        return '-'

    def data_conclusao_formatada(self):
        """Retorna data_conclusao formatada como string"""
        dt = self._converter_timestamp(self.data_conclusao)
        if dt and isinstance(dt, datetime):
            return dt.strftime('%d/%m/%Y %H:%M')
        return '-'

    def data_cancelamento_formatada(self):
        """Retorna data_cancelamento formatada como string"""
        dt = self._converter_timestamp(self.data_cancelamento)
        if dt and isinstance(dt, datetime):
            return dt.strftime('%d/%m/%Y %H:%M')
        return '-'

    def to_dict(self):
        """Converte para dicionário para salvar no Firestore"""
        return {
            'numero_chamado': self.numero_chamado,
            'categoria': self.categoria,
            'rl_codigo': self.rl_codigo,
            'prioridade': self.prioridade,
            'tipo_solicitacao': self.tipo_solicitacao,
            'gate': self.gate,
            'impacto': self.impacto,
            'descricao': self.descricao,
            'anexo': self.anexo,
            'anexos': self.anexos,
            'responsavel': self.responsavel,
            'responsavel_id': self.responsavel_id,
            'motivo_atribuicao': self.motivo_atribuicao,
            'solicitante_id': self.solicitante_id,
            'solicitante_nome': self.solicitante_nome,
            'area': self.area,
            'status': self.status,
            'data_abertura': self.data_abertura,
            'data_conclusao': self.data_conclusao,
            'setores_adicionais': self.setores_adicionais,
            'motivo_cancelamento': self.motivo_cancelamento,
            'data_cancelamento': self.data_cancelamento,
            'grupo_rl_id': self.grupo_rl_id,
            'sla_dias': self.sla_dias,
        }

    @classmethod
    def from_dict(cls, data: dict, id: str = None):
        """Cria um objeto Chamado a partir de um dicionário do Firestore.
        Usa valores padrão para campos ausentes (documentos antigos ou migrados).
        Raises:
            ValidacaoChamadoError: Se dados estiverem vazios.
        """
        if not data:
            raise ValidacaoChamadoError('Dados do chamado estão vazios')
        # Garante strings para campos usados em exibição (evita None em templates)
        def _str(v):
            return v if v is not None else ''
        return cls(
            id=id,
            numero_chamado=data.get('numero_chamado'),
            categoria=_str(data.get('categoria')),
            rl_codigo=_str(data.get('rl_codigo')),
            prioridade=data.get('prioridade', 1),
            tipo_solicitacao=_str(data.get('tipo_solicitacao')),
            gate=data.get('gate'),
            impacto=data.get('impacto'),
            descricao=_str(data.get('descricao')),
            anexo=data.get('anexo'),
            anexos=data.get('anexos') if isinstance(data.get('anexos'), list) else [],
            responsavel=_str(data.get('responsavel')),
            responsavel_id=data.get('responsavel_id'),
            motivo_atribuicao=data.get('motivo_atribuicao'),
            solicitante_id=data.get('solicitante_id'),
            solicitante_nome=data.get('solicitante_nome'),
            area=data.get('area'),
            status=data.get('status', 'Aberto'),
            data_abertura=data.get('data_abertura'),
            data_conclusao=data.get('data_conclusao'),
            setores_adicionais=data.get('setores_adicionais') if isinstance(data.get('setores_adicionais'), list) else [],
            motivo_cancelamento=data.get('motivo_cancelamento'),
            data_cancelamento=data.get('data_cancelamento'),
            grupo_rl_id=data.get('grupo_rl_id'),
            sla_dias=data.get('sla_dias'),
        )

    def __repr__(self):
        return f'<Chamado {self.id} - {self.categoria}>'
