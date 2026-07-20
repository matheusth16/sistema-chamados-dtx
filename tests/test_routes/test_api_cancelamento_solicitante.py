"""
Fase 4 — TDD: rota POST /api/chamado/<id>/cancelar-solicitante.
"""

import json
from unittest.mock import MagicMock, patch


def _usuario_mock(uid, perfil):
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
    u.is_gestor_only = False
    u.nivel_gestao = None
    return u


class TestCancelarSolicitanteRota:
    def test_solicitante_owner_pode_cancelar(self, client_logado_solicitante, app):
        """POST /api/chamado/ch1/cancelar-solicitante com motivo válido → 200."""
        sol = _usuario_mock("sol_1", "solicitante")

        with (
            patch("app.models_usuario.Usuario.get_by_id", return_value=sol),
            patch(
                "app.routes.api_solicitante.cancelar_chamado_solicitante",
                return_value={"sucesso": True},
            ),
        ):
            resp = client_logado_solicitante.post(
                "/api/chamado/ch1/cancelar-solicitante",
                data=json.dumps({"motivo": "Problema resolvido por outra via"}),
                content_type="application/json",
            )

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["sucesso"] is True

    def test_supervisor_nao_dono_recebe_403_do_service(self, client_logado_supervisor, app):
        """Supervisor que NÃO é dono → 403 do service (rota não bloqueia por perfil)."""
        sup = _usuario_mock("sup_1", "supervisor")

        with (
            patch("app.models_usuario.Usuario.get_by_id", return_value=sup),
            patch(
                "app.routes.api_solicitante.cancelar_chamado_solicitante",
                return_value={"sucesso": False, "erro": "Sem permissão.", "codigo": 403},
            ),
        ):
            resp = client_logado_supervisor.post(
                "/api/chamado/ch1/cancelar-solicitante",
                data=json.dumps({"motivo": "Motivo suficientemente longo aqui"}),
                content_type="application/json",
            )

        assert resp.status_code == 403

    def test_supervisor_dono_pode_cancelar(self, client_logado_supervisor, app):
        """Lacuna D: supervisor que é dono do chamado consegue cancelar."""
        sup = _usuario_mock("sup_1", "supervisor")

        with (
            patch("app.models_usuario.Usuario.get_by_id", return_value=sup),
            patch(
                "app.routes.api_solicitante.cancelar_chamado_solicitante",
                return_value={"sucesso": True},
            ),
        ):
            resp = client_logado_supervisor.post(
                "/api/chamado/ch1/cancelar-solicitante",
                data=json.dumps({"motivo": "Motivo suficientemente longo aqui"}),
                content_type="application/json",
            )

        assert resp.status_code == 200

    def test_motivo_vazio_retorna_400(self, client_logado_solicitante, app):
        """Motivo vazio → 400 sem chamar service."""
        sol = _usuario_mock("sol_1", "solicitante")

        with patch("app.models_usuario.Usuario.get_by_id", return_value=sol):
            resp = client_logado_solicitante.post(
                "/api/chamado/ch1/cancelar-solicitante",
                data=json.dumps({"motivo": ""}),
                content_type="application/json",
            )

        assert resp.status_code == 400

    def test_service_erro_propaga_codigo(self, client_logado_solicitante, app):
        """Se service retorna {sucesso: False, codigo: 403} → rota propaga 403."""
        sol = _usuario_mock("sol_1", "solicitante")

        with (
            patch("app.models_usuario.Usuario.get_by_id", return_value=sol),
            patch(
                "app.routes.api_solicitante.cancelar_chamado_solicitante",
                return_value={
                    "sucesso": False,
                    "erro": "Não pode cancelar chamado concluído.",
                    "codigo": 403,
                },
            ),
        ):
            resp = client_logado_solicitante.post(
                "/api/chamado/ch1/cancelar-solicitante",
                data=json.dumps({"motivo": "Motivo suficientemente longo"}),
                content_type="application/json",
            )

        assert resp.status_code == 403
        data = json.loads(resp.data)
        assert data["sucesso"] is False

    def test_sem_login_redireciona(self, client, app):
        """Sem sessão → redirect."""
        resp = client.post(
            "/api/chamado/ch1/cancelar-solicitante",
            data=json.dumps({"motivo": "Qualquer"}),
            content_type="application/json",
        )
        assert resp.status_code in (302, 401, 403)
