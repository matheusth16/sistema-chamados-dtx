"""
Fase 0 — TDD: observadores no modelo Chamado + permissões + listagem.

Testes escritos ANTES da implementação (Red → Green → Refactor).
"""

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _chamado_mock(
    area="Manutencao",
    responsavel_id=None,
    solicitante_id="sol_1",
    participantes=None,
    observadores=None,
):
    c = MagicMock()
    c.area = area
    c.responsavel_id = responsavel_id
    c.solicitante_id = solicitante_id
    c.participantes = participantes or []
    c.observadores = observadores or []
    return c


def _usuario_mock(perfil, uid="u_1", areas=None):
    u = MagicMock()
    u.id = uid
    u.perfil = perfil
    u.areas = areas or []
    u.is_admin_or_above = perfil in ("admin", "admin_global")
    u.is_supervisor_or_above = perfil in ("supervisor", "admin", "admin_global")
    u.is_gestor = False
    u.is_gestor_only = False
    return u


# ---------------------------------------------------------------------------
# Modelo Chamado — campo observadores
# ---------------------------------------------------------------------------


class TestModeloObservadores:
    def test_chamado_inicia_com_observadores_vazio(self):
        from app.models import Chamado

        c = Chamado(
            categoria="TI",
            tipo_solicitacao="Suporte",
            descricao="Teste",
            responsavel="sup",
        )
        assert c.observadores == []

    def test_chamado_aceita_observadores_na_criacao(self):
        from app.models import Chamado

        obs = [{"usuario_id": "u1", "nome": "Alice", "email": "alice@test.com"}]
        c = Chamado(
            categoria="TI",
            tipo_solicitacao="Suporte",
            descricao="Teste",
            responsavel="sup",
            observadores=obs,
        )
        assert c.observadores == obs

    def test_to_dict_inclui_observadores(self):
        from app.models import Chamado

        obs = [{"usuario_id": "u1", "nome": "Alice", "email": "alice@test.com"}]
        c = Chamado(
            categoria="TI",
            tipo_solicitacao="Suporte",
            descricao="Teste",
            responsavel="sup",
            observadores=obs,
        )
        d = c.to_dict()
        assert "observadores" in d
        assert d["observadores"] == obs

    def test_from_dict_carrega_observadores(self):
        from app.models import Chamado

        obs = [{"usuario_id": "u1", "nome": "Alice", "email": "alice@test.com"}]
        data = {
            "categoria": "TI",
            "tipo_solicitacao": "Suporte",
            "descricao": "Teste",
            "responsavel": "sup",
            "observadores": obs,
        }
        c = Chamado.from_dict(data, id="abc")
        assert c.observadores == obs

    def test_from_dict_sem_observadores_retorna_lista_vazia(self):
        from app.models import Chamado

        data = {
            "categoria": "TI",
            "tipo_solicitacao": "Suporte",
            "descricao": "Teste",
            "responsavel": "sup",
        }
        c = Chamado.from_dict(data, id="abc")
        assert c.observadores == []

    def test_from_dict_observadores_invalido_retorna_lista_vazia(self):
        """Protege contra dados corrompidos no Firestore (campo não-lista)."""
        from app.models import Chamado

        data = {
            "categoria": "TI",
            "tipo_solicitacao": "Suporte",
            "descricao": "Teste",
            "responsavel": "sup",
            "observadores": "nao_e_lista",
        }
        c = Chamado.from_dict(data, id="abc")
        assert c.observadores == []


# ---------------------------------------------------------------------------
# Permissões — observador pode VER (read-only)
# ---------------------------------------------------------------------------


class TestPermissoesObservador:
    def test_solicitante_observador_ve_chamado_alheio(self):
        """Solicitante que está em observadores[] de um chamado alheio pode ver."""
        from app.services.permissions import usuario_pode_ver_chamado

        user = _usuario_mock("solicitante", uid="obs_id")
        chamado = _chamado_mock(
            solicitante_id="outro_dono",
            observadores=[{"usuario_id": "obs_id", "nome": "Obs", "email": "obs@test.com"}],
        )
        assert usuario_pode_ver_chamado(user, chamado) is True

    def test_solicitante_nao_observador_nao_ve_chamado_alheio(self):
        """Solicitante fora de observadores não acessa chamado alheio."""
        from app.services.permissions import usuario_pode_ver_chamado

        user = _usuario_mock("solicitante", uid="outro_id")
        chamado = _chamado_mock(
            solicitante_id="dono_id",
            observadores=[{"usuario_id": "obs_id", "nome": "Obs", "email": "obs@test.com"}],
        )
        assert usuario_pode_ver_chamado(user, chamado) is False

    def test_supervisor_observador_ve_chamado_fora_area(self):
        """Supervisor em observadores vê o chamado mesmo fora da sua área."""
        from app.services.permissions import usuario_pode_ver_chamado

        user = _usuario_mock("supervisor", uid="sup_obs", areas=["TI"])
        chamado = _chamado_mock(
            area="Manutencao",
            responsavel_id="outro_sup",
            solicitante_id="sol_x",
            observadores=[{"usuario_id": "sup_obs", "nome": "Sup", "email": "s@t.com"}],
        )
        assert usuario_pode_ver_chamado(user, chamado) is True

    def test_observadores_separado_de_participantes(self):
        """Campo observadores é independente de participantes (supervisores operacionais)."""
        from app.services.permissions import usuario_pode_ver_chamado

        user = _usuario_mock("solicitante", uid="obs_id")
        # participantes tem outro_sup, observadores tem obs_id
        chamado = _chamado_mock(
            solicitante_id="dono",
            participantes=[{"supervisor_id": "outro_sup"}],
            observadores=[{"usuario_id": "obs_id", "nome": "Obs", "email": "obs@t.com"}],
        )
        assert usuario_pode_ver_chamado(user, chamado) is True

    def test_observador_chamado_aceita_edicao_operacional_nao_bloqueado_por_observador(self):
        """chamado_aceita_edicao_operacional é sobre congelamento de status, não observador.

        O controle de quem EDITA (vs só visualiza) é feito nas rotas por perfil.
        Observador com chamado não-Concluído: chamado_aceita_edicao_operacional retorna True.
        """
        from app.services.permission_validation import chamado_aceita_edicao_operacional

        user = _usuario_mock("solicitante", uid="obs_id")
        chamado = _chamado_mock()
        chamado.status = "Aberto"
        chamado.confirmacao_solicitante = None
        # Observadores em chamado não-Concluído não são bloqueados por essa função
        pode, _ = chamado_aceita_edicao_operacional(user, chamado)
        assert pode is True


# ---------------------------------------------------------------------------
# Validators — validar_observadores
# ---------------------------------------------------------------------------


class TestValidarObservadores:
    def test_lista_vazia_valida(self):
        from app.services.validators import validar_observadores

        erros = validar_observadores([], solicitante_id="sol_1")
        assert erros == []

    def test_maximo_5_observadores(self):
        from app.services.validators import validar_observadores

        obs = [{"usuario_id": f"u{i}"} for i in range(6)]
        with patch("app.models_usuario.Usuario.get_by_id", return_value=None):
            erros = validar_observadores(obs, solicitante_id="sol_1")
        assert any("5" in e or "máximo" in e.lower() for e in erros)

    def test_solicitante_nao_pode_ser_observador(self):
        from app.services.validators import validar_observadores

        obs = [{"usuario_id": "sol_1", "nome": "Sol", "email": "s@t.com"}]
        with patch("app.models_usuario.Usuario.get_by_id", return_value=None):
            erros = validar_observadores(obs, solicitante_id="sol_1")
        assert any("requester" in e.lower() or "own ticket" in e.lower() for e in erros)

    def test_deduplica_observadores(self):
        """validar_observadores remove duplicatas silenciosamente (sem erro)."""
        from app.services.validators import validar_observadores

        obs = [
            {"usuario_id": "u1", "nome": "A", "email": "a@t.com"},
            {"usuario_id": "u1", "nome": "A", "email": "a@t.com"},
        ]
        with patch("app.models_usuario.Usuario.get_by_id", return_value=None):
            erros = validar_observadores(obs, solicitante_id="sol_1")
        assert erros == []

    def test_ids_invalidos_retornam_erro(self):
        """Observadores com usuario_id faltando geram erro."""
        from app.services.validators import validar_observadores

        obs = [{"nome": "Sem ID"}]
        erros = validar_observadores(obs, solicitante_id="sol_1")
        assert len(erros) > 0


# ---------------------------------------------------------------------------
# Listagem — chamados onde user é observador aparecem em meus_chamados
# ---------------------------------------------------------------------------


class TestListagemObservador:
    def test_listar_chamados_como_observador(self):
        """listar_chamados_observador retorna chamados onde user está em observadores[]."""
        from app.services.chamados_listagem_service import listar_chamados_como_observador

        obs_doc = MagicMock()
        obs_doc.id = "chamado_obs_1"
        obs_doc.to_dict.return_value = {
            "categoria": "TI",
            "tipo_solicitacao": "Suporte",
            "descricao": "X",
            "responsavel": "sup",
            "status": "Aberto",
            "observadores": [{"usuario_id": "u_obs", "nome": "Obs", "email": "o@t.com"}],
        }

        mock_query = MagicMock()
        mock_query.where.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.stream.return_value = [obs_doc]

        with patch("app.services.chamados_listagem_service.db") as mock_db:
            mock_db.collection.return_value.where.return_value = mock_query
            chamados = listar_chamados_como_observador(user_id="u_obs")

        assert len(chamados) == 1
        assert chamados[0].id == "chamado_obs_1"

    def test_chamados_como_observador_marcados(self):
        """Chamados retornados por listar_chamados_como_observador têm flag em_copia=True."""
        from app.services.chamados_listagem_service import listar_chamados_como_observador

        obs_doc = MagicMock()
        obs_doc.id = "ch_1"
        obs_doc.to_dict.return_value = {
            "categoria": "TI",
            "tipo_solicitacao": "Suporte",
            "descricao": "X",
            "responsavel": "sup",
            "status": "Aberto",
            "observadores": [{"usuario_id": "u_obs"}],
        }

        mock_query = MagicMock()
        mock_query.where.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.stream.return_value = [obs_doc]

        with patch("app.services.chamados_listagem_service.db") as mock_db:
            mock_db.collection.return_value.where.return_value = mock_query
            chamados = listar_chamados_como_observador(user_id="u_obs")

        assert chamados[0].em_copia is True
