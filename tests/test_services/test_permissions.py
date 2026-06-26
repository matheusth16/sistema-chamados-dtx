"""Testes do serviço de permissões: usuario_pode_ver_chamado e edge cases."""

from unittest.mock import MagicMock, patch

from app.services.permissions import (
    calcular_supervisor_ids_com_acesso,
    usuario_pode_ver_chamado,
    usuario_pode_ver_chamado_otimizado,
)

# IDs explícitos — evita ambiguidade de comparação com MagicMock auto-attributes
_DONO_ID = "chamado_dono"
_OUTRO_ID = "outro_usuario"
_TEST_USER_ID = "test_user"


def _chamado_mock(
    area="Manutencao",
    responsavel_id=None,
    solicitante_id=_DONO_ID,
    participantes=None,
):
    c = MagicMock()
    c.area = area
    c.responsavel_id = responsavel_id
    c.solicitante_id = solicitante_id
    c.participantes = participantes or []
    return c


def _usuario_mock(perfil, areas=None, uid=_TEST_USER_ID):
    u = MagicMock()
    u.id = uid
    u.perfil = perfil
    u.areas = areas or []
    u.is_admin_or_above = perfil in ("admin", "admin_global")
    u.is_supervisor_or_above = perfil in ("supervisor", "admin", "admin_global")
    return u


class TestUsuarioPodeVerChamado:
    """Cobertura de usuario_pode_ver_chamado."""

    def test_admin_pode_ver_qualquer_chamado(self):
        admin = _usuario_mock("admin", areas=[])
        chamado = _chamado_mock(area="TI")
        assert usuario_pode_ver_chamado(admin, chamado) is True
        chamado.area = "QualquerArea"
        assert usuario_pode_ver_chamado(admin, chamado) is True

    # ── Supervisor: fila sem owner ───────────────────────────────────────────

    def test_supervisor_ve_fila_sem_owner_na_sua_area(self):
        """Fila sem responsável: supervisor da área enxerga."""
        supervisor = _usuario_mock("supervisor", areas=["Manutencao", "TI"])
        chamado = _chamado_mock(area="Manutencao", responsavel_id=None)
        assert usuario_pode_ver_chamado(supervisor, chamado) is True

    def test_supervisor_nao_ve_fila_de_outra_area(self):
        """Fila sem owner mas em área diferente: supervisor não enxerga."""
        supervisor = _usuario_mock("supervisor", areas=["Manutencao"])
        chamado = _chamado_mock(area="TI", responsavel_id=None)
        assert usuario_pode_ver_chamado(supervisor, chamado) is False

    # ── Supervisor: isolamento por owner ────────────────────────────────────

    def test_supervisor_nao_ve_ticket_atribuido_a_colega(self):
        """Júlia e Matheus na mesma área — Júlia não vê ticket do Matheus."""
        chamado = _chamado_mock(area="Engenharia", responsavel_id="id_matheus")
        julia = _usuario_mock("supervisor", areas=["Engenharia"], uid="id_julia")
        assert usuario_pode_ver_chamado(julia, chamado) is False

    def test_supervisor_ve_ticket_atribuido_a_si(self):
        """Supervisor vê ticket onde ele mesmo é o responsável."""
        chamado = _chamado_mock(area="Engenharia", responsavel_id="id_julia")
        julia = _usuario_mock("supervisor", areas=["Engenharia"], uid="id_julia")
        assert usuario_pode_ver_chamado(julia, chamado) is True

    def test_supervisor_mesma_area_colega_owner_nao_ve(self):
        """Regressão explícita: colega owner bloqueia acesso mesmo na mesma área."""
        chamado = _chamado_mock(area="Manutencao", responsavel_id="outro_supervisor")
        supervisor = _usuario_mock("supervisor", areas=["Manutencao"], uid=_TEST_USER_ID)
        assert usuario_pode_ver_chamado(supervisor, chamado) is False

    # ── Supervisor: participante ────────────────────────────────────────────

    def test_supervisor_ve_ticket_onde_e_participante(self):
        """Supervisor é participante de chamado de outra área: deve enxergar."""
        chamado = _chamado_mock(
            area="Planejamento",
            responsavel_id="id_outro",
            participantes=[{"supervisor_id": "id_julia", "status": "em_atendimento"}],
        )
        julia = _usuario_mock("supervisor", areas=["Engenharia"], uid="id_julia")
        assert usuario_pode_ver_chamado(julia, chamado) is True

    def test_supervisor_nao_ve_ticket_outro_participante(self):
        """Supervisor não é participante — não deve ver o ticket de outra área."""
        chamado = _chamado_mock(
            area="Planejamento",
            responsavel_id="id_outro",
            participantes=[{"supervisor_id": "id_terceiro", "status": "em_atendimento"}],
        )
        julia = _usuario_mock("supervisor", areas=["Engenharia"], uid="id_julia")
        assert usuario_pode_ver_chamado(julia, chamado) is False

    # ── Supervisor: abriu o chamado ─────────────────────────────────────────

    def test_supervisor_que_abriu_o_chamado_pode_ver(self):
        """Supervisor que criou o chamado sempre pode ver, independente de owner."""
        sup = _usuario_mock("supervisor", areas=[])
        sup.id = "sup42"
        chamado = MagicMock()
        chamado.area = "OutraArea"
        chamado.responsavel_id = "outro_sup"
        chamado.solicitante_id = "sup42"
        chamado.participantes = []
        assert usuario_pode_ver_chamado(sup, chamado) is True

    # ── Supervisor sem áreas ────────────────────────────────────────────────

    def test_supervisor_areas_vazias_nao_pode_ver_fila(self):
        supervisor = _usuario_mock("supervisor", areas=[])
        chamado = _chamado_mock(area="Manutencao", responsavel_id=None)
        assert usuario_pode_ver_chamado(supervisor, chamado) is False

    def test_supervisor_nao_pode_ver_chamado_de_outra_area(self):
        """Edge case: supervisor de outra área não pode ver/editar chamado."""
        supervisor = _usuario_mock("supervisor", areas=["Manutencao"])
        chamado = _chamado_mock(area="TI", responsavel_id=None)
        assert usuario_pode_ver_chamado(supervisor, chamado) is False
        chamado.area = "Planejamento"
        assert usuario_pode_ver_chamado(supervisor, chamado) is False

    # ── Admin ────────────────────────────────────────────────────────────────

    def test_admin_ve_todos(self):
        chamado = _chamado_mock(area="Engenharia", responsavel_id="id_matheus")
        admin = _usuario_mock("admin", uid="id_admin")
        assert usuario_pode_ver_chamado(admin, chamado) is True

    # ── Solicitante: acesso ao próprio vs. chamado alheio ────────────────────

    def test_solicitante_pode_ver_proprio_chamado(self):
        """Solicitante pode ver chamado que ele mesmo abriu (solicitante_id == user.id)."""
        solicitante = _usuario_mock("solicitante", uid="sol_123")
        chamado = _chamado_mock(area="Manutencao", solicitante_id="sol_123")
        assert usuario_pode_ver_chamado(solicitante, chamado) is True

    def test_solicitante_nao_pode_ver_chamado_alheio(self):
        """Solicitante não pode ver chamado de outro usuário (solicitante_id != user.id)."""
        solicitante = _usuario_mock("solicitante", uid="sol_123")
        chamado = _chamado_mock(area="Manutencao", solicitante_id="outro_sol_999")
        assert usuario_pode_ver_chamado(solicitante, chamado) is False

    # ── Participantes com participantes=None (legado) ───────────────────────

    def test_supervisor_ve_fila_chamado_sem_campo_participantes(self):
        """Chamado legado sem campo participantes — deve funcionar como fila (sem owner)."""
        sup = _usuario_mock("supervisor", areas=["TI"])
        chamado = MagicMock()
        chamado.area = "TI"
        chamado.responsavel_id = None
        chamado.solicitante_id = "sol_x"
        del chamado.participantes  # simula campo ausente
        assert usuario_pode_ver_chamado(sup, chamado) is True


class TestUsuarioPodeVerChamadoOtimizado:
    """Cobertura da versão otimizada (mesma regra lógica)."""

    def test_supervisor_outra_area_retorna_false(self):
        supervisor = _usuario_mock("supervisor", areas=["AreaA"])
        chamado = _chamado_mock(area="AreaB", responsavel_id=None)
        assert usuario_pode_ver_chamado_otimizado(supervisor, chamado) is False

    def test_supervisor_mesma_area_fila_retorna_true(self):
        """Fila (sem owner) na mesma área retorna True."""
        supervisor = _usuario_mock("supervisor", areas=["AreaA"])
        chamado = _chamado_mock(area="AreaA", responsavel_id=None)
        assert usuario_pode_ver_chamado_otimizado(supervisor, chamado) is True

    def test_supervisor_mesma_area_colega_owner_retorna_false(self):
        """Colega como owner bloqueia acesso mesmo na mesma área — versão otimizada."""
        supervisor = _usuario_mock("supervisor", areas=["AreaA"], uid="sup_test")
        chamado = _chamado_mock(area="AreaA", responsavel_id="sup_colega")
        assert usuario_pode_ver_chamado_otimizado(supervisor, chamado) is False

    def test_admin_retorna_true_ignora_cache(self):
        admin = _usuario_mock("admin", areas=[])
        chamado = _chamado_mock(area="Qualquer")
        assert usuario_pode_ver_chamado_otimizado(admin, chamado, cache_usuarios={}) is True

    def test_solicitante_nao_pode_ver_chamado_alheio(self):
        """Solicitante com solicitante_id diferente do seu id retorna False."""
        sol = _usuario_mock("solicitante", areas=["TI"], uid="sol_abc")
        chamado = _chamado_mock(area="TI", solicitante_id="outro_usuario")
        assert usuario_pode_ver_chamado_otimizado(sol, chamado) is False

    def test_solicitante_pode_ver_proprio_chamado_otimizado(self):
        """Solicitante pode ver o próprio chamado na versão otimizada."""
        sol = _usuario_mock("solicitante", areas=[], uid="sol_xyz")
        chamado = _chamado_mock(area="TI", solicitante_id="sol_xyz")
        assert usuario_pode_ver_chamado_otimizado(sol, chamado) is True

    def test_supervisor_solicitante_do_chamado_retorna_true(self):
        """Supervisor que abriu o chamado (solicitante_id == user.id) pode ver."""
        sup = _usuario_mock("supervisor", areas=[])
        sup.id = "sup_id_123"
        chamado = MagicMock()
        chamado.area = "OutraArea"
        chamado.solicitante_id = "sup_id_123"
        chamado.responsavel_id = "outra_pessoa"
        chamado.participantes = []
        assert usuario_pode_ver_chamado_otimizado(sup, chamado) is True

    def test_supervisor_nao_ve_ticket_atribuido_a_colega_otimizado(self):
        """Versão otimizada: Júlia não vê ticket de Matheus na mesma área."""
        chamado = _chamado_mock(area="Engenharia", responsavel_id="id_matheus")
        julia = _usuario_mock("supervisor", areas=["Engenharia"], uid="id_julia")
        assert usuario_pode_ver_chamado_otimizado(julia, chamado) is False


class TestCalcularSupervisorIdsComAcesso:
    """Lacuna 7: cobertura de calcular_supervisor_ids_com_acesso."""

    def test_com_responsavel_inclui_apenas_owner(self):
        """Com responsavel_id: resultado contém apenas o owner (sem busca ao Firestore)."""
        ids = calcular_supervisor_ids_com_acesso("Manutencao", "owner_id", [])
        assert "owner_id" in ids

    def test_com_responsavel_nao_busca_supervisores_da_area(self):
        """Com responsavel_id: get_supervisores_por_area NÃO deve ser chamado."""
        with patch("app.services.permissions.Usuario") as mock_usuario_cls:
            calcular_supervisor_ids_com_acesso("Manutencao", "owner_id", [])
        mock_usuario_cls.get_supervisores_por_area.assert_not_called()

    def test_sem_responsavel_inclui_supervisores_da_area(self):
        """Sem owner: inclui todos supervisores/admins da área."""
        sup = MagicMock()
        sup.id = "sup_area"
        with patch("app.services.permissions.Usuario") as mock_usuario_cls:
            mock_usuario_cls.get_supervisores_por_area.return_value = [sup]
            ids = calcular_supervisor_ids_com_acesso("Manutencao", None, [])
        assert "sup_area" in ids

    def test_participantes_sempre_incluidos(self):
        """Participantes são incluídos independente de haver owner."""
        participante = {"supervisor_id": "part_id"}
        ids = calcular_supervisor_ids_com_acesso("Manutencao", "owner_id", [participante])
        assert "part_id" in ids
        assert "owner_id" in ids

    def test_retorna_lista_ordenada_e_deduplicada(self):
        """Resultado é lista deduplicada e ordenada alfabeticamente."""
        participante = {"supervisor_id": "zz_id"}
        ids = calcular_supervisor_ids_com_acesso("Manutencao", "aa_id", [participante])
        assert ids == sorted(set(ids))
        assert len(ids) == len(set(ids))

    def test_excecao_em_get_supervisores_e_swallowed(self):
        """Exceção em get_supervisores_por_area é absorvida (fail-open)."""
        with patch("app.services.permissions.Usuario") as mock_usuario_cls:
            mock_usuario_cls.get_supervisores_por_area.side_effect = RuntimeError("db down")
            ids = calcular_supervisor_ids_com_acesso("Manutencao", None, [])
        assert isinstance(ids, list)


# Regression test: isolamento de colegas (Fase 2 — supervisor vê apenas seus chamados)


def test_regression_supervisor_colega_owner_nao_ve_na_fila():
    """Regressão Fase 2: supervisor não vê chamado com owner diferente na mesma área."""
    chamado = _chamado_mock(area="TI", responsavel_id="id_colega", solicitante_id="sol_x")
    julia = _usuario_mock("supervisor", areas=["TI"], uid="id_julia")
    assert usuario_pode_ver_chamado(julia, chamado) is False


class TestPermissoesAdicionais:
    def test_supervisor_pode_ver_chamado_que_abriu(self):
        """Supervisor que abriu o chamado (solicitante_id == user.id) pode ver — versão base."""
        sup = _usuario_mock("supervisor", areas=[])
        sup.id = "sup42"
        chamado = MagicMock()
        chamado.area = "OutraArea"
        chamado.responsavel_id = "outro_sup"
        chamado.solicitante_id = "sup42"
        chamado.participantes = []
        assert usuario_pode_ver_chamado(sup, chamado) is True
