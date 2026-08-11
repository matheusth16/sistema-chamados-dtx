"""Testes do serviço de digest diário de chamados abertos (feature separada
do motor de escalonamento — ver app/services/digest_diario_service.py).

Gatilho por PESSOA, não por chamado: dispara 24h depois da abertura do
chamado pendente mais antigo dela (se nunca recebeu digest), e depois se
repete a cada 24h enquanto ela continuar com chamados abertos."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app import db as db_module
from app.db.models.apoio import DigestDiarioUsuarioRow
from app.db.models.chamado import ChamadoRow
from app.models import Chamado
from app.services.digest_diario_service import processar_digest_diario

pytestmark = pytest.mark.usefixtures("db_session")

_contador_numero = {"n": 0}


def _numero_unico() -> str:
    _contador_numero["n"] += 1
    return f"CH-DIGEST-{_contador_numero['n']:04d}"


def _dt(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute)


def _forcar_data_abertura(chamado_id: int, dt: datetime) -> None:
    with db_module.SessionLocal() as session, session.begin():
        row = session.get(ChamadoRow, chamado_id)
        row.data_abertura = dt


def _criar_chamado(
    *,
    responsavel_id: str,
    data_abertura: datetime,
    categoria: str = "Manutenção",
    status: str = "Aberto",
) -> int:
    chamado = Chamado(
        categoria=categoria,
        tipo_solicitacao="Corretiva",
        descricao="Teste",
        responsavel="Resp",
        responsavel_id=responsavel_id,
        area="Engenharia",
        status=status,
        numero_chamado=_numero_unico(),
    )
    chamado_id = chamado.salvar()
    assert chamado_id is not None
    _forcar_data_abertura(chamado_id, data_abertura)
    return chamado_id


def _definir_ultimo_envio(usuario_id: str, quando: datetime) -> None:
    with db_module.SessionLocal() as session, session.begin():
        row = session.get(DigestDiarioUsuarioRow, usuario_id)
        if row is None:
            row = DigestDiarioUsuarioRow(usuario_id=usuario_id, ultimo_envio_em=quando)
            session.add(row)
        else:
            row.ultimo_envio_em = quando


def _mock_usuario(email: str = "resp@dtx.aero"):
    u = MagicMock()
    u.email = email
    return u


def test_digest_dispara_24h_apos_chamado_mais_antigo():
    agora = _dt(2024, 6, 6, 9, 0)  # 24h depois
    _criar_chamado(responsavel_id="resp_1", data_abertura=_dt(2024, 6, 5, 9, 0))

    with (
        patch("app.services.digest_diario_service.notificar_digest_diario") as mock_notif,
        patch("app.models_usuario.Usuario.get_by_id", return_value=_mock_usuario()),
    ):
        resultado = processar_digest_diario(agora=agora)

    assert resultado["digests_enviados"] == 1
    mock_notif.assert_called_once()
    assert mock_notif.call_args.kwargs["usuario_id"] == "resp_1"


def test_digest_nao_dispara_antes_de_24h():
    agora = _dt(2024, 6, 5, 20, 0)  # só 11h depois
    _criar_chamado(responsavel_id="resp_1", data_abertura=_dt(2024, 6, 5, 9, 0))

    with patch("app.services.digest_diario_service.notificar_digest_diario") as mock_notif:
        resultado = processar_digest_diario(agora=agora)

    assert resultado["digests_enviados"] == 0
    mock_notif.assert_not_called()


def test_digest_repete_a_cada_24h():
    agora = _dt(2024, 6, 7, 10, 0)
    _criar_chamado(responsavel_id="resp_1", data_abertura=_dt(2024, 6, 1, 9, 0))
    _definir_ultimo_envio("resp_1", _dt(2024, 6, 6, 9, 30))  # >=24h atrás

    with (
        patch("app.services.digest_diario_service.notificar_digest_diario") as mock_notif,
        patch("app.models_usuario.Usuario.get_by_id", return_value=_mock_usuario()),
    ):
        resultado = processar_digest_diario(agora=agora)

    assert resultado["digests_enviados"] == 1
    mock_notif.assert_called_once()


def test_digest_nao_repete_antes_de_24h_do_ultimo_envio():
    agora = _dt(2024, 6, 6, 12, 0)
    _criar_chamado(responsavel_id="resp_1", data_abertura=_dt(2024, 6, 1, 9, 0))
    _definir_ultimo_envio("resp_1", _dt(2024, 6, 6, 9, 0))  # só 3h atrás

    with patch("app.services.digest_diario_service.notificar_digest_diario") as mock_notif:
        resultado = processar_digest_diario(agora=agora)

    assert resultado["digests_enviados"] == 0
    mock_notif.assert_not_called()


def test_digest_agrupa_vencidos_perto_de_vencer_vs_abertos():
    """Chamado com TAT quase todo consumido cai em 'vencidos_ou_perto'; um
    recém-aberto cai em 'abertos'."""
    agora = _dt(2024, 6, 6, 16, 0)
    # Aberto segunda 09:00, categoria Manutenção (TAT=3 dias úteis, vence
    # quarta 16:30) — quase 100% consumido em 'agora' (quinta).
    _criar_chamado(
        responsavel_id="resp_1", data_abertura=_dt(2024, 6, 3, 9, 0), categoria="Manutenção"
    )
    # Aberto quinta 15:00, quase nada do TAT consumido ainda.
    _criar_chamado(
        responsavel_id="resp_1", data_abertura=_dt(2024, 6, 6, 15, 0), categoria="Manutenção"
    )

    with (
        patch("app.services.digest_diario_service.notificar_digest_diario") as mock_notif,
        patch("app.models_usuario.Usuario.get_by_id", return_value=_mock_usuario()),
    ):
        processar_digest_diario(agora=agora)

    kwargs = mock_notif.call_args.kwargs
    assert len(kwargs["vencidos_ou_perto"]) == 1
    assert len(kwargs["abertos"]) == 1


def test_digest_ordena_por_prioridade_categoria():
    """Dentro do mesmo grupo, AOG vem antes de Projetos, que vem antes de Rotina."""
    agora = _dt(2024, 6, 7, 9, 0)
    abertura = _dt(2024, 6, 6, 8, 0)  # todos recém-abertos, mesmo grupo "abertos"
    _criar_chamado(
        responsavel_id="resp_1", data_abertura=abertura, categoria="Manutenção", status="Aberto"
    )
    _criar_chamado(
        responsavel_id="resp_1", data_abertura=abertura, categoria="AOG", status="Aberto"
    )
    _criar_chamado(
        responsavel_id="resp_1", data_abertura=abertura, categoria="Projetos", status="Aberto"
    )

    with (
        patch("app.services.digest_diario_service.notificar_digest_diario") as mock_notif,
        patch("app.models_usuario.Usuario.get_by_id", return_value=_mock_usuario()),
    ):
        processar_digest_diario(agora=agora)

    kwargs = mock_notif.call_args.kwargs
    todos = kwargs["vencidos_ou_perto"] + kwargs["abertos"]
    categorias_em_ordem = [item["categoria"] for item in todos]
    assert categorias_em_ordem == ["AOG", "Projetos", "Manutenção"]


def test_digest_sem_chamados_pendentes_nao_envia():
    agora = _dt(2024, 6, 7, 9, 0)

    with patch("app.services.digest_diario_service.notificar_digest_diario") as mock_notif:
        resultado = processar_digest_diario(agora=agora)

    assert resultado["digests_enviados"] == 0
    mock_notif.assert_not_called()


def test_digest_usuario_sem_email_pula():
    agora = _dt(2024, 6, 6, 9, 0)
    _criar_chamado(responsavel_id="resp_1", data_abertura=_dt(2024, 6, 5, 9, 0))
    u_sem_email = MagicMock()
    u_sem_email.email = None

    with (
        patch("app.services.digest_diario_service.notificar_digest_diario") as mock_notif,
        patch("app.models_usuario.Usuario.get_by_id", return_value=u_sem_email),
    ):
        resultado = processar_digest_diario(agora=agora)

    assert resultado["digests_enviados"] == 0
    mock_notif.assert_not_called()


def test_digest_erro_consulta_retorna_stats_com_erro():
    agora = _dt(2024, 6, 6, 9, 0)

    with patch("app.services.digest_diario_service.db_module") as mock_db_module:
        mock_db_module.SessionLocal.side_effect = Exception("Postgres unavailable")
        resultado = processar_digest_diario(agora=agora)

    assert resultado["erros"] == 1
    assert resultado["digests_enviados"] == 0


def test_digest_grava_ultimo_envio_apos_disparar():
    agora = _dt(2024, 6, 6, 9, 0)
    _criar_chamado(responsavel_id="resp_1", data_abertura=_dt(2024, 6, 5, 9, 0))

    with (
        patch("app.services.digest_diario_service.notificar_digest_diario"),
        patch("app.models_usuario.Usuario.get_by_id", return_value=_mock_usuario()),
    ):
        processar_digest_diario(agora=agora)

    with db_module.SessionLocal() as session:
        estado = session.get(DigestDiarioUsuarioRow, "resp_1")
        assert estado is not None
        assert estado.ultimo_envio_em is not None
