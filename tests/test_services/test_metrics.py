"""Testes do serviço de métricas de negócio (app/services/metrics.py)."""

import contextlib
import logging

from app.services.metrics import (
    chamado_criado,
    chamado_resolucao_confirmada,
    chamado_status_alterado,
    log_evento,
    login_falha,
    login_lockout,
    login_sucesso,
    logout,
    medir_duracao,
    sla_prazo_proximo,
    sla_vencido,
    webpush_falha,
)


def test_log_evento_emite_no_logger(caplog):
    """log_evento deve registrar uma linha no logger app.metrics."""
    with caplog.at_level(logging.INFO, logger="app.metrics"):
        log_evento("teste_evento", campo="valor", numero=42)

    assert any("teste_evento" in r.message for r in caplog.records)


def test_log_evento_inclui_campos(caplog):
    """Campos passados como kwargs devem aparecer na mensagem."""
    with caplog.at_level(logging.INFO, logger="app.metrics"):
        log_evento("chamado_criado", setor="Planejamento", tipo="Manutenção")

    msg = next(r.message for r in caplog.records if "chamado_criado" in r.message)
    assert "setor=Planejamento" in msg
    assert "tipo=Manutenção" in msg


def test_log_evento_ignora_campos_none(caplog):
    """Campos None não devem aparecer na mensagem."""
    with caplog.at_level(logging.INFO, logger="app.metrics"):
        log_evento("teste", presente="sim", ausente=None)

    msg = next(r.message for r in caplog.records if "teste" in r.message)
    assert "presente=sim" in msg
    assert "ausente" not in msg


def test_chamado_criado_emite_evento(caplog):
    """chamado_criado deve emitir evento com os campos corretos."""
    with caplog.at_level(logging.INFO, logger="app.metrics"):
        chamado_criado("u1", "c123", "TI", "Manutenção")

    assert any("chamado_criado" in r.message for r in caplog.records)
    msg = next(r.message for r in caplog.records if "chamado_criado" in r.message)
    assert "c123" in msg
    assert "u1" in msg


def test_chamado_status_alterado_emite_evento(caplog):
    """chamado_status_alterado deve registrar de/para no log."""
    with caplog.at_level(logging.INFO, logger="app.metrics"):
        chamado_status_alterado("c456", de="Aberto", para="Concluído", user_id="u2")

    assert any("chamado_status_alterado" in r.message for r in caplog.records)
    msg = next(r.message for r in caplog.records if "chamado_status_alterado" in r.message)
    assert "de=Aberto" in msg
    assert "para=Concluído" in msg


def test_login_sucesso_emite_evento(caplog):
    with caplog.at_level(logging.INFO, logger="app.metrics"):
        login_sucesso("u3", "supervisor")

    assert any("login_sucesso" in r.message for r in caplog.records)


def test_login_falha_nao_loga_email(caplog):
    """login_falha não deve expor o e-mail no log."""
    with caplog.at_level(logging.INFO, logger="app.metrics"):
        login_falha("secreto@dtx.com", motivo="credenciais")

    for r in caplog.records:
        assert "secreto@dtx.com" not in r.message


def test_logout_emite_evento(caplog):
    with caplog.at_level(logging.INFO, logger="app.metrics"):
        logout("u4")

    assert any("logout" in r.message for r in caplog.records)


def test_sla_vencido_emite_evento(caplog):
    with caplog.at_level(logging.INFO, logger="app.metrics"):
        sla_vencido("c789")

    assert any("sla_vencido" in r.message for r in caplog.records)
    assert any("c789" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Decorador medir_duracao
# ---------------------------------------------------------------------------


def test_medir_duracao_registra_ok(caplog):
    """@medir_duracao deve registrar operacao_ok quando a função retorna normalmente."""

    @medir_duracao("teste_operacao")
    def operacao_rapida():
        return "resultado"

    with caplog.at_level(logging.INFO, logger="app.metrics"):
        result = operacao_rapida()

    assert result == "resultado"
    assert any("operacao_ok" in r.message for r in caplog.records)
    assert any("teste_operacao" in r.message for r in caplog.records)


def test_medir_duracao_registra_erro_e_propaga(caplog):
    """@medir_duracao deve registrar operacao_erro e propagar a exceção."""

    @medir_duracao("operacao_falha")
    def operacao_que_falha():
        raise ValueError("simulação de erro")

    with caplog.at_level(logging.INFO, logger="app.metrics"), contextlib.suppress(ValueError):
        operacao_que_falha()

    assert any("operacao_erro" in r.message for r in caplog.records)
    assert any("operacao_falha" in r.message for r in caplog.records)


def test_medir_duracao_inclui_duration_ms(caplog):
    """@medir_duracao deve incluir duration_ms no log."""

    @medir_duracao("medir_duracao_test")
    def func():
        return 1

    with caplog.at_level(logging.INFO, logger="app.metrics"):
        func()

    msg = next(r.message for r in caplog.records if "medir_duracao_test" in r.message)
    assert "duration_ms=" in msg


def test_chamado_resolucao_confirmada_emite_evento(caplog):
    """chamado_resolucao_confirmada deve emitir evento com chamado_id e user_id."""
    with caplog.at_level(logging.INFO, logger="app.metrics"):
        chamado_resolucao_confirmada("cABC", "uXYZ")

    assert any("chamado_resolucao_confirmada" in r.message for r in caplog.records)
    msg = next(r.message for r in caplog.records if "chamado_resolucao_confirmada" in r.message)
    assert "cABC" in msg
    assert "uXYZ" in msg


def test_sla_prazo_proximo_emite_evento_com_horas(caplog):
    """sla_prazo_proximo deve emitir evento com horas_restantes arredondado."""
    with caplog.at_level(logging.INFO, logger="app.metrics"):
        sla_prazo_proximo("cDEF", horas_restantes=2.567)

    assert any("sla_prazo_proximo" in r.message for r in caplog.records)
    msg = next(r.message for r in caplog.records if "sla_prazo_proximo" in r.message)
    assert "2.6" in msg or "horas_restantes" in msg


def test_webpush_falha_emite_evento_com_motivo(caplog):
    """webpush_falha deve emitir evento webpush_falha com user_id e motivo."""
    with caplog.at_level(logging.INFO, logger="app.metrics"):
        webpush_falha("u_push", motivo="endpoint_expirado")

    assert any("webpush_falha" in r.message for r in caplog.records)
    msg = next(r.message for r in caplog.records if "webpush_falha" in r.message)
    assert "u_push" in msg
    assert "endpoint_expirado" in msg


def test_webpush_falha_sem_motivo_usa_unknown(caplog):
    """webpush_falha sem motivo deve usar 'unknown' como fallback."""
    with caplog.at_level(logging.INFO, logger="app.metrics"):
        webpush_falha("u_push2")

    msg = next(r.message for r in caplog.records if "webpush_falha" in r.message)
    assert "unknown" in msg


def test_login_lockout_emite_evento(caplog):
    """login_lockout deve emitir evento sem expor email completo."""
    with caplog.at_level(logging.INFO, logger="app.metrics"):
        login_lockout()

    assert any("login_lockout" in r.message for r in caplog.records)


def test_login_lockout_com_hash_emite_evento(caplog):
    """login_lockout com email_hash inclui o hash no log."""
    with caplog.at_level(logging.INFO, logger="app.metrics"):
        login_lockout(email_hash="abc123hash")

    msg = next(r.message for r in caplog.records if "login_lockout" in r.message)
    assert "abc123hash" in msg
