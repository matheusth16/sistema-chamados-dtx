"""Testes do serviço de lembrete de MFA pendente.

Banco real (db_session), como o serviço irmão lembrete_confirmacao_service.
Cobre grace period, intervalo de reenvio, claim atômico, isolamento de
exceção e a regressão de "sem teto" (decisão explícita do usuário)."""

import os
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from app import db as db_module
from app.db.models.usuario import UsuarioRow
from app.models_usuario import Usuario

pytestmark = pytest.mark.usefixtures("db_session")


def _pii_off():
    return patch.dict(os.environ, {"ENCRYPT_PII_AT_REST": "false"})


def _criar_usuario_sem_mfa(
    *,
    horas_atras_criacao: float = 30,
    dias_atras_ultimo_lembrete: float | None = None,
    mfa_enabled: bool = False,
    ativo: bool = True,
    criado_em_none: bool = False,
    must_change_password: bool = False,
) -> str:
    usuario_id = f"u_{uuid.uuid4().hex[:8]}"
    Usuario(
        id=usuario_id,
        email=f"{usuario_id}@test.com",
        nome=f"Usuario {usuario_id}",
        mfa_enabled=mfa_enabled,
        ativo=ativo,
        must_change_password=must_change_password,
    ).save()

    criado_em = None if criado_em_none else datetime.now(UTC) - timedelta(hours=horas_atras_criacao)
    mfa_lembrete_enviado_em = (
        datetime.now(UTC) - timedelta(days=dias_atras_ultimo_lembrete)
        if dias_atras_ultimo_lembrete is not None
        else None
    )
    with db_module.SessionLocal() as session, session.begin():
        row = session.get(UsuarioRow, usuario_id)
        row.criado_em = criado_em
        row.mfa_lembrete_enviado_em = mfa_lembrete_enviado_em

    return usuario_id


def _patched(**overrides):
    return patch("app.services.mfa_lembrete_service.notificar_lembrete_mfa_pendente", **overrides)


def _patched_com_senha(**overrides):
    return patch(
        "app.services.mfa_lembrete_service.notificar_lembrete_mfa_pendente_com_senha", **overrides
    )


def test_envia_apos_grace_period_sem_lembrete_anterior(app):
    with _pii_off():
        usuario_id = _criar_usuario_sem_mfa(horas_atras_criacao=25)

        with app.app_context(), _patched(return_value=True) as mock_notif:
            from app.services.mfa_lembrete_service import processar_lembretes_mfa

            stats = processar_lembretes_mfa()

    assert stats == {"processados": 1, "enviados": 1, "erros": 0}
    mock_notif.assert_called_once()
    usuario = Usuario.get_by_id(usuario_id)
    assert usuario.mfa_lembrete_enviado_em is not None


def test_nao_envia_antes_do_grace_period(app):
    with _pii_off():
        _criar_usuario_sem_mfa(horas_atras_criacao=2)

        with app.app_context(), _patched(return_value=True) as mock_notif:
            from app.services.mfa_lembrete_service import processar_lembretes_mfa

            stats = processar_lembretes_mfa()

    assert stats["enviados"] == 0
    mock_notif.assert_not_called()


def test_nao_reenvia_antes_de_3_dias(app):
    with _pii_off():
        usuario_id = _criar_usuario_sem_mfa(horas_atras_criacao=200, dias_atras_ultimo_lembrete=1)

        with app.app_context(), _patched(return_value=True) as mock_notif:
            from app.services.mfa_lembrete_service import processar_lembretes_mfa

            stats = processar_lembretes_mfa()

    assert stats["enviados"] == 0
    mock_notif.assert_not_called()
    usuario = Usuario.get_by_id(usuario_id)
    # timestamp não avança
    assert (datetime.now(UTC) - usuario.mfa_lembrete_enviado_em) >= timedelta(days=1)


def test_reenvia_depois_de_3_dias(app):
    with _pii_off():
        usuario_id = _criar_usuario_sem_mfa(horas_atras_criacao=200, dias_atras_ultimo_lembrete=4)

        with app.app_context(), _patched(return_value=True) as mock_notif:
            from app.services.mfa_lembrete_service import processar_lembretes_mfa

            stats = processar_lembretes_mfa()

    assert stats["enviados"] == 1
    mock_notif.assert_called_once()
    usuario = Usuario.get_by_id(usuario_id)
    assert (datetime.now(UTC) - usuario.mfa_lembrete_enviado_em) < timedelta(minutes=1)


def test_falha_no_envio_nao_avanca_timestamp(app):
    with _pii_off():
        usuario_id = _criar_usuario_sem_mfa(horas_atras_criacao=25)

        with app.app_context(), _patched(return_value=False):
            from app.services.mfa_lembrete_service import processar_lembretes_mfa

            stats = processar_lembretes_mfa()

    assert stats == {"processados": 1, "enviados": 0, "erros": 0}
    usuario = Usuario.get_by_id(usuario_id)
    assert usuario.mfa_lembrete_enviado_em is None


def test_falha_no_envio_permite_retentativa_na_proxima_rodada(app):
    with _pii_off():
        _criar_usuario_sem_mfa(horas_atras_criacao=25)

        with app.app_context():
            from app.services.mfa_lembrete_service import processar_lembretes_mfa

            with _patched(return_value=False):
                processar_lembretes_mfa()

            with _patched(return_value=True) as mock_notif:
                stats = processar_lembretes_mfa()

    assert stats["enviados"] == 1
    mock_notif.assert_called_once()


def test_excecao_num_usuario_nao_derruba_processamento_dos_outros(app):
    with _pii_off():
        _criar_usuario_sem_mfa(horas_atras_criacao=25)
        _criar_usuario_sem_mfa(horas_atras_criacao=25)

        with (
            app.app_context(),
            _patched(side_effect=[RuntimeError("boom"), True]) as mock_notif,
        ):
            from app.services.mfa_lembrete_service import processar_lembretes_mfa

            stats = processar_lembretes_mfa()

    assert stats["processados"] == 2
    assert stats["enviados"] == 1
    assert stats["erros"] == 1
    assert mock_notif.call_count == 2


def test_erro_na_query_retorna_stats_sem_crashar(app):
    with app.app_context(), patch("app.services.mfa_lembrete_service.Usuario") as mock_usuario:
        mock_usuario.get_sem_mfa.side_effect = RuntimeError("db indisponível")

        from app.services.mfa_lembrete_service import processar_lembretes_mfa

        stats = processar_lembretes_mfa()

    assert stats == {"processados": 0, "enviados": 0, "erros": 1}


def test_criado_em_none_nao_quebra_so_pula(app):
    with _pii_off():
        _criar_usuario_sem_mfa(criado_em_none=True)

        with app.app_context(), _patched(return_value=True) as mock_notif:
            from app.services.mfa_lembrete_service import processar_lembretes_mfa

            stats = processar_lembretes_mfa()

    assert stats == {"processados": 1, "enviados": 0, "erros": 0}
    mock_notif.assert_not_called()


def test_regressao_sem_teto_continua_reenviando_apos_varios_ciclos(app):
    """Documenta a decisão explícita do usuário: reenvio a cada 3 dias,
    indefinidamente, sem limite de tentativas. Simula 4 ciclos de 3+ dias."""
    with _pii_off():
        usuario_id = _criar_usuario_sem_mfa(horas_atras_criacao=1000)

        with app.app_context():
            from app.services.mfa_lembrete_service import processar_lembretes_mfa

            for _ in range(4):
                with _patched(return_value=True):
                    stats = processar_lembretes_mfa()
                assert stats["enviados"] == 1

                # empurra o último lembrete pra 4 dias atrás, simulando passagem de tempo
                with db_module.SessionLocal() as session, session.begin():
                    row = session.get(UsuarioRow, usuario_id)
                    row.mfa_lembrete_enviado_em = datetime.now(UTC) - timedelta(days=4)


# ── ramo: nunca trocou a senha inicial (must_change_password=True) ───────────


def test_usuario_nunca_trocou_senha_recebe_senha_nova_e_email_combinado(app):
    """Conta que nunca logou (must_change_password=True) recebe senha nova +
    e-mail combinado, não o e-mail de MFA simples."""
    with _pii_off():
        usuario_id = _criar_usuario_sem_mfa(horas_atras_criacao=25, must_change_password=True)

        with (
            app.app_context(),
            _patched_com_senha(return_value=True) as mock_combo,
            _patched(return_value=True) as mock_simples,
        ):
            from app.services.mfa_lembrete_service import processar_lembretes_mfa

            stats = processar_lembretes_mfa()

    assert stats == {"processados": 1, "enviados": 1, "erros": 0}
    mock_combo.assert_called_once()
    mock_simples.assert_not_called()

    _, _, senha_nova = mock_combo.call_args[0]
    assert len(senha_nova) >= 12

    usuario = Usuario.get_by_id(usuario_id)
    assert usuario.mfa_lembrete_enviado_em is not None
    assert usuario.must_change_password is True  # continua pendente de troca
    assert usuario.check_password(senha_nova) is True  # senha realmente foi trocada no banco


def test_usuario_ja_trocou_senha_recebe_so_email_de_mfa(app):
    """Conta que já trocou a senha (must_change_password=False) não aciona
    o ramo de senha nova — só o e-mail de MFA simples."""
    with _pii_off():
        _criar_usuario_sem_mfa(horas_atras_criacao=25, must_change_password=False)

        with (
            app.app_context(),
            _patched_com_senha(return_value=True) as mock_combo,
            _patched(return_value=True) as mock_simples,
        ):
            from app.services.mfa_lembrete_service import processar_lembretes_mfa

            stats = processar_lembretes_mfa()

    assert stats["enviados"] == 1
    mock_simples.assert_called_once()
    mock_combo.assert_not_called()


def test_falha_no_envio_combinado_nao_avanca_timestamp(app):
    """Se o e-mail combinado falhar, o timestamp de claim é revertido (senha já
    trocada permanece — mesmo comportamento do reset manual do admin, só
    reprocessa o lembrete, não a senha)."""
    with _pii_off():
        usuario_id = _criar_usuario_sem_mfa(horas_atras_criacao=25, must_change_password=True)

        with app.app_context(), _patched_com_senha(return_value=False):
            from app.services.mfa_lembrete_service import processar_lembretes_mfa

            stats = processar_lembretes_mfa()

    assert stats == {"processados": 1, "enviados": 0, "erros": 0}
    usuario = Usuario.get_by_id(usuario_id)
    assert usuario.mfa_lembrete_enviado_em is None
