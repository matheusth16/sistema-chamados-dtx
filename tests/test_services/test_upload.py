"""Testes do serviço de upload de anexos (upload.py)."""

from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from app.services.upload import gerar_url_presignada, salvar_anexo


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
        mock_r2.return_value = "r2:chamados/20260101_doc.pdf"
        result = salvar_anexo(fake_file)

    assert result == "r2:chamados/20260101_doc.pdf"
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


def test_gerar_url_presignada_retorna_url(app):
    """gerar_url_presignada gera URL temporária para chave r2:."""
    with patch("app.services.upload._get_r2_client") as mock_client:
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = (
            "https://r2.cloudflarestorage.com/signed?X-Amz=abc"
        )
        mock_client.return_value = (mock_s3, "meu-bucket", "acc123")
        url = gerar_url_presignada("r2:chamados/20260101_doc.pdf")
    assert url == "https://r2.cloudflarestorage.com/signed?X-Amz=abc"
    mock_s3.generate_presigned_url.assert_called_once_with(
        "get_object",
        Params={"Bucket": "meu-bucket", "Key": "chamados/20260101_doc.pdf"},
        ExpiresIn=3600,
    )


def test_gerar_url_presignada_rejeita_chave_sem_prefixo():
    """gerar_url_presignada retorna None para chave sem prefixo r2:."""
    assert gerar_url_presignada("chamados/20260101_doc.pdf") is None
    assert gerar_url_presignada("https://storage.googleapis.com/x") is None


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


# ── _get_r2_client ────────────────────────────────────────────────────────────


def test_get_r2_client_sem_credenciais_retorna_none():
    """_get_r2_client sem variáveis R2 retorna (None, None, None)."""
    from app.services.upload import _get_r2_client

    env = {"R2_ACCOUNT_ID": "", "R2_ACCESS_KEY_ID": "", "R2_SECRET_ACCESS_KEY": ""}
    with patch.dict("os.environ", env):
        s3, bucket, account = _get_r2_client()
    assert s3 is None
    assert bucket is None
    assert account is None


def test_get_r2_client_sem_boto3_retorna_none():
    """_get_r2_client com credenciais mas boto3 ausente retorna (None, None, None)."""
    from app.services.upload import _get_r2_client

    env = {"R2_ACCOUNT_ID": "acc", "R2_ACCESS_KEY_ID": "key", "R2_SECRET_ACCESS_KEY": "sec"}
    with patch.dict("os.environ", env), patch.dict("sys.modules", {"boto3": None}):
        s3, bucket, account = _get_r2_client()
    assert s3 is None
    assert bucket is None
    assert account is None


def test_get_r2_client_com_credenciais_retorna_cliente():
    """_get_r2_client com credenciais e boto3 disponível retorna (s3, bucket, account)."""

    from app.services.upload import _get_r2_client

    mock_s3 = MagicMock()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_s3
    mock_botocore_client = MagicMock()

    env = {
        "R2_ACCOUNT_ID": "acc123",
        "R2_ACCESS_KEY_ID": "key123",
        "R2_SECRET_ACCESS_KEY": "sec123",
        "R2_BUCKET_NAME": "my-bucket",
    }
    with (
        patch.dict("os.environ", env),
        patch.dict(
            "sys.modules",
            {"boto3": mock_boto3, "botocore": MagicMock(), "botocore.client": mock_botocore_client},
        ),
    ):
        s3, bucket, account = _get_r2_client()

    assert s3 is mock_s3
    assert bucket == "my-bucket"
    assert account == "acc123"
    mock_boto3.client.assert_called_once()


# ── _upload_r2 ────────────────────────────────────────────────────────────────


def test_upload_r2_sem_cliente_retorna_none():
    """_upload_r2 sem cliente R2 configurado retorna None."""
    from app.services.upload import _upload_r2

    with patch("app.services.upload._get_r2_client", return_value=(None, None, None)):
        result = _upload_r2(MagicMock(filename="doc.pdf"), "20260101_doc.pdf")
    assert result is None


def test_upload_r2_sucesso_retorna_chave_r2():
    """_upload_r2 com cliente configurado e upload bem-sucedido retorna chave r2:."""
    from app.services.upload import _upload_r2

    mock_s3 = MagicMock()
    mock_arquivo = MagicMock()
    mock_arquivo.filename = "doc.pdf"
    mock_arquivo.stream = BytesIO(b"%PDF-1.4")
    with patch("app.services.upload._get_r2_client", return_value=(mock_s3, "meu-bucket", "acc")):
        result = _upload_r2(mock_arquivo, "20260101_doc.pdf")
    assert result == "r2:chamados/20260101_doc.pdf"
    mock_s3.upload_fileobj.assert_called_once()


def test_upload_r2_excecao_retorna_none():
    """_upload_r2 com exceção durante upload retorna None."""
    from app.services.upload import _upload_r2

    mock_s3 = MagicMock()
    mock_s3.upload_fileobj.side_effect = Exception("connection error")
    mock_arquivo = MagicMock()
    mock_arquivo.filename = "doc.pdf"
    mock_arquivo.stream = BytesIO(b"%PDF-1.4")
    with patch("app.services.upload._get_r2_client", return_value=(mock_s3, "meu-bucket", "acc")):
        result = _upload_r2(mock_arquivo, "20260101_doc.pdf")
    assert result is None


# ── gerar_url_presignada — casos de falha ────────────────────────────────────


def test_gerar_url_presignada_r2_indisponivel_retorna_none():
    """gerar_url_presignada quando R2 não configurado retorna None."""
    with patch("app.services.upload._get_r2_client", return_value=(None, None, None)):
        result = gerar_url_presignada("r2:chamados/doc.pdf")
    assert result is None


def test_gerar_url_presignada_excecao_retorna_none():
    """gerar_url_presignada com exceção na presign retorna None."""
    mock_s3 = MagicMock()
    mock_s3.generate_presigned_url.side_effect = Exception("presign error")
    with patch("app.services.upload._get_r2_client", return_value=(mock_s3, "bucket", "acc")):
        result = gerar_url_presignada("r2:chamados/doc.pdf")
    assert result is None


# ── _upload_firebase_storage ─────────────────────────────────────────────────


def test_upload_firebase_storage_nao_inicializado_retorna_none():
    """_upload_firebase_storage quando Firebase lança exceção ao obter bucket retorna None."""

    from app.services.upload import _upload_firebase_storage

    mock_arquivo = MagicMock()
    mock_arquivo.filename = "doc.pdf"
    mock_arquivo.stream = BytesIO(b"%PDF-1.4")

    with patch("firebase_admin.storage.bucket", side_effect=Exception("Firebase not initialized")):
        result = _upload_firebase_storage(mock_arquivo, "20260101_doc.pdf")
    assert result is None


def test_upload_firebase_storage_falha_upload_retorna_none():
    """_upload_firebase_storage quando upload_from_file falha retorna None."""

    from app.services.upload import _upload_firebase_storage

    mock_blob = MagicMock()
    mock_blob.upload_from_file.side_effect = Exception("upload failed")
    mock_bucket_inst = MagicMock()
    mock_bucket_inst.blob.return_value = mock_blob
    mock_arquivo = MagicMock()
    mock_arquivo.filename = "doc.pdf"
    mock_arquivo.stream = BytesIO(b"%PDF-1.4")

    with patch("firebase_admin.storage.bucket", return_value=mock_bucket_inst):
        result = _upload_firebase_storage(mock_arquivo, "20260101_doc.pdf")
    assert result is None


def test_upload_firebase_storage_sucesso_retorna_url():
    """_upload_firebase_storage com Firebase disponível retorna URL pública."""

    from app.services.upload import _upload_firebase_storage

    mock_blob = MagicMock()
    mock_blob.public_url = "https://storage.googleapis.com/bucket/chamados/doc.pdf"
    mock_bucket_inst = MagicMock()
    mock_bucket_inst.blob.return_value = mock_blob
    mock_arquivo = MagicMock()
    mock_arquivo.filename = "doc.pdf"
    mock_arquivo.stream = BytesIO(b"%PDF-1.4")

    with patch("firebase_admin.storage.bucket", return_value=mock_bucket_inst):
        result = _upload_firebase_storage(mock_arquivo, "20260101_doc.pdf")
    assert result == "https://storage.googleapis.com/bucket/chamados/doc.pdf"


# ── salvar_anexo — validações de extensão e conteúdo ─────────────────────────


def test_salvar_anexo_extensao_invalida_levanta_valueerror(app):
    """salvar_anexo com extensão não permitida levanta ValueError."""
    fake_file = MagicMock()
    fake_file.filename = "malware.exe"
    fake_file.stream = BytesIO(b"MZ\x90\x00")

    with (
        patch("app.services.upload.current_app", app),
        pytest.raises(ValueError, match="Invalid file format"),
    ):
        salvar_anexo(fake_file)


def test_salvar_anexo_magic_bytes_invalidos_levanta_valueerror(app):
    """salvar_anexo com extensão .pdf mas conteúdo não-PDF levanta ValueError."""
    fake_file = MagicMock()
    fake_file.filename = "doc.pdf"
    fake_file.stream = BytesIO(b"this is definitely not a pdf")
    fake_file.content_type = "application/pdf"

    with (
        patch("app.services.upload.current_app", app),
        pytest.raises(ValueError),
    ):
        salvar_anexo(fake_file)
