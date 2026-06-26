"""Testes do serviço de validação de permissões (permission_validation)."""

from unittest.mock import MagicMock

from app.services.permission_validation import (
    filtrar_supervisores_por_area,
    supervisor_pode_alterar_chamado,
    usuario_pode_mutar_chamado,
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
    sup.is_admin_or_above = False
    assert supervisor_pode_alterar_chamado(sup, "TI") is False


def test_supervisor_pode_alterar_chamado_solicitante_nunca_pode():
    sol = MagicMock()
    sol.perfil = "solicitante"
    sol.is_admin_or_above = False
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


# ---------------------------------------------------------------------------
# Fase 5 — gestor read-only (bloqueio de mutações)
# ---------------------------------------------------------------------------


def test_gestor_only_nao_pode_mudar_status():
    """verificar_permissao_mudanca_status retorna False para gestor read-only."""
    from unittest.mock import patch

    from app.models_usuario import Usuario

    with patch("app.models_usuario.db"):
        gestor = Usuario(
            id="g_t01",
            email="g@dtx.aero",
            nome="G",
            perfil="supervisor",
            nivel_gestao="gestor_setor",
        )
    chamado = MagicMock()
    chamado.solicitante_id = "outro"

    with patch("app.services.permissions.usuario_pode_ver_chamado", return_value=True):
        # is_gestor_only is True (supervisor + nivel_gestao)
        assert gestor.is_gestor_only is True
        permitido, erro = verificar_permissao_mudanca_status(gestor, chamado, "Em Atendimento")

    assert permitido is False
    assert erro is not None
    assert "read-only" in erro.lower() or "gestor" in erro.lower()


def test_gestor_only_supervisor_pode_alterar_chamado_retorna_false():
    """supervisor_pode_alterar_chamado retorna False para gestor read-only."""
    from unittest.mock import patch

    from app.models_usuario import Usuario

    with patch("app.models_usuario.db"):
        gestor = Usuario(
            id="g_t02",
            email="g2@dtx.aero",
            nome="G2",
            perfil="supervisor",
            areas=["Manutencao"],
            nivel_gestao="gestor_setor",
        )
    assert gestor.is_gestor_only is True
    assert supervisor_pode_alterar_chamado(gestor, "Manutencao") is False


def test_admin_com_nivel_gestao_ainda_edita():
    """Admin com nivel_gestao ainda tem permissão de escrita (is_admin_or_above=True)."""
    from unittest.mock import patch

    from app.models_usuario import Usuario

    with patch("app.models_usuario.db"):
        admin_gestor = Usuario(
            id="a_t01",
            email="ag@dtx.aero",
            nome="AG",
            perfil="admin",
            nivel_gestao="gm",
        )
    chamado = MagicMock()

    assert admin_gestor.is_gestor_only is False
    permitido, erro = verificar_permissao_mudanca_status(admin_gestor, chamado, "Concluído")
    assert permitido is True
    assert erro is None


# ---------------------------------------------------------------------------
# usuario_pode_mutar_chamado — helper central Lacuna 4
# ---------------------------------------------------------------------------


def test_usuario_pode_mutar_chamado_gestor_bloqueado():
    """Gestor read-only é bloqueado por usuario_pode_mutar_chamado."""
    gestor = MagicMock()
    gestor.is_gestor_only = True
    permitido, erro = usuario_pode_mutar_chamado(gestor)
    assert permitido is False
    assert erro is not None
    assert "read-only" in erro.lower() or "gestor" in erro.lower()


def test_usuario_pode_mutar_chamado_supervisor_permitido():
    """Supervisor comum pode mutar (retorna True)."""
    sup = MagicMock()
    sup.is_gestor_only = False
    permitido, erro = usuario_pode_mutar_chamado(sup)
    assert permitido is True
    assert erro is None


def test_usuario_pode_mutar_chamado_admin_permitido():
    """Admin pode mutar (retorna True)."""
    admin = MagicMock()
    admin.is_gestor_only = False
    permitido, erro = usuario_pode_mutar_chamado(admin)
    assert permitido is True
    assert erro is None


def test_usuario_pode_mutar_chamado_mock_legado_sem_is_gestor_only():
    """Mock sem is_gestor_only (legado) retorna True — não quebra testes antigos."""
    u = MagicMock(spec=[])  # sem atributo is_gestor_only
    permitido, erro = usuario_pode_mutar_chamado(u)
    assert permitido is True
    assert erro is None


def test_usuario_pode_mutar_chamado_ignora_argumento_chamado():
    """chamado=None é aceito (argumento reservado para versões futuras)."""
    gestor = MagicMock()
    gestor.is_gestor_only = True
    permitido, _ = usuario_pode_mutar_chamado(gestor, chamado=None)
    assert permitido is False


# ---------------------------------------------------------------------------
# Defesa em profundidade — processar_edicao_chamado bloqueia gestor
# ---------------------------------------------------------------------------


def test_processar_edicao_chamado_bloqueia_gestor_defesa_em_profundidade():
    """Defesa em profundidade: processar_edicao_chamado bloqueia gestor no serviço (sem tocar db)."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    gestor = MagicMock()
    gestor.is_gestor_only = True

    resultado = processar_edicao_chamado(
        usuario_atual=gestor,
        chamado_id="ch_test",
        novo_status=None,
        motivo_cancelamento="",
        nova_descricao=None,
        novo_responsavel_id=None,
        novo_sla_str="",
        arquivos_novos=[],
        setores_adicionais_lista=[],
    )

    assert resultado["sucesso"] is False
    assert resultado.get("codigo") == 403
