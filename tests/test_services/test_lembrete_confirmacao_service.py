"""Testes do serviço de lembretes de confirmação de resolução."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch


def _doc_pendente(
    chamado_id="ch_1",
    horas_atras=30,
    lembrete_1=False,
    lembrete_2=False,
    solicitante_id="sol_1",
):
    doc = MagicMock()
    doc.id = chamado_id
    doc.to_dict.return_value = {
        "status": "Concluído",
        "confirmacao_solicitante": "pendente",
        "data_conclusao": datetime.now(UTC) - timedelta(hours=horas_atras),
        "solicitante_id": solicitante_id,
        "numero_chamado": "CH-001",
        "categoria": "Manutenção",
        "lembrete_confirmacao_1_enviado": lembrete_1,
        "lembrete_confirmacao_2_enviado": lembrete_2,
    }
    return doc


def _mock_stream(docs):
    """Cria um mock de .stream() que itera sobre docs."""
    q = MagicMock()
    q.where.return_value = q
    q.limit.return_value = q
    q.stream.return_value = iter(docs)
    return q


# ── 1º lembrete ───────────────────────────────────────────────────────────────


def test_envia_lembrete_1_apos_24h(app):
    """Deve enviar 1º lembrete quando passaram >= 24 h e flag ainda False."""
    doc = _doc_pendente(horas_atras=25, lembrete_1=False, lembrete_2=False)
    solicitante = MagicMock()
    solicitante.email = "sol@test.com"

    with (
        app.app_context(),
        patch("app.services.lembrete_confirmacao_service.db") as mock_db,
        patch("app.services.lembrete_confirmacao_service.Usuario") as mock_usuario,
        patch(
            "app.services.lembrete_confirmacao_service.notificar_solicitante_lembrete_confirmacao"
        ) as mock_notif,
        patch("app.services.lembrete_confirmacao_service._criar_inapp_lembrete"),
    ):
        mock_db.collection.return_value.where.return_value.where.return_value.limit.return_value.stream.return_value = iter(
            [doc]
        )
        mock_db.collection.return_value.document.return_value.update = MagicMock()
        mock_usuario.get_by_id.return_value = solicitante

        from app.services.lembrete_confirmacao_service import processar_lembretes_confirmacao

        stats = processar_lembretes_confirmacao()

    assert stats["lembrete_1"] == 1
    assert stats["lembrete_2"] == 0
    mock_notif.assert_called_once_with(
        chamado_id="ch_1",
        numero_chamado="CH-001",
        categoria="Manutenção",
        solicitante_usuario=solicitante,
        numero_lembrete=1,
    )
    # Flag gravada após envio bem-sucedido
    mock_db.collection.return_value.document.return_value.update.assert_called_once_with(
        {"lembrete_confirmacao_1_enviado": True}
    )


def test_nao_envia_lembrete_1_antes_de_24h(app):
    """Não deve enviar lembrete se ainda não passaram 24 h."""
    doc = _doc_pendente(horas_atras=10, lembrete_1=False, lembrete_2=False)

    with (
        app.app_context(),
        patch("app.services.lembrete_confirmacao_service.db") as mock_db,
        patch("app.services.lembrete_confirmacao_service.Usuario"),
        patch(
            "app.services.lembrete_confirmacao_service.notificar_solicitante_lembrete_confirmacao"
        ) as mock_notif,
    ):
        mock_db.collection.return_value.where.return_value.where.return_value.limit.return_value.stream.return_value = iter(
            [doc]
        )

        from app.services.lembrete_confirmacao_service import processar_lembretes_confirmacao

        stats = processar_lembretes_confirmacao()

    assert stats["lembrete_1"] == 0
    mock_notif.assert_not_called()


# ── 2º lembrete ───────────────────────────────────────────────────────────────


def test_envia_lembrete_2_apos_48h(app):
    """Deve enviar 2º lembrete quando passaram >= 48 h e apenas flag 1 está True."""
    doc = _doc_pendente(horas_atras=50, lembrete_1=True, lembrete_2=False)
    solicitante = MagicMock()
    solicitante.email = "sol@test.com"

    with (
        app.app_context(),
        patch("app.services.lembrete_confirmacao_service.db") as mock_db,
        patch("app.services.lembrete_confirmacao_service.Usuario") as mock_usuario,
        patch(
            "app.services.lembrete_confirmacao_service.notificar_solicitante_lembrete_confirmacao"
        ) as mock_notif,
        patch("app.services.lembrete_confirmacao_service._criar_inapp_lembrete"),
    ):
        mock_db.collection.return_value.where.return_value.where.return_value.limit.return_value.stream.return_value = iter(
            [doc]
        )
        mock_db.collection.return_value.document.return_value.update = MagicMock()
        mock_usuario.get_by_id.return_value = solicitante

        from app.services.lembrete_confirmacao_service import processar_lembretes_confirmacao

        stats = processar_lembretes_confirmacao()

    assert stats["lembrete_1"] == 0
    assert stats["lembrete_2"] == 1
    mock_notif.assert_called_once_with(
        chamado_id="ch_1",
        numero_chamado="CH-001",
        categoria="Manutenção",
        solicitante_usuario=solicitante,
        numero_lembrete=2,
    )


def test_nao_envia_lembrete_2_se_flag_1_nao_enviada(app):
    """Não envia 2º lembrete se o 1º ainda não foi enviado (mesmo com 48 h+)."""
    doc = _doc_pendente(horas_atras=60, lembrete_1=False, lembrete_2=False)

    with (
        app.app_context(),
        patch("app.services.lembrete_confirmacao_service.db") as mock_db,
        patch("app.services.lembrete_confirmacao_service.Usuario") as mock_usuario,
        patch(
            "app.services.lembrete_confirmacao_service.notificar_solicitante_lembrete_confirmacao"
        ),
        patch("app.services.lembrete_confirmacao_service._criar_inapp_lembrete"),
    ):
        mock_db.collection.return_value.where.return_value.where.return_value.limit.return_value.stream.return_value = iter(
            [doc]
        )
        mock_db.collection.return_value.document.return_value.update = MagicMock()
        mock_usuario.get_by_id.return_value = MagicMock(email="sol@test.com")

        from app.services.lembrete_confirmacao_service import processar_lembretes_confirmacao

        stats = processar_lembretes_confirmacao()

    # Deve ter enviado o 1º (pois 60h > 24h e flag_1=False), mas não o 2º
    assert stats["lembrete_1"] == 1
    assert stats["lembrete_2"] == 0


# ── Idempotência / sem duplicação ─────────────────────────────────────────────


def test_nao_reenvia_apos_ambos_enviados(app):
    """Chamado com ambas as flags True não recebe mais lembretes."""
    doc = _doc_pendente(horas_atras=100, lembrete_1=True, lembrete_2=True)

    with (
        app.app_context(),
        patch("app.services.lembrete_confirmacao_service.db") as mock_db,
        patch(
            "app.services.lembrete_confirmacao_service.notificar_solicitante_lembrete_confirmacao"
        ) as mock_notif,
    ):
        mock_db.collection.return_value.where.return_value.where.return_value.limit.return_value.stream.return_value = iter(
            [doc]
        )

        from app.services.lembrete_confirmacao_service import processar_lembretes_confirmacao

        stats = processar_lembretes_confirmacao()

    assert stats["lembrete_1"] == 0
    assert stats["lembrete_2"] == 0
    mock_notif.assert_not_called()


def test_nao_grava_flag_se_email_falhar(app):
    """Se o envio de e-mail falhar, a flag NÃO deve ser gravada (permite retry na próxima execução)."""
    doc = _doc_pendente(horas_atras=25, lembrete_1=False, lembrete_2=False)

    with (
        app.app_context(),
        patch("app.services.lembrete_confirmacao_service.db") as mock_db,
        patch("app.services.lembrete_confirmacao_service.Usuario") as mock_usuario,
        patch(
            "app.services.lembrete_confirmacao_service.notificar_solicitante_lembrete_confirmacao",
            return_value=False,  # simula falha de envio
        ),
    ):
        mock_db.collection.return_value.where.return_value.where.return_value.limit.return_value.stream.return_value = iter(
            [doc]
        )
        mock_db.collection.return_value.document.return_value.update = MagicMock()
        mock_usuario.get_by_id.return_value = MagicMock(email="sol@test.com")

        from app.services.lembrete_confirmacao_service import processar_lembretes_confirmacao

        stats = processar_lembretes_confirmacao()

    # Flag não deve ter sido gravada — próxima execução do job vai tentar novamente
    mock_db.collection.return_value.document.return_value.update.assert_not_called()
    assert stats["lembrete_1"] == 0


def test_lembrete_1_enviado_cria_notificacao_inapp(app):
    """Lembrete 1 bem-sucedido deve criar notificação in-app para o solicitante."""
    doc = _doc_pendente(horas_atras=25, lembrete_1=False, lembrete_2=False)

    with (
        app.app_context(),
        patch("app.services.lembrete_confirmacao_service.db") as mock_db,
        patch("app.services.lembrete_confirmacao_service.Usuario") as mock_usuario,
        patch(
            "app.services.lembrete_confirmacao_service.notificar_solicitante_lembrete_confirmacao",
            return_value=True,
        ),
        patch("app.services.lembrete_confirmacao_service._criar_inapp_lembrete") as mock_inapp,
    ):
        mock_db.collection.return_value.where.return_value.where.return_value.limit.return_value.stream.return_value = iter(
            [doc]
        )
        mock_db.collection.return_value.document.return_value.update = MagicMock()
        mock_usuario.get_by_id.return_value = MagicMock(email="sol@test.com")

        from app.services.lembrete_confirmacao_service import processar_lembretes_confirmacao

        processar_lembretes_confirmacao()

    mock_inapp.assert_called_once_with("ch_1", "sol_1", "CH-001", "Manutenção", 1)


def test_lembrete_2_enviado_cria_notificacao_inapp(app):
    """Lembrete 2 bem-sucedido deve criar notificação in-app para o solicitante."""
    doc = _doc_pendente(horas_atras=50, lembrete_1=True, lembrete_2=False)

    with (
        app.app_context(),
        patch("app.services.lembrete_confirmacao_service.db") as mock_db,
        patch("app.services.lembrete_confirmacao_service.Usuario") as mock_usuario,
        patch(
            "app.services.lembrete_confirmacao_service.notificar_solicitante_lembrete_confirmacao",
            return_value=True,
        ),
        patch("app.services.lembrete_confirmacao_service._criar_inapp_lembrete") as mock_inapp,
    ):
        mock_db.collection.return_value.where.return_value.where.return_value.limit.return_value.stream.return_value = iter(
            [doc]
        )
        mock_db.collection.return_value.document.return_value.update = MagicMock()
        mock_usuario.get_by_id.return_value = MagicMock(email="sol@test.com")

        from app.services.lembrete_confirmacao_service import processar_lembretes_confirmacao

        processar_lembretes_confirmacao()

    mock_inapp.assert_called_once_with("ch_1", "sol_1", "CH-001", "Manutenção", 2)


def test_lembrete_email_falhou_nao_cria_inapp(app):
    """Se e-mail falhar (return False), NÃO deve criar notificação in-app."""
    doc = _doc_pendente(horas_atras=25, lembrete_1=False, lembrete_2=False)

    with (
        app.app_context(),
        patch("app.services.lembrete_confirmacao_service.db") as mock_db,
        patch("app.services.lembrete_confirmacao_service.Usuario") as mock_usuario,
        patch(
            "app.services.lembrete_confirmacao_service.notificar_solicitante_lembrete_confirmacao",
            return_value=False,
        ),
        patch("app.services.lembrete_confirmacao_service._criar_inapp_lembrete") as mock_inapp,
    ):
        mock_db.collection.return_value.where.return_value.where.return_value.limit.return_value.stream.return_value = iter(
            [doc]
        )
        mock_db.collection.return_value.document.return_value.update = MagicMock()
        mock_usuario.get_by_id.return_value = MagicMock(email="sol@test.com")

        from app.services.lembrete_confirmacao_service import processar_lembretes_confirmacao

        processar_lembretes_confirmacao()

    mock_inapp.assert_not_called()


def test_ignora_chamado_sem_data_conclusao(app):
    """Chamado sem data_conclusao deve ser ignorado sem erro."""
    doc = MagicMock()
    doc.id = "ch_sem_data"
    doc.to_dict.return_value = {
        "status": "Concluído",
        "confirmacao_solicitante": "pendente",
        "data_conclusao": None,
        "lembrete_confirmacao_1_enviado": False,
        "lembrete_confirmacao_2_enviado": False,
    }

    with (
        app.app_context(),
        patch("app.services.lembrete_confirmacao_service.db") as mock_db,
        patch(
            "app.services.lembrete_confirmacao_service.notificar_solicitante_lembrete_confirmacao"
        ) as mock_notif,
    ):
        mock_db.collection.return_value.where.return_value.where.return_value.limit.return_value.stream.return_value = iter(
            [doc]
        )

        from app.services.lembrete_confirmacao_service import processar_lembretes_confirmacao

        stats = processar_lembretes_confirmacao()

    mock_notif.assert_not_called()
    assert stats["erros"] == 0


# ── Cobertura de branches de exceção e caminhos secundários ──────────────────


def test_criar_inapp_lembrete_captura_excecao(app):
    """_criar_inapp_lembrete não propaga exceção quando criar_notificacao_solicitante falha."""
    with (
        app.app_context(),
        patch(
            "app.services.notifications_inapp.criar_notificacao_solicitante",
            side_effect=Exception("Firestore down"),
        ),
    ):
        from app.services.lembrete_confirmacao_service import _criar_inapp_lembrete

        # Não deve lançar exceção
        _criar_inapp_lembrete("ch1", "sol1", "CH-001", "TI", 1)


def test_processar_lembretes_retorna_erro_quando_firestore_falha(app):
    """processar_lembretes_confirmacao conta erro quando query Firestore falha."""
    with (
        app.app_context(),
        patch("app.services.lembrete_confirmacao_service.db") as mock_db,
    ):
        mock_db.collection.return_value.where.return_value.where.return_value.limit.return_value.stream.side_effect = Exception(
            "Firestore unavailable"
        )

        from app.services.lembrete_confirmacao_service import processar_lembretes_confirmacao

        stats = processar_lembretes_confirmacao()

    assert stats["erros"] == 1
    assert stats["processados"] == 0


def test_processar_lembretes_conta_erro_de_processamento_individual(app):
    """processar_lembretes_confirmacao conta erro quando _processar_chamado lança exceção."""
    doc = _doc_pendente(horas_atras=25, lembrete_1=False, lembrete_2=False)

    with (
        app.app_context(),
        patch("app.services.lembrete_confirmacao_service.db") as mock_db,
        patch(
            "app.services.lembrete_confirmacao_service._processar_chamado",
            side_effect=Exception("unexpected"),
        ),
    ):
        mock_db.collection.return_value.where.return_value.where.return_value.limit.return_value.stream.return_value = iter(
            [doc]
        )

        from app.services.lembrete_confirmacao_service import processar_lembretes_confirmacao

        stats = processar_lembretes_confirmacao()

    assert stats["erros"] == 1


def test_lembrete_2_falha_nao_grava_flag(app):
    """Lembrete 2: se e-mail falhar, a flag NÃO é gravada e warning é emitido."""
    doc = _doc_pendente(horas_atras=50, lembrete_1=True, lembrete_2=False)

    with (
        app.app_context(),
        patch("app.services.lembrete_confirmacao_service.db") as mock_db,
        patch("app.services.lembrete_confirmacao_service.Usuario") as mock_usuario,
        patch(
            "app.services.lembrete_confirmacao_service.notificar_solicitante_lembrete_confirmacao",
            return_value=False,
        ),
    ):
        mock_db.collection.return_value.where.return_value.where.return_value.limit.return_value.stream.return_value = iter(
            [doc]
        )
        mock_db.collection.return_value.document.return_value.update = MagicMock()
        mock_usuario.get_by_id.return_value = MagicMock(email="sol@test.com")

        from app.services.lembrete_confirmacao_service import processar_lembretes_confirmacao

        stats = processar_lembretes_confirmacao()

    mock_db.collection.return_value.document.return_value.update.assert_not_called()
    assert stats["lembrete_2"] == 0


def test_ts_para_datetime_naive_datetime():
    """_ts_para_datetime converte datetime sem tz para UTC aware."""
    from datetime import datetime

    from app.services.lembrete_confirmacao_service import _ts_para_datetime

    naive = datetime(2026, 1, 1, 10, 0, 0)
    result = _ts_para_datetime(naive)
    assert result is not None
    assert result.tzinfo is not None


def test_ts_para_datetime_com_to_datetime():
    """_ts_para_datetime usa .ToDatetime() quando disponível (Firestore Timestamp)."""
    from datetime import UTC, datetime

    from app.services.lembrete_confirmacao_service import _ts_para_datetime

    class FakeTimestamp:
        def ToDatetime(self, tzinfo=None):
            return datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)

    result = _ts_para_datetime(FakeTimestamp())
    assert result is not None
    assert result.year == 2026
