"""Testes de cancelamento_solicitante_service.

Fase 2 (Marco 7): persistência real contra Postgres (fixture db_session)
via Chamado.salvar()/get_by_id()/atualizar_campos() — substitui o antigo
mock de db.collection("chamados").document(id).update(...).
"""

from unittest.mock import MagicMock, patch

import pytest

from app.models import Chamado

pytestmark = pytest.mark.usefixtures("db_session")

_ID_INEXISTENTE = 999999999


def _usuario_mock(uid="sol_1", nome="Solicitante Teste"):
    u = MagicMock()
    u.id = uid
    u.nome = nome
    return u


def _criar_chamado_real(solicitante_id="sol_1", status="Aberto", **overrides) -> int:
    defaults = {
        "categoria": "TI",
        "tipo_solicitacao": "Suporte",
        "descricao": "Descrição de teste",
        "responsavel": "Responsável",
        "solicitante_id": solicitante_id,
        "solicitante_nome": "Solicitante Teste",
        "status": status,
    }
    defaults.update(overrides)
    chamado = Chamado(**defaults)
    chamado_id = chamado.salvar()
    assert chamado_id is not None
    return chamado_id


def test_cancelar_chamado_inexistente_retorna_404(app):
    from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

    with app.app_context():
        resultado = cancelar_chamado_solicitante(
            _ID_INEXISTENTE, "Motivo qualquer aqui", _usuario_mock()
        )

    assert resultado["sucesso"] is False
    assert resultado["codigo"] == 404


def test_cancelar_chamado_de_outro_solicitante_retorna_403(app):
    from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

    chamado_id = _criar_chamado_real(solicitante_id="sol_dono", status="Aberto")

    with app.app_context():
        resultado = cancelar_chamado_solicitante(
            chamado_id, "Motivo qualquer aqui", _usuario_mock(uid="sol_intruso")
        )

    assert resultado["sucesso"] is False
    assert resultado["codigo"] == 403


def test_cancelar_chamado_motivo_curto_retorna_400(app):
    from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

    chamado_id = _criar_chamado_real(solicitante_id="sol_1", status="Aberto")

    with app.app_context():
        resultado = cancelar_chamado_solicitante(chamado_id, "curto", _usuario_mock())

    assert resultado["sucesso"] is False
    assert resultado["codigo"] == 400


@pytest.mark.parametrize("status_bloqueado", ["Concluído", "Cancelado"])
def test_cancelar_chamado_status_nao_cancelavel_retorna_403(app, status_bloqueado):
    from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

    chamado_id = _criar_chamado_real(solicitante_id="sol_1", status=status_bloqueado)

    with app.app_context():
        resultado = cancelar_chamado_solicitante(
            chamado_id, "Motivo qualquer aqui", _usuario_mock()
        )

    assert resultado["sucesso"] is False
    assert resultado["codigo"] == 403


@pytest.mark.parametrize("status_ok", ["Aberto", "Em Atendimento", "Aguardando Informação"])
def test_cancelar_chamado_sucesso_atualiza_status_e_grava_historico(app, status_ok):
    from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

    chamado_id = _criar_chamado_real(
        solicitante_id="sol_1", status=status_ok, numero_chamado="CH-001", categoria="TI"
    )

    with (
        app.app_context(),
        patch("app.services.cancelamento_solicitante_service.Historico") as mock_historico,
        patch("threading.Thread"),
    ):
        resultado = cancelar_chamado_solicitante(
            chamado_id, "Motivo qualquer aqui", _usuario_mock()
        )

    assert resultado == {"sucesso": True}
    atualizado = Chamado.get_by_id(chamado_id)
    assert atualizado.status == "Cancelado"
    assert atualizado.motivo_cancelamento == "Motivo qualquer aqui"
    mock_historico.assert_called_once()
    assert mock_historico.call_args.kwargs["valor_anterior"] == status_ok
    assert mock_historico.call_args.kwargs["valor_novo"] == "Cancelado"


def test_cancelar_chamado_erro_no_update_retorna_500(app):
    from app.services.cancelamento_solicitante_service import cancelar_chamado_solicitante

    chamado_id = _criar_chamado_real(solicitante_id="sol_1", status="Aberto")

    with (
        app.app_context(),
        patch("app.models.Chamado.atualizar_campos", return_value=False),
    ):
        resultado = cancelar_chamado_solicitante(
            chamado_id, "Motivo qualquer aqui", _usuario_mock()
        )

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
