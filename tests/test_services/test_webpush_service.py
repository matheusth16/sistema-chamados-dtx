"""Testes do serviço Web Push (webpush_service)."""

import logging
from unittest.mock import MagicMock, patch

from app.services.webpush_service import (
    MAX_INSCRICOES,
    enviar_webpush_usuario,
    obter_inscricoes,
    salvar_inscricao,
)


def test_salvar_inscricao_sem_usuario_id_retorna_false():
    """Sem usuario_id, retorna False."""
    assert salvar_inscricao("", {"endpoint": "https://push.example.com"}) is False
    assert salvar_inscricao(None, {"endpoint": "https://push.example.com"}) is False


def test_salvar_inscricao_sem_endpoint_retorna_false():
    """Sem endpoint na subscription, retorna False."""
    assert salvar_inscricao("u1", {}) is False
    assert salvar_inscricao("u1", {"keys": {}}) is False


def test_salvar_inscricao_com_dados_chama_firestore():
    """Com usuario_id e endpoint, chama db.collection().add()."""
    mock_db = MagicMock()
    mock_add = MagicMock()
    mock_db.collection.return_value.add = mock_add
    with (
        patch("app.services.webpush_service.db", mock_db),
        patch("app.services.webpush_service.firestore") as mock_fs,
    ):
        mock_fs.SERVER_TIMESTAMP = "SERVER_TIMESTAMP"
        result = salvar_inscricao(
            "u1",
            {
                "endpoint": "https://push.example.com/send/abc",
                "keys": {"p256dh": "k1", "auth": "k2"},
            },
        )
    assert result is True
    mock_add.assert_called_once()
    call_args = mock_add.call_args[0][0]
    assert call_args["usuario_id"] == "u1"
    assert call_args["endpoint"] == "https://push.example.com/send/abc"


def test_obter_inscricoes_sem_usuario_retorna_lista_vazia():
    """Sem usuario_id, retorna lista vazia."""
    assert obter_inscricoes("") == []
    assert obter_inscricoes(None) == []


def test_obter_inscricoes_com_usuario_retorna_lista(app):
    """Com usuario_id, consulta Firestore e retorna lista de subscriptions."""
    mock_stream = MagicMock(return_value=[])
    mock_db = MagicMock()
    mock_db.collection.return_value.where.return_value.stream = mock_stream
    with patch("app.services.webpush_service.db", mock_db):
        result = obter_inscricoes("u1")
    assert result == []


def test_enviar_webpush_usuario_sem_vapid_retorna_zero(app):
    """Sem VAPID_PRIVATE_KEY configurada, retorna 0 envios."""
    app.config["VAPID_PRIVATE_KEY"] = ""
    with app.app_context(), patch("app.services.webpush_service.obter_inscricoes", return_value=[]):
        n = enviar_webpush_usuario("u1", "Título", "Corpo")
    assert n == 0


def test_salvar_inscricao_deduplica_endpoint_existente():
    """Se o endpoint já existe para o usuário, atualiza (set merge) em vez de .add()."""
    mock_db = MagicMock()
    mock_add = MagicMock()
    mock_db.collection.return_value.add = mock_add

    doc_existente = MagicMock()
    query = mock_db.collection.return_value.where.return_value.where.return_value.limit.return_value
    query.stream.return_value = [doc_existente]

    with (
        patch("app.services.webpush_service.db", mock_db),
        patch("app.services.webpush_service.firestore") as mock_fs,
    ):
        mock_fs.SERVER_TIMESTAMP = "SERVER_TIMESTAMP"
        result = salvar_inscricao(
            "u1",
            {
                "endpoint": "https://push.example.com/send/abc",
                "keys": {"p256dh": "k1", "auth": "k2"},
            },
        )

    assert result is True
    mock_add.assert_not_called()
    doc_existente.reference.set.assert_called_once()
    set_args = doc_existente.reference.set.call_args
    assert set_args[0][0]["p256dh"] == "k1"
    assert set_args[1]["merge"] is True


def test_enviar_webpush_deleta_subscricao_expirada(app):
    """Erro 410 Gone do servidor push remove a inscrição expirada do Firestore."""
    import pywebpush

    app.config["VAPID_PRIVATE_KEY"] = "chave-privada"
    fake_response = MagicMock()
    fake_response.status_code = 410
    sub = {
        "doc_id": "doc123",
        "endpoint": "https://push.example.com/send/abc",
        "keys": {"p256dh": "k1", "auth": "k2"},
    }
    mock_db = MagicMock()
    with (
        app.app_context(),
        patch("app.services.webpush_service.obter_inscricoes", return_value=[sub]),
        patch("app.services.webpush_service.db", mock_db),
        patch.object(
            pywebpush,
            "webpush",
            side_effect=pywebpush.WebPushException("gone", response=fake_response),
        ),
    ):
        n = enviar_webpush_usuario("u1", "Título", "Corpo", url="https://x")

    assert n == 0
    mock_db.collection.return_value.document.assert_called_once_with("doc123")
    mock_db.collection.return_value.document.return_value.delete.assert_called_once()


def test_enviar_webpush_le_chave_via_config_get(app):
    """A chave privada VAPID deve ser lida via config.get (não getattr)."""
    import pywebpush

    app.config["VAPID_PRIVATE_KEY"] = "chave-privada"
    sub = {
        "doc_id": "doc1",
        "endpoint": "https://push.example.com/send/abc",
        "keys": {"p256dh": "k1", "auth": "k2"},
    }
    with (
        app.app_context(),
        patch("app.services.webpush_service.obter_inscricoes", return_value=[sub]),
        patch.object(pywebpush, "webpush") as mock_webpush,
    ):
        n = enviar_webpush_usuario("u1", "Título", "Corpo")

    assert n == 1
    mock_webpush.assert_called_once()


# ── S4-04: Limite de inscrições WebPush ──────────────────────────────────────


def test_obter_inscricoes_aplica_limite_maximo():
    """obter_inscricoes deve chamar .limit(MAX_INSCRICOES) na query."""
    mock_doc = MagicMock()
    mock_doc.to_dict.return_value = {
        "endpoint": "https://push.example.com/x",
        "p256dh": "k1",
        "auth": "k2",
    }

    mock_db = MagicMock()
    mock_col = mock_db.collection.return_value
    mock_col.where.return_value = mock_col
    mock_col.limit.return_value = mock_col
    mock_col.stream.return_value = iter([mock_doc] * MAX_INSCRICOES)

    with patch("app.services.webpush_service.db", mock_db):
        result = obter_inscricoes("u1")

    mock_col.limit.assert_called_with(MAX_INSCRICOES)
    assert len(result) == MAX_INSCRICOES


# ── Caminhos de erro / exceção ────────────────────────────────────────────────


def test_enviar_webpush_sem_app_context_retorna_zero():
    """Fora de app context, enviar_webpush_usuario captura RuntimeError e retorna 0."""
    n = enviar_webpush_usuario("u1", "Título", "Corpo")
    assert n == 0


def test_enviar_webpush_pywebpush_nao_instalado_retorna_zero(app):
    """Quando pywebpush não está disponível (ImportError), retorna 0."""
    import sys

    app.config["VAPID_PRIVATE_KEY"] = "chave-privada"
    with (
        app.app_context(),
        patch("app.services.webpush_service.obter_inscricoes", return_value=[]),
        patch.dict(sys.modules, {"pywebpush": None}),
    ):
        n = enviar_webpush_usuario("u1", "Título", "Corpo")
    assert n == 0


def test_enviar_webpush_excecao_generica_continua_outros_envios(app):
    """Exceção genérica em um dispositivo não interrompe envio para os demais."""
    import pywebpush

    app.config["VAPID_PRIVATE_KEY"] = "chave-privada"
    sub1 = {"doc_id": "d1", "endpoint": "https://x.com/1", "keys": {"p256dh": "k1", "auth": "a1"}}
    sub2 = {"doc_id": "d2", "endpoint": "https://x.com/2", "keys": {"p256dh": "k2", "auth": "a2"}}

    call_count = [0]

    def _fake_webpush(**kw):
        if kw["subscription_info"]["endpoint"].endswith("1"):
            raise Exception("generic device error")
        call_count[0] += 1

    with (
        app.app_context(),
        patch("app.services.webpush_service.obter_inscricoes", return_value=[sub1, sub2]),
        patch.object(pywebpush, "webpush", side_effect=_fake_webpush),
    ):
        n = enviar_webpush_usuario("u1", "T", "B")

    assert n == 1


def test_salvar_inscricao_excecao_retorna_false():
    """Exceção no Firestore durante salvar_inscricao retorna False sem propagar."""
    mock_db = MagicMock()
    mock_db.collection.return_value.where.return_value.where.return_value.limit.return_value.stream.side_effect = Exception(
        "firestore error"
    )
    with patch("app.services.webpush_service.db", mock_db):
        result = salvar_inscricao(
            "u1",
            {
                "endpoint": "https://push.example.com/send/x",
                "keys": {"p256dh": "k1", "auth": "k2"},
            },
        )
    assert result is False


def test_obter_inscricoes_excecao_retorna_lista_vazia():
    """Exceção no Firestore durante obter_inscricoes retorna lista vazia."""
    mock_db = MagicMock()
    mock_db.collection.return_value.where.return_value.limit.return_value.stream.side_effect = (
        Exception("firestore unavailable")
    )
    with patch("app.services.webpush_service.db", mock_db):
        result = obter_inscricoes("u1")
    assert result == []


def test_deletar_subscricao_sem_doc_id_nao_acessa_firestore():
    """_deletar_subscricao com doc_id vazio retorna sem chamar Firestore."""
    from app.services.webpush_service import _deletar_subscricao

    mock_db = MagicMock()
    with patch("app.services.webpush_service.db", mock_db):
        _deletar_subscricao("")
        _deletar_subscricao(None)
    mock_db.collection.assert_not_called()


def test_deletar_subscricao_excecao_nao_propaga():
    """_deletar_subscricao com exceção no delete não propaga o erro."""
    from app.services.webpush_service import _deletar_subscricao

    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value.delete.side_effect = Exception(
        "firestore error"
    )
    with patch("app.services.webpush_service.db", mock_db):
        _deletar_subscricao("doc_abc")  # não deve levantar
    mock_db.collection.return_value.document.assert_called_once_with("doc_abc")


def test_obter_inscricoes_loga_warning_ao_atingir_limite(caplog):
    """obter_inscricoes emite warning quando o limite de inscrições é atingido."""
    mock_doc = MagicMock()
    mock_doc.to_dict.return_value = {
        "endpoint": "https://push.example.com/x",
        "p256dh": "k1",
        "auth": "k2",
    }

    mock_db = MagicMock()
    mock_col = mock_db.collection.return_value
    mock_col.where.return_value = mock_col
    mock_col.limit.return_value = mock_col
    mock_col.stream.return_value = iter([mock_doc] * MAX_INSCRICOES)

    with (
        patch("app.services.webpush_service.db", mock_db),
        caplog.at_level(logging.WARNING, logger="app.services.webpush_service"),
    ):
        obter_inscricoes("u1")

    assert "limite" in caplog.text.lower()
