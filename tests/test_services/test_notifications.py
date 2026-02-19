"""Testes dos serviços de notificação (e-mail, in-app)."""
import pytest
from unittest.mock import patch, MagicMock


def test_enviar_email_retorna_false_sem_destinatario(app):
    """enviar_email retorna False quando destinatário está vazio."""
    from app.services.notifications import enviar_email
    with app.app_context():
        assert enviar_email('', 'Assunto', '<p>Teste</p>') is False


def test_criar_notificacao_retorna_none_sem_usuario_id():
    """criar_notificacao retorna None quando usuario_id é vazio."""
    from app.services.notifications_inapp import criar_notificacao
    with patch('app.services.notifications_inapp.db') as mock_db:
        r = criar_notificacao('', 'ch1', 'CHM-0001', 'Título', 'Msg')
    assert r is None


def test_listar_para_usuario_retorna_lista_vazia_sem_usuario_id():
    """listar_para_usuario retorna [] quando usuario_id é vazio."""
    from app.services.notifications_inapp import listar_para_usuario
    assert listar_para_usuario('') == []
    assert listar_para_usuario(None) == []


def test_contar_nao_lidas_retorna_zero_sem_usuario_id():
    """contar_nao_lidas retorna 0 quando usuario_id é vazio."""
    from app.services.notifications_inapp import contar_nao_lidas
    assert contar_nao_lidas('') == 0
