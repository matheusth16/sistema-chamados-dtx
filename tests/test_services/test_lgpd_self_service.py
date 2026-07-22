"""Testes: lgpd_self_service (autoatendimento LGPD — exportação e solicitação de exclusão)."""

from unittest.mock import MagicMock, patch

import pytest


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
    with patch("app.services.lgpd_self_service.db") as mock_db:
        yield mock_db


# ── exportar_dados_usuario ───────────────────────────────────────────────────


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
        "ch1", numero_chamado="0001", titulo="Impressora quebrada", categoria="TI", status="Aberto"
    )
    mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = [
        doc1
    ]
    usuario = _usuario_mock()

    resultado = exportar_dados_usuario(usuario)

    assert len(resultado["chamados_criados"]) == 1
    assert resultado["chamados_criados"][0]["id"] == "ch1"
    assert resultado["chamados_criados"][0]["numero_chamado"] == "0001"


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


# ── possui_solicitacao_exclusao_pendente ─────────────────────────────────────


def test_possui_solicitacao_pendente_retorna_true_quando_existe(mock_db):
    from app.services.lgpd_self_service import possui_solicitacao_exclusao_pendente

    doc = MagicMock()
    doc.to_dict.return_value = {"status": "pendente"}
    mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = [
        doc
    ]

    assert possui_solicitacao_exclusao_pendente("u1") is True


def test_possui_solicitacao_pendente_retorna_false_quando_so_ha_concluidas(mock_db):
    from app.services.lgpd_self_service import possui_solicitacao_exclusao_pendente

    doc = MagicMock()
    doc.to_dict.return_value = {"status": "concluida"}
    mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = [
        doc
    ]

    assert possui_solicitacao_exclusao_pendente("u1") is False


def test_possui_solicitacao_pendente_retorna_false_quando_vazio(mock_db):
    from app.services.lgpd_self_service import possui_solicitacao_exclusao_pendente

    mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = []

    assert possui_solicitacao_exclusao_pendente("u1") is False


def test_possui_solicitacao_pendente_retorna_false_quando_firestore_falha(mock_db):
    from app.services.lgpd_self_service import possui_solicitacao_exclusao_pendente

    mock_db.collection.return_value.where.return_value.limit.return_value.stream.side_effect = (
        Exception("err")
    )

    assert possui_solicitacao_exclusao_pendente("u1") is False


# ── solicitar_exclusao_propria ───────────────────────────────────────────────


def test_solicitar_exclusao_propria_sucesso(mock_db):
    from app.services.lgpd_self_service import solicitar_exclusao_propria

    mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = []
    usuario = _usuario_mock()

    with patch("app.services.lgpd_self_service.registrar_historico_usuario") as mock_hist:
        resultado = solicitar_exclusao_propria(usuario)

    assert resultado == {"sucesso": True}
    mock_db.collection.return_value.add.assert_called_once()
    payload = mock_db.collection.return_value.add.call_args[0][0]
    assert payload["usuario_id"] == "u1"
    assert payload["status"] == "pendente"
    assert payload["tipo"] == "exclusao"
    mock_hist.assert_called_once()
    assert mock_hist.call_args.kwargs["acao"] == "solicitacao_exclusao_lgpd"


def test_solicitar_exclusao_propria_bloqueia_pedido_duplicado(mock_db):
    from app.services.lgpd_self_service import solicitar_exclusao_propria

    doc = MagicMock()
    doc.to_dict.return_value = {"status": "pendente"}
    mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = [
        doc
    ]
    usuario = _usuario_mock()

    resultado = solicitar_exclusao_propria(usuario)

    assert resultado == {"sucesso": False, "erro_key": "lgpd_exclusion_request_already_pending"}
    mock_db.collection.return_value.add.assert_not_called()


def test_solicitar_exclusao_propria_retorna_erro_quando_firestore_falha(mock_db):
    from app.services.lgpd_self_service import solicitar_exclusao_propria

    mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = []
    mock_db.collection.return_value.add.side_effect = Exception("err")
    usuario = _usuario_mock()

    resultado = solicitar_exclusao_propria(usuario)

    assert resultado == {"sucesso": False, "erro_key": "internal_error_retry"}


# ── listar_usuarios_com_solicitacao_pendente (uso admin) ─────────────────────


def test_listar_usuarios_com_solicitacao_pendente_retorna_ids(mock_db):
    from app.services.lgpd_self_service import listar_usuarios_com_solicitacao_pendente

    doc1 = MagicMock()
    doc1.to_dict.return_value = {"usuario_id": "u1", "status": "pendente"}
    doc2 = MagicMock()
    doc2.to_dict.return_value = {"usuario_id": "u2", "status": "pendente"}
    mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = [
        doc1,
        doc2,
    ]

    resultado = listar_usuarios_com_solicitacao_pendente()

    assert resultado == {"u1", "u2"}


def test_listar_usuarios_com_solicitacao_pendente_retorna_vazio_quando_firestore_falha(mock_db):
    from app.services.lgpd_self_service import listar_usuarios_com_solicitacao_pendente

    mock_db.collection.return_value.where.return_value.limit.return_value.stream.side_effect = (
        Exception("err")
    )

    resultado = listar_usuarios_com_solicitacao_pendente()

    assert resultado == set()
