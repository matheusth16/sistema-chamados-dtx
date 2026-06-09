"""Testes do serviço de upload de anexos (upload.py)."""

from io import BytesIO
from unittest.mock import MagicMock, patch

from app.services.upload import salvar_anexo


def test_salvar_anexo_sem_arquivo_retorna_none():
    """Sem arquivo ou filename vazio, retorna None."""
    assert salvar_anexo(None) is None
    fake = MagicMock()
    fake.filename = ""
    fake.stream = BytesIO(b"x")
    assert salvar_anexo(fake) is None


def test_salvar_anexo_r2_tem_prioridade(app):
    """Quando R2 está disponível, usa R2 e não chama Firebase Storage."""
    fake_file = MagicMock()
    fake_file.filename = "doc.pdf"
    fake_file.stream = BytesIO(b"%PDF-1.4 minimal")
    fake_file.content_type = "application/pdf"
    fake_file.stream.seek = MagicMock()

    with (
        patch("app.services.upload._upload_r2") as mock_r2,
        patch("app.services.upload._upload_firebase_storage") as mock_firebase,
        patch("app.services.upload.current_app", app),
    ):
        mock_r2.return_value = "https://pub-xxx.r2.dev/chamados/20260101_doc.pdf"
        result = salvar_anexo(fake_file)

    assert result == "https://pub-xxx.r2.dev/chamados/20260101_doc.pdf"
    mock_firebase.assert_not_called()


def test_salvar_anexo_r2_falha_usa_firebase(app):
    """Quando R2 falha, cai no Firebase Storage como fallback."""
    fake_file = MagicMock()
    fake_file.filename = "doc.pdf"
    fake_file.stream = BytesIO(b"%PDF-1.4 minimal")
    fake_file.content_type = "application/pdf"
    fake_file.stream.seek = MagicMock()

    with (
        patch("app.services.upload._upload_r2", return_value=None),
        patch("app.services.upload._upload_firebase_storage") as mock_firebase,
        patch("app.services.upload.current_app", app),
    ):
        mock_firebase.return_value = "https://storage.googleapis.com/chamados/doc.pdf"
        result = salvar_anexo(fake_file)

    assert result == "https://storage.googleapis.com/chamados/doc.pdf"


def test_salvar_anexo_ambos_falham_producao_retorna_none(app):
    """Em produção, quando R2 e Firebase falham, retorna None sem salvar em disco."""
    app.config["ENV"] = "production"
    fake_file = MagicMock()
    fake_file.filename = "doc.pdf"
    fake_file.stream = BytesIO(b"%PDF-1.4 minimal")
    fake_file.content_type = "application/pdf"
    fake_file.stream.seek = MagicMock()

    with (
        patch("app.services.upload._upload_r2", return_value=None),
        patch("app.services.upload._upload_firebase_storage", return_value=None),
        patch("app.services.upload.current_app", app),
    ):
        result = salvar_anexo(fake_file)

    assert result is None


def test_salvar_anexo_ambos_falham_dev_salva_local(app):
    """Em desenvolvimento, quando R2 e Firebase falham, salva em disco local."""
    app.config["ENV"] = "development"
    app.config["UPLOAD_FOLDER"] = "/tmp/test_uploads_sistema_chamados"
    fake_file = MagicMock()
    fake_file.filename = "test.png"
    fake_file.stream = BytesIO(b"\x89PNG\r\n\x1a\n" + b"x" * 10)
    fake_file.content_type = "image/png"
    fake_file.stream.seek = MagicMock()
    fake_file.save = MagicMock()

    with (
        patch("app.services.upload._upload_r2", return_value=None),
        patch("app.services.upload._upload_firebase_storage", return_value=None),
        patch("app.services.upload.current_app", app),
        patch("app.services.upload.os.path.exists", return_value=False),
        patch("app.services.upload.os.makedirs"),
    ):
        result = salvar_anexo(fake_file)

    assert result is not None
    assert "test.png" in result
    fake_file.save.assert_called_once()
