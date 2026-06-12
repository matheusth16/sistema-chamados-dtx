"""Testes do serviço Web Push (webpush_service)."""

from unittest.mock import MagicMock, patch

from app.services.webpush_service import enviar_webpush_usuario, obter_inscricoes, salvar_inscricao


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
