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


# ── F-58: Confirma uso de transação atômica em gerar_numero_chamado ──────────


def test_gerar_numero_chamado_usa_transaction_set_quando_doc_nao_existe(app):
    """F-58: gerar_numero_chamado chama transaction.set() quando o doc contador não existe.
    Confirma que o caminho @firestore.transactional é executado para garantir atomicidade."""

    class DocNovo:
        exists = False

    with patch("app.utils.db") as mock_db:
        mock_transaction = MagicMock()
        mock_transaction.get.return_value = DocNovo()
        mock_db.transaction.return_value = mock_transaction
        mock_db.collection.return_value.document.return_value = MagicMock()

        with app.app_context():
            result = gerar_numero_chamado()

    mock_db.transaction.assert_called_once()
    mock_transaction.set.assert_called_once()
    call_args = mock_transaction.set.call_args[0]
    assert call_args[1]["proximo_numero"] == 1
    assert result == "CHM-0001"


def test_gerar_numero_chamado_usa_transaction_get_para_ler_contador(app):
    """F-58: gerar_numero_chamado lê o contador via transaction.get() antes de incrementar."""

    class DocExistente:
        exists = True

        def get(self, k):
            return 5 if k == "proximo_numero" else None

    with patch("app.utils.db") as mock_db:
        mock_transaction = MagicMock()
        mock_transaction.get.return_value = DocExistente()
        mock_db.transaction.return_value = mock_transaction
        mock_db.collection.return_value.document.return_value = MagicMock()

        with app.app_context():
            result = gerar_numero_chamado()

    mock_transaction.get.assert_called()
    assert result == "CHM-0006"


def test_gerar_numero_chamado_concorrencia_gera_numeros_unicos(app):
    """F-58: Múltiplas threads chamando gerar_numero_chamado() com mock serializado devem gerar números únicos."""
    import threading

    counter = {"n": 0}
    state_lock = threading.Lock()

    class RealDoc:
        """Doc sem __next__ para cair no caminho else (não-generator) em utils.py."""

        def __init__(self, n):
            self.exists = True
            self._n = n

        def get(self, k, **kwargs):
            return self._n if k == "proximo_numero" else None

    def make_transaction():
        mock_tx = MagicMock()

        def atomic_get(doc_ref, **kwargs):
            with state_lock:
                counter["n"] += 1
                return RealDoc(counter["n"])

        mock_tx.get.side_effect = atomic_get
        return mock_tx

    results = []
    results_lock = threading.Lock()

    with patch("app.utils.db") as mock_db:
        mock_db.transaction.side_effect = make_transaction
        mock_db.collection.return_value.document.return_value = MagicMock()

        def worker():
            with app.app_context():
                num = gerar_numero_chamado()
            with results_lock:
                results.append(num)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert len(results) == 5, f"Esperado 5 resultados, obtido {len(results)}"
    assert len(set(results)) == 5, f"Race condition detectada — números duplicados: {results}"
