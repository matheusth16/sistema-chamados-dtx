"""Testes das rotas de onboarding: avancar, concluir, pular."""

import json
from unittest.mock import MagicMock, patch

import pytest

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _post_json(client, url, body=None):
    return client.post(
        url,
        data=json.dumps(body or {}),
        content_type="application/json",
    )


_MEUS_CHAMADOS_CTX_VAZIO = {
    "chamados": [],
    "pagina_atual": 1,
    "total_paginas": 1,
    "total_chamados": 0,
    "status_counts": {"Aberto": 0, "Em Atendimento": 0, "Concluído": 0, "Cancelado": 0},
    "cursor_next": None,
    "cursor_prev": None,
}


# ─── Autenticação obrigatória ─────────────────────────────────────────────────


def test_avancar_requer_login(client):
    r = _post_json(client, "/api/onboarding/avancar", {"passo": 1})
    assert r.status_code in (302, 401)


def test_concluir_requer_login(client):
    r = _post_json(client, "/api/onboarding/concluir")
    assert r.status_code in (302, 401)


def test_pular_requer_login(client):
    r = _post_json(client, "/api/onboarding/pular")
    assert r.status_code in (302, 401)


# ─── Validação de entrada ──────────────────────────────────────────────────────


def test_avancar_sem_passo_retorna_400(client_logado_solicitante):
    # A validação acontece antes de chamar o serviço — nenhum mock necessário
    r = _post_json(client_logado_solicitante, "/api/onboarding/avancar", {})
    assert r.status_code == 400
    assert r.get_json()["sucesso"] is False


def test_avancar_passo_negativo_retorna_400(client_logado_solicitante):
    r = _post_json(client_logado_solicitante, "/api/onboarding/avancar", {"passo": -1})
    assert r.status_code == 400
    assert r.get_json()["sucesso"] is False


def test_avancar_passo_nao_inteiro_retorna_400(client_logado_solicitante):
    r = _post_json(client_logado_solicitante, "/api/onboarding/avancar", {"passo": "abc"})
    assert r.status_code == 400


# ─── Fluxo feliz: solicitante ─────────────────────────────────────────────────


def test_avancar_passo_solicitante(client_logado_solicitante):
    with patch("app.services.onboarding_service.db") as mock_db:
        mock_db.collection.return_value.document.return_value.update.return_value = None
        r = _post_json(client_logado_solicitante, "/api/onboarding/avancar", {"passo": 2})
    assert r.status_code == 200
    assert r.get_json()["sucesso"] is True


def test_concluir_solicitante(client_logado_solicitante):
    with patch("app.services.onboarding_service.db") as mock_db:
        mock_db.collection.return_value.document.return_value.update.return_value = None
        r = _post_json(client_logado_solicitante, "/api/onboarding/concluir")
    assert r.status_code == 200
    assert r.get_json()["sucesso"] is True


def test_pular_solicitante(client_logado_solicitante):
    with patch("app.services.onboarding_service.db") as mock_db:
        mock_db.collection.return_value.document.return_value.update.return_value = None
        r = _post_json(client_logado_solicitante, "/api/onboarding/pular")
    assert r.status_code == 200
    assert r.get_json()["sucesso"] is True


# ─── Fluxo feliz: supervisor ──────────────────────────────────────────────────


def test_avancar_passo_supervisor(client_logado_supervisor):
    with patch("app.services.onboarding_service.db") as mock_db:
        mock_db.collection.return_value.document.return_value.update.return_value = None
        r = _post_json(client_logado_supervisor, "/api/onboarding/avancar", {"passo": 3})
    assert r.status_code == 200
    assert r.get_json()["sucesso"] is True


def test_concluir_supervisor(client_logado_supervisor):
    with patch("app.services.onboarding_service.db") as mock_db:
        mock_db.collection.return_value.document.return_value.update.return_value = None
        r = _post_json(client_logado_supervisor, "/api/onboarding/concluir")
    assert r.status_code == 200
    assert r.get_json()["sucesso"] is True


# ─── Fluxo feliz: admin ───────────────────────────────────────────────────────


def test_avancar_passo_admin(client_logado_admin):
    with patch("app.services.onboarding_service.db") as mock_db:
        mock_db.collection.return_value.document.return_value.update.return_value = None
        r = _post_json(client_logado_admin, "/api/onboarding/avancar", {"passo": 5})
    assert r.status_code == 200
    assert r.get_json()["sucesso"] is True


def test_concluir_admin(client_logado_admin):
    with patch("app.services.onboarding_service.db") as mock_db:
        mock_db.collection.return_value.document.return_value.update.return_value = None
        r = _post_json(client_logado_admin, "/api/onboarding/concluir")
    assert r.status_code == 200
    assert r.get_json()["sucesso"] is True


# ─── Serviço: campos persistidos corretamente ─────────────────────────────────


def test_service_avancar_persiste_passo():
    """avancar_passo chama update com o passo correto."""
    from app.services.onboarding_service import avancar_passo

    with patch("app.services.onboarding_service.db") as mock_db:
        mock_update = mock_db.collection.return_value.document.return_value.update
        avancar_passo("uid_test", 4)
        mock_update.assert_called_once_with({"onboarding_passo": 4})


def test_service_concluir_persiste_flag():
    """concluir_onboarding adiciona o perfil a onboarding_perfis_vistos (via ArrayUnion) e zera o passo."""
    from app.services.onboarding_service import concluir_onboarding

    with patch("app.services.onboarding_service.db") as mock_db:
        mock_update = mock_db.collection.return_value.document.return_value.update
        concluir_onboarding("uid_test", "solicitante")
        call_args = mock_update.call_args[0][0]
        assert call_args["onboarding_passo"] == 0
        assert call_args["onboarding_perfis_vistos"].values == ["solicitante"]


# ─── Template: componente injetado / omitido — só na home de cada perfil ──────


def _usuario_com_onboarding(
    perfil="solicitante", onboarding_perfis_vistos=None, onboarding_passo=0, is_gestor_only=False
):
    u = MagicMock()
    u.id = "uid_ob"
    u.email = "ob@test.com"
    u.nome = "Teste Onboarding"
    u.perfil = perfil
    u.area = "Geral"
    u.areas = ["Geral"]
    u.is_authenticated = True
    u.must_change_password = False
    u.mfa_enabled = True
    u.onboarding_perfis_vistos = onboarding_perfis_vistos or []
    u.onboarding_passo = onboarding_passo
    u.is_gestor_only = is_gestor_only
    u.is_admin_or_above = perfil in ("admin", "admin_global")
    u.is_supervisor_or_above = perfil in ("supervisor", "admin", "admin_global")
    u.get_id = lambda: "uid_ob"
    return u


# home route de cada perfil, usada pra parametrizar os testes de allowlist
_HOME_POR_PERFIL = [
    ("solicitante", "/"),
    ("supervisor", "/painel"),
    ("admin", "/admin"),
]


@pytest.mark.parametrize("perfil,home_route", _HOME_POR_PERFIL)
def test_template_inclui_onboarding_na_home_do_perfil_para_usuario_novo(
    client, app, perfil, home_route
):
    """Usuário novo (perfil nunca visto) vê o tour ao acessar a home do SEU perfil."""
    novo = _usuario_com_onboarding(perfil=perfil)
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=novo),
        patch("app.models_usuario.Usuario.get_by_id", return_value=novo),
        patch("app.routes.auth._dispositivo_confiavel", return_value=True),
        patch("app.routes.chamados.get_static_cached", return_value=[]),
        patch("app.routes.chamados._build_gate_subetapas", return_value={}),
        patch("app.routes.chamados.obter_total_por_contagem", return_value=0),
        patch("app.routes.dashboard.obter_contexto_admin", return_value={}),
        patch("app.routes.dashboard.get_static_cached", return_value=[]),
    ):
        client.post("/login", data={"email": "ob@test.com", "senha": "ok"})
        r = client.get(home_route)
    assert b"onboarding-root" in r.data


def test_template_omite_onboarding_fora_da_home_mesmo_para_usuario_novo(client, app):
    """Usuário novo NÃO vê o tour em página que não é a home dele (ex.: durante MFA/outras telas)."""
    novo = _usuario_com_onboarding(perfil="solicitante")
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=novo),
        patch("app.models_usuario.Usuario.get_by_id", return_value=novo),
        patch("app.routes.auth._dispositivo_confiavel", return_value=True),
        patch("app.routes.chamados.listar_meus_chamados", return_value=_MEUS_CHAMADOS_CTX_VAZIO),
        patch("app.routes.chamados.listar_chamados_como_observador", return_value=[]),
    ):
        client.post("/login", data={"email": "ob@test.com", "senha": "ok"})
        r = client.get("/meus-chamados")
    assert b"onboarding-root" not in r.data


def test_template_omite_onboarding_para_usuario_que_ja_fez(client, app):
    """HTML da home NÃO inclui #onboarding-root pra quem já viu o tour desse perfil."""
    veterano = _usuario_com_onboarding(
        perfil="solicitante", onboarding_perfis_vistos=["solicitante"]
    )
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=veterano),
        patch("app.models_usuario.Usuario.get_by_id", return_value=veterano),
        patch("app.routes.auth._dispositivo_confiavel", return_value=True),
        patch("app.routes.chamados.get_static_cached", return_value=[]),
        patch("app.routes.chamados._build_gate_subetapas", return_value={}),
        patch("app.routes.chamados.obter_total_por_contagem", return_value=0),
    ):
        client.post("/login", data={"email": "ob@test.com", "senha": "ok"})
        r = client.get("/")
    assert b"onboarding-root" not in r.data


# ─── data-lang emitido corretamente ──────────────────────────────────────────


@pytest.mark.parametrize(
    "lang,expected",
    [
        ("pt_BR", b'data-lang="pt_BR"'),
        ("en", b'data-lang="en"'),
        ("es", b'data-lang="es"'),
    ],
)
def test_template_emite_data_lang_correto(client, app, lang, expected):
    """O componente onboarding emite data-lang com o idioma da sessão."""
    novo = _usuario_com_onboarding()
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=novo),
        patch("app.models_usuario.Usuario.get_by_id", return_value=novo),
        patch("app.routes.auth._dispositivo_confiavel", return_value=True),
        patch("app.routes.chamados.get_static_cached", return_value=[]),
        patch("app.routes.chamados._build_gate_subetapas", return_value={}),
        patch("app.routes.chamados.obter_total_por_contagem", return_value=0),
    ):
        client.post("/login", data={"email": "ob@test.com", "senha": "ok"})
        r = client.get("/?lang=" + lang)
    assert expected in r.data


# ─── Rever tour (?onboarding_replay=1) — funciona em qualquer página ──────────


def test_template_inclui_onboarding_com_replay_mesmo_ja_concluido(client, app):
    """Com ?onboarding_replay=1, o tour aparece mesmo fora da home e mesmo já visto antes."""
    veterano = _usuario_com_onboarding(
        perfil="solicitante", onboarding_perfis_vistos=["solicitante"]
    )
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=veterano),
        patch("app.models_usuario.Usuario.get_by_id", return_value=veterano),
        patch("app.routes.auth._dispositivo_confiavel", return_value=True),
        patch("app.routes.chamados.listar_meus_chamados", return_value=_MEUS_CHAMADOS_CTX_VAZIO),
        patch("app.routes.chamados.listar_chamados_como_observador", return_value=[]),
    ):
        client.post("/login", data={"email": "ob@test.com", "senha": "ok"})
        r = client.get("/meus-chamados?onboarding_replay=1")
    assert b"onboarding-root" in r.data


def test_template_omite_onboarding_sem_replay_quando_ja_concluido(client, app):
    """Sem o query param, comportamento é preservado: tour continua omitido pra quem já viu."""
    veterano = _usuario_com_onboarding(
        perfil="solicitante", onboarding_perfis_vistos=["solicitante"]
    )
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=veterano),
        patch("app.models_usuario.Usuario.get_by_id", return_value=veterano),
        patch("app.routes.auth._dispositivo_confiavel", return_value=True),
        patch("app.routes.chamados.get_static_cached", return_value=[]),
        patch("app.routes.chamados._build_gate_subetapas", return_value={}),
        patch("app.routes.chamados.obter_total_por_contagem", return_value=0),
    ):
        client.post("/login", data={"email": "ob@test.com", "senha": "ok"})
        r = client.get("/")
    assert b"onboarding-root" not in r.data


def test_template_data_modo_replay_quando_query_param_presente(client, app):
    """data-modo="replay" é emitido quando ?onboarding_replay=1 está presente."""
    veterano = _usuario_com_onboarding(
        perfil="solicitante", onboarding_perfis_vistos=["solicitante"]
    )
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=veterano),
        patch("app.models_usuario.Usuario.get_by_id", return_value=veterano),
        patch("app.routes.auth._dispositivo_confiavel", return_value=True),
        patch("app.routes.chamados.listar_meus_chamados", return_value=_MEUS_CHAMADOS_CTX_VAZIO),
        patch("app.routes.chamados.listar_chamados_como_observador", return_value=[]),
    ):
        client.post("/login", data={"email": "ob@test.com", "senha": "ok"})
        r = client.get("/meus-chamados?onboarding_replay=1")
    assert b'data-modo="replay"' in r.data


def test_template_data_modo_inicial_no_primeiro_acesso(client, app):
    """data-modo="inicial" é emitido no fluxo normal de primeiro acesso, na home."""
    novo = _usuario_com_onboarding()
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=novo),
        patch("app.models_usuario.Usuario.get_by_id", return_value=novo),
        patch("app.routes.auth._dispositivo_confiavel", return_value=True),
        patch("app.routes.chamados.get_static_cached", return_value=[]),
        patch("app.routes.chamados._build_gate_subetapas", return_value={}),
        patch("app.routes.chamados.obter_total_por_contagem", return_value=0),
    ):
        client.post("/login", data={"email": "ob@test.com", "senha": "ok"})
        r = client.get("/")
    assert b'data-modo="inicial"' in r.data


def test_template_data_passo_zero_em_replay_ignora_passo_persistido(client, app):
    """Em replay, data-passo é sempre 0, mesmo que onboarding_passo persistido seja outro."""
    veterano = _usuario_com_onboarding(
        perfil="solicitante", onboarding_perfis_vistos=["solicitante"], onboarding_passo=4
    )
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=veterano),
        patch("app.models_usuario.Usuario.get_by_id", return_value=veterano),
        patch("app.routes.auth._dispositivo_confiavel", return_value=True),
        patch("app.routes.chamados.listar_meus_chamados", return_value=_MEUS_CHAMADOS_CTX_VAZIO),
        patch("app.routes.chamados.listar_chamados_como_observador", return_value=[]),
    ):
        client.post("/login", data={"email": "ob@test.com", "senha": "ok"})
        r = client.get("/meus-chamados?onboarding_replay=1")
    assert b'data-passo="0"' in r.data
