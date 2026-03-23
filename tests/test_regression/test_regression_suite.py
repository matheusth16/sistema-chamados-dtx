"""
Suite de testes de regressão: cenários críticos que devem sempre passar.

Garante que novas funcionalidades ou mudanças não quebrem:
- Health e infra (health, sw.js)
- Autenticação (login, logout, redirect por perfil, rotas protegidas)
- Criação de chamado (com e sem login, validação)
- API status (atualizar, bulk, códigos 401/400/403)
- API edição (403 solicitante, 400 sem chamado_id)
- API listagem e notificações (estrutura e 401 sem login)
- Permissões (admin/supervisor área)
- Validação de formulário (descrição, Projetos+RL, anexo)
"""

from unittest.mock import MagicMock, patch

import pytest

# Aplica @pytest.mark.regression a todos os testes deste módulo automaticamente
pytestmark = pytest.mark.regression


# --- Health / Infra ---


def test_regression_health_retorna_200_ok(client):
    """Regressão: GET /health retorna 200 e status ok."""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok"}


def test_regression_sw_js_retorna_javascript(client):
    """Regressão: GET /sw.js retorna 200 e content-type JavaScript."""
    r = client.get("/sw.js")
    assert r.status_code == 200
    assert "javascript" in (r.content_type or "").lower()


# --- Autenticação ---


def test_regression_login_sem_credenciais_permanece_em_login(client):
    """Regressão: Login sem email/senha não redireciona para área restrita."""
    r = client.post("/login", data={"email": "", "senha": ""}, follow_redirects=True)
    assert r.status_code == 200
    assert b"login" in r.data.lower() or b"email" in r.data.lower()


def test_regression_login_solicitante_redireciona_para_raiz(client):
    """Regressão: Login como solicitante redireciona para /."""
    usuario = MagicMock()
    usuario.id = "sol_1"
    usuario.perfil = "solicitante"
    usuario.email = "sol@test.com"
    usuario.check_password = MagicMock(return_value=True)
    usuario.get_id = lambda: "sol_1"
    usuario.must_change_password = False  # senão app redireciona para /alterar-senha-obrigatoria
    with patch("app.routes.auth.Usuario.get_by_email", return_value=usuario):
        r = client.post(
            "/login", data={"email": "sol@test.com", "senha": "ok"}, follow_redirects=False
        )
    assert r.status_code == 302
    assert r.location.endswith("/") or (r.location and "/" in r.location)


def test_regression_login_supervisor_redireciona_para_admin(client):
    """Regressão: Login como supervisor redireciona para /admin."""
    usuario = MagicMock()
    usuario.id = "sup_1"
    usuario.perfil = "supervisor"
    usuario.email = "sup@test.com"
    usuario.check_password = MagicMock(return_value=True)
    usuario.get_id = lambda: "sup_1"
    usuario.must_change_password = False  # senão app redireciona para /alterar-senha-obrigatoria
    with patch("app.routes.auth.Usuario.get_by_email", return_value=usuario):
        r = client.post(
            "/login", data={"email": "sup@test.com", "senha": "ok"}, follow_redirects=False
        )
    assert r.status_code == 302
    assert "admin" in r.location


def test_regression_logout_redireciona_para_login(client_logado_solicitante):
    """Regressão: Logout redireciona para /login."""
    r = client_logado_solicitante.get("/logout", follow_redirects=False)
    assert r.status_code == 302
    assert "login" in r.location


def test_regression_index_sem_login_redireciona_para_login(client):
    """Regressão: Acesso a / sem login redireciona para login."""
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert "login" in r.location


# --- Criação de chamado ---


def test_regression_criar_chamado_sem_login_redireciona(client):
    """Regressão: POST / (criar chamado) sem login redireciona para login."""
    r = client.post(
        "/",
        data={"categoria": "Chamado", "tipo": "X", "descricao": "Teste"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert "login" in r.location


def test_regression_criar_chamado_valido_redireciona(client_logado_solicitante):
    """Regressão: POST / com dados válidos (mock) redireciona após sucesso."""
    with patch("app.routes.chamados.criar_chamado") as mock_criar:
        mock_criar.return_value = ("doc_1", "CHM-0001", None, None)
        r = client_logado_solicitante.post(
            "/",
            data={
                "categoria": "Chamado",
                "tipo": "Manutencao",
                "descricao": "Descrição válida com mais de 3 caracteres",
                "gate": "Gate 1",
                "impacto": "Qualidade",
            },
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert r.location


# --- API Status ---


def test_regression_atualizar_status_sem_login_401(client):
    """Regressão: POST /api/atualizar-status sem login retorna 401, 403 ou 302 para login."""
    r = client.post(
        "/api/atualizar-status",
        json={"chamado_id": "x", "novo_status": "Aberto"},
        content_type="application/json",
    )
    assert r.status_code in (401, 403, 302)
    if r.status_code == 302:
        assert "login" in (r.location or "")


def test_regression_atualizar_status_sem_chamado_id_400(client_logado_supervisor):
    """Regressão: POST /api/atualizar-status sem chamado_id retorna 400."""
    r = client_logado_supervisor.post(
        "/api/atualizar-status", json={"novo_status": "Aberto"}, content_type="application/json"
    )
    assert r.status_code == 400


def test_regression_bulk_status_solicitante_403(client_logado_solicitante):
    """Regressão: POST /api/bulk-status como solicitante retorna 403."""
    r = client_logado_solicitante.post(
        "/api/bulk-status",
        json={"chamado_ids": ["ch1"], "novo_status": "Concluído"},
        content_type="application/json",
    )
    assert r.status_code == 403


# --- API Edição ---


def test_regression_editar_chamado_solicitante_403(client_logado_solicitante):
    """Regressão: POST /api/editar-chamado como solicitante retorna 403."""
    r = client_logado_solicitante.post(
        "/api/editar-chamado", data={"chamado_id": "ch1"}, content_type="multipart/form-data"
    )
    assert r.status_code == 403


def test_regression_editar_chamado_sem_chamado_id_400(client_logado_supervisor):
    """Regressão: POST /api/editar-chamado sem chamado_id retorna 400."""
    with patch("app.routes.api.db"):
        r = client_logado_supervisor.post(
            "/api/editar-chamado", data={}, content_type="multipart/form-data"
        )
    assert r.status_code == 400


# --- API Listagem e notificações ---


def test_regression_carregar_mais_sem_login_401(client):
    """Regressão: POST /api/carregar-mais sem login retorna 401, 403 ou 302 para login."""
    r = client.post("/api/carregar-mais", json={}, content_type="application/json")
    assert r.status_code in (401, 403, 302)
    if r.status_code == 302:
        assert "login" in (r.location or "")


def test_regression_carregar_mais_com_login_200_estrutura(client_logado_supervisor):
    """Regressão: POST /api/carregar-mais com login retorna 200 e estrutura."""
    with patch("app.routes.api.aplicar_filtros_dashboard_com_paginacao") as mock_f:
        mock_f.return_value = {"docs": [], "proximo_cursor": None, "tem_proxima": False}
        r = client_logado_supervisor.post(
            "/api/carregar-mais",
            json={"cursor": None, "limite": 20},
            content_type="application/json",
        )
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("sucesso") is True
    assert "chamados" in data and "cursor_proximo" in data and "tem_proxima" in data


def test_regression_notificacoes_sem_login_401(client):
    """Regressão: GET /api/notificacoes sem login retorna 401 ou 302 para login."""
    r = client.get("/api/notificacoes")
    assert r.status_code in (401, 302)
    if r.status_code == 302:
        assert "login" in (r.location or "")


def test_regression_notificacoes_com_login_200_estrutura(client_logado_solicitante):
    """Regressão: GET /api/notificacoes com login retorna 200 e notificacoes, total_nao_lidas."""
    with (
        patch("app.routes.api.listar_para_usuario", return_value=[]),
        patch("app.routes.api.contar_nao_lidas", return_value=0),
    ):
        r = client_logado_solicitante.get("/api/notificacoes")
    assert r.status_code == 200
    data = r.get_json()
    assert "notificacoes" in data and "total_nao_lidas" in data


# --- Permissões ---


def test_regression_admin_pode_ver_qualquer_chamado():
    """Regressão: Serviço de permissões: admin pode ver qualquer chamado."""
    from app.services.permissions import usuario_pode_ver_chamado

    admin = MagicMock()
    admin.perfil = "admin"
    admin.areas = []
    chamado = MagicMock()
    chamado.area = "Qualquer"
    assert usuario_pode_ver_chamado(admin, chamado) is True


def test_regression_supervisor_so_ve_sua_area():
    """Regressão: Supervisor só vê chamados da sua área."""
    from app.services.permissions import usuario_pode_ver_chamado

    supervisor = MagicMock()
    supervisor.perfil = "supervisor"
    supervisor.areas = ["Manutencao"]
    chamado_ok = MagicMock()
    chamado_ok.area = "Manutencao"
    chamado_outro = MagicMock()
    chamado_outro.area = "TI"
    assert usuario_pode_ver_chamado(supervisor, chamado_ok) is True
    assert usuario_pode_ver_chamado(supervisor, chamado_outro) is False


# --- Validação formulário ---


def test_regression_validacao_descricao_obrigatoria():
    """Regressão: Validador exige descrição."""
    from app.services.validators import validar_novo_chamado

    erros = validar_novo_chamado({"descricao": "", "tipo": "X", "categoria": "Chamado"})
    assert any("descrição" in e.lower() for e in erros)


def test_regression_validacao_projetos_exige_rl():
    """Regressão: Categoria Projetos exige código RL."""
    from app.services.validators import validar_novo_chamado

    erros = validar_novo_chamado(
        {"descricao": "Projeto", "tipo": "X", "categoria": "Projetos", "rl_codigo": ""}
    )
    assert any("RL" in e or "rl" in e.lower() for e in erros)


def test_regression_validacao_arquivo_extensao_invalida():
    """Regressão: Anexo com extensão não permitida gera erro."""
    from app.services.validators import validar_novo_chamado

    arquivo = MagicMock()
    arquivo.filename = "arquivo.exe"
    erros = validar_novo_chamado({"descricao": "Ok", "tipo": "X", "categoria": "Chamado"}, arquivo)
    assert any(
        "formato" in e.lower() or "inválido" in e.lower() or "arquivo" in e.lower() for e in erros
    )
