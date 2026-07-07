"""Testes para contadores_uso.py — limites diários por usuário."""

from unittest.mock import MagicMock, patch


def _make_doc(exists=True, count=0, campo="relatorio_geracoes"):
    doc = MagicMock()
    doc.exists = exists
    doc.to_dict.return_value = {campo: count}
    return doc


def _mock_db(doc):
    """Cria mock_db com doc_ref.get() retornando doc (com ou sem transaction=)."""
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
    # Com transação: set() é chamado no objeto transaction, não no doc_ref diretamente
    mock_db.transaction.return_value.set.assert_called_once()


def test_relatorio_doc_existe_abaixo_limite_incrementa():
    doc = _make_doc(exists=True, count=2, campo="relatorio_geracoes")
    mock_db = _mock_db(doc)
    with patch("app.services.contadores_uso.db", mock_db):
        from app.services.contadores_uso import verificar_e_incrementar_relatorio

        ok, err = verificar_e_incrementar_relatorio("user1", 5)
    assert ok is True
    assert err is None
    # Com transação: update() é chamado no objeto transaction, não no doc_ref diretamente
    mock_db.transaction.return_value.update.assert_called_once()


def test_relatorio_limite_atingido_retorna_false():
    doc = _make_doc(exists=True, count=5, campo="relatorio_geracoes")
    mock_db = _mock_db(doc)
    with patch("app.services.contadores_uso.db", mock_db):
        from app.services.contadores_uso import verificar_e_incrementar_relatorio

        ok, err = verificar_e_incrementar_relatorio("user1", 5)
    assert ok is False
    assert err is not None
    assert "limit" in (err or "").lower()


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
    mock_db.transaction.return_value.set.assert_called_once()


def test_export_doc_existe_abaixo_limite_incrementa():
    doc = _make_doc(exists=True, count=1, campo="export_excel_geracoes")
    mock_db = _mock_db(doc)
    with patch("app.services.contadores_uso.db", mock_db):
        from app.services.contadores_uso import verificar_e_incrementar_export

        ok, err = verificar_e_incrementar_export("user2", 5)
    assert ok is True
    assert err is None
    mock_db.transaction.return_value.update.assert_called_once()


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


# ── Testes de transação (S2-01) ───────────────────────────────────────────────


def test_relatorio_usa_transacao_firestore():
    """verificar_e_incrementar_relatorio usa db.transaction() para atomicidade."""
    doc = _make_doc(exists=True, count=2, campo="relatorio_geracoes")
    mock_db = _mock_db(doc)
    with patch("app.services.contadores_uso.db", mock_db):
        from app.services.contadores_uso import verificar_e_incrementar_relatorio

        verificar_e_incrementar_relatorio("user1", 5)
    mock_db.transaction.assert_called()


def test_export_usa_transacao_firestore():
    """verificar_e_incrementar_export usa db.transaction() para atomicidade."""
    doc = _make_doc(exists=True, count=1, campo="export_excel_geracoes")
    mock_db = _mock_db(doc)
    with patch("app.services.contadores_uso.db", mock_db):
        from app.services.contadores_uso import verificar_e_incrementar_export

        verificar_e_incrementar_export("user2", 5)
    mock_db.transaction.assert_called()


def test_relatorio_concorrencia_nao_ultrapassa_limite():
    """10 chamadas sequenciais com limite=5: exatamente 5 aprovadas, 5 rejeitadas.

    Testa a lógica de limite no mock da transação. Concorrência real é garantida
    pela transação Firestore (@firestore.transactional) em produção.
    """
    import threading

    limite = 5
    num_threads = 10

    # Contador compartilhado simulando o documento Firestore (com lock para thread safety do mock)
    counter = [0]
    counter_lock = threading.Lock()

    def mock_get(transaction=None):
        doc = MagicMock()
        with counter_lock:
            doc.to_dict.return_value = {"relatorio_geracoes": counter[0]}
            doc.exists = True
        return doc

    # A transação serializa o ciclo get+check+update via lock (simula Firestore transaction)
    serial_lock = threading.Lock()

    def make_tx():
        tx = MagicMock()

        def tx_update(doc_ref, update_dict):
            with counter_lock:
                counter[0] += 1

        tx.update.side_effect = tx_update
        return tx

    mock_db = MagicMock()
    mock_db.transaction.side_effect = make_tx
    mock_db.collection.return_value.document.return_value.get.side_effect = mock_get

    results = []
    results_lock = threading.Lock()

    def run():
        # serial_lock serializa as chamadas para replicar o comportamento da transação Firestore
        with serial_lock:
            from app.services.contadores_uso import verificar_e_incrementar_relatorio

            ok, _ = verificar_e_incrementar_relatorio("user1", limite)
        with results_lock:
            results.append(ok)

    with patch("app.services.contadores_uso.db", mock_db):
        threads = [threading.Thread(target=run) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    aprovadas = sum(results)
    assert aprovadas == limite, (
        f"Esperado exatamente {limite} aprovadas com limite={limite}; obtido {aprovadas}"
    )
    assert sum(1 for r in results if not r) == num_threads - limite, "Rejeições incorretas"


def test_export_concorrencia_nao_ultrapassa_limite():
    """10 chamadas com limite=3: exatamente 3 aprovadas, 7 rejeitadas."""
    import threading

    limite = 3
    num_threads = 10

    counter = [0]
    counter_lock = threading.Lock()

    def mock_get(transaction=None):
        doc = MagicMock()
        with counter_lock:
            doc.to_dict.return_value = {"export_excel_geracoes": counter[0]}
            doc.exists = True
        return doc

    serial_lock = threading.Lock()

    def make_tx():
        tx = MagicMock()

        def tx_update(doc_ref, update_dict):
            with counter_lock:
                counter[0] += 1

        tx.update.side_effect = tx_update
        return tx

    mock_db = MagicMock()
    mock_db.transaction.side_effect = make_tx
    mock_db.collection.return_value.document.return_value.get.side_effect = mock_get

    results = []
    results_lock = threading.Lock()

    def run():
        with serial_lock:
            from app.services.contadores_uso import verificar_e_incrementar_export

            ok, _ = verificar_e_incrementar_export("user2", limite)
        with results_lock:
            results.append(ok)

    with patch("app.services.contadores_uso.db", mock_db):
        threads = [threading.Thread(target=run) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    aprovadas = sum(results)
    assert aprovadas == limite, (
        f"Esperado exatamente {limite} aprovadas com limite={limite}; obtido {aprovadas}"
    )


# ── F-29: Increment importado diretamente (sem fallback silencioso para None) ─


def test_increment_e_importado_diretamente_e_nao_none():
    """F-29: Increment deve ser a classe real de google.cloud.firestore_v1, não None.
    Remove fallback silencioso que transformava 'Increment' em None se unavailable,
    causando TypeError tardio ('NoneType' object is not callable) difícil de depurar."""
    from app.services import contadores_uso

    assert contadores_uso.Increment is not None, (
        "Increment foi definido como None pelo fallback silencioso — "
        "a importação direta deve falhar loudly se não disponível"
    )
    assert callable(contadores_uso.Increment), (
        "Increment deve ser chamável (a classe Increment do Firestore)"
    )


# ── F-31: limpar_contadores_antigos ──────────────────────────────────────────


def _make_old_doc(doc_id: str, data_str: str):
    """Cria mock de documento Firestore com id e campo data."""
    doc = MagicMock()
    doc.id = doc_id
    doc.to_dict.return_value = {"data": data_str}
    doc.reference = MagicMock()
    return doc


def test_limpar_contadores_dry_run_nao_faz_delete():
    """dry_run=True: conta docs antigos mas não chama batch.delete nem batch.commit."""

    from app.services.contadores_uso import limpar_contadores_antigos

    doc_antigo = _make_old_doc("user1_2020-01-01", "2020-01-01")

    mock_db = MagicMock()
    mock_db.collection.return_value.where.return_value.stream.return_value = iter([doc_antigo])

    with patch("app.services.contadores_uso.db", mock_db):
        resultado = limpar_contadores_antigos(dias=90, dry_run=True)

    assert resultado["dry_run"] is True
    assert resultado["removidos"] == 1
    # Nenhum batch.delete nem batch.commit deve ter sido chamado
    mock_db.batch.assert_not_called()


def test_limpar_contadores_apply_deleta_docs_antigos():
    """dry_run=False: chama batch.delete e batch.commit para docs antigos."""
    from app.services.contadores_uso import limpar_contadores_antigos

    doc_antigo = _make_old_doc("user1_2020-01-01", "2020-01-01")

    mock_batch = MagicMock()
    mock_db = MagicMock()
    mock_db.collection.return_value.where.return_value.stream.return_value = iter([doc_antigo])
    mock_db.batch.return_value = mock_batch

    with patch("app.services.contadores_uso.db", mock_db):
        resultado = limpar_contadores_antigos(dias=90, dry_run=False)

    assert resultado["dry_run"] is False
    assert resultado["removidos"] >= 1
    mock_batch.delete.assert_called_once_with(doc_antigo.reference)
    mock_batch.commit.assert_called_once()


def test_limpar_contadores_sem_docs_antigos_retorna_zero():
    """Sem docs antigos: removidos=0 independente de dry_run."""
    from app.services.contadores_uso import limpar_contadores_antigos

    mock_db = MagicMock()
    mock_db.collection.return_value.where.return_value.stream.return_value = iter([])

    with patch("app.services.contadores_uso.db", mock_db):
        resultado = limpar_contadores_antigos(dias=90, dry_run=False)

    assert resultado["removidos"] == 0
    mock_db.batch.assert_not_called()


def test_limpar_contadores_pagina_em_lotes_de_500():
    """501 docs antigos → dois commits (lote de 500 + lote de 1)."""
    from app.services.contadores_uso import limpar_contadores_antigos

    docs_antigos = [_make_old_doc(f"user_{i}_2020-01-01", "2020-01-01") for i in range(501)]

    mock_batch = MagicMock()
    mock_db = MagicMock()
    mock_db.collection.return_value.where.return_value.stream.return_value = iter(docs_antigos)
    mock_db.batch.return_value = mock_batch

    with patch("app.services.contadores_uso.db", mock_db):
        resultado = limpar_contadores_antigos(dias=90, dry_run=False)

    assert resultado["removidos"] == 501
    assert mock_batch.commit.call_count == 2


def test_limpar_contadores_retorna_dict_campos_corretos():
    """Resultado sempre contém chaves removidos, dry_run, erros."""
    from app.services.contadores_uso import limpar_contadores_antigos

    mock_db = MagicMock()
    mock_db.collection.return_value.where.return_value.stream.return_value = iter([])

    with patch("app.services.contadores_uso.db", mock_db):
        resultado = limpar_contadores_antigos(dias=90, dry_run=True)

    assert "removidos" in resultado
    assert "dry_run" in resultado
    assert "erros" in resultado


def test_limpar_contadores_filtra_pela_data_corte():
    """Verifica que a query usa campo 'data' com operador '<' e a data de corte calculada."""

    from app.services.contadores_uso import limpar_contadores_antigos

    mock_db = MagicMock()
    mock_db.collection.return_value.where.return_value.stream.return_value = iter([])

    with patch("app.services.contadores_uso.db", mock_db):
        limpar_contadores_antigos(dias=90, dry_run=True)

    # Verifica que .where("data", "<", <alguma string de data>) foi chamado
    mock_db.collection.return_value.where.assert_called_once()
    call_args = mock_db.collection.return_value.where.call_args
    assert call_args[0][0] == "data"
    assert call_args[0][1] == "<"
    # O terceiro arg é a data de corte; deve ser uma string no formato YYYY-MM-DD
    import re

    assert re.match(r"\d{4}-\d{2}-\d{2}", call_args[0][2])
