"""Testes de caracterização: cancelamento_solicitante_service."""

from unittest.mock import MagicMock, patch

import pytest


def _usuario_mock(uid="sol_1", nome="Solicitante Teste"):
    u = MagicMock()
    u.id = uid
    u.nome = nome
    return u


def _doc_mock(exists=True, **dados):
    doc = MagicMock()
    doc.exists = exists
    doc.to_dict.return_value = dados
    return doc


@pytest.fixture
def mock_db():
    with patch("app.services.cancelamento_solicitante_service.db") as mock_db:
        yield mock_db


def test_cancelar_chamado_inexistente_retorna_404(app, mock_db):
    from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

    mock_db.collection.return_value.document.return_value.get.return_value = _doc_mock(exists=False)

    with app.app_context():
        resultado = cancelar_chamado_solicitante("ch1", "Motivo qualquer aqui", _usuario_mock())

    assert resultado["sucesso"] is False
    assert resultado["codigo"] == 404


def test_cancelar_chamado_de_outro_solicitante_retorna_403(app, mock_db):
    from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

    mock_db.collection.return_value.document.return_value.get.return_value = _doc_mock(
        solicitante_id="sol_dono", status="Aberto"
    )

    with app.app_context():
        resultado = cancelar_chamado_solicitante(
            "ch1", "Motivo qualquer aqui", _usuario_mock(uid="sol_intruso")
        )

    assert resultado["sucesso"] is False
    assert resultado["codigo"] == 403


def test_cancelar_chamado_motivo_curto_retorna_400(app, mock_db):
    from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

    mock_db.collection.return_value.document.return_value.get.return_value = _doc_mock(
        solicitante_id="sol_1", status="Aberto"
    )

    with app.app_context():
        resultado = cancelar_chamado_solicitante("ch1", "curto", _usuario_mock())

    assert resultado["sucesso"] is False
    assert resultado["codigo"] == 400


@pytest.mark.parametrize("status_bloqueado", ["Concluído", "Cancelado"])
def test_cancelar_chamado_status_nao_cancelavel_retorna_403(app, mock_db, status_bloqueado):
    from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

    mock_db.collection.return_value.document.return_value.get.return_value = _doc_mock(
        solicitante_id="sol_1", status=status_bloqueado
    )

    with app.app_context():
        resultado = cancelar_chamado_solicitante("ch1", "Motivo qualquer aqui", _usuario_mock())

    assert resultado["sucesso"] is False
    assert resultado["codigo"] == 403


@pytest.mark.parametrize("status_ok", ["Aberto", "Em Atendimento", "Aguardando Informação"])
def test_cancelar_chamado_sucesso_atualiza_status_e_grava_historico(app, mock_db, status_ok):
    from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

    mock_db.collection.return_value.document.return_value.get.return_value = _doc_mock(
        solicitante_id="sol_1", status=status_ok, numero_chamado="CH-001", categoria="TI"
    )

    with (
        app.app_context(),
        patch("app.services.cancelamento_solicitante_service.Historico") as mock_historico,
        patch("threading.Thread"),
    ):
        resultado = cancelar_chamado_solicitante("ch1", "Motivo qualquer aqui", _usuario_mock())

    assert resultado == {"sucesso": True}
    update_kwargs = mock_db.collection.return_value.document.return_value.update.call_args[0][0]
    assert update_kwargs["status"] == "Cancelado"
    assert update_kwargs["motivo_cancelamento"] == "Motivo qualquer aqui"
    mock_historico.assert_called_once()
    assert mock_historico.call_args.kwargs["valor_anterior"] == status_ok
    assert mock_historico.call_args.kwargs["valor_novo"] == "Cancelado"


def test_cancelar_chamado_erro_no_update_retorna_500(app, mock_db):
    from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

    mock_db.collection.return_value.document.return_value.get.return_value = _doc_mock(
        solicitante_id="sol_1", status="Aberto"
    )
    mock_db.collection.return_value.document.return_value.update.side_effect = RuntimeError(
        "firestore down"
    )

    with app.app_context():
        resultado = cancelar_chamado_solicitante("ch1", "Motivo qualquer aqui", _usuario_mock())

    assert resultado["sucesso"] is False
    assert resultado["codigo"] == 500


def test_notificar_cancelamento_dispara_thread_daemon(app):
    from app.services.cancelamento_solicitante_service import _notificar_cancelamento

    with patch("threading.Thread") as mock_thread_cls:
        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread

        with app.app_context():
            _notificar_cancelamento(
                chamado_id="ch1",
                dados={"numero_chamado": "CH-001", "categoria": "TI"},
                motivo="Motivo qualquer aqui",
                usuario=_usuario_mock(),
            )

    mock_thread_cls.assert_called_once()
    assert mock_thread_cls.call_args.kwargs["daemon"] is True
    mock_thread.start.assert_called_once()
