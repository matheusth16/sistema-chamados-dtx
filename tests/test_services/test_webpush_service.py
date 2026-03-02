"""Testes do serviço Web Push (webpush_service)."""

import pytest
from unittest.mock import patch, MagicMock

from app.services.webpush_service import salvar_inscricao, obter_inscricoes, enviar_webpush_usuario


def test_salvar_inscricao_sem_usuario_id_retorna_false():
    """Sem usuario_id, retorna False."""
    assert salvar_inscricao('', {'endpoint': 'https://push.example.com'}) is False
    assert salvar_inscricao(None, {'endpoint': 'https://push.example.com'}) is False


def test_salvar_inscricao_sem_endpoint_retorna_false():
    """Sem endpoint na subscription, retorna False."""
    assert salvar_inscricao('u1', {}) is False
    assert salvar_inscricao('u1', {'keys': {}}) is False


def test_salvar_inscricao_com_dados_chama_firestore():
    """Com usuario_id e endpoint, chama db.collection().add()."""
    mock_db = MagicMock()
    mock_add = MagicMock()
    mock_db.collection.return_value.add = mock_add
    with patch('app.services.webpush_service.db', mock_db), \
         patch('app.services.webpush_service.firestore') as mock_fs:
        mock_fs.SERVER_TIMESTAMP = 'SERVER_TIMESTAMP'
        result = salvar_inscricao('u1', {
            'endpoint': 'https://push.example.com/send/abc',
            'keys': {'p256dh': 'k1', 'auth': 'k2'},
        })
    assert result is True
    mock_add.assert_called_once()
    call_args = mock_add.call_args[0][0]
    assert call_args['usuario_id'] == 'u1'
    assert call_args['endpoint'] == 'https://push.example.com/send/abc'


def test_obter_inscricoes_sem_usuario_retorna_lista_vazia():
    """Sem usuario_id, retorna lista vazia."""
    assert obter_inscricoes('') == []
    assert obter_inscricoes(None) == []


def test_obter_inscricoes_com_usuario_retorna_lista(app):
    """Com usuario_id, consulta Firestore e retorna lista de subscriptions."""
    mock_stream = MagicMock(return_value=[])
    mock_db = MagicMock()
    mock_db.collection.return_value.where.return_value.stream = mock_stream
    with patch('app.services.webpush_service.db', mock_db):
        result = obter_inscricoes('u1')
    assert result == []


def test_enviar_webpush_usuario_sem_vapid_retorna_zero(app):
    """Sem VAPID_PRIVATE_KEY configurada, retorna 0 envios."""
    app.config['VAPID_PRIVATE_KEY'] = ''
    with app.app_context():
        with patch('app.services.webpush_service.obter_inscricoes', return_value=[]):
            n = enviar_webpush_usuario('u1', 'Título', 'Corpo')
    assert n == 0
