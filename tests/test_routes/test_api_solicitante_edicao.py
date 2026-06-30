"""
Fase 3 — TDD: rota POST /api/chamado/<id>/editar-solicitante.

Regras:
- Só o solicitante dono pode usar esta rota
- Supervisores e admins recebem 403 (NÃO reutilizar /api/editar-chamado)
- Validações de janela/status ficam no service (já cobertas em test_solicitante_edicao_service)
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
    u.onboarding_completo = True
    u.onboarding_passo = 0
    u.is_gestor = False
    u.is_gestor_only = False
    u.nivel_gestao = None
    return u


class TestEditarSolicitanteRota:
    def test_solicitante_owner_pode_editar(self, client_logado_solicitante, app):
        """POST /api/chamado/ch1/editar-solicitante por dono → 200 sucesso."""
        sol = _usuario_mock("sol_1", "solicitante")
        resultado_service = {"sucesso": True}

        with (
            patch("app.models_usuario.Usuario.get_by_id", return_value=sol),
            patch(
                "app.routes.api.editar_descricao_solicitante",
                return_value=resultado_service,
            ),
        ):
            resp = client_logado_solicitante.post(
                "/api/chamado/ch1/editar-solicitante",
                data=json.dumps({"descricao": "Nova descrição suficientemente longa"}),
                content_type="application/json",
            )

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["sucesso"] is True

    def test_supervisor_nao_dono_recebe_403_do_service(self, client_logado_supervisor, app):
        """Supervisor que NÃO é dono → 403 vindo do service (rota não bloqueia por perfil)."""
        sup = _usuario_mock("sup_1", "supervisor")

        with (
            patch("app.models_usuario.Usuario.get_by_id", return_value=sup),
            patch(
                "app.routes.api.editar_descricao_solicitante",
                return_value={"sucesso": False, "erro": "Sem permissão.", "codigo": 403},
            ),
        ):
            resp = client_logado_supervisor.post(
                "/api/chamado/ch1/editar-solicitante",
                data=json.dumps({"descricao": "Texto suficientemente longo aqui"}),
                content_type="application/json",
            )

        assert resp.status_code == 403

    def test_supervisor_dono_pode_editar(self, client_logado_supervisor, app):
        """Lacuna D: supervisor que é dono do chamado consegue editar (403 vira 200)."""
        sup = _usuario_mock("sup_1", "supervisor")

        with (
            patch("app.models_usuario.Usuario.get_by_id", return_value=sup),
            patch(
                "app.routes.api.editar_descricao_solicitante",
                return_value={"sucesso": True},
            ),
        ):
            resp = client_logado_supervisor.post(
                "/api/chamado/ch1/editar-solicitante",
                data=json.dumps({"descricao": "Texto suficientemente longo aqui"}),
                content_type="application/json",
            )

        assert resp.status_code == 200

    def test_admin_nao_dono_recebe_403_do_service(self, client_logado_admin, app):
        """Admin que NÃO é dono → 403 do service."""
        adm = _usuario_mock("adm_1", "admin")

        with (
            patch("app.models_usuario.Usuario.get_by_id", return_value=adm),
            patch(
                "app.routes.api.editar_descricao_solicitante",
                return_value={"sucesso": False, "erro": "Sem permissão.", "codigo": 403},
            ),
        ):
            resp = client_logado_admin.post(
                "/api/chamado/ch1/editar-solicitante",
                data=json.dumps({"descricao": "Texto suficientemente longo aqui"}),
                content_type="application/json",
            )

        assert resp.status_code == 403

    def test_descricao_vazia_retorna_400(self, client_logado_solicitante, app):
        """Descrição vazia ou muito curta → 400 sem chamar o service."""
        sol = _usuario_mock("sol_1", "solicitante")

        with patch("app.models_usuario.Usuario.get_by_id", return_value=sol):
            resp = client_logado_solicitante.post(
                "/api/chamado/ch1/editar-solicitante",
                data=json.dumps({"descricao": ""}),
                content_type="application/json",
            )

        assert resp.status_code == 400

    def test_service_retorna_erro_propaga_codigo(self, client_logado_solicitante, app):
        """Se service retorna {sucesso: False, codigo: 403} → rota propaga 403."""
        sol = _usuario_mock("sol_1", "solicitante")
        resultado_service = {
            "sucesso": False,
            "erro": "Janela de edição encerrada.",
            "codigo": 403,
        }

        with (
            patch("app.models_usuario.Usuario.get_by_id", return_value=sol),
            patch(
                "app.routes.api.editar_descricao_solicitante",
                return_value=resultado_service,
            ),
        ):
            resp = client_logado_solicitante.post(
                "/api/chamado/ch1/editar-solicitante",
                data=json.dumps({"descricao": "Texto suficientemente longo"}),
                content_type="application/json",
            )

        assert resp.status_code == 403
        data = json.loads(resp.data)
        assert data["sucesso"] is False

    def test_sem_login_redireciona(self, client, app):
        """Rota protegida por login — sem sessão → redirect."""
        resp = client.post(
            "/api/chamado/ch1/editar-solicitante",
            data=json.dumps({"descricao": "Texto qualquer"}),
            content_type="application/json",
        )
        assert resp.status_code in (302, 401, 403)

    def test_descricao_3_chars_passa_validacao(self, client_logado_solicitante, app):
        """Lacuna G: descrição de 3 caracteres deve passar (mínimo = 3)."""
        sol = _usuario_mock("sol_1", "solicitante")

        with (
            patch("app.models_usuario.Usuario.get_by_id", return_value=sol),
            patch(
                "app.routes.api.editar_descricao_solicitante",
                return_value={"sucesso": True},
            ),
        ):
            resp = client_logado_solicitante.post(
                "/api/chamado/ch1/editar-solicitante",
                data=json.dumps({"descricao": "abc"}),
                content_type="application/json",
            )

        assert resp.status_code == 200

    def test_descricao_2_chars_retorna_400(self, client_logado_solicitante, app):
        """Lacuna G: descrição de 2 caracteres deve falhar (abaixo do mínimo de 3)."""
        sol = _usuario_mock("sol_1", "solicitante")

        with patch("app.models_usuario.Usuario.get_by_id", return_value=sol):
            resp = client_logado_solicitante.post(
                "/api/chamado/ch1/editar-solicitante",
                data=json.dumps({"descricao": "ab"}),
                content_type="application/json",
            )

        assert resp.status_code == 400
