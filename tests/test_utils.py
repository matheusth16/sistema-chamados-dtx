"""Testes das funções utilitárias (utils)."""

from datetime import datetime
from unittest.mock import MagicMock, patch

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


def test_gerar_numero_chamado_formato(app):
    """gerar_numero_chamado retorna string no formato CHM-XXXX (transação mockada)."""

    class DocContador:
        exists = True

        def get(self, k):
            return 1 if k == "proximo_numero" else None

    with patch("app.utils.db") as mock_db:
        mock_transaction = MagicMock()
        mock_transaction.get.return_value = DocContador()
        mock_db.transaction.return_value = mock_transaction
        mock_db.collection.return_value.document.return_value = MagicMock()

        with app.app_context():
            result = gerar_numero_chamado()

    assert result.startswith("CHM-")
    assert len(result) == 8
    assert result[4:].isdigit()
    assert result == "CHM-0002"


def test_gerar_numero_chamado_doc_nao_existe_inicia_em_1(app):
    """Quando o documento contador não existe, começa do número 1."""

    class DocNovo:
        exists = False

    with patch("app.utils.db") as mock_db:
        mock_transaction = MagicMock()
        mock_transaction.get.return_value = DocNovo()
        mock_db.transaction.return_value = mock_transaction
        mock_db.collection.return_value.document.return_value = MagicMock()

        with app.app_context():
            result = gerar_numero_chamado()

    assert result == "CHM-0001"


def test_gerar_numero_chamado_fallback_em_excecao(app):
    """Exceção na transação cai para fallback CHM-XXXX com timestamp."""
    with patch("app.utils.db") as mock_db:
        mock_db.transaction.side_effect = Exception("Firestore error")
        with app.app_context():
            result = gerar_numero_chamado()
    assert result.startswith("CHM-")


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


def test_get_client_ip_com_x_forwarded_for(app):
    """X-Forwarded-For com múltiplos IPs retorna o primeiro."""
    with app.test_request_context(headers={"X-Forwarded-For": "1.2.3.4, 5.6.7.8"}):
        assert get_client_ip() == "1.2.3.4"


def test_get_client_ip_com_x_real_ip(app):
    """X-Real-IP é usado quando X-Forwarded-For está ausente."""
    with app.test_request_context(headers={"X-Real-IP": "9.8.7.6"}):
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
