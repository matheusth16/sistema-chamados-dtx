"""Testes do serviço de upload de anexos (upload.py)."""

import pytest
from unittest.mock import patch, MagicMock
from io import BytesIO

from app.services.upload import salvar_anexo


def test_salvar_anexo_sem_arquivo_retorna_none():
    """Sem arquivo ou filename vazio, retorna None."""
    assert salvar_anexo(None) is None
    fake = MagicMock()
    fake.filename = ''
    fake.stream = BytesIO(b'x')
    assert salvar_anexo(fake) is None


def test_salvar_anexo_com_firebase_storage_retorna_url(app):
    """Quando Firebase Storage está disponível, retorna URL pública."""
    fake_file = MagicMock()
    fake_file.filename = 'doc.pdf'
    fake_file.stream = BytesIO(b'%PDF-1.4 minimal')  # magic bytes PDF para _arquivo_conteudo_permitido
    fake_file.content_type = 'application/pdf'
    fake_file.stream.seek = MagicMock()

    with patch('app.services.upload._upload_firebase_storage') as mock_firebase:
        mock_firebase.return_value = 'https://storage.example.com/chamados/20260101_120000_doc.pdf'
        with patch('app.services.upload.current_app', app):
            result = salvar_anexo(fake_file)
    assert result == 'https://storage.example.com/chamados/20260101_120000_doc.pdf'


def test_salvar_anexo_firebase_falha_dev_salva_local(app):
    """Em desenvolvimento, quando Firebase falha, salva em disco local e retorna nome do arquivo."""
    app.config['ENV'] = 'development'
    app.config['UPLOAD_FOLDER'] = '/tmp/test_uploads_sistema_chamados'
    # PNG magic bytes (8 bytes) para passar em _arquivo_conteudo_permitido
    fake_file = MagicMock()
    fake_file.filename = 'test.png'
    fake_file.stream = BytesIO(b'\x89PNG\r\n\x1a\n' + b'x' * 10)
    fake_file.content_type = 'image/png'
    fake_file.stream.seek = MagicMock()
    fake_file.save = MagicMock()

    with patch('app.services.upload._upload_firebase_storage', return_value=None), \
         patch('app.services.upload.current_app', app), \
         patch('app.services.upload.os.path.exists', return_value=False), \
         patch('app.services.upload.os.makedirs'):
        result = salvar_anexo(fake_file)
    assert result is not None
    assert result.endswith('test.png') or 'test.png' in result
    fake_file.save.assert_called_once()
