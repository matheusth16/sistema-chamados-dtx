"""
Lacuna 1 — TDD: rota POST /api/chamado/<id>/anexo-solicitante.

Regras:
- Só perfil solicitante (dono) pode usar
- FormData: anexo (file) + motivo (str, mín 10 chars)
- salvar_anexo → adicionar_anexo_tardio → resposta JSON
- Motivo vazio → 400 sem chamar service
- Supervisor / admin → 403
"""

import io
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


def _multipart(motivo="Documento esquecido no envio", filename="relatorio.pdf"):
    """Dados multipart para POST /api/chamado/ch1/anexo-solicitante."""
    return {
        "motivo": motivo,
        "anexo": (io.BytesIO(b"%PDF-1.4 teste"), filename),
    }


class TestAnexoSolicitanteRota:
    def test_solicitante_owner_envia_anexo_com_sucesso(self, client_logado_solicitante, app):
        """POST multipart por dono → 200 sucesso."""
        sol = _usuario_mock("sol_1", "solicitante")

        with (
            patch("app.models_usuario.Usuario.get_by_id", return_value=sol),
            patch("app.routes.api_solicitante.salvar_anexo", return_value="path/relatorio.pdf"),
            patch(
                "app.routes.api_solicitante.adicionar_anexo_tardio",
                return_value={"sucesso": True},
            ),
        ):
            resp = client_logado_solicitante.post(
                "/api/chamado/ch1/anexo-solicitante",
                data=_multipart(),
                content_type="multipart/form-data",
            )

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["sucesso"] is True

    def test_supervisor_nao_dono_recebe_403_do_service(self, client_logado_supervisor, app):
        """Supervisor que NÃO é dono → 403 do service (rota não bloqueia por perfil)."""
        sup = _usuario_mock("sup_1", "supervisor")

        with (
            patch("app.models_usuario.Usuario.get_by_id", return_value=sup),
            patch("app.routes.api_solicitante.salvar_anexo", return_value="path/f.pdf"),
            patch(
                "app.routes.api_solicitante.adicionar_anexo_tardio",
                return_value={"sucesso": False, "erro": "Sem permissão.", "codigo": 403},
            ),
        ):
            resp = client_logado_supervisor.post(
                "/api/chamado/ch1/anexo-solicitante",
                data=_multipart(),
                content_type="multipart/form-data",
            )

        assert resp.status_code == 403

    def test_supervisor_dono_pode_enviar_anexo(self, client_logado_supervisor, app):
        """Lacuna D: supervisor que é dono do chamado consegue enviar anexo tardio."""
        sup = _usuario_mock("sup_1", "supervisor")

        with (
            patch("app.models_usuario.Usuario.get_by_id", return_value=sup),
            patch("app.routes.api_solicitante.salvar_anexo", return_value="path/relatorio.pdf"),
            patch(
                "app.routes.api_solicitante.adicionar_anexo_tardio",
                return_value={"sucesso": True},
            ),
        ):
            resp = client_logado_supervisor.post(
                "/api/chamado/ch1/anexo-solicitante",
                data=_multipart(),
                content_type="multipart/form-data",
            )

        assert resp.status_code == 200

    def test_admin_nao_dono_recebe_403_do_service(self, client_logado_admin, app):
        """Admin que NÃO é dono → 403 do service."""
        adm = _usuario_mock("admin_1", "admin")

        with (
            patch("app.models_usuario.Usuario.get_by_id", return_value=adm),
            patch("app.routes.api_solicitante.salvar_anexo", return_value="path/f.pdf"),
            patch(
                "app.routes.api_solicitante.adicionar_anexo_tardio",
                return_value={"sucesso": False, "erro": "Sem permissão.", "codigo": 403},
            ),
        ):
            resp = client_logado_admin.post(
                "/api/chamado/ch1/anexo-solicitante",
                data=_multipart(),
                content_type="multipart/form-data",
            )

        assert resp.status_code == 403

    def test_motivo_vazio_retorna_400(self, client_logado_solicitante, app):
        """Motivo curto (< 10 chars) → 400 sem chamar service."""
        sol = _usuario_mock("sol_1", "solicitante")

        with (
            patch("app.models_usuario.Usuario.get_by_id", return_value=sol),
            patch("app.routes.api_solicitante.adicionar_anexo_tardio") as mock_svc,
        ):
            resp = client_logado_solicitante.post(
                "/api/chamado/ch1/anexo-solicitante",
                data={"motivo": "curto", "anexo": (io.BytesIO(b"x"), "f.pdf")},
                content_type="multipart/form-data",
            )

        assert resp.status_code == 400
        mock_svc.assert_not_called()

    def test_sem_arquivo_retorna_400(self, client_logado_solicitante, app):
        """Sem arquivo no FormData → 400."""
        sol = _usuario_mock("sol_1", "solicitante")

        with patch("app.models_usuario.Usuario.get_by_id", return_value=sol):
            resp = client_logado_solicitante.post(
                "/api/chamado/ch1/anexo-solicitante",
                data={"motivo": "Motivo suficientemente longo"},
                content_type="multipart/form-data",
            )

        assert resp.status_code == 400

    def test_service_retorna_403_propagado(self, client_logado_solicitante, app):
        """Quando service retorna 403 (não é dono) → rota repassa 403."""
        sol = _usuario_mock("sol_1", "solicitante")

        with (
            patch("app.models_usuario.Usuario.get_by_id", return_value=sol),
            patch("app.routes.api_solicitante.salvar_anexo", return_value="path/f.pdf"),
            patch(
                "app.routes.api_solicitante.adicionar_anexo_tardio",
                return_value={"sucesso": False, "erro": "Sem permissão.", "codigo": 403},
            ),
        ):
            resp = client_logado_solicitante.post(
                "/api/chamado/ch1/anexo-solicitante",
                data=_multipart(),
                content_type="multipart/form-data",
            )

        assert resp.status_code == 403
        data = json.loads(resp.data)
        assert data["sucesso"] is False
