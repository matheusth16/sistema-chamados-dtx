"""Models SQLAlchemy (Fase 2). Um módulo por tabela, adicionados marco a marco."""

from app.db.models.categoria import (  # noqa: F401
    CategoriaGateRow,
    CategoriaImpactoRow,
    CategoriaSetorRow,
)
from app.db.models.grupo_rl import GrupoRLRow  # noqa: F401
