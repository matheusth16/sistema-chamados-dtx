"""Testes da rota POST /api/chamado/<id>/previsao-atendimento.

Segue padrão do projeto (mesmo de test_api_escalonamento.py, Fase 2, Marco 10):
- patch('app.routes.api_colaboracao.Chamado') para simular Chamado.get_by_id() (Postgres)
- patch do serviço importado inline pela rota
- Usa fixtures client_logado_supervisor, client_logado_admin, client_logado_solicitante
"""

from unittest.mock import MagicMock, patch


def _mock_chamado_obj(area="Manutencao", responsavel_id="sup_1"):
    c = MagicMock()
    c.id = "id_chamado_teste"
    c.area = area
    c.responsavel_id = responsavel_id
    c.solicitante_id = "sol_outro"
    c.participantes = []
    c.supervisor_ids_com_acesso = [responsavel_id] if responsavel_id else []
    return c


class TestPrevisaoAtendimentoRota:
    def test_sucesso_retorna_200(self, client_logado_supervisor):
        """Owner supervisor pode definir previsão com payload válido → 200 sucesso=True."""
        chamado_mock = _mock_chamado_obj(area="Manutencao", responsavel_id="sup_1")

        with (
            patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls,
            patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=True),
            patch(
                "app.services.escalonamento_service.definir_previsao_atendimento",
                return_value={
                    "sucesso": True,
                    "dados": {"previsao_atendimento": "2026-07-15 16:00:00"},
                },
            ),
        ):
            mock_chamado_cls.get_by_id.return_value = chamado_mock

            resp = client_logado_supervisor.post(
                "/api/chamado/id123/previsao-atendimento",
                json={"previsao": "2026-07-15T16:00", "motivo": "Combinado com o gestor"},
                content_type="application/json",
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["sucesso"] is True

    def test_sem_motivo_retorna_400(self, client_logado_supervisor):
        chamado_mock = _mock_chamado_obj(area="Manutencao", responsavel_id="sup_1")

        with (
            patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls,
            patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=True),
        ):
            mock_chamado_cls.get_by_id.return_value = chamado_mock

            resp = client_logado_supervisor.post(
                "/api/chamado/id123/previsao-atendimento",
                json={"previsao": "2026-07-15T16:00", "motivo": ""},
                content_type="application/json",
            )

        assert resp.status_code == 400
        assert resp.get_json()["sucesso"] is False

    def test_sem_previsao_retorna_400(self, client_logado_supervisor):
        resp = client_logado_supervisor.post(
            "/api/chamado/id123/previsao-atendimento",
            json={"previsao": "", "motivo": "motivo válido"},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_previsao_invalida_retorna_400(self, client_logado_supervisor):
        resp = client_logado_supervisor.post(
            "/api/chamado/id123/previsao-atendimento",
            json={"previsao": "isso-nao-e-uma-data", "motivo": "motivo válido"},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_solicitante_retorna_302_ou_403(self, client_logado_solicitante):
        """Solicitante não tem acesso à rota de supervisor (@requer_supervisor_area)."""
        resp = client_logado_solicitante.post(
            "/api/chamado/id123/previsao-atendimento",
            json={"previsao": "2026-07-15T16:00", "motivo": "motivo"},
            content_type="application/json",
        )
        assert resp.status_code in (302, 403)

    def test_nao_owner_supervisor_retorna_403(self, client_logado_supervisor):
        """Supervisor que não é owner do chamado → 403."""
        chamado_mock = _mock_chamado_obj(area="Manutencao", responsavel_id="outro_sup")

        with (
            patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls,
            patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=True),
        ):
            mock_chamado_cls.get_by_id.return_value = chamado_mock

            resp = client_logado_supervisor.post(
                "/api/chamado/id123/previsao-atendimento",
                json={"previsao": "2026-07-15T16:00", "motivo": "motivo"},
                content_type="application/json",
            )

        assert resp.status_code == 403

    def test_idor_sem_acesso_retorna_403(self, client_logado_supervisor):
        """Supervisor sem acesso ao chamado (usuario_pode_ver_chamado=False) → 403."""
        chamado_mock = _mock_chamado_obj(area="TI", responsavel_id="outro_sup")

        with (
            patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls,
            patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=False),
        ):
            mock_chamado_cls.get_by_id.return_value = chamado_mock

            resp = client_logado_supervisor.post(
                "/api/chamado/id123/previsao-atendimento",
                json={"previsao": "2026-07-15T16:00", "motivo": "motivo"},
                content_type="application/json",
            )

        assert resp.status_code == 403

    def test_chamado_nao_encontrado_retorna_404(self, client_logado_supervisor):
        with patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls:
            mock_chamado_cls.get_by_id.return_value = None
            resp = client_logado_supervisor.post(
                "/api/chamado/id_inexistente/previsao-atendimento",
                json={"previsao": "2026-07-15T16:00", "motivo": "motivo"},
                content_type="application/json",
            )

        assert resp.status_code == 404

    def test_admin_nao_owner_permitido(self, client_logado_admin):
        """Admin pode definir mesmo não sendo owner do chamado."""
        chamado_mock = _mock_chamado_obj(area="Manutencao", responsavel_id="sup_1")

        with (
            patch("app.routes.api_colaboracao.Chamado") as mock_chamado_cls,
            patch("app.routes.api_colaboracao.usuario_pode_ver_chamado", return_value=True),
            patch(
                "app.services.escalonamento_service.definir_previsao_atendimento",
                return_value={
                    "sucesso": True,
                    "dados": {"previsao_atendimento": "2026-07-15 16:00:00"},
                },
            ),
        ):
            mock_chamado_cls.get_by_id.return_value = chamado_mock

            resp = client_logado_admin.post(
                "/api/chamado/id123/previsao-atendimento",
                json={"previsao": "2026-07-15T16:00", "motivo": "motivo"},
                content_type="application/json",
            )

        assert resp.status_code == 200
