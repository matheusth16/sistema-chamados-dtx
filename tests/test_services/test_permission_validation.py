"""Testes do serviço de validação de permissões (permission_validation)."""

from unittest.mock import MagicMock

from app.services.permission_validation import (
    filtrar_supervisores_por_area,
    supervisor_pode_alterar_chamado,
    verificar_permissao_mudanca_status,
)

# ---------------------------------------------------------------------------
# supervisor_pode_alterar_chamado (já existia, garante não-regressão)
# ---------------------------------------------------------------------------


def test_supervisor_pode_alterar_chamado_admin_sempre_pode():
    admin = MagicMock()
    admin.perfil = "admin"
    assert supervisor_pode_alterar_chamado(admin, "QualquerArea") is True


def test_supervisor_pode_alterar_chamado_supervisor_area_correta():
    sup = MagicMock()
    sup.perfil = "supervisor"
    sup.areas = ["Manutencao"]
    assert supervisor_pode_alterar_chamado(sup, "Manutencao") is True


def test_supervisor_pode_alterar_chamado_supervisor_area_errada():
    sup = MagicMock()
    sup.perfil = "supervisor"
    sup.areas = ["Manutencao"]
    assert supervisor_pode_alterar_chamado(sup, "TI") is False


def test_supervisor_pode_alterar_chamado_solicitante_nunca_pode():
    sol = MagicMock()
    sol.perfil = "solicitante"
    assert supervisor_pode_alterar_chamado(sol, "Manutencao") is False


# ---------------------------------------------------------------------------
# verificar_permissao_mudanca_status
# ---------------------------------------------------------------------------


def test_permissao_mudanca_admin_sempre_permitido():
    """Admin pode alterar qualquer chamado para qualquer status."""
    admin = MagicMock()
    admin.perfil = "admin"
    chamado = MagicMock()
    permitido, erro = verificar_permissao_mudanca_status(admin, chamado, "Concluído")
    assert permitido is True
    assert erro is None


def test_permissao_mudanca_solicitante_proprio_chamado_cancelar():
    """Solicitante pode cancelar seu próprio chamado."""
    sol = MagicMock()
    sol.perfil = "solicitante"
    sol.id = "sol_1"
    chamado = MagicMock()
    chamado.solicitante_id = "sol_1"
    permitido, erro = verificar_permissao_mudanca_status(sol, chamado, "Cancelado")
    assert permitido is True
    assert erro is None


def test_permissao_mudanca_solicitante_proprio_chamado_outro_status_negado():
    """Solicitante não pode alterar para status diferente de Cancelado."""
    sol = MagicMock()
    sol.perfil = "solicitante"
    sol.id = "sol_1"
    chamado = MagicMock()
    chamado.solicitante_id = "sol_1"
    permitido, erro = verificar_permissao_mudanca_status(sol, chamado, "Em Atendimento")
    assert permitido is False
    assert erro is not None
    assert "Cancelar" in erro or "cancelar" in erro.lower()


def test_permissao_mudanca_solicitante_chamado_de_outro_negado():
    """Solicitante não pode alterar chamado de outro usuário."""
    sol = MagicMock()
    sol.perfil = "solicitante"
    sol.id = "sol_1"
    chamado = MagicMock()
    chamado.solicitante_id = "sol_2"
    permitido, erro = verificar_permissao_mudanca_status(sol, chamado, "Cancelado")
    assert permitido is False
    assert erro is not None
    assert "próprios" in erro or "negado" in erro.lower()


def test_permissao_mudanca_supervisor_area_correta_permitido():
    """Supervisor da área do chamado pode alterar."""
    from unittest.mock import patch

    sup = MagicMock()
    sup.perfil = "supervisor"
    sup.areas = ["Manutencao"]
    chamado = MagicMock()
    chamado.area = "Manutencao"

    # A função faz `from app.services.permissions import usuario_pode_ver_chamado`
    # internamente, então o patch deve ser no módulo de origem.
    with patch("app.services.permissions.usuario_pode_ver_chamado", return_value=True) as mock_perm:
        permitido, erro = verificar_permissao_mudanca_status(sup, chamado, "Concluído")
        mock_perm.assert_called_once_with(sup, chamado)

    assert permitido is True
    assert erro is None


def test_permissao_mudanca_supervisor_area_errada_negado():
    """Supervisor fora da área do chamado é negado."""
    from unittest.mock import patch

    sup = MagicMock()
    sup.perfil = "supervisor"
    sup.areas = ["TI"]
    chamado = MagicMock()
    chamado.area = "Manutencao"

    with patch("app.services.permissions.usuario_pode_ver_chamado", return_value=False):
        permitido, erro = verificar_permissao_mudanca_status(sup, chamado, "Concluído")

    assert permitido is False
    assert erro is not None
    assert "área" in erro.lower() or "permissão" in erro.lower()


# ---------------------------------------------------------------------------
# filtrar_supervisores_por_area (já existia, garante não-regressão)
# ---------------------------------------------------------------------------


def test_filtrar_supervisores_admin_retorna_todos():
    admin = MagicMock()
    admin.perfil = "admin"
    sups = [MagicMock(), MagicMock()]
    assert filtrar_supervisores_por_area(admin, sups) == sups


def test_filtrar_supervisores_supervisor_filtra_por_area():
    sup = MagicMock()
    sup.perfil = "supervisor"
    sup.areas = ["Manutencao"]

    s1 = MagicMock()
    s1.areas = ["Manutencao"]
    s2 = MagicMock()
    s2.areas = ["TI"]

    resultado = filtrar_supervisores_por_area(sup, [s1, s2])
    assert s1 in resultado
    assert s2 not in resultado
