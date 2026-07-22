"""Testes da rota /internal/cron/sla-escalacao — Auditoria CI/CD 2026-07-21.

Contexto: o Container App roda com min-replicas=0 (scale-to-zero, free tier),
o que mata o APScheduler in-process na maior parte do tempo. Esta rota permite
que um workflow externo (GitHub Actions, cron a cada 10 min) acorde o
container só pelo tempo de rodar o job de escalonamento SLA, via HTTP
autenticado por CRON_SECRET — mesmo padrão de X-Health-Token já usado em /health.
"""

import os
from unittest.mock import patch

import pytest


@pytest.fixture
def _sem_redis(app):
    """Garante execução direta do job (sem lock Redis) nestes testes."""
    app.config["REDIS_URL"] = ""
    with patch.dict(os.environ, {"REDIS_URL": ""}, clear=False):
        yield


def test_cron_sla_escalacao_sem_secret_configurado_retorna_503(client, _sem_redis):
    """Sem CRON_SECRET configurado, a rota nunca fica aberta por engano."""
    with patch.dict(os.environ, {"CRON_SECRET": ""}, clear=False):
        resp = client.post("/internal/cron/sla-escalacao")
    assert resp.status_code == 503


def test_cron_sla_escalacao_sem_token_retorna_401(client, _sem_redis):
    with patch.dict(os.environ, {"CRON_SECRET": "segredo-teste-cron-valido-32ch"}, clear=False):
        resp = client.post("/internal/cron/sla-escalacao")
    assert resp.status_code == 401


def test_cron_sla_escalacao_token_invalido_retorna_401(client, _sem_redis):
    with patch.dict(os.environ, {"CRON_SECRET": "segredo-teste-cron-valido-32ch"}, clear=False):
        resp = client.post(
            "/internal/cron/sla-escalacao",
            headers={"X-Cron-Token": "token-errado"},
        )
    assert resp.status_code == 401


def test_cron_sla_escalacao_token_correto_executa_job(client, _sem_redis):
    """Token correto: chama os 3 processadores da Escada A/B e retorna sucesso+dados."""
    secret = "segredo-teste-cron-valido-32ch"
    with (
        patch.dict(os.environ, {"CRON_SECRET": secret}, clear=False),
        patch(
            "app.services.sla_escalacao_service.processar_escada_a",
            return_value={"escalados": 1},
        ) as mock_a,
        patch(
            "app.services.sla_escalacao_service.processar_avisos_resolucao",
            return_value={"avisados": 0},
        ) as mock_avisos,
        patch(
            "app.services.sla_escalacao_service.processar_escada_b",
            return_value={"escalados": 0},
        ) as mock_b,
    ):
        resp = client.post(
            "/internal/cron/sla-escalacao",
            headers={"X-Cron-Token": secret},
        )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["sucesso"] is True
    assert body["dados"]["escada_a"] == {"escalados": 1}
    assert body["dados"]["avisos_resolucao"] == {"avisados": 0}
    assert body["dados"]["escada_b"] == {"escalados": 0}
    mock_a.assert_called_once()
    mock_avisos.assert_called_once()
    mock_b.assert_called_once()


def test_cron_sla_escalacao_metodo_get_nao_permitido(client, _sem_redis):
    resp = client.get("/internal/cron/sla-escalacao")
    assert resp.status_code == 405


def test_cron_sla_escalacao_isento_de_csrf():
    """POST /internal/cron/sla-escalacao deve funcionar mesmo com CSRF protection ativa.

    O GitHub Actions chama essa rota via curl puro (sem sessão de navegador nem
    token CSRF) — a rota precisa estar isenta ou toda chamada do workflow vira
    400 "CSRF token is missing" (bug real encontrado ao validar o workflow
    manualmente em produção, 2026-07-22).
    """
    import os
    from unittest.mock import patch

    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = True
    app.config["SECRET_KEY"] = "test-secret"
    app.config["APP_BASE_URL"] = ""
    app.config["SSO_REDIRECT_URI"] = ""
    app.config["REDIS_URL"] = ""
    client_csrf = app.test_client()

    secret = "segredo-teste-cron-valido-32ch"
    with (
        patch.dict(os.environ, {"CRON_SECRET": secret, "REDIS_URL": ""}, clear=False),
        patch("app.services.sla_escalacao_service.processar_escada_a", return_value={}),
        patch("app.services.sla_escalacao_service.processar_avisos_resolucao", return_value={}),
        patch("app.services.sla_escalacao_service.processar_escada_b", return_value={}),
    ):
        resp = client_csrf.post(
            "/internal/cron/sla-escalacao",
            headers={"X-Cron-Token": secret},
        )
    assert resp.status_code == 200
