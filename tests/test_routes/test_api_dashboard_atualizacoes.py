"""TDD: rota GET /api/dashboard/tem-atualizacoes — polling leve do dashboard
(Gestão de Chamados) pra avisar sobre mudanças novas sem recarregar
automaticamente (generaliza o padrão de mensagens-novas da Conversa)."""

from app.models_historico import Historico


def _hist(chamado_id, acao="criacao"):
    h = Historico(chamado_id=chamado_id, usuario_id="u1", usuario_nome="U1", acao=acao)
    assert h.save()
    return h


class TestDashboardTemAtualizacoesRota:
    def test_sem_login_retorna_401(self, client, db_session):
        r = client.get("/api/dashboard/tem-atualizacoes")
        assert r.status_code == 401

    def test_solicitante_nao_ve_atualizacao_de_chamado_alheio(
        self, client_logado_solicitante, db_session
    ):
        """Item 4 do plano de tempo real (Meus Chamados): endpoint agora é
        acessível ao solicitante, mas escopado só aos próprios chamados —
        deixou de ser exclusivo de supervisor/admin."""
        from tests.factories import make_chamado

        chamado = make_chamado(solicitante_id="outro_solicitante")
        _hist(chamado.id)

        r = client_logado_solicitante.get("/api/dashboard/tem-atualizacoes?apos_id=0")

        assert r.status_code == 200
        assert r.get_json()["tem_atualizacoes"] is False

    def test_solicitante_ve_atualizacao_do_proprio_chamado(
        self, client_logado_solicitante, db_session
    ):
        from tests.factories import make_chamado

        chamado = make_chamado(solicitante_id="sol_1")
        h = _hist(chamado.id)

        r = client_logado_solicitante.get("/api/dashboard/tem-atualizacoes?apos_id=0")

        assert r.status_code == 200
        data = r.get_json()
        assert data["tem_atualizacoes"] is True
        assert data["cursor_atual"] == h.id

    def test_admin_sem_apos_id_nao_acusa_atualizacao_sobre_o_cursor_atual(
        self, client_logado_admin, db_session
    ):
        from tests.factories import make_chamado

        chamado = make_chamado()
        h = _hist(chamado.id)

        r = client_logado_admin.get(f"/api/dashboard/tem-atualizacoes?apos_id={h.id}")

        assert r.status_code == 200
        data = r.get_json()
        assert data["sucesso"] is True
        assert data["tem_atualizacoes"] is False

    def test_admin_ve_atualizacao_apos_cursor_antigo(self, client_logado_admin, db_session):
        from tests.factories import make_chamado

        chamado = make_chamado()
        h = _hist(chamado.id)

        r = client_logado_admin.get("/api/dashboard/tem-atualizacoes?apos_id=0")

        assert r.status_code == 200
        data = r.get_json()
        assert data["tem_atualizacoes"] is True
        assert data["cursor_atual"] == h.id

    def test_supervisor_nao_ve_atualizacao_de_area_alheia(
        self, client_logado_supervisor, db_session
    ):
        from tests.factories import make_chamado

        chamado = make_chamado(area="TI", supervisor_ids_com_acesso=["outro_supervisor"])
        _hist(chamado.id)

        r = client_logado_supervisor.get("/api/dashboard/tem-atualizacoes?apos_id=0")

        assert r.status_code == 200
        assert r.get_json()["tem_atualizacoes"] is False

    def test_supervisor_ve_atualizacao_da_propria_area(self, client_logado_supervisor, db_session):
        from tests.factories import make_chamado

        chamado = make_chamado(area="Manutencao", supervisor_ids_com_acesso=["sup_1"])
        h = _hist(chamado.id)

        r = client_logado_supervisor.get("/api/dashboard/tem-atualizacoes?apos_id=0")

        assert r.status_code == 200
        data = r.get_json()
        assert data["tem_atualizacoes"] is True
        assert data["cursor_atual"] == h.id
