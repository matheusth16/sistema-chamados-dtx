"""
Fase 2 — TDD: rotas /api/usuarios/buscar e observadores na criação de chamados.
"""

import json
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _usuario_mock(uid, email, nome, perfil, ativo=True):
    u = MagicMock()
    u.id = uid
    u.email = email
    u.nome = nome
    u.perfil = perfil
    u.ativo = ativo
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


# ---------------------------------------------------------------------------
# GET /api/usuarios/buscar?q=
# ---------------------------------------------------------------------------


class TestBuscarUsuarios:
    def test_busca_retorna_usuarios_ativos(self, client_logado_solicitante, app):
        """GET /api/usuarios/buscar?q=ali retorna lista de usuários que casam."""
        user_alice = _usuario_mock("u_alice", "alice@test.com", "Alice Silva", "supervisor")
        with (
            patch("app.models_usuario.Usuario.get_by_id", return_value=user_alice),
            patch("app.routes.api.Usuario") as mock_usuario_cls,
        ):
            mock_usuario_cls.buscar_ativos.return_value = [user_alice]
            resp = client_logado_solicitante.get(
                "/api/usuarios/buscar?q=alice",
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["sucesso"] is True
        assert isinstance(data["dados"], list)

    def test_busca_requer_login(self, client, app):
        """Rota /api/usuarios/buscar é protegida por login."""
        resp = client.get("/api/usuarios/buscar?q=teste")
        assert resp.status_code in (302, 401, 403)

    def test_busca_sem_q_retorna_lista_vazia(self, client_logado_solicitante, app):
        """q com menos de 2 chars retorna lista vazia sem erro."""
        resp = client_logado_solicitante.get("/api/usuarios/buscar")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["sucesso"] is True
        assert data["dados"] == []

    def test_busca_exclui_usuario_logado(self, client_logado_solicitante, app):
        """Usuário logado não aparece em sua própria busca."""
        # O solicitante tem uid="sol_1" (conftest)
        user_sol = _usuario_mock("sol_1", "sol@test.com", "Solicitante Teste", "solicitante")
        user_outro = _usuario_mock("u_outro", "outro@test.com", "Outro Usuário", "supervisor")
        with (
            patch("app.models_usuario.Usuario.get_by_id", return_value=user_sol),
            patch("app.routes.api.Usuario") as mock_usuario_cls,
        ):
            mock_usuario_cls.buscar_ativos.return_value = [user_sol, user_outro]
            resp = client_logado_solicitante.get("/api/usuarios/buscar?q=te")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        if data.get("sucesso"):
            ids = [u.get("id") for u in data.get("dados", [])]
            assert "sol_1" not in ids

    def test_busca_exclui_admin_e_admin_global(self, client_logado_solicitante, app):
        """Usuários com perfil admin/admin_global não podem ser observadores (CC)."""
        user_admin = _usuario_mock("u_admin", "admin@test.com", "Admin Um", "admin")
        user_admin_global = _usuario_mock(
            "u_admin_global", "adminglobal@test.com", "Admin Global", "admin_global"
        )
        user_supervisor = _usuario_mock("u_sup", "sup@test.com", "Supervisor Um", "supervisor")
        with (
            patch(
                "app.models_usuario.Usuario.get_by_id",
                return_value=_usuario_mock("sol_1", "sol@test.com", "Sol", "solicitante"),
            ),
            patch("app.routes.api.Usuario") as mock_usuario_cls,
        ):
            mock_usuario_cls.buscar_ativos.return_value = [
                user_admin,
                user_admin_global,
                user_supervisor,
            ]
            resp = client_logado_solicitante.get("/api/usuarios/buscar?q=admin")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["sucesso"] is True
        ids = [u.get("id") for u in data["dados"]]
        assert "u_admin" not in ids
        assert "u_admin_global" not in ids
        assert "u_sup" in ids

    def test_busca_limita_a_10_resultados(self, client_logado_solicitante, app):
        """Máximo 10 resultados por busca."""
        usuarios = [
            _usuario_mock(f"u_{i}", f"u{i}@test.com", f"User {i}", "supervisor") for i in range(15)
        ]
        with (
            patch(
                "app.models_usuario.Usuario.get_by_id",
                return_value=_usuario_mock("sol_1", "sol@test.com", "Sol", "solicitante"),
            ),
            patch("app.routes.api.Usuario") as mock_usuario_cls,
        ):
            mock_usuario_cls.buscar_ativos.return_value = usuarios
            resp = client_logado_solicitante.get("/api/usuarios/buscar?q=user")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        if data.get("sucesso"):
            assert len(data.get("dados", [])) <= 10


# ---------------------------------------------------------------------------
# Validação de observadores
# ---------------------------------------------------------------------------


class TestValidacaoObservadores:
    def test_validar_observadores_maximo(self):
        from app.services.validators import validar_observadores

        obs = [{"usuario_id": f"u{i}", "nome": f"U{i}", "email": f"u{i}@t.com"} for i in range(6)]
        with patch("app.models_usuario.Usuario.get_by_id", return_value=None):
            erros = validar_observadores(obs, solicitante_id="sol_1")
        assert any("5" in e or "máximo" in e.lower() for e in erros)

    def test_validar_observadores_solicitante_removido(self):
        from app.services.validators import validar_observadores

        obs = [{"usuario_id": "sol_1", "nome": "Sol", "email": "sol@t.com"}]
        with patch("app.models_usuario.Usuario.get_by_id", return_value=None):
            erros = validar_observadores(obs, solicitante_id="sol_1")
        assert len(erros) > 0

    def test_validar_5_observadores_ok(self):
        from app.services.validators import validar_observadores

        obs = [{"usuario_id": f"u{i}", "nome": f"U{i}", "email": f"u{i}@t.com"} for i in range(5)]
        with patch("app.models_usuario.Usuario.get_by_id", return_value=None):
            erros = validar_observadores(obs, solicitante_id="sol_1")
        assert erros == []

    def test_validar_observadores_rejeita_admin(self):
        """Admin/admin_global não pode ser incluído como observador (CC)."""
        from app.services.validators import validar_observadores

        admin = _usuario_mock("u_admin", "admin@t.com", "Admin", "admin")
        obs = [{"usuario_id": "u_admin", "nome": "Admin", "email": "admin@t.com"}]
        with patch("app.models_usuario.Usuario.get_by_id", return_value=admin):
            erros = validar_observadores(obs, solicitante_id="sol_1")
        assert len(erros) > 0

    def test_validar_observadores_rejeita_admin_global(self):
        from app.services.validators import validar_observadores

        admin_global = _usuario_mock("u_ag", "ag@t.com", "Admin Global", "admin_global")
        obs = [{"usuario_id": "u_ag", "nome": "Admin Global", "email": "ag@t.com"}]
        with patch("app.models_usuario.Usuario.get_by_id", return_value=admin_global):
            erros = validar_observadores(obs, solicitante_id="sol_1")
        assert len(erros) > 0
