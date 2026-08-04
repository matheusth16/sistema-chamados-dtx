"""Testes: lgpd_self_service (autoatendimento LGPD — exportação e solicitação
de exclusão).

Fase 2, Marco 10: exportar_dados_usuario()/csv rodam contra Postgres real
(db_session) via tests.factories.make_chamado — assim como as demais
funções deste módulo (solicitacoes_lgpd)."""

from unittest.mock import MagicMock, patch

import pytest

from tests.factories import make_chamado

pytestmark = pytest.mark.usefixtures("db_session")


def _usuario_mock(uid="u1", nome="Fulano", email="fulano@dtx.aero", perfil="solicitante"):
    u = MagicMock()
    u.id = uid
    u.nome = nome
    u.email = email
    u.perfil = perfil
    u.areas = ["TI"]
    u.nivel_gestao = None
    u.auth_provider = "local"
    u.mfa_enabled = True
    u.password_changed_at = None
    return u


# ── exportar_dados_usuario (Postgres real) ────────────────────────────────────


def test_exportar_dados_usuario_inclui_dados_da_conta():
    from app.services.lgpd_self_service import exportar_dados_usuario

    usuario = _usuario_mock()

    resultado = exportar_dados_usuario(usuario)

    assert resultado["conta"]["id"] == "u1"
    assert resultado["conta"]["nome"] == "Fulano"
    assert resultado["conta"]["email"] == "fulano@dtx.aero"
    assert resultado["conta"]["perfil"] == "solicitante"
    assert resultado["chamados_criados"] == []


def test_exportar_dados_usuario_inclui_chamados_criados():
    from app.services.lgpd_self_service import exportar_dados_usuario

    usuario = _usuario_mock(uid="u1")
    chamado = make_chamado(
        solicitante_id="u1",
        numero_chamado="0001",
        tipo_solicitacao="Impressora quebrada",
        descricao="Impressora do 2o andar nao liga",
        categoria="TI",
        status="Aberto",
    )

    resultado = exportar_dados_usuario(usuario)

    assert len(resultado["chamados_criados"]) == 1
    assert resultado["chamados_criados"][0]["id"] == chamado.id
    assert resultado["chamados_criados"][0]["numero_chamado"] == "0001"
    assert resultado["chamados_criados"][0]["tipo_solicitacao"] == "Impressora quebrada"
    assert resultado["chamados_criados"][0]["descricao"] == "Impressora do 2o andar nao liga"
    assert resultado["chamados_criados"][0]["data_criacao"] is not None


def test_exportar_dados_usuario_csv_contem_secao_conta():
    from app.services.lgpd_self_service import exportar_dados_usuario_csv

    usuario = _usuario_mock()

    csv_texto = exportar_dados_usuario_csv(usuario)

    assert "u1" in csv_texto
    assert "fulano@dtx.aero" in csv_texto
    assert "solicitante" in csv_texto


def test_exportar_dados_usuario_csv_contem_chamados():
    from app.services.lgpd_self_service import exportar_dados_usuario_csv

    make_chamado(
        solicitante_id="u1",
        numero_chamado="0001",
        tipo_solicitacao="Impressora quebrada",
        descricao="Impressora do 2o andar nao liga",
        categoria="TI",
        status="Aberto",
    )
    usuario = _usuario_mock(uid="u1")

    csv_texto = exportar_dados_usuario_csv(usuario)

    assert "0001" in csv_texto
    assert "Impressora quebrada" in csv_texto


def test_exportar_dados_usuario_csv_sanitiza_formula_injection():
    """Título de chamado começando com '=' não deve virar fórmula executável no Excel."""
    from app.services.lgpd_self_service import exportar_dados_usuario_csv

    make_chamado(
        solicitante_id="u1",
        numero_chamado="0001",
        tipo_solicitacao="=cmd|'/c calc'!A1",
        descricao="normal",
        categoria="TI",
        status="Aberto",
    )
    usuario = _usuario_mock(uid="u1")

    csv_texto = exportar_dados_usuario_csv(usuario)

    assert "'=cmd" in csv_texto
    assert "\n=cmd" not in csv_texto
    assert ",=cmd" not in csv_texto


def test_exportar_dados_usuario_filtra_apenas_chamados_do_proprio_usuario():
    """A exportação não deve vazar chamados de outros usuários."""
    from app.services.lgpd_self_service import exportar_dados_usuario

    make_chamado(solicitante_id="outro_usuario", numero_chamado="9999")
    usuario = _usuario_mock(uid="u42")

    resultado = exportar_dados_usuario(usuario)

    assert resultado["chamados_criados"] == []


# ── possui_solicitacao_exclusao_pendente (Postgres real) ─────────────────────


def test_possui_solicitacao_pendente_retorna_true_quando_existe(app):
    from app.services.lgpd_self_service import (
        possui_solicitacao_exclusao_pendente,
        solicitar_exclusao_propria,
    )

    with patch("app.services.lgpd_self_service.registrar_historico_usuario"):
        solicitar_exclusao_propria(_usuario_mock(uid="u1"))

    assert possui_solicitacao_exclusao_pendente("u1") is True


def test_possui_solicitacao_pendente_retorna_false_quando_vazio(app):
    from app.services.lgpd_self_service import possui_solicitacao_exclusao_pendente

    assert possui_solicitacao_exclusao_pendente("usuario_sem_solicitacao") is False


def test_possui_solicitacao_pendente_retorna_false_quando_banco_falha(app, monkeypatch):
    from app.services import lgpd_self_service

    def _explode():
        raise RuntimeError("banco indisponível")

    monkeypatch.setattr(lgpd_self_service.db_module, "SessionLocal", _explode)

    assert lgpd_self_service.possui_solicitacao_exclusao_pendente("u1") is False


# ── solicitar_exclusao_propria (Postgres real) ───────────────────────────────


def test_solicitar_exclusao_propria_sucesso(app):
    from app.services.lgpd_self_service import solicitar_exclusao_propria

    usuario = _usuario_mock()

    with patch("app.services.lgpd_self_service.registrar_historico_usuario") as mock_hist:
        resultado = solicitar_exclusao_propria(usuario)

    assert resultado == {"sucesso": True}
    mock_hist.assert_called_once()
    assert mock_hist.call_args.kwargs["acao"] == "solicitacao_exclusao_lgpd"


def test_solicitar_exclusao_propria_bloqueia_pedido_duplicado(app):
    from app.services.lgpd_self_service import solicitar_exclusao_propria

    usuario = _usuario_mock()
    with patch("app.services.lgpd_self_service.registrar_historico_usuario"):
        solicitar_exclusao_propria(usuario)

    resultado = solicitar_exclusao_propria(usuario)

    assert resultado == {"sucesso": False, "erro_key": "lgpd_exclusion_request_already_pending"}


def test_solicitar_exclusao_propria_retorna_erro_quando_banco_falha(app, monkeypatch):
    from app.services import lgpd_self_service

    def _explode():
        raise RuntimeError("banco indisponível")

    monkeypatch.setattr(
        lgpd_self_service, "possui_solicitacao_exclusao_pendente", lambda _uid: False
    )
    monkeypatch.setattr(lgpd_self_service.db_module, "SessionLocal", _explode)

    resultado = lgpd_self_service.solicitar_exclusao_propria(_usuario_mock())

    assert resultado == {"sucesso": False, "erro_key": "internal_error_retry"}


# ── listar_usuarios_com_solicitacao_pendente (uso admin, Postgres real) ──────


def test_listar_usuarios_com_solicitacao_pendente_retorna_ids(app):
    from app.services.lgpd_self_service import (
        listar_usuarios_com_solicitacao_pendente,
        solicitar_exclusao_propria,
    )

    with patch("app.services.lgpd_self_service.registrar_historico_usuario"):
        solicitar_exclusao_propria(_usuario_mock(uid="u1"))
        solicitar_exclusao_propria(_usuario_mock(uid="u2"))

    resultado = listar_usuarios_com_solicitacao_pendente()

    assert resultado == {"u1", "u2"}


def test_listar_usuarios_com_solicitacao_pendente_retorna_vazio_quando_banco_falha(
    app, monkeypatch
):
    from app.services import lgpd_self_service

    def _explode():
        raise RuntimeError("banco indisponível")

    monkeypatch.setattr(lgpd_self_service.db_module, "SessionLocal", _explode)

    assert lgpd_self_service.listar_usuarios_com_solicitacao_pendente() == set()


# ── resolver_solicitacoes_exclusao_pendentes (Postgres real) ─────────────────


def test_resolver_solicitacoes_marca_pendente_como_concluida(app):
    from app.services.lgpd_self_service import (
        resolver_solicitacoes_exclusao_pendentes,
        solicitar_exclusao_propria,
    )

    with patch("app.services.lgpd_self_service.registrar_historico_usuario"):
        solicitar_exclusao_propria(_usuario_mock(uid="u1"))

    resultado = resolver_solicitacoes_exclusao_pendentes("u1", admin_id="a1", admin_nome="Admin")

    assert resultado == 1


def test_resolver_solicitacoes_ignora_as_ja_concluidas(app):
    from app.services.lgpd_self_service import (
        resolver_solicitacoes_exclusao_pendentes,
        solicitar_exclusao_propria,
    )

    with patch("app.services.lgpd_self_service.registrar_historico_usuario"):
        solicitar_exclusao_propria(_usuario_mock(uid="u1"))
    resolver_solicitacoes_exclusao_pendentes("u1", admin_id="a1", admin_nome="Admin")

    resultado = resolver_solicitacoes_exclusao_pendentes("u1", admin_id="a1", admin_nome="Admin")

    assert resultado == 0


def test_resolver_solicitacoes_retorna_zero_quando_nao_ha_pedido(app):
    from app.services.lgpd_self_service import resolver_solicitacoes_exclusao_pendentes

    resultado = resolver_solicitacoes_exclusao_pendentes(
        "usuario_sem_pedido", admin_id="a1", admin_nome="Admin"
    )

    assert resultado == 0


def test_resolver_solicitacoes_retorna_zero_quando_banco_falha(app, monkeypatch):
    from app.services import lgpd_self_service

    def _explode():
        raise RuntimeError("banco indisponível")

    monkeypatch.setattr(lgpd_self_service.db_module, "SessionLocal", _explode)

    resultado = lgpd_self_service.resolver_solicitacoes_exclusao_pendentes(
        "u1", admin_id="a1", admin_nome="Admin"
    )

    assert resultado == 0
