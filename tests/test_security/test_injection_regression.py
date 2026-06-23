"""CWI 3.1 — Regressão injection: payloads SQL-like e NoSQL-like não causam leak ou 500.
CWI 4.2 — Swagger/docs não exposto: /swagger, /docs, /openapi.json → 404.
"""

from unittest.mock import MagicMock, patch

import pytest

PAYLOADS_SQL = [
    "' OR 1=1--",
    "%27%20OR%201%3D1%20--",
    "1; DROP TABLE chamados--",
    "' UNION SELECT * FROM usuarios--",
]

PAYLOADS_NOSQL = [
    '{"$gt": ""}',
    "'; return true;//",
    "1; return db.collection('usuarios').get();//",
    "{$where: 'sleep(1000)'}",
]

PAYLOADS_ALL = PAYLOADS_SQL + PAYLOADS_NOSQL

STRINGS_PROIBIDAS = [
    "Firestore",
    "Traceback",
    "Exception",
    "password_hash",
    "senha_hash",
    "Google",
    "firebase",
]


def _mock_paginacao_vazia():
    return {"docs": [], "proximo_cursor": None, "tem_proxima": False}


def _mock_db_com_ref():
    mock_db = MagicMock()
    mock_ref = MagicMock()
    mock_db.collection.return_value = mock_ref
    mock_ref.where.return_value = mock_ref
    mock_ref.order_by.return_value = mock_ref
    mock_ref.limit.return_value = mock_ref
    return mock_db


@pytest.mark.parametrize("payload", PAYLOADS_ALL)
def test_search_payload_nao_causa_500(client_logado_supervisor, payload):
    """search=<injection_payload> retorna 200, 400 ou 403 — nunca 500."""
    with (
        patch("app.routes.api.db", _mock_db_com_ref()),
        patch(
            "app.routes.api.aplicar_filtros_dashboard_com_paginacao",
            return_value=_mock_paginacao_vazia(),
        ),
    ):
        r = client_logado_supervisor.get(f"/api/chamados/paginar?search={payload}")
    assert r.status_code in (200, 400, 403), f"payload={payload!r} devolveu {r.status_code}"


@pytest.mark.parametrize("payload", PAYLOADS_ALL)
def test_search_payload_nao_vaza_internals(client_logado_supervisor, payload):
    """search=<injection_payload> não vaza nomes internos de tecnologia/campo."""
    with (
        patch("app.routes.api.db", _mock_db_com_ref()),
        patch(
            "app.routes.api.aplicar_filtros_dashboard_com_paginacao",
            return_value=_mock_paginacao_vazia(),
        ),
    ):
        r = client_logado_supervisor.get(f"/api/chamados/paginar?search={payload}")

    body = r.data.decode("utf-8", errors="replace")
    for proibida in STRINGS_PROIBIDAS:
        assert proibida not in body, (
            f"Payload={payload!r}: string proibida {proibida!r} encontrada na resposta"
        )


@pytest.mark.parametrize("payload", PAYLOADS_ALL)
def test_search_payload_nao_retorna_dados_extras(client_logado_supervisor, payload):
    """search=<injection_payload> retorna lista vazia (mock controlado), não dados de outros."""
    with (
        patch("app.routes.api.db", _mock_db_com_ref()),
        patch(
            "app.routes.api.aplicar_filtros_dashboard_com_paginacao",
            return_value=_mock_paginacao_vazia(),
        ),
    ):
        r = client_logado_supervisor.get(f"/api/chamados/paginar?search={payload}")

    if r.status_code == 200:
        data = r.get_json()
        assert data is not None
        assert isinstance(data.get("chamados"), list)
        assert len(data["chamados"]) == 0, (
            f"Payload={payload!r}: esperado 0 chamados, obtidos {len(data['chamados'])}"
        )


@pytest.mark.parametrize("payload", PAYLOADS_SQL[:2])
def test_payload_tratado_como_string_literal(client_logado_supervisor, payload):
    """Payload é passado como argumento de string para o serviço de filtros, não executado."""
    captured_args = {}

    def capturar_filtros(ref, args, **kwargs):
        captured_args["search"] = args.get("search", "")
        return _mock_paginacao_vazia()

    with (
        patch("app.routes.api.db", _mock_db_com_ref()),
        patch(
            "app.routes.api.aplicar_filtros_dashboard_com_paginacao", side_effect=capturar_filtros
        ),
    ):
        client_logado_supervisor.get(f"/api/chamados/paginar?search={payload}")

    if "search" in captured_args:
        assert isinstance(captured_args["search"], str)


@pytest.mark.parametrize(
    "path",
    ["/swagger", "/docs", "/openapi.json", "/swagger.json", "/api-docs"],
)
def test_swagger_routes_retornam_404(client, path):
    """CWI 4.2 — Rotas de documentação automática (swagger/openapi) não estão expostas."""
    r = client.get(path)
    assert r.status_code == 404, f"Rota {path} devolveu {r.status_code}, esperado 404"
