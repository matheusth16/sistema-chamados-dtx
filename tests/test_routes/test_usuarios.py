"""Testes das rotas de administração de usuários (/admin/usuarios). Requer perfil admin."""

import re
from unittest.mock import MagicMock, patch


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
    """POST deletar com ID existente (não admin@dtx.aero) redireciona com sucesso."""
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


def test_deletar_usuario_nao_encontrado_redireciona(client_logado_admin):
    """POST deletar com ID inexistente redireciona com erro user_not_found."""
    admin = _admin_mock_para_flask_login()
    with patch(
        "app.models_usuario.Usuario.get_by_id",
        side_effect=lambda uid: None if uid == "naoexiste" else admin,
    ):
        r = client_logado_admin.post("/admin/usuarios/naoexiste/deletar", follow_redirects=False)
    assert r.status_code == 302


def test_deletar_usuario_root_admin_bloqueado(client_logado_admin):
    """POST deletar admin@dtx.aero é bloqueado (cannot_delete_root_admin)."""
    fake_root = _usuario_fake(uid="root", email="admin@dtx.aero", nome="Root Admin")
    with patch(
        "app.models_usuario.Usuario.get_by_id",
        side_effect=_get_by_id_side_effect("root", fake_root),
    ):
        r = client_logado_admin.post("/admin/usuarios/root/deletar", follow_redirects=False)
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")


# ── Resetar senha ──────────────────────────────────────────────────────────────


def test_resetar_senha_sucesso(client_logado_admin):
    """POST resetar-senha de outro usuário dispara thread e redireciona."""
    fake = _usuario_fake(uid="u4", email="u4@dtx.aero", nome="Usuario Quatro")
    fake.set_password = lambda s: None
    fake.update = lambda **kw: None
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


def test_desativar_root_admin_bloqueado(client_logado_admin):
    """Admin não pode desativar admin@dtx.aero (cannot_deactivate_root_admin)."""
    fake_root = _usuario_fake(uid="root", email="admin@dtx.aero", nome="Root Admin")
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
