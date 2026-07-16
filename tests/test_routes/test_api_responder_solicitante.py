"""
TDD: rota POST /api/chamado/<id>/responder-solicitante.

Regras:
- Só o solicitante dono pode usar (validado pelo service)
- JSON: mensagem (str) — sem exigir anexo
- Mensagem vazia → 400 sem chamar o service
- Supervisor/admin que não é dono → 403 do service
- is_gestor_only → 403 direto na rota
"""

import json
from unittest.mock import MagicMock, patch


def _usuario_mock(uid, perfil, is_gestor_only=False):
    u = MagicMock()
    u.id = uid
    u.nome = f"User {uid}"
    u.email = f"{uid}@test.com"
    u.perfil = perfil
    u.is_admin_or_above = perfil in ("admin", "admin_global")
    u.is_supervisor_or_above = perfil in ("supervisor", "admin", "admin_global")
    u.is_authenticated = True
    u.get_id = lambda: str(uid)
    u.must_change_password = False
    u.mfa_enabled = True
    u.onboarding_perfis_vistos = [perfil]
    u.onboarding_passo = 0
    u.is_gestor = False
    u.is_gestor_only = is_gestor_only
    u.nivel_gestao = None
    return u


class TestResponderSolicitanteRota:
    def test_solicitante_owner_pode_responder(self, client_logado_solicitante, app):
        """POST /api/chamado/ch1/responder-solicitante por dono → 200 sucesso."""
        sol = _usuario_mock("sol_1", "solicitante")

        with (
            patch("app.models_usuario.Usuario.get_by_id", return_value=sol),
            patch(
                "app.routes.api.responder_chamado_solicitante",
                return_value={"sucesso": True},
            ),
        ):
            resp = client_logado_solicitante.post(
                "/api/chamado/ch1/responder-solicitante",
                data=json.dumps({"mensagem": "Modelo XYZ-123"}),
                content_type="application/json",
            )

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["sucesso"] is True

    def test_supervisor_nao_dono_recebe_403_do_service(self, client_logado_supervisor, app):
        sup = _usuario_mock("sup_1", "supervisor")

        with (
            patch("app.models_usuario.Usuario.get_by_id", return_value=sup),
            patch(
                "app.routes.api.responder_chamado_solicitante",
                return_value={"sucesso": False, "erro": "Sem permissão.", "codigo": 403},
            ),
        ):
            resp = client_logado_supervisor.post(
                "/api/chamado/ch1/responder-solicitante",
                data=json.dumps({"mensagem": "Resposta qualquer"}),
                content_type="application/json",
            )

        assert resp.status_code == 403

    def test_supervisor_dono_pode_responder(self, client_logado_supervisor, app):
        sup = _usuario_mock("sup_1", "supervisor")

        with (
            patch("app.models_usuario.Usuario.get_by_id", return_value=sup),
            patch(
                "app.routes.api.responder_chamado_solicitante",
                return_value={"sucesso": True},
            ),
        ):
            resp = client_logado_supervisor.post(
                "/api/chamado/ch1/responder-solicitante",
                data=json.dumps({"mensagem": "Resposta qualquer"}),
                content_type="application/json",
            )

        assert resp.status_code == 200

    def test_mensagem_vazia_retorna_400_sem_chamar_service(self, client_logado_solicitante, app):
        sol = _usuario_mock("sol_1", "solicitante")

        with (
            patch("app.models_usuario.Usuario.get_by_id", return_value=sol),
            patch("app.routes.api.responder_chamado_solicitante") as mock_svc,
        ):
            resp = client_logado_solicitante.post(
                "/api/chamado/ch1/responder-solicitante",
                data=json.dumps({"mensagem": ""}),
                content_type="application/json",
            )

        assert resp.status_code == 400
        mock_svc.assert_not_called()

    def test_gestor_only_recebe_403_direto_na_rota(self, client_logado_solicitante, app):
        gestor_only = _usuario_mock("sol_1", "solicitante", is_gestor_only=True)

        with (
            patch("app.models_usuario.Usuario.get_by_id", return_value=gestor_only),
            patch("app.routes.api.responder_chamado_solicitante") as mock_svc,
        ):
            resp = client_logado_solicitante.post(
                "/api/chamado/ch1/responder-solicitante",
                data=json.dumps({"mensagem": "Resposta qualquer"}),
                content_type="application/json",
            )

        assert resp.status_code == 403
        mock_svc.assert_not_called()

    def test_sem_login_redireciona(self, client, app):
        resp = client.post(
            "/api/chamado/ch1/responder-solicitante",
            data=json.dumps({"mensagem": "Resposta qualquer"}),
            content_type="application/json",
        )
        assert resp.status_code in (302, 401, 403)

    def test_service_retorna_erro_propaga_codigo(self, client_logado_solicitante, app):
        sol = _usuario_mock("sol_1", "solicitante")
        resultado_service = {
            "sucesso": False,
            "erro": "Não é possível responder com status 'Concluído'.",
            "codigo": 403,
        }

        with (
            patch("app.models_usuario.Usuario.get_by_id", return_value=sol),
            patch(
                "app.routes.api.responder_chamado_solicitante",
                return_value=resultado_service,
            ),
        ):
            resp = client_logado_solicitante.post(
                "/api/chamado/ch1/responder-solicitante",
                data=json.dumps({"mensagem": "Resposta qualquer"}),
                content_type="application/json",
            )

        assert resp.status_code == 403
        data = json.loads(resp.data)
        assert data["sucesso"] is False
