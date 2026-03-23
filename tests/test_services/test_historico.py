"""
Testes unitários do modelo Historico.
Cobre: from_dict, to_dict, save, get_by_chamado_id, data_acao_formatada.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

# ── Construção ─────────────────────────────────────────────────────────────────


def test_from_dict_cria_historico_com_campos_corretos():
    """from_dict cria Historico com todos os campos esperados."""
    from app.models_historico import Historico

    data = {
        "chamado_id": "ch1",
        "usuario_id": "u1",
        "usuario_nome": "Admin",
        "acao": "criacao",
        "campo_alterado": None,
        "valor_anterior": None,
        "valor_novo": None,
        "data_acao": None,
        "detalhe": "info extra",
    }
    with patch("app.models_historico.db"):
        h = Historico.from_dict(data, "hist_001")

    assert h.id == "hist_001"
    assert h.chamado_id == "ch1"
    assert h.acao == "criacao"
    assert h.detalhe == "info extra"


def test_to_dict_sem_detalhe_nao_inclui_campo():
    """to_dict sem detalhe não inclui a chave 'detalhe'."""
    from app.models_historico import Historico

    with patch("app.models_historico.db"):
        h = Historico(
            chamado_id="ch1",
            usuario_id="u1",
            usuario_nome="Admin",
            acao="criacao",
        )
        d = h.to_dict()

    assert "detalhe" not in d
    assert d["chamado_id"] == "ch1"


def test_to_dict_com_detalhe_inclui_campo():
    """to_dict com detalhe inclui a chave 'detalhe' no dicionário."""
    from app.models_historico import Historico

    with patch("app.models_historico.db"):
        h = Historico(
            chamado_id="ch1",
            usuario_id="u1",
            usuario_nome="Admin",
            acao="alteracao_dados",
            detalhe="arquivo.pdf",
        )
        d = h.to_dict()

    assert d["detalhe"] == "arquivo.pdf"


# ── save ───────────────────────────────────────────────────────────────────────


def test_save_chama_firestore_add_e_retorna_true():
    """save chama db.collection('historico').add() e retorna True."""
    from app.models_historico import Historico

    mock_ref = MagicMock()
    mock_ref.id = "hist_999"
    with patch("app.models_historico.db") as mock_db:
        mock_db.collection.return_value.add.return_value = (None, mock_ref)
        h = Historico(chamado_id="ch1", usuario_id="u1", usuario_nome="A", acao="criacao")
        result = h.save()

    assert result is True
    mock_db.collection.return_value.add.assert_called_once()


def test_save_retorna_false_quando_firestore_falha():
    """save retorna False quando Firestore lança exceção."""
    from app.models_historico import Historico

    with patch("app.models_historico.db") as mock_db:
        mock_db.collection.return_value.add.side_effect = Exception("timeout")
        h = Historico(chamado_id="ch1", usuario_id="u1", usuario_nome="A", acao="criacao")
        result = h.save()

    assert result is False


# ── get_by_chamado_id ──────────────────────────────────────────────────────────


def test_get_by_chamado_id_retorna_lista_ordenada():
    """get_by_chamado_id retorna lista de Historico para o chamado."""
    from app.models_historico import Historico

    doc = MagicMock()
    doc.id = "h1"
    doc.to_dict.return_value = {
        "chamado_id": "ch1",
        "usuario_id": "u1",
        "usuario_nome": "Admin",
        "acao": "criacao",
        "campo_alterado": None,
        "valor_anterior": None,
        "valor_novo": None,
        "data_acao": None,
    }

    with patch("app.models_historico.db") as mock_db:
        mock_query = MagicMock()
        mock_db.collection.return_value.where.return_value = mock_query
        mock_query.order_by.return_value.stream.return_value = [doc]
        result = Historico.get_by_chamado_id("ch1")

    assert len(result) == 1
    assert result[0].chamado_id == "ch1"


def test_get_by_chamado_id_fallback_sem_indice():
    """get_by_chamado_id usa fallback sem order_by quando índice não existe."""
    from app.models_historico import Historico

    doc = MagicMock()
    doc.id = "h1"
    doc.to_dict.return_value = {
        "chamado_id": "ch1",
        "usuario_id": "u1",
        "usuario_nome": "Admin",
        "acao": "criacao",
        "campo_alterado": None,
        "valor_anterior": None,
        "valor_novo": None,
        "data_acao": None,
    }

    with patch("app.models_historico.db") as mock_db:
        mock_query = MagicMock()
        mock_db.collection.return_value.where.return_value = mock_query
        # order_by falha com erro de índice
        mock_query.order_by.return_value.stream.side_effect = Exception("index building")
        # fallback sem order_by
        mock_query.stream.return_value = [doc]
        result = Historico.get_by_chamado_id("ch1")

    assert len(result) == 1


def test_get_by_chamado_id_retorna_vazio_quando_firestore_falha():
    """get_by_chamado_id retorna [] quando Firestore lança exceção não relacionada a índice."""
    from app.models_historico import Historico

    with patch("app.models_historico.db") as mock_db:
        mock_db.collection.return_value.where.side_effect = Exception("conexão perdida")
        result = Historico.get_by_chamado_id("ch1")

    assert result == []


# ── data_acao_formatada ────────────────────────────────────────────────────────


def test_data_acao_formatada_com_datetime():
    """data_acao_formatada retorna string formatada quando data_acao é datetime."""
    import pytz

    from app.models_historico import Historico

    dt = pytz.utc.localize(datetime(2026, 3, 20, 10, 30, 0))
    with patch("app.models_historico.db"):
        h = Historico(
            chamado_id="ch1", usuario_id="u1", usuario_nome="A", acao="criacao", data_acao=dt
        )
        result = h.data_acao_formatada()

    assert "2026" in result
    assert "/" in result


def test_data_acao_formatada_sem_data_retorna_traco():
    """data_acao_formatada retorna '-' quando data_acao é None."""

    from app.models_historico import Historico

    with patch("app.models_historico.db"):
        h = Historico(chamado_id="ch1", usuario_id="u1", usuario_nome="A", acao="criacao")
        # Forçar data_acao como None para o _converter_timestamp retornar None
        h.data_acao = None
        result = h.data_acao_formatada()

    assert result == "-"


# ── __repr__ ───────────────────────────────────────────────────────────────────


def test_repr_contem_chamado_id_e_acao():
    """__repr__ de Historico contém chamado_id e acao."""
    from app.models_historico import Historico

    with patch("app.models_historico.db"):
        h = Historico(chamado_id="ch99", usuario_id="u1", usuario_nome="A", acao="criacao")
        r = repr(h)

    assert "ch99" in r
    assert "criacao" in r
