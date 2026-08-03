"""Testes do serviço de histórico de ações administrativas sobre usuários
(Fase 2 — Postgres real)."""

import pytest

pytestmark = pytest.mark.usefixtures("db_session")


def test_registrar_historico_usuario_grava_com_campos_esperados(app):
    from app.services.historico_usuario_service import (
        obter_historico_usuario,
        registrar_historico_usuario,
    )

    resultado = registrar_historico_usuario(
        usuario_alvo_id="user_1",
        usuario_alvo_nome="Fulano",
        admin_id="admin_1",
        admin_nome="Admin Root",
        acao="criacao",
        detalhe="perfil=solicitante",
    )

    assert resultado is True
    historico = obter_historico_usuario("user_1")
    assert len(historico) == 1
    assert historico[0]["usuario_alvo_nome"] == "Fulano"
    assert historico[0]["admin_nome"] == "Admin Root"
    assert historico[0]["acao"] == "criacao"
    assert historico[0]["detalhe"] == "perfil=solicitante"


def test_registrar_historico_usuario_sem_detalhe_fica_none(app):
    from app.services.historico_usuario_service import (
        obter_historico_usuario,
        registrar_historico_usuario,
    )

    registrar_historico_usuario(
        usuario_alvo_id="user_2",
        usuario_alvo_nome="Fulano",
        admin_id="admin_1",
        admin_nome="Admin Root",
        acao="desativacao",
    )

    historico = obter_historico_usuario("user_2")
    assert historico[0]["detalhe"] is None


def test_obter_historico_usuario_ordena_por_data_desc(app):
    from app.services.historico_usuario_service import (
        obter_historico_usuario,
        registrar_historico_usuario,
    )

    registrar_historico_usuario("user_3", "Fulano", "admin_1", "Admin", acao="criacao")
    registrar_historico_usuario("user_3", "Fulano", "admin_1", "Admin", acao="edicao")
    registrar_historico_usuario("user_3", "Fulano", "admin_1", "Admin", acao="desativacao")

    historico = obter_historico_usuario("user_3")

    assert len(historico) == 3
    assert historico[0]["acao"] == "desativacao"  # mais recente primeiro


def test_obter_historico_usuario_sem_registros_retorna_lista_vazia(app):
    from app.services.historico_usuario_service import obter_historico_usuario

    assert obter_historico_usuario("user_sem_historico") == []
