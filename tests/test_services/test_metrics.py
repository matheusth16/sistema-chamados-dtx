"""Testes do serviço de métricas de negócio (app/services/metrics.py)."""

import contextlib
import logging

from app.services.metrics import (
    chamado_criado,
    chamado_status_alterado,
    log_evento,
    login_falha,
    login_sucesso,
    logout,
    medir_duracao,
    sla_vencido,
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
