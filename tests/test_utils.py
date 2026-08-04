"""Testes das funções utilitárias (utils)."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from app.utils import (
    extrair_numero_chamado,
    formatar_data_para_excel,
    gerar_numero_chamado,
    get_client_ip,
    mask_email_for_log,
)


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        (None, "-"),
        ("10/02/2026", "10/02/2026"),
        (datetime(2026, 2, 10, 14, 30), "10/02/2026 14:30"),
    ],
    ids=["none", "string", "datetime"],
)
def test_formatar_data_para_excel(entrada, esperado):
    assert formatar_data_para_excel(entrada) == esperado


@pytest.mark.parametrize(
    "numero,esperado",
    [
        ("CHM-0001", 1),
        ("CHM-0045", 45),
        (None, float("inf")),
        ("", float("inf")),
        ("CHM-abc", float("inf")),
    ],
    ids=["um_digito", "dois_digitos", "none", "vazio", "invalido"],
)
def test_extrair_numero_chamado(numero, esperado):
    assert extrair_numero_chamado(numero) == esperado


def test_gerar_numero_chamado_formato(app, db_session):
    """gerar_numero_chamado retorna string no formato CHM-XXXX usando a
    sequence real (chamados_numero_seq, Fase 2 — Marco 9)."""
    with app.app_context():
        result = gerar_numero_chamado()

    assert result.startswith("CHM-")
    assert len(result) == 8
    assert result[4:].isdigit()


def test_gerar_numero_chamado_incrementa_a_cada_chamada(app, db_session):
    """Chamadas sucessivas retornam números estritamente crescentes — a
    sequence nunca repete (nem sob rollback: SEQUENCE não é transacional)."""
    with app.app_context():
        primeiro = gerar_numero_chamado()
        segundo = gerar_numero_chamado()

    assert extrair_numero_chamado(segundo) > extrair_numero_chamado(primeiro)


def test_gerar_numero_chamado_fallback_em_excecao(app, monkeypatch):
    """Exceção ao acessar o banco cai para fallback CHM-XXXX com timestamp."""
    from app import utils

    class _SessionLocalQuebrada:
        """Levanta ao ser chamada; .remove() vira no-op — sem isso, o
        teardown_appcontext (app/db/__init__.py::_remove_session) quebra ao
        tentar chamar .remove() no valor monkeypatchado quando o `with
        app.app_context()` sai, antes do monkeypatch reverter no fim do teste."""

        def __call__(self):
            raise RuntimeError("banco indisponível")

        def remove(self):
            pass

    monkeypatch.setattr(utils.db_module, "SessionLocal", _SessionLocalQuebrada())

    with app.app_context():
        result = gerar_numero_chamado()

    assert result.startswith("CHM-")
    assert len(result) == 8


# ── formatar_data_para_excel (ramos adicionais) ───────────────────────────────


def test_formatar_data_para_excel_com_to_pydatetime():
    """Objeto com .to_pydatetime() mas sem .strftime é formatado via to_pydatetime()."""

    class FakeTimestamp:
        def to_pydatetime(self):
            return datetime(2024, 3, 15, 9, 0)

    assert formatar_data_para_excel(FakeTimestamp()) == "15/03/2024 09:00"


def test_formatar_data_para_excel_com_timestamp():
    """Objeto com .timestamp() mas sem .strftime e sem .to_pydatetime retorna data formatada."""
    mock_obj = MagicMock(spec=["timestamp"])
    mock_obj.timestamp.return_value = datetime(2024, 3, 15, 9, 0).timestamp()
    result = formatar_data_para_excel(mock_obj)
    assert result.startswith("15/03/2024")


def test_formatar_data_para_excel_objeto_desconhecido_retorna_traco():
    """Objeto sem nenhum dos atributos reconhecidos retorna '-'."""

    class Opaco:
        pass

    assert formatar_data_para_excel(Opaco()) == "-"


# ── mask_email_for_log ────────────────────────────────────────────────────────


def test_mask_email_for_log_em_producao_mascara_email(app):
    """Em produção, retorna local[0]***@domain."""
    with app.app_context():
        app.config["ENV"] = "production"
        result = mask_email_for_log("usuario@empresa.com")
    assert result == "u***@empresa.com"


def test_mask_email_for_log_fora_de_producao_retorna_original(app):
    """Fora de produção, retorna email sem máscara."""
    with app.app_context():
        app.config["ENV"] = "testing"
        result = mask_email_for_log("usuario@empresa.com")
    assert result == "usuario@empresa.com"


def test_mask_email_for_log_none_retorna_vazio():
    assert mask_email_for_log(None) == ""


def test_mask_email_for_log_sem_arroba_retorna_original():
    """Email sem @ é retornado sem modificação."""
    assert mask_email_for_log("naoemail") == "naoemail"


def test_mask_email_for_log_nao_string_retorna_valor_original():
    # int truthy: `email or ""` = 123 (type hint é str; apenas para cobertura do branch)
    assert mask_email_for_log(123) == 123


# ── get_client_ip ─────────────────────────────────────────────────────────────
# Com ProxyFix configurado em create_app(), get_client_ip() lê request.remote_addr
# (ProxyFix já ajustou esse valor com base em X-Forwarded-For via proxy confiável).
# Em test_request_context(), o middleware WSGI não é executado, portanto REMOTE_ADDR
# permanece exatamente como configurado no environ.


def test_get_client_ip_retorna_remote_addr(app):
    """get_client_ip() retorna request.remote_addr, sem ler XFF diretamente."""
    with app.test_request_context(
        environ_base={"REMOTE_ADDR": "10.0.0.5"},
        headers={"X-Forwarded-For": "1.2.3.4", "X-Real-IP": "9.9.9.9"},
    ):
        assert get_client_ip() == "10.0.0.5"


def test_get_client_ip_com_x_forwarded_for(app):
    """ProxyFix processa XFF no WSGI; get_client_ip() usa apenas remote_addr."""
    with app.test_request_context(
        environ_base={"REMOTE_ADDR": "10.0.0.1"},
        headers={"X-Forwarded-For": "1.2.3.4, 5.6.7.8"},
    ):
        assert get_client_ip() == "10.0.0.1"


def test_get_client_ip_sem_xff_usa_remote_addr(app):
    """Sem X-Forwarded-For, retorna request.remote_addr diretamente."""
    with app.test_request_context(environ_base={"REMOTE_ADDR": "9.8.7.6"}):
        assert get_client_ip() == "9.8.7.6"


def test_get_client_ip_fallback_remote_addr(app):
    """Sem headers de proxy, usa request.remote_addr."""
    with app.test_request_context(environ_base={"REMOTE_ADDR": "127.0.0.1"}):
        assert get_client_ip() == "127.0.0.1"


def test_mask_email_for_log_local_vazio_retorna_asteriscos(app):
    """Email que começa com '@' tem local vazio → retorna '***@***' em produção."""
    with app.app_context():
        app.config["ENV"] = "production"
        result = mask_email_for_log("@empresa.com")
    assert result == "***@***"


def test_mask_email_for_log_excecao_ao_acessar_config_retorna_email(monkeypatch):
    """Quando current_app não está disponível (RuntimeError), retorna email original."""
    result = mask_email_for_log("usuario@empresa.com")
    assert result == "usuario@empresa.com"


# ── mask_email Jinja2 filter ──────────────────────────────────────────────────


def test_mask_email_filter_registrado_na_app(app):
    """Filtro mask_email deve estar registrado no ambiente Jinja2 da app."""
    assert "mask_email" in app.jinja_env.filters


def test_mask_email_filter_mascara_local_mantem_dominio(app):
    """mask_email: mostra só a primeira letra do local, mantém domínio completo."""
    f = app.jinja_env.filters["mask_email"]
    assert f("matheus@dtx.aero") == "m***@dtx.aero"
    assert f("admin@empresa.com.br") == "a***@empresa.com.br"


def test_mask_email_filter_email_invalido_retorna_inalterado(app):
    """mask_email: entrada sem '@' ou vazia retorna o valor original."""
    f = app.jinja_env.filters["mask_email"]
    assert f("") == ""
    assert f("naoemail") == "naoemail"
    assert f(None) == ""


# ── F-58: atomicidade de gerar_numero_chamado (Fase 2 — sequence nativa) ─────
#
# A garantia de unicidade agora vem da própria SEQUENCE do Postgres (atômica
# por construção do banco, inclusive sob concorrência real) — não precisa de
# teste de concorrência aqui como precisou pra GrupoRL/contadores_uso, onde
# a migração corrigia uma race condition de fato (check-then-act). Aqui a
# implementação antiga (transação Firestore) já era atômica; a mudança é só
# de mecanismo. Um teste com threads reais contra a mesma SQLAlchemy Session
# de teste (não thread-safe) só introduziria flakiness sem provar nada novo.
