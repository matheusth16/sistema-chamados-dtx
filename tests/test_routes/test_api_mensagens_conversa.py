"""TDD: rota GET /api/chamado/<id>/mensagens-novas — polling da Conversa
(solicitante ↔ responsável) pra atualizar sem recarregar a página."""

from app.models_historico import Historico


def _msg(chamado_id, acao, usuario_nome="Fulano", texto="oi"):
    h = Historico(
        chamado_id=chamado_id,
        usuario_id="u1",
        usuario_nome=usuario_nome,
        acao=acao,
        valor_novo=texto,
    )
    assert h.save()
    return h


class TestMensagensNovasRota:
    def test_sem_login_retorna_401(self, client, db_session):
        from tests.factories import make_chamado

        chamado = make_chamado()
        r = client.get(f"/api/chamado/{chamado.id}/mensagens-novas")
        assert r.status_code == 401

    def test_chamado_inexistente_retorna_404(self, client_logado_admin, db_session):
        r = client_logado_admin.get("/api/chamado/999999999/mensagens-novas")
        assert r.status_code == 404

    def test_solicitante_de_outro_chamado_recebe_403(self, client_logado_solicitante, db_session):
        from tests.factories import make_chamado

        chamado = make_chamado(solicitante_id="outro_usuario_id")
        r = client_logado_solicitante.get(f"/api/chamado/{chamado.id}/mensagens-novas")
        assert r.status_code == 403

    def test_dono_do_chamado_ve_mensagens_novas(self, client_logado_solicitante, db_session):
        from tests.factories import make_chamado

        chamado = make_chamado(solicitante_id="sol_1")
        _msg(chamado.id, "resposta_responsavel", usuario_nome="Supervisor", texto="Já verificamos")

        r = client_logado_solicitante.get(f"/api/chamado/{chamado.id}/mensagens-novas")

        assert r.status_code == 200
        data = r.get_json()
        assert data["sucesso"] is True
        assert len(data["mensagens"]) == 1
        assert data["mensagens"][0]["texto"] == "Já verificamos"
        assert data["mensagens"][0]["eh_solicitante"] is False

    def test_apos_id_filtra_mensagens_ja_vistas(self, client_logado_supervisor, db_session):
        from tests.factories import make_chamado

        chamado = make_chamado(area="Manutencao", responsavel_id=None)
        m1 = _msg(chamado.id, "resposta_solicitante", texto="primeira")
        _msg(chamado.id, "resposta_responsavel", texto="segunda")

        r = client_logado_supervisor.get(
            f"/api/chamado/{chamado.id}/mensagens-novas?apos_id={m1.id}"
        )

        assert r.status_code == 200
        data = r.get_json()
        assert len(data["mensagens"]) == 1
        assert data["mensagens"][0]["texto"] == "segunda"

    def test_sem_apos_id_retorna_todas_as_mensagens(self, client_logado_supervisor, db_session):
        from tests.factories import make_chamado

        chamado = make_chamado(area="Manutencao", responsavel_id=None)
        _msg(chamado.id, "resposta_solicitante", texto="primeira")
        _msg(chamado.id, "resposta_responsavel", texto="segunda")

        r = client_logado_supervisor.get(f"/api/chamado/{chamado.id}/mensagens-novas")

        assert r.status_code == 200
        assert len(r.get_json()["mensagens"]) == 2

    def test_sem_mensagens_novas_retorna_lista_vazia(self, client_logado_supervisor, db_session):
        from tests.factories import make_chamado

        chamado = make_chamado(area="Manutencao", responsavel_id=None)
        r = client_logado_supervisor.get(f"/api/chamado/{chamado.id}/mensagens-novas")
        assert r.status_code == 200
        assert r.get_json()["mensagens"] == []
