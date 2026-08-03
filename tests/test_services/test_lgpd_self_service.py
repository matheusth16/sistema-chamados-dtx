"""Testes: lgpd_self_service (autoatendimento LGPD — exportação e solicitação
de exclusão).

Fase 2 — migração parcial: exportar_dados_usuario()/csv ainda consultam a
coleção `chamados` do Firestore (Chamado só migra no Marco 7, mock_db abaixo
continua valendo pra essas). As demais funções (solicitacoes_lgpd) já rodam
contra Postgres real (db_session)."""

from unittest.mock import MagicMock, patch

import pytest

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


def _chamado_doc(doc_id, **dados):
    doc = MagicMock()
    doc.id = doc_id
    doc.to_dict.return_value = dados
    return doc


@pytest.fixture
def mock_db():
    """Mock do Firestore usado só pelas queries de `chamados` (ainda não
    migrado — ver docstring do módulo)."""
    with patch("app.services.lgpd_self_service.db") as mock_db:
        yield mock_db


# ── exportar_dados_usuario (ainda Firestore — chamados não migrado) ─────────


def test_exportar_dados_usuario_inclui_dados_da_conta(mock_db):
    from app.services.lgpd_self_service import exportar_dados_usuario

    mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = []
    usuario = _usuario_mock()

    resultado = exportar_dados_usuario(usuario)

    assert resultado["conta"]["id"] == "u1"
    assert resultado["conta"]["nome"] == "Fulano"
    assert resultado["conta"]["email"] == "fulano@dtx.aero"
    assert resultado["conta"]["perfil"] == "solicitante"


def test_exportar_dados_usuario_inclui_chamados_criados(mock_db):
    from app.services.lgpd_self_service import exportar_dados_usuario

    doc1 = _chamado_doc(
        "ch1",
        numero_chamado="0001",
        tipo_solicitacao="Impressora quebrada",
        descricao="Impressora do 2o andar nao liga",
        categoria="TI",
        status="Aberto",
    )
    mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = [
        doc1
    ]
    usuario = _usuario_mock()

    resultado = exportar_dados_usuario(usuario)

    assert len(resultado["chamados_criados"]) == 1
    assert resultado["chamados_criados"][0]["id"] == "ch1"
    assert resultado["chamados_criados"][0]["numero_chamado"] == "0001"
    assert resultado["chamados_criados"][0]["tipo_solicitacao"] == "Impressora quebrada"
    assert resultado["chamados_criados"][0]["descricao"] == "Impressora do 2o andar nao liga"


def test_exportar_dados_usuario_csv_contem_secao_conta(mock_db):
    from app.services.lgpd_self_service import exportar_dados_usuario_csv

    mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = []
    usuario = _usuario_mock()

    csv_texto = exportar_dados_usuario_csv(usuario)

    assert "u1" in csv_texto
    assert "fulano@dtx.aero" in csv_texto
    assert "solicitante" in csv_texto


def test_exportar_dados_usuario_csv_contem_chamados(mock_db):
    from app.services.lgpd_self_service import exportar_dados_usuario_csv

    doc1 = _chamado_doc(
        "ch1",
        numero_chamado="0001",
        tipo_solicitacao="Impressora quebrada",
        descricao="Impressora do 2o andar nao liga",
        categoria="TI",
        status="Aberto",
    )
    mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = [
        doc1
    ]
    usuario = _usuario_mock()

    csv_texto = exportar_dados_usuario_csv(usuario)

    assert "0001" in csv_texto
    assert "Impressora quebrada" in csv_texto


def test_exportar_dados_usuario_csv_sanitiza_formula_injection(mock_db):
    """Título de chamado começando com '=' não deve virar fórmula executável no Excel."""
    from app.services.lgpd_self_service import exportar_dados_usuario_csv

    doc1 = _chamado_doc(
        "ch1",
        numero_chamado="0001",
        tipo_solicitacao="=cmd|'/c calc'!A1",
        descricao="normal",
        categoria="TI",
        status="Aberto",
    )
    mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = [
        doc1
    ]
    usuario = _usuario_mock()

    csv_texto = exportar_dados_usuario_csv(usuario)

    assert "'=cmd" in csv_texto
    assert "\n=cmd" not in csv_texto
    assert ",=cmd" not in csv_texto


def test_exportar_dados_usuario_filtra_apenas_chamados_do_proprio_usuario(mock_db):
    """A query deve filtrar por solicitante_id == usuario.id (não vazar dados de outros)."""
    from google.cloud.firestore_v1.base_query import FieldFilter

    from app.services.lgpd_self_service import exportar_dados_usuario

    mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = []
    usuario = _usuario_mock(uid="u42")

    exportar_dados_usuario(usuario)

    call_kwargs = mock_db.collection.return_value.where.call_args.kwargs
    filtro = call_kwargs["filter"]
    assert isinstance(filtro, FieldFilter)
    assert filtro.field_path == "solicitante_id"
    assert filtro.value == "u42"


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
