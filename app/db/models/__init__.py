"""Models SQLAlchemy (Fase 2). Um módulo por tabela, adicionados marco a marco."""

from app.db.models.apoio import (  # noqa: F401
    ContadorUsoRow,
    HistoricoUsuarioRow,
    PushSubscriptionRow,
    SolicitacaoLgpdRow,
)
from app.db.models.categoria import (  # noqa: F401
    CategoriaGateRow,
    CategoriaImpactoRow,
    CategoriaSetorRow,
)
from app.db.models.chamado import (  # noqa: F401
    ChamadoObservadorRow,
    ChamadoParticipanteRow,
    ChamadoRow,
)
from app.db.models.grupo_rl import GrupoRLRow  # noqa: F401
from app.db.models.usuario import UsuarioRow  # noqa: F401
