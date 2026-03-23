"""
Testes unitários do serviço de notificações in-app (notifications_inapp.py).
Cobre: criar_notificacao, listar_para_usuario, contar_nao_lidas,
marcar_como_lida, marcar_todas_como_lidas.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

# ── criar_notificacao ──────────────────────────────────────────────────────────


def test_criar_notificacao_retorna_id_quando_firestore_ok():
    """criar_notificacao retorna o ID do documento criado quando Firestore responde OK."""
    from app.services.notifications_inapp import criar_notificacao

    mock_ref = MagicMock()
    mock_ref.id = "notif_abc123"
    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_db.collection.return_value.add.return_value = (None, mock_ref)
        result = criar_notificacao(
            "user1", "ch1", "CHM-001", "Novo chamado", "Descrição", "novo_chamado"
        )

    assert result == "notif_abc123"


def test_criar_notificacao_retorna_none_sem_chamado_id():
    """criar_notificacao retorna None quando chamado_id é vazio."""
    from app.services.notifications_inapp import criar_notificacao

    result = criar_notificacao("user1", "", "CHM-001", "Título", "Msg")
    assert result is None


def test_criar_notificacao_retorna_none_quando_firestore_falha():
    """criar_notificacao captura exceção do Firestore e retorna None."""
    from app.services.notifications_inapp import criar_notificacao

    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_db.collection.return_value.add.side_effect = Exception("Firestore down")
        result = criar_notificacao("user1", "ch1", "CHM-001", "Título", "Msg")

    assert result is None


# ── listar_para_usuario ────────────────────────────────────────────────────────


def test_listar_para_usuario_retorna_docs_ordenados_por_data():
    """listar_para_usuario retorna lista de dicts com campo data_criacao serializado."""
    from app.services.notifications_inapp import listar_para_usuario

    doc1 = MagicMock()
    doc1.id = "n1"
    doc1.to_dict.return_value = {
        "usuario_id": "u1",
        "chamado_id": "ch1",
        "numero_chamado": "CHM-001",
        "titulo": "Notif 1",
        "mensagem": "Mensagem 1",
        "tipo": "novo_chamado",
        "lida": False,
        "data_criacao": datetime(2026, 3, 20, 10, 0, 0),
    }

    doc2 = MagicMock()
    doc2.id = "n2"
    doc2.to_dict.return_value = {
        "usuario_id": "u1",
        "chamado_id": "ch2",
        "numero_chamado": "CHM-002",
        "titulo": "Notif 2",
        "mensagem": "Mensagem 2",
        "tipo": "novo_chamado",
        "lida": False,
        "data_criacao": datetime(2026, 3, 21, 10, 0, 0),
    }

    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_query = MagicMock()
        mock_db.collection.return_value.where.return_value = mock_query
        mock_query.limit.return_value.stream.return_value = [doc1, doc2]
        result = listar_para_usuario("u1")

    assert len(result) == 2
    # Mais recente primeiro
    assert result[0]["id"] == "n2"
    assert result[1]["id"] == "n1"


def test_listar_para_usuario_apenas_nao_lidas():
    """listar_para_usuario com apenas_nao_lidas=True adiciona filtro na query."""
    from app.services.notifications_inapp import listar_para_usuario

    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_query = MagicMock()
        mock_db.collection.return_value.where.return_value = mock_query
        mock_query.where.return_value = mock_query
        mock_query.limit.return_value.stream.return_value = []
        listar_para_usuario("u1", apenas_nao_lidas=True)

    # Verifica que .where foi chamado duas vezes (usuario_id + lida==False)
    assert mock_db.collection.return_value.where.call_count >= 1
    assert mock_query.where.call_count >= 1


def test_listar_para_usuario_retorna_vazio_quando_firestore_falha():
    """listar_para_usuario retorna [] quando Firestore lança exceção."""
    from app.services.notifications_inapp import listar_para_usuario

    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_db.collection.return_value.where.side_effect = Exception("timeout")
        result = listar_para_usuario("u1")

    assert result == []


def test_listar_para_usuario_serializa_data_isoformat():
    """listar_para_usuario serializa data_criacao datetime para string ISO."""
    from app.services.notifications_inapp import listar_para_usuario

    doc = MagicMock()
    doc.id = "n1"
    doc.to_dict.return_value = {
        "usuario_id": "u1",
        "chamado_id": "ch1",
        "numero_chamado": "CHM-001",
        "titulo": "T",
        "mensagem": "M",
        "tipo": "novo",
        "lida": False,
        "data_criacao": datetime(2026, 1, 1, 12, 0, 0),
    }

    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_query = MagicMock()
        mock_db.collection.return_value.where.return_value = mock_query
        mock_query.limit.return_value.stream.return_value = [doc]
        result = listar_para_usuario("u1")

    assert isinstance(result[0]["data_criacao"], str)
    assert "2026" in result[0]["data_criacao"]


# ── contar_nao_lidas ───────────────────────────────────────────────────────────


def test_contar_nao_lidas_retorna_valor_do_firestore():
    """contar_nao_lidas retorna o count retornado pelo Firestore."""
    from app.services.notifications_inapp import contar_nao_lidas

    mock_count_val = MagicMock()
    mock_count_val.value = 5
    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_query = MagicMock()
        mock_db.collection.return_value.where.return_value = mock_query
        mock_query.where.return_value = mock_query
        mock_query.count.return_value.get.return_value = [[mock_count_val]]
        result = contar_nao_lidas("u1")

    assert result == 5


def test_contar_nao_lidas_retorna_zero_quando_firestore_falha():
    """contar_nao_lidas retorna 0 quando Firestore lança exceção."""
    from app.services.notifications_inapp import contar_nao_lidas

    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_db.collection.return_value.where.side_effect = Exception("err")
        result = contar_nao_lidas("u1")

    assert result == 0


# ── marcar_como_lida ───────────────────────────────────────────────────────────


def test_marcar_como_lida_retorna_true_quando_pertence_ao_usuario():
    """marcar_como_lida retorna True quando doc existe e pertence ao usuário."""
    from app.services.notifications_inapp import marcar_como_lida

    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {"usuario_id": "u1"}

    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_ref
        mock_ref.get.return_value = mock_doc
        result = marcar_como_lida("notif1", "u1")

    assert result is True
    mock_ref.update.assert_called_once_with({"lida": True})


def test_marcar_como_lida_retorna_false_quando_nao_existe():
    """marcar_como_lida retorna False quando o documento não existe."""
    from app.services.notifications_inapp import marcar_como_lida

    mock_doc = MagicMock()
    mock_doc.exists = False

    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_ref
        mock_ref.get.return_value = mock_doc
        result = marcar_como_lida("notif1", "u1")

    assert result is False


def test_marcar_como_lida_retorna_false_quando_pertence_a_outro_usuario():
    """marcar_como_lida retorna False quando o doc pertence a outro usuário."""
    from app.services.notifications_inapp import marcar_como_lida

    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {"usuario_id": "outro_usuario"}

    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_ref
        mock_ref.get.return_value = mock_doc
        result = marcar_como_lida("notif1", "u1")

    assert result is False


def test_marcar_como_lida_retorna_false_quando_firestore_falha():
    """marcar_como_lida retorna False quando Firestore lança exceção."""
    from app.services.notifications_inapp import marcar_como_lida

    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.side_effect = Exception("err")
        result = marcar_como_lida("notif1", "u1")

    assert result is False


# ── marcar_todas_como_lidas ────────────────────────────────────────────────────


def test_marcar_todas_como_lidas_retorna_contagem():
    """marcar_todas_como_lidas retorna a quantidade de notificações marcadas."""
    from app.services.notifications_inapp import marcar_todas_como_lidas

    doc1 = MagicMock()
    doc2 = MagicMock()

    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_query = MagicMock()
        mock_db.collection.return_value.where.return_value = mock_query
        mock_query.where.return_value = mock_query
        mock_query.stream.return_value = [doc1, doc2]
        mock_batch = MagicMock()
        mock_db.batch.return_value = mock_batch
        result = marcar_todas_como_lidas("u1")

    assert result == 2
    mock_batch.commit.assert_called()


def test_marcar_todas_como_lidas_retorna_zero_sem_notificacoes():
    """marcar_todas_como_lidas retorna 0 quando não há notificações não lidas."""
    from app.services.notifications_inapp import marcar_todas_como_lidas

    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_query = MagicMock()
        mock_db.collection.return_value.where.return_value = mock_query
        mock_query.where.return_value = mock_query
        mock_query.stream.return_value = []
        result = marcar_todas_como_lidas("u1")

    assert result == 0


def test_marcar_todas_como_lidas_retorna_zero_quando_firestore_falha():
    """marcar_todas_como_lidas retorna 0 quando Firestore lança exceção."""
    from app.services.notifications_inapp import marcar_todas_como_lidas

    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_db.collection.return_value.where.side_effect = Exception("err")
        result = marcar_todas_como_lidas("u1")

    assert result == 0
