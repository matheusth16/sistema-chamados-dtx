"""Testes do serviço Web Push (webpush_service) — Fase 2, Postgres real
pra persistência; envio via pywebpush continua mockado (rede externa)."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from app.services.webpush_service import (
    MAX_INSCRICOES,
    enviar_webpush_usuario,
    obter_inscricoes,
    salvar_inscricao,
)

pytestmark = pytest.mark.usefixtures("db_session")


def test_salvar_inscricao_sem_usuario_id_retorna_false(app):
    assert salvar_inscricao("", {"endpoint": "https://push.example.com"}) is False
    assert salvar_inscricao(None, {"endpoint": "https://push.example.com"}) is False


def test_salvar_inscricao_sem_endpoint_retorna_false(app):
    assert salvar_inscricao("u1", {}) is False
    assert salvar_inscricao("u1", {"keys": {}}) is False


def test_salvar_inscricao_persiste_e_obter_inscricoes_retorna(app):
    """Salva uma inscrição real e confirma que obter_inscricoes a devolve."""
    resultado = salvar_inscricao(
        "u1",
        {"endpoint": "https://push.example.com/send/abc", "keys": {"p256dh": "k1", "auth": "k2"}},
    )

    assert resultado is True
    inscricoes = obter_inscricoes("u1")
    assert len(inscricoes) == 1
    assert inscricoes[0]["endpoint"] == "https://push.example.com/send/abc"
    assert inscricoes[0]["keys"] == {"p256dh": "k1", "auth": "k2"}


def test_obter_inscricoes_sem_usuario_retorna_lista_vazia(app):
    assert obter_inscricoes("") == []
    assert obter_inscricoes(None) == []


def test_obter_inscricoes_sem_registros_retorna_lista_vazia(app):
    assert obter_inscricoes("usuario_sem_inscricao") == []


def test_salvar_inscricao_deduplica_endpoint_existente(app):
    """Mesmo usuario_id+endpoint: atualiza em vez de duplicar."""
    salvar_inscricao(
        "u1",
        {"endpoint": "https://push.example.com/send/abc", "keys": {"p256dh": "k1", "auth": "k2"}},
    )
    salvar_inscricao(
        "u1",
        {
            "endpoint": "https://push.example.com/send/abc",
            "keys": {"p256dh": "k1-novo", "auth": "k2"},
        },
    )

    inscricoes = obter_inscricoes("u1")
    assert len(inscricoes) == 1  # não duplicou
    assert inscricoes[0]["keys"]["p256dh"] == "k1-novo"  # atualizou


def test_enviar_webpush_deleta_subscricao_expirada(app):
    """Erro 410 Gone do servidor push remove a inscrição expirada."""
    import pywebpush

    salvar_inscricao(
        "u1",
        {"endpoint": "https://push.example.com/send/abc", "keys": {"p256dh": "k1", "auth": "k2"}},
    )
    app.config["VAPID_PRIVATE_KEY"] = "chave-privada"
    fake_response = MagicMock()
    fake_response.status_code = 410

    with (
        app.app_context(),
        patch.object(
            pywebpush,
            "webpush",
            side_effect=pywebpush.WebPushException("gone", response=fake_response),
        ),
    ):
        n = enviar_webpush_usuario("u1", "Título", "Corpo", url="https://x")

    assert n == 0
    assert obter_inscricoes("u1") == []  # removida


def test_enviar_webpush_le_chave_via_config_get(app):
    import pywebpush

    salvar_inscricao(
        "u1",
        {"endpoint": "https://push.example.com/send/abc", "keys": {"p256dh": "k1", "auth": "k2"}},
    )
    app.config["VAPID_PRIVATE_KEY"] = "chave-privada"

    with app.app_context(), patch.object(pywebpush, "webpush") as mock_webpush:
        n = enviar_webpush_usuario("u1", "Título", "Corpo")

    assert n == 1
    mock_webpush.assert_called_once()


def test_enviar_webpush_sem_vapid_retorna_zero(app):
    app.config["VAPID_PRIVATE_KEY"] = ""
    with app.app_context():
        n = enviar_webpush_usuario("u1", "Título", "Corpo")
    assert n == 0


def test_enviar_webpush_sem_app_context_retorna_zero(app):
    n = enviar_webpush_usuario("u1", "Título", "Corpo")
    assert n == 0


def test_enviar_webpush_pywebpush_nao_instalado_retorna_zero(app):
    import sys

    app.config["VAPID_PRIVATE_KEY"] = "chave-privada"
    with app.app_context(), patch.dict(sys.modules, {"pywebpush": None}):
        n = enviar_webpush_usuario("u1", "Título", "Corpo")
    assert n == 0


def test_enviar_webpush_excecao_generica_continua_outros_envios(app):
    import pywebpush

    salvar_inscricao("u1", {"endpoint": "https://x.com/1", "keys": {"p256dh": "k1", "auth": "a1"}})
    salvar_inscricao("u1", {"endpoint": "https://x.com/2", "keys": {"p256dh": "k2", "auth": "a2"}})
    app.config["VAPID_PRIVATE_KEY"] = "chave-privada"

    def _fake_webpush(**kw):
        if kw["subscription_info"]["endpoint"].endswith("1"):
            raise Exception("generic device error")

    with app.app_context(), patch.object(pywebpush, "webpush", side_effect=_fake_webpush):
        n = enviar_webpush_usuario("u1", "T", "B")

    assert n == 1


def test_obter_inscricoes_aplica_limite_maximo(app):
    for i in range(MAX_INSCRICOES + 5):
        salvar_inscricao(
            "u_muitas",
            {"endpoint": f"https://push.example.com/{i}", "keys": {"p256dh": "k", "auth": "a"}},
        )

    result = obter_inscricoes("u_muitas")

    assert len(result) == MAX_INSCRICOES


def test_obter_inscricoes_loga_warning_ao_atingir_limite(app, caplog):
    for i in range(MAX_INSCRICOES):
        salvar_inscricao(
            "u_limite",
            {"endpoint": f"https://push.example.com/{i}", "keys": {"p256dh": "k", "auth": "a"}},
        )

    with caplog.at_level(logging.WARNING, logger="app.services.webpush_service"):
        obter_inscricoes("u_limite")

    assert "limite" in caplog.text.lower()


def test_deletar_subscricao_sem_doc_id_nao_lanca(app):
    from app.services.webpush_service import _deletar_subscricao

    _deletar_subscricao("")
    _deletar_subscricao(None)  # não deve levantar


def test_deletar_subscricao_id_invalido_nao_propaga(app):
    from app.services.webpush_service import _deletar_subscricao

    _deletar_subscricao("nao-e-um-id-valido")  # não deve levantar
