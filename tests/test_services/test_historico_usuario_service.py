"""Testes do serviço de histórico de ações administrativas sobre usuários."""

from unittest.mock import MagicMock, patch


def test_registrar_historico_usuario_grava_documento_com_campos_esperados():
    from app.services.historico_usuario_service import registrar_historico_usuario

    with patch("app.services.historico_usuario_service.db") as mock_db:
        mock_add = MagicMock(return_value=(None, MagicMock(id="hist_001")))
        mock_db.collection.return_value.add = mock_add

        resultado = registrar_historico_usuario(
            usuario_alvo_id="user_1",
            usuario_alvo_nome="Fulano",
            admin_id="admin_1",
            admin_nome="Admin Root",
            acao="criacao",
            detalhe="perfil=solicitante",
        )

    assert resultado is True
    mock_db.collection.assert_called_once_with("historico_usuarios")
    payload = mock_add.call_args[0][0]
    assert payload["usuario_alvo_id"] == "user_1"
    assert payload["usuario_alvo_nome"] == "Fulano"
    assert payload["admin_id"] == "admin_1"
    assert payload["admin_nome"] == "Admin Root"
    assert payload["acao"] == "criacao"
    assert payload["detalhe"] == "perfil=solicitante"
    assert "data_acao" in payload


def test_registrar_historico_usuario_sem_detalhe_nao_inclui_campo():
    from app.services.historico_usuario_service import registrar_historico_usuario

    with patch("app.services.historico_usuario_service.db") as mock_db:
        mock_add = MagicMock(return_value=(None, MagicMock(id="hist_002")))
        mock_db.collection.return_value.add = mock_add

        registrar_historico_usuario(
            usuario_alvo_id="user_1",
            usuario_alvo_nome="Fulano",
            admin_id="admin_1",
            admin_nome="Admin Root",
            acao="desativacao",
        )

    payload = mock_add.call_args[0][0]
    assert "detalhe" not in payload


def test_registrar_historico_usuario_erro_firestore_retorna_false_sem_levantar():
    from app.services.historico_usuario_service import registrar_historico_usuario

    with patch("app.services.historico_usuario_service.db") as mock_db:
        mock_db.collection.return_value.add.side_effect = Exception("firestore indisponível")

        resultado = registrar_historico_usuario(
            usuario_alvo_id="user_1",
            usuario_alvo_nome="Fulano",
            admin_id="admin_1",
            admin_nome="Admin Root",
            acao="edicao",
        )

    assert resultado is False


def test_obter_historico_usuario_retorna_lista_ordenada_por_data_desc():
    from app.services.historico_usuario_service import obter_historico_usuario

    doc1 = MagicMock()
    doc1.id = "h1"
    doc1.to_dict.return_value = {
        "usuario_alvo_id": "user_1",
        "usuario_alvo_nome": "Fulano",
        "admin_id": "admin_1",
        "admin_nome": "Admin Root",
        "acao": "criacao",
        "data_acao": None,
    }

    with patch("app.services.historico_usuario_service.db") as mock_db:
        query = mock_db.collection.return_value.where.return_value
        query.order_by.return_value.stream.return_value = [doc1]

        resultado = obter_historico_usuario("user_1")

    assert len(resultado) == 1
    assert resultado[0]["acao"] == "criacao"
