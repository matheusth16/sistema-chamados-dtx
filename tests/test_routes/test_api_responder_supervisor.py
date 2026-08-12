"""
TDD: rota POST /api/chamado/<id>/responder.

Via inversa de test_api_responder_solicitante.py — aqui é o RESPONSÁVEL
(supervisor/admin) respondendo ao solicitante, não o contrário.

Regras:
- Só supervisor/admin da área pode usar (validado pelo service)
- JSON: mensagem (str) — sem exigir anexo
- Mensagem vazia → 400 sem chamar o service
- Solicitante não pode usar → 403 direto na rota
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


class TestResponderSupervisorRota:
    def test_supervisor_da_area_pode_responder(self, client_logado_supervisor, app):
        """POST /api/chamado/ch1/responder por supervisor → 200 sucesso."""
        sup = _usuario_mock("sup_1", "supervisor")

        with (
            patch("app.models_usuario.Usuario.get_by_id", return_value=sup),
            patch(
                "app.services.edicao_chamado_service.responder_chamado_supervisor",
                return_value={"sucesso": True},
            ),
        ):
            resp = client_logado_supervisor.post(
                "/api/chamado/ch1/responder",
                data=json.dumps({"mensagem": "Já verificamos, aguardando a peça."}),
                content_type="application/json",
            )

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["sucesso"] is True

    def test_admin_pode_responder(self, client_logado_admin, app):
        adm = _usuario_mock("adm_1", "admin")

        with (
            patch("app.models_usuario.Usuario.get_by_id", return_value=adm),
            patch(
                "app.services.edicao_chamado_service.responder_chamado_supervisor",
                return_value={"sucesso": True},
            ),
        ):
            resp = client_logado_admin.post(
                "/api/chamado/ch1/responder",
                data=json.dumps({"mensagem": "Resposta qualquer"}),
                content_type="application/json",
            )

        assert resp.status_code == 200

    def test_solicitante_recebe_403_direto_na_rota(self, client_logado_solicitante, app):
        """Solicitante não é supervisor/admin — bloqueado antes de chamar o service."""
        sol = _usuario_mock("sol_1", "solicitante")

        with (
            patch("app.models_usuario.Usuario.get_by_id", return_value=sol),
            patch("app.services.edicao_chamado_service.responder_chamado_supervisor") as mock_svc,
        ):
            resp = client_logado_solicitante.post(
                "/api/chamado/ch1/responder",
                data=json.dumps({"mensagem": "Resposta qualquer"}),
                content_type="application/json",
            )

        assert resp.status_code == 403
        mock_svc.assert_not_called()

    def test_supervisor_fora_da_area_recebe_403_do_service(self, client_logado_supervisor, app):
        sup = _usuario_mock("sup_1", "supervisor")

        with (
            patch("app.models_usuario.Usuario.get_by_id", return_value=sup),
            patch(
                "app.services.edicao_chamado_service.responder_chamado_supervisor",
                return_value={"sucesso": False, "erro": "Sem permissão.", "codigo": 403},
            ),
        ):
            resp = client_logado_supervisor.post(
                "/api/chamado/ch1/responder",
                data=json.dumps({"mensagem": "Resposta qualquer"}),
                content_type="application/json",
            )

        assert resp.status_code == 403

    def test_mensagem_vazia_retorna_400_sem_chamar_service(self, client_logado_supervisor, app):
        sup = _usuario_mock("sup_1", "supervisor")

        with (
            patch("app.models_usuario.Usuario.get_by_id", return_value=sup),
            patch("app.services.edicao_chamado_service.responder_chamado_supervisor") as mock_svc,
        ):
            resp = client_logado_supervisor.post(
                "/api/chamado/ch1/responder",
                data=json.dumps({"mensagem": ""}),
                content_type="application/json",
            )

        assert resp.status_code == 400
        mock_svc.assert_not_called()

    def test_gestor_only_recebe_403_direto_na_rota(self, client_logado_supervisor, app):
        gestor_only = _usuario_mock("sup_1", "supervisor", is_gestor_only=True)

        with (
            patch("app.models_usuario.Usuario.get_by_id", return_value=gestor_only),
            patch("app.services.edicao_chamado_service.responder_chamado_supervisor") as mock_svc,
        ):
            resp = client_logado_supervisor.post(
                "/api/chamado/ch1/responder",
                data=json.dumps({"mensagem": "Resposta qualquer"}),
                content_type="application/json",
            )

        assert resp.status_code == 403
        mock_svc.assert_not_called()

    def test_sem_login_redireciona(self, client, app):
        resp = client.post(
            "/api/chamado/ch1/responder",
            data=json.dumps({"mensagem": "Resposta qualquer"}),
            content_type="application/json",
        )
        assert resp.status_code in (302, 401, 403)

    def test_service_retorna_erro_propaga_codigo(self, client_logado_supervisor, app):
        sup = _usuario_mock("sup_1", "supervisor")
        resultado_service = {
            "sucesso": False,
            "erro": "Chamado bloqueado para edição.",
            "codigo": 403,
        }

        with (
            patch("app.models_usuario.Usuario.get_by_id", return_value=sup),
            patch(
                "app.services.edicao_chamado_service.responder_chamado_supervisor",
                return_value=resultado_service,
            ),
        ):
            resp = client_logado_supervisor.post(
                "/api/chamado/ch1/responder",
                data=json.dumps({"mensagem": "Resposta qualquer"}),
                content_type="application/json",
            )

        assert resp.status_code == 403
        data = json.loads(resp.data)
        assert data["sucesso"] is False
