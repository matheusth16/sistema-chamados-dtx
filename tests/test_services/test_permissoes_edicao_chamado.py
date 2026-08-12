"""Testes do serviço de validação de permissões (permissoes_edicao_chamado)."""

from unittest.mock import MagicMock, patch

from app.services.permissions import usuario_pode_ver_chamado
from app.services.permissoes_edicao_chamado import (
    filtrar_supervisores_por_area,
    montar_anexos_para_exibicao,
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
    assert erro == "access_denied_requester_cancel_only"


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
    assert erro == "access_denied_own_tickets_only"


def test_permissao_mudanca_supervisor_area_correta_permitido():
    """Supervisor da área do chamado pode alterar."""
    from unittest.mock import patch

    sup = MagicMock()
    sup.perfil = "supervisor"
    sup.areas = ["Manutencao"]
    chamado = MagicMock()
    chamado.area = "Manutencao"

    # A função faz `from app.services.permissions import usuario_pode_operar_chamado`
    # internamente (gate de escrita, não o de leitura), então o patch deve ser no
    # módulo de origem.
    with patch(
        "app.services.permissions.usuario_pode_operar_chamado", return_value=True
    ) as mock_perm:
        permitido, erro = verificar_permissao_mudanca_status(sup, chamado, "Concluído")
        mock_perm.assert_called_once_with(sup, chamado)

    assert permitido is True
    assert erro is None


def test_permissao_mudanca_supervisor_area_errada_negado():
    """Supervisor fora da área do chamado é negado."""
    from unittest.mock import patch

    sup = MagicMock()
    sup.perfil = "supervisor"
    sup.is_admin_or_above = False
    sup.is_gestor_only = False
    sup.areas = ["TI"]
    chamado = MagicMock()
    chamado.area = "Manutencao"

    with patch("app.services.permissions.usuario_pode_operar_chamado", return_value=False):
        permitido, erro = verificar_permissao_mudanca_status(sup, chamado, "Concluído")

    assert permitido is False
    assert erro is not None
    assert erro == "access_denied_out_of_area"


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


def test_supervisor_gestor_setor_pode_mudar_status_do_proprio_chamado():
    """Nível 3: dual role (supervisor + gestor_setor) mantém escrita no que é dele —
    is_gestor_only é False, então verificar_permissao_mudanca_status segue a regra
    normal de supervisor (dono/fila/participante)."""

    from app.models_usuario import Usuario

    gestor = Usuario(
        id="g_t01",
        email="g@dtx.aero",
        nome="G",
        perfil="supervisor",
        areas=["Manutencao"],
        nivel_gestao="gestor_setor",
    )
    chamado = MagicMock()
    chamado.area = "Manutencao"
    chamado.solicitante_id = "outro"
    chamado.responsavel_id = "g_t01"
    chamado.participantes = []

    assert gestor.is_gestor_only is False
    permitido, erro = verificar_permissao_mudanca_status(gestor, chamado, "Em Atendimento")

    assert permitido is True
    assert erro is None


def test_supervisor_gestor_setor_nao_pode_mudar_status_de_chamado_do_colega():
    """QA (Nível 3): a leitura ampliada de gestor_setor sobre chamado do colega na
    própria área NÃO pode virar permissão de escrita — precisa do fluxo normal de
    reatribuição de responsável antes de poder mexer no chamado."""

    from app.models_usuario import Usuario

    gestor = Usuario(
        id="g_t01",
        email="g@dtx.aero",
        nome="G",
        perfil="supervisor",
        areas=["Manutencao"],
        nivel_gestao="gestor_setor",
    )
    chamado = MagicMock()
    chamado.area = "Manutencao"
    chamado.solicitante_id = "outro"
    chamado.responsavel_id = "colega_supervisor"
    chamado.participantes = []

    # Enxerga o chamado (leitura ampliada de gestor_setor)...
    assert usuario_pode_ver_chamado(gestor, chamado) is True
    # ...mas não pode mudar o status dele.
    permitido, erro = verificar_permissao_mudanca_status(gestor, chamado, "Em Atendimento")

    assert permitido is False
    assert erro is not None


def test_gestor_puro_nao_pode_mudar_status():
    """Gestor "puro" (perfil não-operacional, ex.: solicitante + nivel_gestao) continua
    bloqueado — read-only real, diferente do dual role supervisor + gestor_setor."""

    from app.models_usuario import Usuario

    gestor_puro = Usuario(
        id="g_puro",
        email="gp@dtx.aero",
        nome="GP",
        perfil="solicitante",
        nivel_gestao="gm",
    )
    chamado = MagicMock()

    assert gestor_puro.is_gestor_only is True
    permitido, erro = verificar_permissao_mudanca_status(gestor_puro, chamado, "Em Atendimento")

    assert permitido is False
    assert erro is not None
    assert "read-only" in erro.lower() or "gestor" in erro.lower()


def test_supervisor_gestor_setor_pode_alterar_chamado_na_propria_area():
    """supervisor_pode_alterar_chamado (sem o chamado completo, só a área — modo
    legado) retorna True para dual role dentro da própria área."""

    from app.models_usuario import Usuario

    gestor = Usuario(
        id="g_t02",
        email="g2@dtx.aero",
        nome="G2",
        perfil="supervisor",
        areas=["Manutencao"],
        nivel_gestao="gestor_setor",
    )
    assert gestor.is_gestor_only is False
    assert supervisor_pode_alterar_chamado(gestor, "Manutencao") is True


def test_supervisor_gestor_setor_com_chamado_do_colega_nao_pode_alterar():
    """QA (Nível 3): quando o chamado completo é passado, supervisor_pode_alterar_chamado
    aplica a restrição de posse pra dual role — vendo o chamado do colega não editando."""

    from app.models_usuario import Usuario

    gestor = Usuario(
        id="g_t02b",
        email="g2b@dtx.aero",
        nome="G2b",
        perfil="supervisor",
        areas=["Manutencao"],
        nivel_gestao="gestor_setor",
    )
    chamado = MagicMock()
    chamado.area = "Manutencao"
    chamado.solicitante_id = "outro"
    chamado.responsavel_id = "colega_supervisor"
    chamado.participantes = []

    assert supervisor_pode_alterar_chamado(gestor, "Manutencao", chamado) is False


def test_supervisor_gestor_setor_com_chamado_proprio_pode_alterar():
    """Quando o chamado completo é passado e é do próprio gestor_setor, continua podendo."""

    from app.models_usuario import Usuario

    gestor = Usuario(
        id="g_t02c",
        email="g2c@dtx.aero",
        nome="G2c",
        perfil="supervisor",
        areas=["Manutencao"],
        nivel_gestao="gestor_setor",
    )
    chamado = MagicMock()
    chamado.area = "Manutencao"
    chamado.solicitante_id = "outro"
    chamado.responsavel_id = "g_t02c"
    chamado.participantes = []

    assert supervisor_pode_alterar_chamado(gestor, "Manutencao", chamado) is True


def test_supervisor_gestor_setor_nao_altera_chamado_fora_da_area():
    """Fora da própria área, dual role continua bloqueado (regra normal de área do supervisor)."""

    from app.models_usuario import Usuario

    gestor = Usuario(
        id="g_t03",
        email="g3@dtx.aero",
        nome="G3",
        perfil="supervisor",
        areas=["Manutencao"],
        nivel_gestao="gestor_setor",
    )
    assert supervisor_pode_alterar_chamado(gestor, "TI") is False


def test_admin_com_nivel_gestao_ainda_edita():
    """Admin com nivel_gestao ainda tem permissão de escrita (is_admin_or_above=True)."""

    from app.models_usuario import Usuario

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
# nivel_congelamento_chamado — Nível 1 / Nível 2 / sem congelamento
# ---------------------------------------------------------------------------


def test_nivel_congelamento_nao_concluido_retorna_none():
    """Chamado não Concluído → sem congelamento (None)."""
    from app.services.permissoes_edicao_chamado import nivel_congelamento_chamado

    chamado = MagicMock()
    chamado.status = "Aberto"
    chamado.confirmacao_solicitante = None
    assert nivel_congelamento_chamado(chamado) is None


def test_nivel_congelamento_concluido_pendente():
    """Concluído + confirmacao pendente → nível 1 ('pendente')."""
    from app.services.permissoes_edicao_chamado import nivel_congelamento_chamado

    chamado = MagicMock()
    chamado.status = "Concluído"
    chamado.confirmacao_solicitante = "pendente"
    assert nivel_congelamento_chamado(chamado) == "pendente"


def test_nivel_congelamento_concluido_confirmado():
    """Concluído + confirmacao confirmado → nível 2 ('confirmado')."""
    from app.services.permissoes_edicao_chamado import nivel_congelamento_chamado

    chamado = MagicMock()
    chamado.status = "Concluído"
    chamado.confirmacao_solicitante = "confirmado"
    assert nivel_congelamento_chamado(chamado) == "confirmado"


def test_nivel_congelamento_aceita_dict():
    """nivel_congelamento_chamado aceita dict além de objeto."""
    from app.services.permissoes_edicao_chamado import nivel_congelamento_chamado

    assert (
        nivel_congelamento_chamado({"status": "Concluído", "confirmacao_solicitante": "pendente"})
        == "pendente"
    )
    assert nivel_congelamento_chamado({"status": "Aberto", "confirmacao_solicitante": None}) is None


# ---------------------------------------------------------------------------
# Lacuna 1 — chamados legados (confirmacao_solicitante ausente / None)
# ---------------------------------------------------------------------------


def test_nivel_congelamento_concluido_confirmacao_none_congela_como_pendente():
    """Lacuna 1: Concluído + confirmacao_solicitante=None → congelado como pendente (legado)."""
    from app.services.permissoes_edicao_chamado import nivel_congelamento_chamado

    chamado = MagicMock()
    chamado.status = "Concluído"
    chamado.confirmacao_solicitante = None
    assert nivel_congelamento_chamado(chamado) == "pendente"


def test_nivel_congelamento_concluido_campo_ausente_no_dict_congela():
    """Lacuna 1: dict Concluído sem campo confirmacao_solicitante → congelado como pendente."""
    from app.services.permissoes_edicao_chamado import nivel_congelamento_chamado

    # dict sem a chave (get retorna None)
    assert nivel_congelamento_chamado({"status": "Concluído"}) == "pendente"


def test_nivel_congelamento_concluido_confirmacao_string_vazia_congela():
    """Lacuna 1: Concluído + confirmacao_solicitante='' → congelado como pendente."""
    from app.services.permissoes_edicao_chamado import nivel_congelamento_chamado

    assert (
        nivel_congelamento_chamado({"status": "Concluído", "confirmacao_solicitante": ""})
        == "pendente"
    )


def test_nivel_congelamento_concluido_reaberto_anomalia_congela_como_pendente():
    """Lacuna 1: Concluído + confirmacao='reaberto' é anomalia → congelado como pendente por segurança."""
    from app.services.permissoes_edicao_chamado import nivel_congelamento_chamado

    chamado = MagicMock()
    chamado.status = "Concluído"
    chamado.confirmacao_solicitante = "reaberto"
    # Deve congelar mesmo sendo estado anômalo
    assert nivel_congelamento_chamado(chamado) == "pendente"


def test_edicao_operacional_concluido_legado_none_bloqueado():
    """Lacuna 1: chamado legado (confirmacao=None) com status Concluído bloqueia edição operacional."""
    from app.services.permissoes_edicao_chamado import chamado_aceita_edicao_operacional

    admin = MagicMock()
    chamado = MagicMock()
    chamado.status = "Concluído"
    chamado.confirmacao_solicitante = None
    pode, msg = chamado_aceita_edicao_operacional(admin, chamado)
    assert pode is False
    assert msg is not None


def test_transicao_nivel1_legado_supervisor_aberto_aceito():
    """Lacuna 1: chamado legado (confirmacao=None) → nível 1; supervisor pode reabrir."""
    from app.services.permissoes_edicao_chamado import chamado_aceita_transicao_status

    sup = MagicMock()
    sup.perfil = "supervisor"
    sup.is_admin_or_above = False
    chamado = MagicMock()
    chamado.status = "Concluído"
    chamado.confirmacao_solicitante = None
    pode, _ = chamado_aceita_transicao_status(sup, chamado, "Aberto")
    assert pode is True


# ---------------------------------------------------------------------------
# chamado_aceita_edicao_operacional — bloqueia qualquer nível
# ---------------------------------------------------------------------------


def test_edicao_operacional_nao_concluido_aceita():
    """Chamado Aberto → edição operacional aceita para qualquer perfil."""
    from app.services.permissoes_edicao_chamado import chamado_aceita_edicao_operacional

    admin = MagicMock()
    chamado = MagicMock()
    chamado.status = "Aberto"
    chamado.confirmacao_solicitante = None
    pode, msg = chamado_aceita_edicao_operacional(admin, chamado)
    assert pode is True
    assert msg is None


def test_edicao_operacional_concluido_pendente_bloqueado_supervisor():
    """Nível 1 (pendente): supervisor não pode editar campos operacionais."""
    from app.services.permissoes_edicao_chamado import chamado_aceita_edicao_operacional

    sup = MagicMock()
    sup.perfil = "supervisor"
    chamado = MagicMock()
    chamado.status = "Concluído"
    chamado.confirmacao_solicitante = "pendente"
    pode, msg = chamado_aceita_edicao_operacional(sup, chamado)
    assert pode is False
    assert msg is not None


def test_edicao_operacional_concluido_pendente_bloqueado_admin():
    """Nível 1 (pendente): admin não pode editar campos operacionais (apenas reabrir)."""
    from app.services.permissoes_edicao_chamado import chamado_aceita_edicao_operacional

    admin = MagicMock()
    admin.perfil = "admin"
    chamado = MagicMock()
    chamado.status = "Concluído"
    chamado.confirmacao_solicitante = "pendente"
    pode, msg = chamado_aceita_edicao_operacional(admin, chamado)
    assert pode is False


def test_edicao_operacional_concluido_confirmado_bloqueado():
    """Nível 2 (confirmado): ninguém pode editar campos operacionais."""
    from app.services.permissoes_edicao_chamado import chamado_aceita_edicao_operacional

    admin = MagicMock()
    chamado = MagicMock()
    chamado.status = "Concluído"
    chamado.confirmacao_solicitante = "confirmado"
    pode, msg = chamado_aceita_edicao_operacional(admin, chamado)
    assert pode is False


# ---------------------------------------------------------------------------
# chamado_aceita_transicao_status — regras por nível e perfil
# ---------------------------------------------------------------------------


def test_transicao_status_nao_concluido_sempre_aceita():
    """Chamado não Concluído → sem restrição adicional de congelamento."""
    from app.services.permissoes_edicao_chamado import chamado_aceita_transicao_status

    sup = MagicMock()
    chamado = MagicMock()
    chamado.status = "Em Atendimento"
    chamado.confirmacao_solicitante = None
    pode, _ = chamado_aceita_transicao_status(sup, chamado, "Concluído")
    assert pode is True


def test_transicao_nivel1_supervisor_aberto_aceito():
    """Nível 1: supervisor pode reabrir (→ Aberto)."""
    from app.services.permissoes_edicao_chamado import chamado_aceita_transicao_status

    sup = MagicMock()
    sup.perfil = "supervisor"
    sup.is_admin_or_above = False
    chamado = MagicMock()
    chamado.status = "Concluído"
    chamado.confirmacao_solicitante = "pendente"
    pode, _ = chamado_aceita_transicao_status(sup, chamado, "Aberto")
    assert pode is True


def test_transicao_nivel1_supervisor_em_atendimento_negado():
    """Nível 1: supervisor NÃO pode ir para Em Atendimento (contorna confirmação)."""
    from app.services.permissoes_edicao_chamado import chamado_aceita_transicao_status

    sup = MagicMock()
    sup.perfil = "supervisor"
    sup.is_admin_or_above = False
    chamado = MagicMock()
    chamado.status = "Concluído"
    chamado.confirmacao_solicitante = "pendente"
    pode, _ = chamado_aceita_transicao_status(sup, chamado, "Em Atendimento")
    assert pode is False


def test_transicao_nivel1_admin_aberto_aceito():
    """Nível 1: admin pode reabrir (→ Aberto)."""
    from app.services.permissoes_edicao_chamado import chamado_aceita_transicao_status

    admin = MagicMock()
    admin.perfil = "admin"
    admin.is_admin_or_above = True
    chamado = MagicMock()
    chamado.status = "Concluído"
    chamado.confirmacao_solicitante = "pendente"
    pode, _ = chamado_aceita_transicao_status(admin, chamado, "Aberto")
    assert pode is True


def test_transicao_nivel1_admin_em_atendimento_negado():
    """Nível 1: admin NÃO pode ir para Em Atendimento (bloqueia bypass)."""
    from app.services.permissoes_edicao_chamado import chamado_aceita_transicao_status

    admin = MagicMock()
    admin.perfil = "admin"
    admin.is_admin_or_above = True
    chamado = MagicMock()
    chamado.status = "Concluído"
    chamado.confirmacao_solicitante = "pendente"
    pode, _ = chamado_aceita_transicao_status(admin, chamado, "Em Atendimento")
    assert pode is False


def test_transicao_nivel2_supervisor_tudo_negado():
    """Nível 2: supervisor não pode fazer nenhuma transição."""
    from app.services.permissoes_edicao_chamado import chamado_aceita_transicao_status

    sup = MagicMock()
    sup.perfil = "supervisor"
    sup.is_admin_or_above = False
    chamado = MagicMock()
    chamado.status = "Concluído"
    chamado.confirmacao_solicitante = "confirmado"
    for status in ("Aberto", "Em Atendimento", "Cancelado"):
        pode, _ = chamado_aceita_transicao_status(sup, chamado, status)
        assert pode is False, f"Supervisor nível 2 não deveria poder ir para {status}"


def test_transicao_nivel2_admin_somente_aberto():
    """Nível 2: admin pode apenas → Aberto; Cancelado e Em Atendimento negados."""
    from app.services.permissoes_edicao_chamado import chamado_aceita_transicao_status

    admin = MagicMock()
    admin.perfil = "admin"
    admin.is_admin_or_above = True
    chamado = MagicMock()
    chamado.status = "Concluído"
    chamado.confirmacao_solicitante = "confirmado"

    pode_aberto, _ = chamado_aceita_transicao_status(admin, chamado, "Aberto")
    assert pode_aberto is True

    pode_cancelado, _ = chamado_aceita_transicao_status(admin, chamado, "Cancelado")
    assert pode_cancelado is False

    pode_em_at, _ = chamado_aceita_transicao_status(admin, chamado, "Em Atendimento")
    assert pode_em_at is False


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


# ---------------------------------------------------------------------------
# montar_flags_detalhe_chamado — extraído de visualizar_detalhe_chamado
# (app/routes/dashboard.py) na auditoria de 2026-08-05: a rota calculava ~10
# regras de permissão/estado direto no controller.
# ---------------------------------------------------------------------------


def _chamado_mock(**overrides):
    chamado = MagicMock()
    chamado.area = "Manutencao"
    chamado.status = "Aberto"
    chamado.solicitante_id = "id_sol"
    chamado.confirmacao_solicitante = None
    chamado.data_abertura = "qualquer"
    chamado._converter_timestamp.return_value = "dt_convertido"
    for k, v in overrides.items():
        setattr(chamado, k, v)
    return chamado


def _usuario_mock(**overrides):
    usuario = MagicMock()
    usuario.id = "id_sup"
    usuario.perfil = "supervisor"
    usuario.areas = ["Manutencao"]
    usuario.is_admin_or_above = False
    usuario.is_gestor_only = False
    for k, v in overrides.items():
        setattr(usuario, k, v)
    return usuario


def test_montar_flags_supervisor_area_correta_pode_editar():
    from app.services.permissoes_edicao_chamado import montar_flags_detalhe_chamado

    usuario = _usuario_mock()
    chamado = _chamado_mock()
    flags = montar_flags_detalhe_chamado(usuario, chamado)
    assert flags["pode_editar_base"] is True
    assert flags["pode_editar"] is True
    assert flags["pode_editar_descricao"] is False  # supervisor não é admin
    assert flags["nivel_congelamento"] is None


def test_montar_flags_admin_pode_editar_descricao():
    from app.services.permissoes_edicao_chamado import montar_flags_detalhe_chamado

    usuario = _usuario_mock(perfil="admin", is_admin_or_above=True)
    chamado = _chamado_mock()
    flags = montar_flags_detalhe_chamado(usuario, chamado)
    assert flags["pode_editar_descricao"] is True


def test_montar_flags_chamado_concluido_bloqueia_edicao():
    from app.services.permissoes_edicao_chamado import montar_flags_detalhe_chamado

    usuario = _usuario_mock()
    chamado = _chamado_mock(status="Concluído", confirmacao_solicitante=None)
    flags = montar_flags_detalhe_chamado(usuario, chamado)
    assert flags["nivel_congelamento"] == "pendente"
    assert flags["pode_editar"] is False


def test_montar_flags_dono_aberto_calcula_janela_edicao():
    from app.services.permissoes_edicao_chamado import montar_flags_detalhe_chamado

    usuario = _usuario_mock(id="id_sol", perfil="solicitante", areas=[])
    chamado = _chamado_mock(status="Aberto", solicitante_id="id_sol")

    with patch(
        "app.services.permissoes_edicao_chamado.segundos_restantes_janela_edicao",
        return_value=120,
    ):
        flags = montar_flags_detalhe_chamado(usuario, chamado)

    assert flags["pode_editar_descricao_solicitante"] is True
    assert flags["segundos_restantes_edicao"] == 120
    assert flags["pode_cancelar_solicitante"] is True
    assert flags["pode_anexo_tardio_solicitante"] is True


def test_montar_flags_dono_janela_edicao_expirada():
    from app.services.permissoes_edicao_chamado import montar_flags_detalhe_chamado

    usuario = _usuario_mock(id="id_sol", perfil="solicitante", areas=[])
    chamado = _chamado_mock(status="Aberto", solicitante_id="id_sol")

    with patch(
        "app.services.permissoes_edicao_chamado.segundos_restantes_janela_edicao",
        return_value=0,
    ):
        flags = montar_flags_detalhe_chamado(usuario, chamado)

    assert flags["pode_editar_descricao_solicitante"] is False
    assert flags["segundos_restantes_edicao"] == 0
    # cancelar/anexo tardio não dependem da janela de 15min, só do status
    assert flags["pode_cancelar_solicitante"] is True


def test_montar_flags_nao_dono_nao_ganha_flags_de_solicitante():
    from app.services.permissoes_edicao_chamado import montar_flags_detalhe_chamado

    usuario = _usuario_mock(id="id_outro", perfil="solicitante", areas=[])
    chamado = _chamado_mock(status="Aberto", solicitante_id="id_sol")
    flags = montar_flags_detalhe_chamado(usuario, chamado)
    assert flags["pode_cancelar_solicitante"] is False
    assert flags["pode_anexo_tardio_solicitante"] is False
    assert flags["pode_editar_descricao_solicitante"] is False


def test_montar_flags_gestor_only_nao_ganha_flags_de_solicitante_mesmo_sendo_dono():
    from app.services.permissoes_edicao_chamado import montar_flags_detalhe_chamado

    usuario = _usuario_mock(id="id_sol", perfil="solicitante", areas=[], is_gestor_only=True)
    chamado = _chamado_mock(status="Aberto", solicitante_id="id_sol")
    flags = montar_flags_detalhe_chamado(usuario, chamado)
    assert flags["pode_cancelar_solicitante"] is False
    assert flags["pode_anexo_tardio_solicitante"] is False


def test_montar_flags_status_aguardando_informacao_permite_cancelar_e_anexo():
    from app.services.permissoes_edicao_chamado import montar_flags_detalhe_chamado

    usuario = _usuario_mock(id="id_sol", perfil="solicitante", areas=[])
    chamado = _chamado_mock(status="Aguardando Informação", solicitante_id="id_sol")
    flags = montar_flags_detalhe_chamado(usuario, chamado)
    assert flags["pode_cancelar_solicitante"] is True
    assert flags["pode_anexo_tardio_solicitante"] is True
    # segundos_restantes só é calculado quando status == "Aberto"
    assert flags["segundos_restantes_edicao"] == 0


# ---------------------------------------------------------------------------
# montar_anexos_para_exibicao
# ---------------------------------------------------------------------------


def _chamado_anexos_mock(anexos=None, anexo=None, solicitante_id="sol_1"):
    m = MagicMock()
    m.anexos = anexos or []
    m.anexo = anexo
    m.solicitante_id = solicitante_id
    return m


def _evento_mock(acao, campo_alterado=None, valor_novo=None, usuario_id=None, usuario_nome=None):
    m = MagicMock()
    m.acao = acao
    m.campo_alterado = campo_alterado
    m.valor_novo = valor_novo
    m.usuario_id = usuario_id
    m.usuario_nome = usuario_nome
    return m


def test_anexos_sem_historico_sao_todos_do_solicitante():
    """Anexo sem entrada no histórico veio da abertura do chamado — sempre do solicitante."""
    chamado = _chamado_anexos_mock(anexos=["local:a.pdf", "local:b.png"])
    itens = montar_anexos_para_exibicao(chamado, historico=[])
    assert len(itens) == 2
    assert all(item["eh_solicitante"] for item in itens)
    assert all(item["usuario_nome"] is None for item in itens)


def test_anexo_adicionado_pelo_responsavel_nao_e_do_solicitante():
    """acao=alteracao_dados + campo_alterado=novo anexo, autor != solicitante → não é do solicitante."""
    chamado = _chamado_anexos_mock(anexos=["local:a.pdf", "local:novo.png"], solicitante_id="sol_1")
    evento = _evento_mock(
        "alteracao_dados",
        campo_alterado="novo anexo",
        valor_novo="local:novo.png",
        usuario_id="sup_1",
        usuario_nome="Supervisor Demo",
    )
    itens = montar_anexos_para_exibicao(chamado, historico=[evento])
    por_caminho = {item["caminho"]: item for item in itens}
    assert por_caminho["local:a.pdf"]["eh_solicitante"] is True
    assert por_caminho["local:novo.png"]["eh_solicitante"] is False
    assert por_caminho["local:novo.png"]["usuario_nome"] == "Supervisor Demo"
    assert por_caminho["local:novo.png"]["usuario_id"] == "sup_1"


def test_anexo_tardio_do_proprio_solicitante_continua_sendo_do_solicitante():
    """acao=anexo_tardio com usuario_id == solicitante_id → continua eh_solicitante=True."""
    chamado = _chamado_anexos_mock(anexos=["local:tardio.pdf"], solicitante_id="sol_1")
    evento = _evento_mock(
        "anexo_tardio",
        campo_alterado="anexos",
        valor_novo="local:tardio.pdf",
        usuario_id="sol_1",
        usuario_nome="Solicitante Demo",
    )
    itens = montar_anexos_para_exibicao(chamado, historico=[evento])
    assert itens[0]["eh_solicitante"] is True
    assert itens[0]["usuario_nome"] is None


def test_ordem_solicitante_primeiro_mesmo_se_apareceu_depois_na_lista_bruta():
    """Solicitante sempre primeiro na exibição, independente da ordem em chamado.anexos."""
    chamado = _chamado_anexos_mock(
        anexos=["local:do_supervisor.pdf", "local:do_solicitante.pdf"], solicitante_id="sol_1"
    )
    evento = _evento_mock(
        "alteracao_dados",
        campo_alterado="novo anexo",
        valor_novo="local:do_supervisor.pdf",
        usuario_id="sup_1",
        usuario_nome="Supervisor Demo",
    )
    itens = montar_anexos_para_exibicao(chamado, historico=[evento])
    assert itens[0]["caminho"] == "local:do_solicitante.pdf"
    assert itens[1]["caminho"] == "local:do_supervisor.pdf"


def test_anexos_duplicados_sao_deduplicados():
    chamado = _chamado_anexos_mock(anexos=["local:a.pdf", "local:a.pdf", "local:b.pdf"])
    itens = montar_anexos_para_exibicao(chamado, historico=[])
    assert len(itens) == 2


def test_fallback_anexo_legado_singular_quando_anexos_vazio():
    """chamado.anexos vazio mas chamado.anexo (legado, singular) setado — ainda funciona."""
    chamado = _chamado_anexos_mock(anexos=[], anexo="local:legado.pdf")
    itens = montar_anexos_para_exibicao(chamado, historico=[])
    assert len(itens) == 1
    assert itens[0]["caminho"] == "local:legado.pdf"
    assert itens[0]["eh_solicitante"] is True


def test_evento_historico_irrelevante_nao_afeta_origem():
    """Entrada de histórico de outro tipo (ex.: alteracao_status) não deve ser usada como origem de anexo."""
    chamado = _chamado_anexos_mock(anexos=["local:a.pdf"], solicitante_id="sol_1")
    evento = _evento_mock(
        "alteracao_status",
        campo_alterado="status",
        valor_novo="Em Atendimento",
        usuario_id="sup_1",
        usuario_nome="Supervisor Demo",
    )
    itens = montar_anexos_para_exibicao(chamado, historico=[evento])
    assert itens[0]["eh_solicitante"] is True


def test_docstring_do_modulo_faz_referencia_cruzada_a_permissions():
    """Achado da task 11 (auditoria pausada 2026-08-05): o docstring de topo
    deste módulo era genérico ("Validação de permissões de acesso a
    chamados"), sem deixar claro que é sobre MUTAÇÃO (não visibilidade) nem
    apontar para permissions.py, que já tem a referência cruzada inversa."""
    import app.services.permissoes_edicao_chamado as modulo

    doc = modulo.__doc__ or ""
    assert "MUTAÇÃO" in doc.upper() or "MUTACAO" in doc.upper()
    assert "permissions.py" in doc
