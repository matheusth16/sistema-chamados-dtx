"""Testes para contadores_uso.py — limites diários por usuário."""

from unittest.mock import MagicMock, patch


def _make_doc(exists=True, count=0, campo="relatorio_geracoes"):
    doc = MagicMock()
    doc.exists = exists
    doc.to_dict.return_value = {campo: count}
    return doc


def _mock_db(doc):
    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value.get.return_value = doc
    return mock_db


# ── verificar_e_incrementar_relatorio ─────────────────────────────────────────


def test_relatorio_limite_zero_retorna_true_sem_firestore():
    with patch("app.services.contadores_uso.db"):
        from app.services.contadores_uso import verificar_e_incrementar_relatorio

        ok, err = verificar_e_incrementar_relatorio("user1", 0)
    assert ok is True
    assert err is None


def test_relatorio_user_id_vazio_retorna_true():
    from app.services.contadores_uso import verificar_e_incrementar_relatorio

    ok, err = verificar_e_incrementar_relatorio("", 10)
    assert ok is True
    assert err is None


def test_relatorio_doc_nao_existe_cria_e_retorna_true():
    doc = _make_doc(exists=False)
    mock_db = _mock_db(doc)
    with patch("app.services.contadores_uso.db", mock_db):
        from app.services.contadores_uso import verificar_e_incrementar_relatorio

        ok, err = verificar_e_incrementar_relatorio("user1", 5)
    assert ok is True
    assert err is None
    mock_db.collection.return_value.document.return_value.set.assert_called_once()


def test_relatorio_doc_existe_abaixo_limite_incrementa():
    doc = _make_doc(exists=True, count=2, campo="relatorio_geracoes")
    mock_db = _mock_db(doc)
    with patch("app.services.contadores_uso.db", mock_db):
        from app.services.contadores_uso import verificar_e_incrementar_relatorio

        ok, err = verificar_e_incrementar_relatorio("user1", 5)
    assert ok is True
    assert err is None
    mock_db.collection.return_value.document.return_value.update.assert_called_once()


def test_relatorio_limite_atingido_retorna_false():
    doc = _make_doc(exists=True, count=5, campo="relatorio_geracoes")
    mock_db = _mock_db(doc)
    with patch("app.services.contadores_uso.db", mock_db):
        from app.services.contadores_uso import verificar_e_incrementar_relatorio

        ok, err = verificar_e_incrementar_relatorio("user1", 5)
    assert ok is False
    assert err is not None
    assert "limite" in (err or "").lower()


def test_relatorio_excecao_firestore_retorna_true_fail_open():
    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value.get.side_effect = Exception("timeout")
    with patch("app.services.contadores_uso.db", mock_db):
        from app.services.contadores_uso import verificar_e_incrementar_relatorio

        ok, err = verificar_e_incrementar_relatorio("user1", 5)
    assert ok is True
    assert err is None


# ── verificar_e_incrementar_export ────────────────────────────────────────────


def test_export_limite_zero_retorna_true():
    with patch("app.services.contadores_uso.db"):
        from app.services.contadores_uso import verificar_e_incrementar_export

        ok, err = verificar_e_incrementar_export("user2", 0)
    assert ok is True
    assert err is None


def test_export_user_id_vazio_retorna_true():
    from app.services.contadores_uso import verificar_e_incrementar_export

    ok, err = verificar_e_incrementar_export("", 10)
    assert ok is True
    assert err is None


def test_export_doc_nao_existe_cria_e_retorna_true():
    doc = _make_doc(exists=False)
    mock_db = _mock_db(doc)
    with patch("app.services.contadores_uso.db", mock_db):
        from app.services.contadores_uso import verificar_e_incrementar_export

        ok, err = verificar_e_incrementar_export("user2", 3)
    assert ok is True
    assert err is None


def test_export_doc_existe_abaixo_limite_incrementa():
    doc = _make_doc(exists=True, count=1, campo="export_excel_geracoes")
    mock_db = _mock_db(doc)
    with patch("app.services.contadores_uso.db", mock_db):
        from app.services.contadores_uso import verificar_e_incrementar_export

        ok, err = verificar_e_incrementar_export("user2", 5)
    assert ok is True
    assert err is None
    mock_db.collection.return_value.document.return_value.update.assert_called_once()


def test_export_limite_atingido_retorna_false():
    doc = _make_doc(exists=True, count=3, campo="export_excel_geracoes")
    mock_db = _mock_db(doc)
    with patch("app.services.contadores_uso.db", mock_db):
        from app.services.contadores_uso import verificar_e_incrementar_export

        ok, err = verificar_e_incrementar_export("user2", 3)
    assert ok is False
    assert err is not None


def test_export_excecao_firestore_retorna_true_fail_open():
    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value.get.side_effect = RuntimeError("err")
    with patch("app.services.contadores_uso.db", mock_db):
        from app.services.contadores_uso import verificar_e_incrementar_export

        ok, err = verificar_e_incrementar_export("user2", 5)
    assert ok is True
    assert err is None
