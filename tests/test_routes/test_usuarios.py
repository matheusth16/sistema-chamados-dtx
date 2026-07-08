"""Testes das rotas de administração de usuários (/admin/usuarios). Requer perfil admin."""

import re
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _mock_historico_usuario_db():
    """Evita chamada real ao Firestore quando a rota registra histórico de auditoria
    e o teste não mocka `registrar_historico_usuario` explicitamente."""
    with patch("app.services.historico_usuario_service.db", MagicMock()):
        yield


class _FakeThread:
    """Thread fake para executar target imediatamente nos testes."""

    def __init__(self, target=None, daemon=None):
        self._target = target
        self.daemon = daemon

    def start(self):
        if self._target:
            self._target()


def test_admin_usuarios_sem_login_redireciona_para_login(client):
    """GET /admin/usuarios sem estar logado redireciona para /login."""
    r = client.get("/admin/usuarios", follow_redirects=False)
    assert r.status_code == 302
    assert "login" in r.location


def test_admin_usuarios_com_solicitante_nao_acessa(client_logado_solicitante):
    """GET /admin/usuarios com perfil solicitante não acessa: 403 ou 302 (ex.: redirect troca de senha)."""
    r = client_logado_solicitante.get("/admin/usuarios", follow_redirects=False)
    assert r.status_code in (403, 302)
    if r.status_code == 302:
        assert "/admin/usuarios" not in (r.location or "")


def test_admin_usuarios_com_supervisor_nao_acessa(client_logado_supervisor):
    """GET /admin/usuarios com perfil supervisor não acessa: 403 ou 302."""
    r = client_logado_supervisor.get("/admin/usuarios", follow_redirects=False)
    assert r.status_code in (403, 302)
    if r.status_code == 302:
        assert "/admin/usuarios" not in (r.location or "")


def test_admin_usuarios_com_admin_retorna_200(client_logado_admin):
    """GET /admin/usuarios com perfil admin retorna 200 e página de usuários."""
    with patch("app.routes.usuarios.Usuario.get_all") as mock_get_all:
        mock_get_all.return_value = []
        r = client_logado_admin.get("/admin/usuarios", follow_redirects=False)
    assert r.status_code == 200
    assert b"usuarios" in r.data.lower() or b"user" in r.data.lower()


def test_admin_usuarios_novo_sem_login_redireciona(client):
    """GET /admin/usuarios/novo sem login redireciona para login."""
    r = client.get("/admin/usuarios/novo", follow_redirects=False)
    assert r.status_code == 302
    assert "login" in r.location


def test_admin_usuarios_novo_com_admin_retorna_200(client_logado_admin):
    """GET /admin/usuarios/novo com admin retorna formulário."""
    r = client_logado_admin.get("/admin/usuarios/novo", follow_redirects=False)
    assert r.status_code == 200


def test_admin_cria_usuario_dispara_thread_notificacao(client_logado_admin):
    """POST /admin/usuarios (acao=criar) dispara thread de notificação ao novo usuário."""
    with (
        patch("app.routes.usuarios.Usuario.email_existe", return_value=False),
        patch("app.routes.usuarios.Usuario.save"),
        patch("app.routes.usuarios.Usuario.invalidar_cache_supervisores_por_area"),
        patch("app.routes.usuarios.threading.Thread") as mock_thread,
    ):
        r = client_logado_admin.post(
            "/admin/usuarios",
            data={
                "acao": "criar",
                "email": "novo.usuario@dtx.aero",
                "nome": "Novo Usuario",
                "perfil": "solicitante",
            },
            follow_redirects=False,
        )

    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")
    assert mock_thread.return_value.start.call_count >= 1


def test_admin_cria_usuario_chama_notificacao_novo_usuario(client_logado_admin):
    """POST criar usuário deve acionar notificação ao novo usuário."""
    with (
        patch("app.routes.usuarios.Usuario.email_existe", return_value=False),
        patch("app.routes.usuarios.Usuario.save"),
        patch("app.routes.usuarios.Usuario.invalidar_cache_supervisores_por_area"),
        patch("app.routes.usuarios.notificar_novo_usuario_cadastrado") as mock_notificar,
        patch("app.routes.usuarios.threading.Thread", side_effect=_FakeThread),
    ):
        r = client_logado_admin.post(
            "/admin/usuarios",
            data={
                "acao": "criar",
                "email": "novo.usuario@dtx.aero",
                "nome": "Novo Usuario",
                "perfil": "solicitante",
                "areas": ["Manutencao"],
            },
            follow_redirects=False,
        )

    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")
    mock_notificar.assert_called_once()
    kwargs = mock_notificar.call_args.kwargs
    assert kwargs["usuario_email"] == "novo.usuario@dtx.aero"
    assert kwargs["perfil"] == "solicitante"
    assert "senha_inicial" in kwargs
    assert kwargs["senha_inicial"] != "123456"
    assert len(kwargs["senha_inicial"]) >= 12


def test_admin_cria_usuario_registra_historico(client_logado_admin):
    """POST criar usuário registra auditoria no histórico de usuários."""
    with (
        patch("app.routes.usuarios.Usuario.email_existe", return_value=False),
        patch("app.routes.usuarios.Usuario.save"),
        patch("app.routes.usuarios.Usuario.invalidar_cache_supervisores_por_area"),
        patch("app.routes.usuarios.notificar_novo_usuario_cadastrado"),
        patch("app.routes.usuarios.threading.Thread", side_effect=_FakeThread),
        patch("app.routes.usuarios.registrar_historico_usuario") as mock_hist,
    ):
        client_logado_admin.post(
            "/admin/usuarios",
            data={
                "acao": "criar",
                "email": "novo2.usuario@dtx.aero",
                "nome": "Novo Usuario Dois",
                "perfil": "solicitante",
                "areas": ["Manutencao"],
            },
            follow_redirects=False,
        )
    mock_hist.assert_called_once()
    kwargs = mock_hist.call_args.kwargs
    assert kwargs["acao"] == "criacao"
    assert kwargs["usuario_alvo_nome"] == "Novo Usuario Dois"
    assert kwargs["admin_id"] == "admin_1"
    assert kwargs["admin_nome"] == "Admin Teste"


# ── Validação de criação ───────────────────────────────────────────────────────


def test_criar_usuario_email_invalido_redireciona_com_erro(client_logado_admin):
    """POST criar com email sem @ redireciona com flash de erro."""
    r = client_logado_admin.post(
        "/admin/usuarios",
        data={
            "acao": "criar",
            "email": "emailinvalido",
            "nome": "Fulano Tal",
            "perfil": "solicitante",
        },
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")


def test_criar_usuario_email_dominio_invalido_redireciona_com_erro(client_logado_admin):
    """POST criar com email fora do domínio @dtx.aero redireciona com erro."""
    r = client_logado_admin.post(
        "/admin/usuarios",
        data={
            "acao": "criar",
            "email": "fulano@gmail.com",
            "nome": "Fulano Tal",
            "perfil": "solicitante",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"dtx.aero" in r.data


def test_criar_usuario_email_ja_existe_redireciona(client_logado_admin):
    """POST criar com email duplicado redireciona com erro email_exists."""
    with patch("app.routes.usuarios.Usuario.email_existe", return_value=True):
        r = client_logado_admin.post(
            "/admin/usuarios",
            data={
                "acao": "criar",
                "email": "dup@dtx.aero",
                "nome": "Fulano Tal",
                "perfil": "solicitante",
            },
            follow_redirects=False,
        )
    assert r.status_code == 302


def test_criar_usuario_nome_curto_redireciona(client_logado_admin):
    """POST criar com nome < 3 chars redireciona com erro name_min_chars."""
    with patch("app.routes.usuarios.Usuario.email_existe", return_value=False):
        r = client_logado_admin.post(
            "/admin/usuarios",
            data={"acao": "criar", "email": "ok@dtx.aero", "nome": "AB", "perfil": "solicitante"},
            follow_redirects=False,
        )
    assert r.status_code == 302


def test_criar_usuario_perfil_invalido_redireciona(client_logado_admin):
    """POST criar com perfil inválido redireciona com erro invalid_profile."""
    with patch("app.routes.usuarios.Usuario.email_existe", return_value=False):
        r = client_logado_admin.post(
            "/admin/usuarios",
            data={
                "acao": "criar",
                "email": "ok@dtx.aero",
                "nome": "Nome Valido",
                "perfil": "hacker",
            },
            follow_redirects=False,
        )
    assert r.status_code == 302


def test_criar_usuario_supervisor_sem_area_redireciona(client_logado_admin):
    """POST criar supervisor sem área redireciona com erro area_required_for_supervisor."""
    with patch("app.routes.usuarios.Usuario.email_existe", return_value=False):
        r = client_logado_admin.post(
            "/admin/usuarios",
            data={
                "acao": "criar",
                "email": "sup@dtx.aero",
                "nome": "Supervisor Tal",
                "perfil": "supervisor",
            },
            follow_redirects=False,
        )
    assert r.status_code == 302


# ── Editar usuário ─────────────────────────────────────────────────────────────


def _usuario_fake(
    uid="u1", email="u@dtx.aero", nome="Usuario Fake", perfil="solicitante", areas=None
):
    from unittest.mock import MagicMock

    u = MagicMock()
    u.id = uid
    u.email = email
    u.nome = nome
    u.perfil = perfil
    u.areas = areas or []
    # Necessário para que o middleware de autenticação não redirecione para troca de senha
    u.must_change_password = False
    # Necessário para que o middleware de autenticação não redirecione para /mfa/configurar
    u.mfa_enabled = True
    u.is_authenticated = True
    u.get_id = lambda: str(uid)
    return u


def _admin_mock_para_flask_login():
    """Cria um mock do admin com o mesmo UID usado no conftest (admin_1)."""
    from unittest.mock import MagicMock

    a = MagicMock()
    a.id = "admin_1"
    a.email = "admin@test.com"
    a.nome = "Admin Teste"
    a.perfil = "admin"
    a.must_change_password = False
    a.mfa_enabled = True
    a.is_authenticated = True
    a.get_id = lambda: "admin_1"
    return a


def _get_by_id_side_effect(target_uid, target_user):
    """Retorna side_effect: admin mock para chamadas do Flask-Login, fake para a rota."""
    admin = _admin_mock_para_flask_login()

    def _side_effect(uid):
        return target_user if uid == target_uid else admin

    return _side_effect


def test_editar_usuario_get_retorna_200(client_logado_admin):
    """GET /admin/usuarios/<id>/editar retorna formulário 200."""
    fake = _usuario_fake(uid="u1")
    with (
        patch(
            "app.models_usuario.Usuario.get_by_id", side_effect=_get_by_id_side_effect("u1", fake)
        ),
        patch("app.routes.usuarios.CategoriaSetor.get_all", return_value=[]),
    ):
        r = client_logado_admin.get("/admin/usuarios/u1/editar", follow_redirects=False)
    assert r.status_code == 200


def test_editar_usuario_form_anonimizar_nao_fica_aninhado_no_form_de_edicao(client_logado_admin):
    """Regressão: o <form> de anonimizar não pode ficar dentro do <form> de editar.

    <form> aninhado é HTML inválido — o navegador descarta a tag interna e o
    clique no botão "Anonymize data" acaba submetendo o form de EDIÇÃO por
    engano (redireciona pra 'usuário atualizado', nunca chama
    anonimizar_usuario). Só reproduz num browser real; aqui garantimos via
    posição das tags no HTML renderizado: o </form> de edição deve fechar
    ANTES do <form> de anonimizar abrir.
    """
    fake = _usuario_fake(uid="u1")
    fake.ativo = False
    with (
        patch(
            "app.models_usuario.Usuario.get_by_id", side_effect=_get_by_id_side_effect("u1", fake)
        ),
        patch("app.routes.usuarios.CategoriaSetor.get_all", return_value=[]),
    ):
        r = client_logado_admin.get("/admin/usuarios/u1/editar", follow_redirects=False)
    assert r.status_code == 200
    html = r.data.decode("utf-8")

    idx_form_edicao_abre = html.index("/admin/usuarios/u1/editar")
    idx_form_edicao_fecha = html.index("</form>", idx_form_edicao_abre)
    idx_form_anonimizar_abre = html.index("/admin/usuarios/u1/anonimizar")
    assert idx_form_edicao_fecha < idx_form_anonimizar_abre, (
        "form de anonimizar aparece antes do </form> de edição fechar — voltou a ficar aninhado"
    )


def test_editar_usuario_nao_encontrado_redireciona(client_logado_admin):
    """GET editar com ID inexistente redireciona com erro user_not_found."""
    admin = _admin_mock_para_flask_login()
    with patch(
        "app.models_usuario.Usuario.get_by_id",
        side_effect=lambda uid: None if uid == "naoexiste" else admin,
    ):
        r = client_logado_admin.get("/admin/usuarios/naoexiste/editar", follow_redirects=False)
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")


def test_editar_usuario_post_sucesso(client_logado_admin):
    """POST editar com dados válidos redireciona e atualiza o usuário."""
    fake = _usuario_fake(uid="u2", email="u2@dtx.aero", nome="Usuario Dois", perfil="solicitante")
    with (
        patch("app.routes.usuarios.Usuario.get_by_id", return_value=fake),
        patch("app.routes.usuarios.Usuario.email_existe", return_value=False),
        patch("app.routes.usuarios.Usuario.invalidar_cache_supervisores_por_area"),
    ):
        fake.update = lambda **kw: None
        fake.areas = []
        r = client_logado_admin.post(
            "/admin/usuarios/u2/editar",
            data={"email": "u2novo@dtx.aero", "nome": "Usuario Dois Novo", "perfil": "solicitante"},
            follow_redirects=False,
        )
    assert r.status_code == 302


def test_editar_usuario_post_sucesso_registra_historico(client_logado_admin):
    """POST editar com dados válidos registra auditoria no histórico de usuários."""
    fake = _usuario_fake(uid="u2", email="u2@dtx.aero", nome="Usuario Dois", perfil="solicitante")
    with (
        patch(
            "app.models_usuario.Usuario.get_by_id", side_effect=_get_by_id_side_effect("u2", fake)
        ),
        patch("app.routes.usuarios.Usuario.email_existe", return_value=False),
        patch("app.routes.usuarios.Usuario.invalidar_cache_supervisores_por_area"),
        patch("app.routes.usuarios.registrar_historico_usuario") as mock_hist,
    ):
        fake.update = lambda **kw: None
        fake.areas = []
        client_logado_admin.post(
            "/admin/usuarios/u2/editar",
            data={"email": "u2novo@dtx.aero", "nome": "Usuario Dois Novo", "perfil": "solicitante"},
            follow_redirects=False,
        )
    mock_hist.assert_called_once()
    kwargs = mock_hist.call_args.kwargs
    assert kwargs["acao"] == "edicao"
    assert kwargs["usuario_alvo_id"] == "u2"
    assert kwargs["admin_id"] == "admin_1"


def test_editar_usuario_post_sem_mudanca_nao_registra_historico(client_logado_admin):
    """POST editar sem nenhum campo alterado não registra histórico (nada mudou)."""
    fake = _usuario_fake(uid="u2", email="u2@dtx.aero", nome="Usuario Dois", perfil="solicitante")
    fake.areas = []
    fake.ativo = True
    fake.nivel_gestao = None
    with (
        patch(
            "app.models_usuario.Usuario.get_by_id", side_effect=_get_by_id_side_effect("u2", fake)
        ),
        patch("app.routes.usuarios.Usuario.email_existe", return_value=False),
        patch("app.routes.usuarios.registrar_historico_usuario") as mock_hist,
    ):
        r = client_logado_admin.post(
            "/admin/usuarios/u2/editar",
            data={
                "email": "u2@dtx.aero",
                "nome": "Usuario Dois",
                "perfil": "solicitante",
                "ativo": "on",
            },
            follow_redirects=False,
        )
    assert r.status_code == 302
    mock_hist.assert_not_called()


def test_editar_usuario_post_nome_curto_redireciona(client_logado_admin):
    """POST editar com nome < 3 chars redireciona com erro."""
    fake = _usuario_fake()
    with patch("app.routes.usuarios.Usuario.get_by_id", return_value=fake):
        r = client_logado_admin.post(
            "/admin/usuarios/u1/editar",
            data={"email": "u@dtx.aero", "nome": "AB", "perfil": "solicitante"},
            follow_redirects=False,
        )
    assert r.status_code == 302


# ── Deletar usuário ────────────────────────────────────────────────────────────


def test_deletar_usuario_sucesso(client_logado_admin):
    """POST deletar com ID existente (não matheus.costa@dtx.aero) redireciona com sucesso."""
    fake = _usuario_fake(uid="u3", email="u3@dtx.aero", nome="A Deletar")
    fake.delete = lambda: None
    with (
        patch(
            "app.models_usuario.Usuario.get_by_id", side_effect=_get_by_id_side_effect("u3", fake)
        ),
        patch("app.routes.usuarios.Usuario.invalidar_cache_supervisores_por_area"),
    ):
        r = client_logado_admin.post("/admin/usuarios/u3/deletar", follow_redirects=False)
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")


def test_deletar_usuario_sucesso_registra_historico(client_logado_admin):
    """POST deletar com sucesso registra auditoria no histórico de usuários."""
    fake = _usuario_fake(uid="u3", email="u3@dtx.aero", nome="A Deletar")
    fake.delete = lambda: None
    with (
        patch(
            "app.models_usuario.Usuario.get_by_id", side_effect=_get_by_id_side_effect("u3", fake)
        ),
        patch("app.routes.usuarios.Usuario.invalidar_cache_supervisores_por_area"),
        patch("app.routes.usuarios.registrar_historico_usuario") as mock_hist,
    ):
        client_logado_admin.post("/admin/usuarios/u3/deletar", follow_redirects=False)
    mock_hist.assert_called_once()
    kwargs = mock_hist.call_args.kwargs
    assert kwargs["acao"] == "exclusao"
    assert kwargs["usuario_alvo_id"] == "u3"


def test_deletar_usuario_nao_encontrado_redireciona(client_logado_admin):
    """POST deletar com ID inexistente redireciona com erro user_not_found."""
    admin = _admin_mock_para_flask_login()
    with patch(
        "app.models_usuario.Usuario.get_by_id",
        side_effect=lambda uid: None if uid == "naoexiste" else admin,
    ):
        r = client_logado_admin.post("/admin/usuarios/naoexiste/deletar", follow_redirects=False)
    assert r.status_code == 302


@pytest.mark.parametrize("email_raiz", ["matheus.costa@dtx.aero", "admin@dtx.aero"])
def test_deletar_usuario_root_admin_bloqueado(client_logado_admin, email_raiz):
    """POST deletar de qualquer admin raiz protegido é bloqueado (cannot_delete_root_admin)."""
    fake_root = _usuario_fake(uid="root", email=email_raiz, nome="Root Admin")
    with patch(
        "app.models_usuario.Usuario.get_by_id",
        side_effect=_get_by_id_side_effect("root", fake_root),
    ):
        r = client_logado_admin.post("/admin/usuarios/root/deletar", follow_redirects=False)
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")


def _admin_global_mock_para_flask_login():
    """Cria um mock do admin_global com o mesmo UID usado no conftest (ag_1)."""
    from unittest.mock import MagicMock

    a = MagicMock()
    a.id = "ag_1"
    a.email = "admin_global@test.com"
    a.nome = "Admin Global Teste"
    a.perfil = "admin_global"
    a.must_change_password = False
    a.mfa_enabled = True
    a.is_authenticated = True
    a.get_id = lambda: "ag_1"
    return a


def _get_by_id_side_effect_admin_global(target_uid, target_user):
    """Retorna side_effect: admin_global mock para o Flask-Login, fake para a rota."""
    admin_global = _admin_global_mock_para_flask_login()

    def _side_effect(uid):
        return target_user if uid == target_uid else admin_global

    return _side_effect


@pytest.mark.parametrize("email_raiz", ["matheus.costa@dtx.aero", "admin@dtx.aero"])
def test_editar_usuario_root_admin_bloqueado_para_admin_global(
    client_logado_admin_global, email_raiz
):
    """POST editar de qualquer admin raiz protegido é bloqueado mesmo vindo de admin_global.

    Regressão: a proteção de admin raiz (EMAILS_ADMIN_RAIZ_PROTEGIDOS) só existia em
    deletar/desativar/anonimizar. Um admin_global conseguia rebaixar perfil, trocar
    nome/e-mail e desativar (via checkbox "ativo" ausente) a conta raiz inteira via
    /admin/usuarios/<id>/editar, contornando a proteção por completo.
    """
    fake_root = _usuario_fake(
        uid="root", email=email_raiz, nome="Root Admin", perfil="admin_global"
    )
    fake_root.update = MagicMock()
    with patch(
        "app.models_usuario.Usuario.get_by_id",
        side_effect=_get_by_id_side_effect_admin_global("root", fake_root),
    ):
        r = client_logado_admin_global.post(
            "/admin/usuarios/root/editar",
            data={"email": email_raiz, "nome": "Root Admin Hackeado", "perfil": "solicitante"},
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")
    fake_root.update.assert_not_called()


@pytest.mark.parametrize("email_raiz", ["matheus.costa@dtx.aero", "admin@dtx.aero"])
def test_editar_usuario_root_admin_pode_editar_a_si_mesmo(client_logado_admin_global, email_raiz):
    """Regressão: a proteção de admin raiz bloqueia edição feita por OUTROS, não auto-edição.

    O admin raiz logado (ex.: matheus.costa@dtx.aero) precisa continuar conseguindo
    editar o próprio nome/áreas via /admin/usuarios/<próprio_id>/editar. Perfil
    "admin" no payload só serve pra passar da whitelist do formulário
    (solicitante/supervisor/admin — não inclui admin_global, limitação
    pré-existente e não relacionada a este teste; ver
    test_editar_usuario_post_admin_global_permitido_para_admin_global).
    """
    root_self = _usuario_fake(
        uid="ag_1", email=email_raiz, nome="Root Admin", perfil="admin_global"
    )
    root_self.update = MagicMock()
    with patch("app.models_usuario.Usuario.get_by_id", return_value=root_self):
        r = client_logado_admin_global.post(
            "/admin/usuarios/ag_1/editar",
            data={"email": email_raiz, "nome": "Root Admin Renomeado", "perfil": "admin"},
            follow_redirects=False,
        )
    assert r.status_code == 302
    root_self.update.assert_called_once()


# ── Resetar senha ──────────────────────────────────────────────────────────────


def test_resetar_senha_sucesso(client_logado_admin):
    """POST resetar-senha de outro usuário dispara thread e redireciona."""
    fake = _usuario_fake(uid="u4", email="u4@dtx.aero", nome="Usuario Quatro")
    fake.set_password = MagicMock()
    fake.update = MagicMock()
    fake.areas = []
    with (
        patch(
            "app.models_usuario.Usuario.get_by_id", side_effect=_get_by_id_side_effect("u4", fake)
        ),
        patch("app.routes.usuarios.threading.Thread") as mock_thread,
    ):
        r = client_logado_admin.post("/admin/usuarios/u4/resetar-senha", follow_redirects=False)
    assert r.status_code == 302
    assert mock_thread.return_value.start.call_count >= 1
    # Regressão: reset precisa persistir o hash da senha nova, não só marcar
    # must_change_password (bug real: update() sem "senha" nunca grava senha_hash).
    fake.update.assert_called_once()
    update_kwargs = fake.update.call_args.kwargs
    assert update_kwargs.get("senha")
    assert update_kwargs.get("must_change_password") is True


def test_resetar_senha_usuario_nao_encontrado(client_logado_admin):
    """POST resetar-senha de ID inexistente redireciona com erro."""
    admin = _admin_mock_para_flask_login()
    with patch(
        "app.models_usuario.Usuario.get_by_id",
        side_effect=lambda uid: None if uid == "nao" else admin,
    ):
        r = client_logado_admin.post("/admin/usuarios/nao/resetar-senha", follow_redirects=False)
    assert r.status_code == 302


# ── Resetar EXP ───────────────────────────────────────────────────────────────


def test_resetar_exp_sucesso(client_logado_admin):
    """POST reset-exp de usuário existente zera gamification e redireciona."""
    fake = _usuario_fake(uid="u5", email="u5@dtx.aero", nome="Usuario Cinco")
    fake.update = lambda **kw: None
    with (
        patch(
            "app.models_usuario.Usuario.get_by_id", side_effect=_get_by_id_side_effect("u5", fake)
        ),
        patch("app.routes.usuarios.Usuario.invalidar_cache_supervisores_por_area"),
    ):
        r = client_logado_admin.post("/admin/usuarios/u5/reset-exp", follow_redirects=False)
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")


def test_resetar_exp_usuario_nao_encontrado(client_logado_admin):
    """POST reset-exp de ID inexistente redireciona com erro."""
    admin = _admin_mock_para_flask_login()
    with patch(
        "app.models_usuario.Usuario.get_by_id",
        side_effect=lambda uid: None if uid == "nao" else admin,
    ):
        r = client_logado_admin.post("/admin/usuarios/nao/reset-exp", follow_redirects=False)
    assert r.status_code == 302


# ── Testes de segurança: senha e ID ──────────────────────────────────────────


def test_gerar_senha_aleatoria_tamanho_minimo():
    """Senha gerada deve ter ao menos 12 chars."""
    from app.routes.usuarios import _gerar_senha_aleatoria

    for _ in range(20):
        senha = _gerar_senha_aleatoria()
        assert len(senha) >= 12, f"Senha muito curta: {len(senha)} chars"


def test_gerar_senha_aleatoria_complexidade():
    """Senha gerada deve conter maiúscula, minúscula, dígito e símbolo especial."""
    from app.routes.usuarios import _gerar_senha_aleatoria

    especiais = set("!@#$%&*")
    for _ in range(50):
        senha = _gerar_senha_aleatoria()
        assert any(c.isupper() for c in senha), "Falta maiúscula"
        assert any(c.islower() for c in senha), "Falta minúscula"
        assert any(c.isdigit() for c in senha), "Falta dígito"
        assert any(c in especiais for c in senha), "Falta símbolo especial"


def test_gerar_senha_aleatoria_nao_tem_chars_invalidos():
    """Senha não deve conter espaço nem barras (que causam problemas em logs/URLs)."""
    from app.routes.usuarios import _gerar_senha_aleatoria

    for _ in range(30):
        senha = _gerar_senha_aleatoria()
        assert " " not in senha
        assert "/" not in senha
        assert "\\" not in senha


def test_criar_usuario_id_usa_uuid_completo(client_logado_admin):
    """ID gerado no POST /criar deve usar uuid4 completo (32 hex chars após 'user_')."""

    ids_capturados = []

    class _FakeUsuario:
        email = "novo@dtx.aero"
        nome = "Novo Usuario"
        perfil = "solicitante"
        areas = []
        id = None

        def set_password(self, _): ...

        def save(self):
            pass

    def _fake_constructor(**kw):
        u = _FakeUsuario()
        u.id = kw.get("id", "")
        ids_capturados.append(u.id)
        return u

    with (
        patch("app.routes.usuarios.Usuario.email_existe", return_value=False),
        patch("app.routes.usuarios.Usuario", side_effect=_fake_constructor),
        patch("app.routes.usuarios.cache_delete"),
        patch("app.routes.usuarios.Usuario.invalidar_cache_supervisores_por_area"),
        patch("app.routes.usuarios.threading.Thread"),
    ):
        client_logado_admin.post(
            "/admin/usuarios",
            data={
                "acao": "criar",
                "email": "novo@dtx.aero",
                "nome": "Novo Usuario",
                "perfil": "solicitante",
            },
            follow_redirects=False,
        )

    if ids_capturados:
        uid = ids_capturados[0]
        assert uid.startswith("user_"), f"Prefixo inesperado: {uid}"
        hex_part = uid[len("user_") :]
        assert len(hex_part) == 32, f"UUID truncado — esperado 32 chars, obtido {len(hex_part)}"
        assert re.fullmatch(r"[0-9a-f]{32}", hex_part), f"Hex inválido: {hex_part}"


# ── Segurança: auto-operações bloqueadas ──────────────────────────────────────


def test_deletar_proprio_usuario_bloqueado(client_logado_admin):
    """Admin não pode deletar a própria conta (cannot_delete_own_account)."""
    # perfil="admin" necessário para passar o decorator @requer_perfil("admin")
    admin_self = _usuario_fake(
        uid="admin_1", email="admin@test.com", nome="Admin Teste", perfil="admin"
    )
    with patch("app.models_usuario.Usuario.get_by_id", return_value=admin_self):
        r = client_logado_admin.post("/admin/usuarios/admin_1/deletar", follow_redirects=False)
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")


def test_resetar_senha_proprio_usuario_bloqueado(client_logado_admin):
    """Admin não pode resetar a própria senha (cannot_reset_own_password)."""
    # perfil="admin" necessário para passar o decorator @requer_perfil("admin")
    admin_self = _usuario_fake(
        uid="admin_1", email="admin@test.com", nome="Admin Teste", perfil="admin"
    )
    admin_self.set_password = lambda s: None
    admin_self.update = lambda **kw: None
    admin_self.areas = []
    with patch("app.models_usuario.Usuario.get_by_id", return_value=admin_self):
        r = client_logado_admin.post(
            "/admin/usuarios/admin_1/resetar-senha", follow_redirects=False
        )
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")


# ── Handlers except (flash genérico, sem vazar interno) ──────────────────────


def test_criar_usuario_excecao_retorna_flash_erro(client_logado_admin):
    """POST criar com exceção no save redireciona sem expor detalhe interno."""
    with (
        patch("app.routes.usuarios.Usuario.email_existe", return_value=False),
        patch("app.routes.usuarios.Usuario") as mock_cls,
    ):
        instance = mock_cls.return_value
        instance.set_password = lambda s: None
        instance.save.side_effect = Exception("Firestore down")
        r = client_logado_admin.post(
            "/admin/usuarios",
            data={
                "acao": "criar",
                "email": "x@dtx.aero",
                "nome": "Novo Nome",
                "perfil": "solicitante",
            },
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")


def test_listar_usuarios_excecao_redireciona(client_logado_admin):
    """GET /admin/usuarios com exceção em get_all redireciona com flash de erro."""
    with patch("app.routes.usuarios.Usuario.get_all", side_effect=Exception("db error")):
        r = client_logado_admin.get("/admin/usuarios", follow_redirects=False)
    assert r.status_code == 302


def test_deletar_usuario_excecao_redireciona(client_logado_admin):
    """POST deletar com exceção em delete() redireciona com flash de erro."""
    fake = _usuario_fake(uid="u_del", email="u@dtx.aero", nome="A Deletar")
    fake.delete = MagicMock(side_effect=Exception("delete failed"))
    with (
        patch(
            "app.models_usuario.Usuario.get_by_id",
            side_effect=_get_by_id_side_effect("u_del", fake),
        ),
        patch("app.routes.usuarios.Usuario.invalidar_cache_supervisores_por_area"),
    ):
        r = client_logado_admin.post("/admin/usuarios/u_del/deletar", follow_redirects=False)
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")


def test_resetar_senha_excecao_redireciona(client_logado_admin):
    """POST resetar-senha com exceção em set_password redireciona com flash de erro."""
    fake = _usuario_fake(uid="u_pw", email="u@dtx.aero", nome="Usuario PW")
    fake.set_password = MagicMock(side_effect=Exception("pw error"))
    fake.update = lambda **kw: None
    fake.areas = []
    with patch(
        "app.models_usuario.Usuario.get_by_id", side_effect=_get_by_id_side_effect("u_pw", fake)
    ):
        r = client_logado_admin.post("/admin/usuarios/u_pw/resetar-senha", follow_redirects=False)
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")


def test_resetar_exp_excecao_redireciona(client_logado_admin):
    """POST reset-exp com exceção em update redireciona com flash de erro."""
    fake = _usuario_fake(uid="u_exp", email="u@dtx.aero", nome="Usuario EXP")
    fake.update = MagicMock(side_effect=Exception("exp error"))
    with (
        patch(
            "app.models_usuario.Usuario.get_by_id",
            side_effect=_get_by_id_side_effect("u_exp", fake),
        ),
        patch("app.routes.usuarios.Usuario.invalidar_cache_supervisores_por_area"),
    ):
        r = client_logado_admin.post("/admin/usuarios/u_exp/reset-exp", follow_redirects=False)
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")


# ── Editar usuário: cobertura do path POST ────────────────────────────────────


def test_editar_usuario_post_sucesso_chama_update_e_cache(client_logado_admin):
    """POST editar com dados válidos chama update e invalida cache."""
    fake = _usuario_fake(
        uid="u_edit", email="old@dtx.aero", nome="Usuario Edit", perfil="solicitante"
    )
    fake.areas = []
    fake.update = MagicMock()
    with (
        patch(
            "app.models_usuario.Usuario.get_by_id",
            side_effect=_get_by_id_side_effect("u_edit", fake),
        ),
        patch("app.routes.usuarios.Usuario.email_existe", return_value=False),
        patch("app.routes.usuarios.cache_delete") as mock_cd,
        patch("app.routes.usuarios.Usuario.invalidar_cache_supervisores_por_area") as mock_inval,
    ):
        r = client_logado_admin.post(
            "/admin/usuarios/u_edit/editar",
            data={"email": "new@dtx.aero", "nome": "Usuario Edit Novo", "perfil": "solicitante"},
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")
    fake.update.assert_called_once()
    assert mock_cd.call_count >= 1
    mock_inval.assert_called_once()


def test_editar_usuario_post_perfil_alterado_dispara_notificacao(client_logado_admin):
    """POST editar com perfil alterado dispara notificar_mudanca_perfil."""
    fake = _usuario_fake(
        uid="u_prom", email="prom@dtx.aero", nome="Usuario Prom", perfil="solicitante"
    )
    fake.areas = ["Manutencao"]
    fake.update = MagicMock()
    with (
        patch(
            "app.models_usuario.Usuario.get_by_id",
            side_effect=_get_by_id_side_effect("u_prom", fake),
        ),
        patch("app.routes.usuarios.Usuario.email_existe", return_value=False),
        patch("app.routes.usuarios.cache_delete"),
        patch("app.routes.usuarios.Usuario.invalidar_cache_supervisores_por_area"),
        patch("app.routes.usuarios.notificar_mudanca_perfil") as mock_notificar,
        patch("app.routes.usuarios.threading.Thread", side_effect=_FakeThread),
    ):
        r = client_logado_admin.post(
            "/admin/usuarios/u_prom/editar",
            data={
                "email": "prom@dtx.aero",
                "nome": "Usuario Prom",
                "perfil": "supervisor",
                "areas": ["Manutencao"],
            },
            follow_redirects=False,
        )

    assert r.status_code == 302
    mock_notificar.assert_called_once()
    kwargs = mock_notificar.call_args.kwargs
    assert kwargs["usuario_email"] == "prom@dtx.aero"
    assert kwargs["novo_perfil"] == "supervisor"


def test_editar_usuario_post_perfil_mantido_nao_notifica(client_logado_admin):
    """POST editar sem mudar o perfil não dispara notificar_mudanca_perfil."""
    fake = _usuario_fake(
        uid="u_same", email="same@dtx.aero", nome="Usuario Same", perfil="solicitante"
    )
    fake.areas = []
    fake.update = MagicMock()
    with (
        patch(
            "app.models_usuario.Usuario.get_by_id",
            side_effect=_get_by_id_side_effect("u_same", fake),
        ),
        patch("app.routes.usuarios.Usuario.email_existe", return_value=False),
        patch("app.routes.usuarios.cache_delete"),
        patch("app.routes.usuarios.Usuario.invalidar_cache_supervisores_por_area"),
        patch("app.routes.usuarios.notificar_mudanca_perfil") as mock_notificar,
        patch("app.routes.usuarios.threading.Thread", side_effect=_FakeThread),
    ):
        r = client_logado_admin.post(
            "/admin/usuarios/u_same/editar",
            data={
                "email": "same@dtx.aero",
                "nome": "Usuario Same Novo",
                "perfil": "solicitante",
            },
            follow_redirects=False,
        )

    assert r.status_code == 302
    mock_notificar.assert_not_called()


def test_editar_usuario_post_perfil_novo_ainda_nao_visto_reseta_onboarding(client_logado_admin):
    """POST editar promovendo pra perfil nunca visto reseta onboarding_passo=0."""
    fake = _usuario_fake(
        uid="u_prom2", email="prom2@dtx.aero", nome="Usuario Prom2", perfil="solicitante"
    )
    fake.areas = ["Manutencao"]
    fake.onboarding_perfis_vistos = ["solicitante"]
    fake.update = MagicMock()
    with (
        patch(
            "app.models_usuario.Usuario.get_by_id",
            side_effect=_get_by_id_side_effect("u_prom2", fake),
        ),
        patch("app.routes.usuarios.Usuario.email_existe", return_value=False),
        patch("app.routes.usuarios.cache_delete"),
        patch("app.routes.usuarios.Usuario.invalidar_cache_supervisores_por_area"),
        patch("app.routes.usuarios.notificar_mudanca_perfil"),
        patch("app.routes.usuarios.threading.Thread", side_effect=_FakeThread),
    ):
        r = client_logado_admin.post(
            "/admin/usuarios/u_prom2/editar",
            data={
                "email": "prom2@dtx.aero",
                "nome": "Usuario Prom2",
                "perfil": "supervisor",
                "areas": ["Manutencao"],
            },
            follow_redirects=False,
        )

    assert r.status_code == 302
    _, kwargs = fake.update.call_args
    assert kwargs["onboarding_passo"] == 0


def test_editar_usuario_post_perfil_ja_visto_nao_reseta_onboarding(client_logado_admin):
    """POST editar voltando pra um perfil já visto antes NÃO reseta onboarding_passo."""
    fake = _usuario_fake(
        uid="u_rebaixado", email="rebaixado@dtx.aero", nome="Usuario Rebaixado", perfil="supervisor"
    )
    fake.areas = ["Manutencao"]
    fake.onboarding_perfis_vistos = ["solicitante", "supervisor"]
    fake.update = MagicMock()
    with (
        patch(
            "app.models_usuario.Usuario.get_by_id",
            side_effect=_get_by_id_side_effect("u_rebaixado", fake),
        ),
        patch("app.routes.usuarios.Usuario.email_existe", return_value=False),
        patch("app.routes.usuarios.cache_delete"),
        patch("app.routes.usuarios.Usuario.invalidar_cache_supervisores_por_area"),
        patch("app.routes.usuarios.notificar_mudanca_perfil"),
        patch("app.routes.usuarios.threading.Thread", side_effect=_FakeThread),
    ):
        r = client_logado_admin.post(
            "/admin/usuarios/u_rebaixado/editar",
            data={
                "email": "rebaixado@dtx.aero",
                "nome": "Usuario Rebaixado",
                "perfil": "solicitante",
            },
            follow_redirects=False,
        )

    assert r.status_code == 302
    _, kwargs = fake.update.call_args
    assert "onboarding_passo" not in kwargs


def test_editar_usuario_post_email_invalido_redireciona(client_logado_admin):
    """POST editar com novo email sem @ redireciona com erro."""
    fake = _usuario_fake(uid="u_em", email="old@dtx.aero", nome="Usuario EM", perfil="solicitante")
    fake.areas = []
    with (
        patch(
            "app.models_usuario.Usuario.get_by_id", side_effect=_get_by_id_side_effect("u_em", fake)
        ),
    ):
        r = client_logado_admin.post(
            "/admin/usuarios/u_em/editar",
            data={"email": "invalido", "nome": "Usuario EM", "perfil": "solicitante"},
            follow_redirects=False,
        )
    assert r.status_code == 302


def test_editar_usuario_post_email_duplicado_redireciona(client_logado_admin):
    """POST editar com email já existente redireciona com erro."""
    fake = _usuario_fake(
        uid="u_dup", email="old@dtx.aero", nome="Usuario Dup", perfil="solicitante"
    )
    fake.areas = []
    with (
        patch(
            "app.models_usuario.Usuario.get_by_id",
            side_effect=_get_by_id_side_effect("u_dup", fake),
        ),
        patch("app.routes.usuarios.Usuario.email_existe", return_value=True),
    ):
        r = client_logado_admin.post(
            "/admin/usuarios/u_dup/editar",
            data={"email": "outro@dtx.aero", "nome": "Usuario Dup", "perfil": "solicitante"},
            follow_redirects=False,
        )
    assert r.status_code == 302


def test_editar_usuario_post_supervisor_sem_area_redireciona(client_logado_admin):
    """POST editar promovendo para supervisor sem área redireciona com erro."""
    fake = _usuario_fake(
        uid="u_sup", email="u_sup@dtx.aero", nome="Virar Sup", perfil="solicitante"
    )
    fake.areas = []
    with (
        patch(
            "app.models_usuario.Usuario.get_by_id",
            side_effect=_get_by_id_side_effect("u_sup", fake),
        ),
        patch("app.routes.usuarios.Usuario.email_existe", return_value=False),
    ):
        r = client_logado_admin.post(
            "/admin/usuarios/u_sup/editar",
            data={"email": "u_sup@dtx.aero", "nome": "Virar Sup", "perfil": "supervisor"},
            follow_redirects=False,
        )
    assert r.status_code == 302


def test_editar_usuario_post_admin_bloqueado_para_sub_admin(client_logado_admin):
    """Sub-admin não pode promover usuário para perfil admin via edição (access_denied)."""
    fake = _usuario_fake(uid="u_prom", email="u_prom@dtx.aero", nome="Prom", perfil="supervisor")
    fake.areas = ["Geral"]
    with (
        patch(
            "app.models_usuario.Usuario.get_by_id",
            side_effect=_get_by_id_side_effect("u_prom", fake),
        ),
        patch("app.routes.usuarios.Usuario.email_existe", return_value=False),
    ):
        r = client_logado_admin.post(
            "/admin/usuarios/u_prom/editar",
            data={
                "email": "u_prom@dtx.aero",
                "nome": "Prom",
                "perfil": "admin",
                "areas": ["Geral"],
            },
            follow_redirects=False,
        )
    assert r.status_code == 302


def test_editar_usuario_post_admin_global_pode_promover_para_admin(client_logado_admin_global):
    """admin_global pode promover usuário para perfil admin via edição."""
    fake = _usuario_fake(uid="u_prm2", email="u@dtx.aero", nome="Virar Admin", perfil="supervisor")
    fake.areas = ["Geral"]
    fake.update = MagicMock()
    # admin_global user para o Flask-Login
    ag_mock = _usuario_fake(
        uid="ag_1", email="ag@test.com", nome="Admin Global", perfil="admin_global"
    )

    def _side(uid):
        if uid == "u_prm2":
            return fake
        return ag_mock

    with (
        patch("app.models_usuario.Usuario.get_by_id", side_effect=_side),
        patch("app.routes.usuarios.Usuario.email_existe", return_value=False),
        patch("app.routes.usuarios.cache_delete"),
        patch("app.routes.usuarios.Usuario.invalidar_cache_supervisores_por_area"),
    ):
        r = client_logado_admin_global.post(
            "/admin/usuarios/u_prm2/editar",
            data={
                "email": "u@dtx.aero",
                "nome": "Virar Admin",
                "perfil": "admin",
                "areas": ["Geral"],
            },
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")
    fake.update.assert_called()


def test_editar_usuario_post_excecao_redireciona(client_logado_admin):
    """POST editar com exceção em update() redireciona com flash de erro."""
    fake = _usuario_fake(uid="u_exc", email="u_exc@dtx.aero", nome="Exc User", perfil="solicitante")
    fake.areas = []
    fake.update = MagicMock(side_effect=Exception("db broke"))
    with (
        patch(
            "app.models_usuario.Usuario.get_by_id",
            side_effect=_get_by_id_side_effect("u_exc", fake),
        ),
        patch("app.routes.usuarios.Usuario.email_existe", return_value=False),
    ):
        r = client_logado_admin.post(
            "/admin/usuarios/u_exc/editar",
            data={"email": "u_exc@dtx.aero", "nome": "Exc User Novo", "perfil": "solicitante"},
            follow_redirects=False,
        )
    assert r.status_code == 302


# ── Onda 2: desativar / ativar usuário ────────────────────────────────────────


def test_desativar_usuario_sucesso(client_logado_admin):
    """POST /admin/usuarios/<id>/desativar com usuário existente chama update(ativo=False)."""
    fake = _usuario_fake(uid="u_desat", email="u_desat@dtx.aero", nome="A Desativar")
    fake.ativo = True
    fake.update = MagicMock(return_value=True)
    with (
        patch(
            "app.models_usuario.Usuario.get_by_id",
            side_effect=_get_by_id_side_effect("u_desat", fake),
        ),
        patch("app.routes.usuarios.Usuario.invalidar_cache_supervisores_por_area"),
        patch("app.routes.usuarios.cache_delete"),
    ):
        r = client_logado_admin.post("/admin/usuarios/u_desat/desativar", follow_redirects=False)
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")
    fake.update.assert_called_once_with(ativo=False)


def test_desativar_usuario_sucesso_registra_historico(client_logado_admin):
    """POST desativar com sucesso registra auditoria no histórico de usuários."""
    fake = _usuario_fake(uid="u_desat", email="u_desat@dtx.aero", nome="A Desativar")
    fake.ativo = True
    fake.update = MagicMock(return_value=True)
    with (
        patch(
            "app.models_usuario.Usuario.get_by_id",
            side_effect=_get_by_id_side_effect("u_desat", fake),
        ),
        patch("app.routes.usuarios.Usuario.invalidar_cache_supervisores_por_area"),
        patch("app.routes.usuarios.cache_delete"),
        patch("app.routes.usuarios.registrar_historico_usuario") as mock_hist,
    ):
        client_logado_admin.post("/admin/usuarios/u_desat/desativar", follow_redirects=False)
    mock_hist.assert_called_once()
    kwargs = mock_hist.call_args.kwargs
    assert kwargs["acao"] == "desativacao"
    assert kwargs["usuario_alvo_id"] == "u_desat"


def test_desativar_proprio_usuario_bloqueado(client_logado_admin):
    """Admin não pode desativar a própria conta (cannot_deactivate_own_account)."""
    admin_self = _usuario_fake(
        uid="admin_1", email="admin@test.com", nome="Admin Teste", perfil="admin"
    )
    admin_self.ativo = True
    admin_self.update = MagicMock()
    with patch("app.models_usuario.Usuario.get_by_id", return_value=admin_self):
        r = client_logado_admin.post("/admin/usuarios/admin_1/desativar", follow_redirects=False)
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")
    admin_self.update.assert_not_called()


@pytest.mark.parametrize("email_raiz", ["matheus.costa@dtx.aero", "admin@dtx.aero"])
def test_desativar_root_admin_bloqueado(client_logado_admin, email_raiz):
    """Admin não pode desativar nenhum admin raiz protegido (cannot_deactivate_root_admin)."""
    fake_root = _usuario_fake(uid="root", email=email_raiz, nome="Root Admin")
    fake_root.ativo = True
    fake_root.update = MagicMock()
    with patch(
        "app.models_usuario.Usuario.get_by_id",
        side_effect=_get_by_id_side_effect("root", fake_root),
    ):
        r = client_logado_admin.post("/admin/usuarios/root/desativar", follow_redirects=False)
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")
    fake_root.update.assert_not_called()


def test_desativar_usuario_nao_encontrado(client_logado_admin):
    """POST desativar com ID inexistente redireciona com erro."""
    admin = _admin_mock_para_flask_login()
    with patch(
        "app.models_usuario.Usuario.get_by_id",
        side_effect=lambda uid: None if uid == "naoexiste" else admin,
    ):
        r = client_logado_admin.post("/admin/usuarios/naoexiste/desativar", follow_redirects=False)
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")


def test_ativar_usuario_sucesso(client_logado_admin):
    """POST /admin/usuarios/<id>/ativar chama update(ativo=True) — reativação."""
    fake = _usuario_fake(uid="u_reat", email="u_reat@dtx.aero", nome="A Reativar")
    fake.ativo = False
    fake.update = MagicMock(return_value=True)
    with (
        patch(
            "app.models_usuario.Usuario.get_by_id",
            side_effect=_get_by_id_side_effect("u_reat", fake),
        ),
        patch("app.routes.usuarios.Usuario.invalidar_cache_supervisores_por_area"),
        patch("app.routes.usuarios.cache_delete"),
    ):
        r = client_logado_admin.post("/admin/usuarios/u_reat/ativar", follow_redirects=False)
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")
    fake.update.assert_called_once_with(ativo=True)


def test_ativar_usuario_sucesso_registra_historico(client_logado_admin):
    """POST ativar com sucesso registra auditoria no histórico de usuários."""
    fake = _usuario_fake(uid="u_reat", email="u_reat@dtx.aero", nome="A Reativar")
    fake.ativo = False
    fake.update = MagicMock(return_value=True)
    with (
        patch(
            "app.models_usuario.Usuario.get_by_id",
            side_effect=_get_by_id_side_effect("u_reat", fake),
        ),
        patch("app.routes.usuarios.Usuario.invalidar_cache_supervisores_por_area"),
        patch("app.routes.usuarios.cache_delete"),
        patch("app.routes.usuarios.registrar_historico_usuario") as mock_hist,
    ):
        client_logado_admin.post("/admin/usuarios/u_reat/ativar", follow_redirects=False)
    mock_hist.assert_called_once()
    kwargs = mock_hist.call_args.kwargs
    assert kwargs["acao"] == "ativacao"
    assert kwargs["usuario_alvo_id"] == "u_reat"


def test_desativar_mfa_usuario_sucesso(client_logado_admin):
    """POST /admin/usuarios/<id>/desativar-mfa chama update com os campos de MFA limpos."""
    fake = _usuario_fake(uid="u_mfa_reset", email="u_mfa_reset@dtx.aero", nome="Trancado MFA")
    fake.mfa_enabled = True
    fake.update = MagicMock(return_value=True)
    with patch(
        "app.models_usuario.Usuario.get_by_id",
        side_effect=_get_by_id_side_effect("u_mfa_reset", fake),
    ):
        r = client_logado_admin.post(
            "/admin/usuarios/u_mfa_reset/desativar-mfa", follow_redirects=False
        )
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")
    fake.update.assert_called_once_with(mfa_enabled=False, mfa_secret=None, mfa_backup_codes=None)


def test_desativar_mfa_usuario_nao_encontrado_redireciona(client_logado_admin):
    """POST /admin/usuarios/<id>/desativar-mfa com ID inexistente redireciona com erro."""
    admin = _admin_mock_para_flask_login()
    with patch(
        "app.models_usuario.Usuario.get_by_id",
        side_effect=lambda uid: None if uid == "naoexiste" else admin,
    ):
        r = client_logado_admin.post(
            "/admin/usuarios/naoexiste/desativar-mfa", follow_redirects=False
        )
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")


def test_desativar_mfa_admin_global_bloqueado_para_sub_admin(client_logado_admin):
    """Sub-admin não pode resetar o MFA de uma conta admin_global."""
    fake_ag = _usuario_fake(
        uid="ag_mfa", email="ag_mfa@dtx.aero", nome="AG MFA", perfil="admin_global"
    )
    fake_ag.mfa_enabled = True
    fake_ag.update = MagicMock()
    with patch(
        "app.models_usuario.Usuario.get_by_id",
        side_effect=_get_by_id_side_effect("ag_mfa", fake_ag),
    ):
        r = client_logado_admin.post("/admin/usuarios/ag_mfa/desativar-mfa", follow_redirects=False)
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")
    fake_ag.update.assert_not_called()


def test_editar_usuario_post_admin_global_bloqueado_para_sub_admin(client_logado_admin):
    """Sub-admin não pode editar (POST) uma conta admin_global (cannot_edit_admin_global).

    Submete perfil="supervisor" (valor válido e que não colide com a checagem existente
    de "sub-admin não pode promover para admin") para garantir que o bloqueio vem da
    checagem de alvo admin_global, e não de alguma outra validação já existente.
    """
    fake_ag = _usuario_fake(
        uid="ag_target", email="ag_target@dtx.aero", nome="AG Alvo", perfil="admin_global"
    )
    fake_ag.update = MagicMock()
    with patch(
        "app.models_usuario.Usuario.get_by_id",
        side_effect=_get_by_id_side_effect("ag_target", fake_ag),
    ):
        r = client_logado_admin.post(
            "/admin/usuarios/ag_target/editar",
            data={
                "email": "ag_target@dtx.aero",
                "nome": "AG Alvo Novo",
                "perfil": "supervisor",
                "areas": ["Geral"],
            },
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")
    fake_ag.update.assert_not_called()


def test_editar_usuario_get_admin_global_bloqueado_para_sub_admin(client_logado_admin):
    """Sub-admin não pode nem ver o formulário de edição de uma conta admin_global."""
    fake_ag = _usuario_fake(
        uid="ag_target2", email="ag_target2@dtx.aero", nome="AG Alvo 2", perfil="admin_global"
    )
    with patch(
        "app.models_usuario.Usuario.get_by_id",
        side_effect=_get_by_id_side_effect("ag_target2", fake_ag),
    ):
        r = client_logado_admin.get("/admin/usuarios/ag_target2/editar", follow_redirects=False)
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")


def test_editar_usuario_post_admin_global_permitido_para_admin_global(
    client_logado_admin_global,
):
    """admin_global pode editar outra conta admin_global normalmente.

    O whitelist de perfil do formulário (solicitante/supervisor/admin) não inclui
    "admin_global" — isso é uma limitação pré-existente e não relacionada a este
    bloqueio, então o teste envia perfil="admin" (rebaixamento), um valor aceito
    pelo whitelist, apenas para comprovar que a checagem nova não impede admin_global
    de editar outro admin_global.
    """
    fake_ag = _usuario_fake(
        uid="ag_target3", email="ag_target3@dtx.aero", nome="AG Alvo 3", perfil="admin_global"
    )
    fake_ag.update = MagicMock()
    ag_mock = _usuario_fake(
        uid="ag_1", email="ag@test.com", nome="Admin Global", perfil="admin_global"
    )

    def _side(uid):
        return fake_ag if uid == "ag_target3" else ag_mock

    with (
        patch("app.models_usuario.Usuario.get_by_id", side_effect=_side),
        patch("app.routes.usuarios.Usuario.email_existe", return_value=False),
        patch("app.routes.usuarios.cache_delete"),
        patch("app.routes.usuarios.Usuario.invalidar_cache_supervisores_por_area"),
    ):
        r = client_logado_admin_global.post(
            "/admin/usuarios/ag_target3/editar",
            data={
                "email": "ag_target3@dtx.aero",
                "nome": "AG Alvo 3 Novo",
                "perfil": "admin",
            },
            follow_redirects=False,
        )
    assert r.status_code == 302
    fake_ag.update.assert_called_once()


def test_deletar_usuario_admin_global_bloqueado_para_sub_admin(client_logado_admin):
    """Sub-admin não pode deletar uma conta admin_global (cannot_delete_admin_global)."""
    fake_ag = _usuario_fake(
        uid="ag_del", email="ag_del@dtx.aero", nome="AG A Deletar", perfil="admin_global"
    )
    fake_ag.delete = MagicMock()
    with patch(
        "app.models_usuario.Usuario.get_by_id",
        side_effect=_get_by_id_side_effect("ag_del", fake_ag),
    ):
        r = client_logado_admin.post("/admin/usuarios/ag_del/deletar", follow_redirects=False)
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")
    fake_ag.delete.assert_not_called()


def test_desativar_usuario_admin_global_bloqueado_para_sub_admin(client_logado_admin):
    """Sub-admin não pode desativar uma conta admin_global (cannot_deactivate_admin_global)."""
    fake_ag = _usuario_fake(
        uid="ag_desat", email="ag_desat@dtx.aero", nome="AG A Desativar", perfil="admin_global"
    )
    fake_ag.ativo = True
    fake_ag.update = MagicMock()
    with patch(
        "app.models_usuario.Usuario.get_by_id",
        side_effect=_get_by_id_side_effect("ag_desat", fake_ag),
    ):
        r = client_logado_admin.post("/admin/usuarios/ag_desat/desativar", follow_redirects=False)
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")
    fake_ag.update.assert_not_called()


def test_ativar_usuario_admin_global_bloqueado_para_sub_admin(client_logado_admin):
    """Sub-admin não pode reativar uma conta admin_global."""
    fake_ag = _usuario_fake(
        uid="ag_ativ", email="ag_ativ@dtx.aero", nome="AG A Ativar", perfil="admin_global"
    )
    fake_ag.ativo = False
    fake_ag.update = MagicMock()
    with patch(
        "app.models_usuario.Usuario.get_by_id",
        side_effect=_get_by_id_side_effect("ag_ativ", fake_ag),
    ):
        r = client_logado_admin.post("/admin/usuarios/ag_ativ/ativar", follow_redirects=False)
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")
    fake_ag.update.assert_not_called()


def test_resetar_senha_admin_global_bloqueado_para_sub_admin(client_logado_admin):
    """Sub-admin não pode resetar a senha de uma conta admin_global."""
    fake_ag = _usuario_fake(
        uid="ag_pw", email="ag_pw@dtx.aero", nome="AG PW", perfil="admin_global"
    )
    fake_ag.set_password = MagicMock()
    fake_ag.update = MagicMock()
    with patch(
        "app.models_usuario.Usuario.get_by_id",
        side_effect=_get_by_id_side_effect("ag_pw", fake_ag),
    ):
        r = client_logado_admin.post("/admin/usuarios/ag_pw/resetar-senha", follow_redirects=False)
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")
    fake_ag.set_password.assert_not_called()


def test_admin_global_cria_usuario_admin(client_logado_admin_global):
    """admin_global pode criar usuário com perfil=admin com sucesso."""
    ag_mock = _usuario_fake(
        uid="ag_1", email="ag@test.com", nome="Admin Global", perfil="admin_global"
    )
    with (
        patch("app.models_usuario.Usuario.get_by_id", return_value=ag_mock),
        patch("app.routes.usuarios.Usuario.email_existe", return_value=False),
        patch("app.routes.usuarios.Usuario.save"),
        patch("app.routes.usuarios.Usuario.invalidar_cache_supervisores_por_area"),
        patch("app.routes.usuarios.cache_delete"),
        patch("app.routes.usuarios.threading.Thread"),
    ):
        r = client_logado_admin_global.post(
            "/admin/usuarios",
            data={
                "acao": "criar",
                "email": "novo.admin@dtx.aero",
                "nome": "Novo Admin Global",
                "perfil": "admin",
            },
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")


# ── Anonimizar dados de usuário (LGPD, sob demanda) ─────────────────────────────


def test_anonimizar_usuario_desativado_sucesso(client_logado_admin):
    """POST anonimizar em usuário já desativado sobrescreve nome/email e registra histórico."""
    fake = _usuario_fake(uid="u_anon", email="u_anon@dtx.aero", nome="Pessoa Real")
    fake.ativo = False
    fake.update = MagicMock(return_value=True)
    with (
        patch(
            "app.models_usuario.Usuario.get_by_id",
            side_effect=_get_by_id_side_effect("u_anon", fake),
        ),
        patch("app.routes.usuarios.Usuario.invalidar_cache_supervisores_por_area"),
        patch("app.routes.usuarios.cache_delete"),
        patch("app.routes.usuarios.registrar_historico_usuario") as mock_hist,
    ):
        r = client_logado_admin.post("/admin/usuarios/u_anon/anonimizar", follow_redirects=False)
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")
    fake.update.assert_called_once()
    kwargs = fake.update.call_args.kwargs
    assert kwargs["nome"] != "Pessoa Real"
    assert kwargs["email"] != "u_anon@dtx.aero"
    assert "u_anon" in kwargs["email"]
    mock_hist.assert_called_once()
    assert mock_hist.call_args.kwargs["acao"] == "anonimizacao"


def test_anonimizar_usuario_ativo_bloqueado(client_logado_admin):
    """POST anonimizar em usuário ainda ativo é bloqueado — precisa desativar primeiro."""
    fake = _usuario_fake(uid="u_ativo", email="u_ativo@dtx.aero", nome="Pessoa Ativa")
    fake.ativo = True
    fake.update = MagicMock()
    with patch(
        "app.models_usuario.Usuario.get_by_id",
        side_effect=_get_by_id_side_effect("u_ativo", fake),
    ):
        r = client_logado_admin.post("/admin/usuarios/u_ativo/anonimizar", follow_redirects=False)
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")
    fake.update.assert_not_called()


def test_anonimizar_proprio_usuario_bloqueado(client_logado_admin):
    """Admin não pode anonimizar a própria conta."""
    admin_self = _usuario_fake(
        uid="admin_1", email="admin@test.com", nome="Admin Teste", perfil="admin"
    )
    admin_self.ativo = False
    admin_self.update = MagicMock()
    with patch("app.models_usuario.Usuario.get_by_id", return_value=admin_self):
        r = client_logado_admin.post("/admin/usuarios/admin_1/anonimizar", follow_redirects=False)
    assert r.status_code == 302
    admin_self.update.assert_not_called()


@pytest.mark.parametrize("email_raiz", ["matheus.costa@dtx.aero", "admin@dtx.aero"])
def test_anonimizar_root_admin_bloqueado(client_logado_admin, email_raiz):
    """Admin não pode anonimizar nenhum admin raiz protegido."""
    fake_root = _usuario_fake(uid="root", email=email_raiz, nome="Root Admin")
    fake_root.ativo = False
    fake_root.update = MagicMock()
    with patch(
        "app.models_usuario.Usuario.get_by_id",
        side_effect=_get_by_id_side_effect("root", fake_root),
    ):
        r = client_logado_admin.post("/admin/usuarios/root/anonimizar", follow_redirects=False)
    assert r.status_code == 302
    fake_root.update.assert_not_called()


def test_anonimizar_usuario_nao_encontrado(client_logado_admin):
    """POST anonimizar com ID inexistente redireciona com erro."""
    admin = _admin_mock_para_flask_login()
    with patch(
        "app.models_usuario.Usuario.get_by_id",
        side_effect=lambda uid: None if uid == "naoexiste" else admin,
    ):
        r = client_logado_admin.post("/admin/usuarios/naoexiste/anonimizar", follow_redirects=False)
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")


def test_anonimizar_admin_global_bloqueado_para_sub_admin(client_logado_admin):
    """Sub-admin não pode anonimizar conta admin_global."""
    fake_ag = _usuario_fake(
        uid="ag_target", email="ag_target@dtx.aero", nome="AG Alvo", perfil="admin_global"
    )
    fake_ag.ativo = False
    fake_ag.update = MagicMock()
    with patch(
        "app.models_usuario.Usuario.get_by_id",
        side_effect=_get_by_id_side_effect("ag_target", fake_ag),
    ):
        r = client_logado_admin.post("/admin/usuarios/ag_target/anonimizar", follow_redirects=False)
    assert r.status_code == 302
    fake_ag.update.assert_not_called()
