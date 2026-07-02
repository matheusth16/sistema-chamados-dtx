"""Testes da rota GET /gestor/dashboard e decoradores @requer_gestor / @requer_gestor_ou_admin."""

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures de usuário gestor
# ---------------------------------------------------------------------------


def _mock_gestor(uid="gest_1", perfil="supervisor", nivel_gestao="gestor_setor"):
    """MagicMock de usuário com is_gestor=True e is_gestor_only baseado no perfil."""
    u = MagicMock()
    u.id = uid
    u.email = f"{uid}@dtx.aero"
    u.nome = "Gestor Teste"
    u.perfil = perfil
    u.area = "Geral"
    u.areas = ["Geral"]
    u.nivel_gestao = nivel_gestao
    u.is_authenticated = True
    u.get_id = lambda: str(uid)
    u.must_change_password = False
    u.is_admin_or_above = perfil in ("admin", "admin_global")
    u.is_supervisor_or_above = perfil in ("supervisor", "admin", "admin_global")
    u.is_gestor = nivel_gestao is not None
    u.is_gestor_only = u.is_gestor and not u.is_admin_or_above
    u.onboarding_completo = True
    u.onboarding_passo = 0
    u.ativo = True
    return u


@pytest.fixture
def client_logado_gestor(client, app):
    """Cliente com usuário supervisor gestor_setor já logado."""
    user = _mock_gestor()
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=user),
        patch("app.models_usuario.Usuario.get_by_id", return_value=user),
    ):
        client.post("/login", data={"email": user.email, "senha": "ok"}, follow_redirects=False)
        yield client


@pytest.fixture
def client_logado_admin_gestor(client, app):
    """Cliente com usuário admin + nivel_gestao (acesso total)."""
    user = _mock_gestor(uid="admin_gest_1", perfil="admin", nivel_gestao="gm")
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=user),
        patch("app.models_usuario.Usuario.get_by_id", return_value=user),
    ):
        client.post("/login", data={"email": user.email, "senha": "ok"}, follow_redirects=False)
        yield client


# ---------------------------------------------------------------------------
# Testes da rota /gestor/dashboard
# ---------------------------------------------------------------------------


def test_gestor_acessa_dashboard(client_logado_gestor):
    """Gestor (supervisor com nivel_gestao) obtém 200 em /gestor/dashboard."""
    ctx_mock = {
        "contadores": {
            "total": 0,
            "atrasados": 0,
            "aberto_sem_resposta": 0,
            "multi_setor_travado": 0,
        },
        "chamados": [],
        "filtro_ativo": "todos",
        "insights": {
            "area_critica": None,
            "tempo_medio_sem_resposta_min": None,
            "saude_percentual": 100,
        },
        "grupos": [
            {
                "chave": "atrasados",
                "titulo": "Atrasados",
                "cor": "danger",
                "total": 0,
                "chamados": [],
            },
            {
                "chave": "aberto_sem_resposta",
                "titulo": "Sem resposta",
                "cor": "warn",
                "total": 0,
                "chamados": [],
            },
            {
                "chave": "multi_setor",
                "titulo": "Multi-setor travado",
                "cor": "purple",
                "total": 0,
                "chamados": [],
            },
        ],
    }
    with patch("app.routes.dashboard.obter_contexto_gestor_dashboard", return_value=ctx_mock):
        resp = client_logado_gestor.get("/gestor/dashboard")
    assert resp.status_code == 200
    assert b"gestor" in resp.data.lower() or b"dashboard" in resp.data.lower()


def test_admin_acessa_gestor_dashboard(client_logado_admin_gestor):
    """Admin com nivel_gestao acessa /gestor/dashboard com 200."""
    ctx_mock = {
        "contadores": {
            "total": 0,
            "atrasados": 0,
            "aberto_sem_resposta": 0,
            "multi_setor_travado": 0,
        },
        "chamados": [],
        "filtro_ativo": "todos",
        "insights": {
            "area_critica": None,
            "tempo_medio_sem_resposta_min": None,
            "saude_percentual": 100,
        },
        "grupos": [
            {
                "chave": "atrasados",
                "titulo": "Atrasados",
                "cor": "danger",
                "total": 0,
                "chamados": [],
            },
            {
                "chave": "aberto_sem_resposta",
                "titulo": "Sem resposta",
                "cor": "warn",
                "total": 0,
                "chamados": [],
            },
            {
                "chave": "multi_setor",
                "titulo": "Multi-setor travado",
                "cor": "purple",
                "total": 0,
                "chamados": [],
            },
        ],
    }
    with patch("app.routes.dashboard.obter_contexto_gestor_dashboard", return_value=ctx_mock):
        resp = client_logado_admin_gestor.get("/gestor/dashboard")
    assert resp.status_code == 200


def test_supervisor_sem_nivel_gestao_bloqueado(client_logado_supervisor):
    """Supervisor sem nivel_gestao é redirecionado (302) ao tentar /gestor/dashboard."""
    resp = client_logado_supervisor.get("/gestor/dashboard", follow_redirects=False)
    assert resp.status_code == 302


def test_solicitante_bloqueado_gestor_dashboard(client_logado_solicitante):
    """Solicitante é redirecionado (302) ao tentar /gestor/dashboard."""
    resp = client_logado_solicitante.get("/gestor/dashboard", follow_redirects=False)
    assert resp.status_code == 302


def test_gestor_dashboard_filtro_atrasados(client_logado_gestor):
    """Gestor pode filtrar por atrasados via query string."""
    ctx_mock = {
        "contadores": {
            "total": 5,
            "atrasados": 2,
            "aberto_sem_resposta": 1,
            "multi_setor_travado": 0,
        },
        "chamados": [],
        "filtro_ativo": "atrasados",
        "insights": {
            "area_critica": None,
            "tempo_medio_sem_resposta_min": None,
            "saude_percentual": 100,
        },
        "grupos": [],
    }
    with patch(
        "app.routes.dashboard.obter_contexto_gestor_dashboard", return_value=ctx_mock
    ) as mock_svc:
        resp = client_logado_gestor.get("/gestor/dashboard?filtro=atrasados")
    assert resp.status_code == 200
    mock_svc.assert_called_once_with(filtro="atrasados")


def test_gestor_nao_pode_mudar_status_via_api(client_logado_gestor):
    """POST /api/atualizar-status retorna 403 para gestor read-only."""
    with (
        patch("app.routes.api.db"),
        patch(
            "app.routes.api.verificar_permissao_mudanca_status",
            return_value=(False, "Acesso negado: gestores têm visão read-only"),
        ),
    ):
        resp = client_logado_gestor.post(
            "/api/atualizar-status",
            json={"chamado_id": "ch_001", "novo_status": "Em Atendimento"},
        )
    assert resp.status_code == 403


def test_gestor_visualizar_chamado_pode_editar_false(client_logado_gestor):
    """Gestor visualiza chamado com pode_editar=False no contexto do template."""
    from app.models import Chamado as ChamadoModel

    chamado_mock = MagicMock(spec=ChamadoModel)
    chamado_mock.id = "ch_001"
    chamado_mock.area = "Geral"
    chamado_mock.responsavel_id = None
    chamado_mock.solicitante_id = "outro"
    chamado_mock.participantes = []

    with (
        patch("app.routes.dashboard.db") as mock_db,
        patch("app.routes.dashboard.usuario_pode_ver_chamado", return_value=True),
        patch("app.routes.dashboard.Chamado.from_dict", return_value=chamado_mock),
        patch("app.routes.dashboard.get_static_cached", return_value=[]),
        patch("app.routes.dashboard.CategoriaSetor.get_all", return_value=[]),
    ):
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {}
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        resp = client_logado_gestor.get("/chamado/ch_001")

    # Gestor pode ver o chamado (200) mas pode_editar=False no template
    assert resp.status_code == 200
    # Template não deve renderizar o formulário de edição ({% if pode_editar %} é False)
    assert b"form-status" not in resp.data
