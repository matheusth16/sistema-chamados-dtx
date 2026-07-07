"""
Serviço de upload de anexos.

Prioridade em produção:
  1. Cloudflare R2 (quando R2_ACCOUNT_ID et al. estão configurados)
  2. Firebase Storage (fallback)
  3. Disco local (apenas em desenvolvimento)
"""

import logging
import os
from datetime import datetime
from typing import Any

from flask import current_app
from werkzeug.utils import secure_filename

from app.i18n import get_translation_session
from app.services.validators import _arquivo_conteudo_permitido, _arquivo_permitido


def _t(key, **kwargs):
    return get_translation_session(key, **kwargs)


# MIME types derivados da extensão validada (não confia no Content-Type do cliente)
_EXT_TO_MIME = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "pdf": "application/pdf",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    "xlsb": "application/vnd.ms-excel.sheet.binary.macroEnabled.12",
    "xltx": "application/vnd.openxmlformats-officedocument.spreadsheetml.template",
    "xltm": "application/vnd.ms-excel.template.macroEnabled.12",
    "csv": "text/csv",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "docm": "application/vnd.ms-word.document.macroEnabled.12",
    "dotx": "application/vnd.openxmlformats-officedocument.wordprocessingml.template",
    "dotm": "application/vnd.ms-word.template.macroEnabled.12",
}

logger = logging.getLogger(__name__)


def _get_r2_client():
    """Retorna cliente boto3 para R2, ou None se credenciais não configuradas."""
    account_id = os.getenv("R2_ACCOUNT_ID", "").strip()
    access_key = os.getenv("R2_ACCESS_KEY_ID", "").strip()
    secret_key = os.getenv("R2_SECRET_ACCESS_KEY", "").strip()

    if not all([account_id, access_key, secret_key]):
        return None, None, None

    try:
        import boto3
        from botocore.client import Config as BotocoreConfig
    except ImportError:
        logger.warning("boto3 não instalado; R2 indisponível")
        return None, None, None

    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=BotocoreConfig(signature_version="s3v4"),
        region_name="auto",
    )
    bucket = os.getenv("R2_BUCKET_NAME", "").strip()
    return s3, bucket, account_id


def _upload_r2(arquivo: Any, nome_final: str) -> str | None:
    """
    Envia o arquivo para Cloudflare R2 (bucket privado).
    Retorna 'r2:chamados/<nome_final>' para acesso via URL pré-assinada, ou None em falha.
    """
    s3, bucket, _ = _get_r2_client()
    if not s3 or not bucket:
        return None

    try:
        ext = arquivo.filename.rsplit(".", 1)[-1].lower() if "." in arquivo.filename else ""
        content_type = _EXT_TO_MIME.get(ext, "application/octet-stream")
        key = f"chamados/{nome_final}"
        if hasattr(arquivo.stream, "seek"):
            arquivo.stream.seek(0)
        s3.upload_fileobj(
            arquivo.stream,
            bucket,
            key,
            ExtraArgs={"ContentType": content_type},
        )
        logger.info("Anexo enviado ao R2: %s", nome_final)
        return f"r2:{key}"
    except Exception as e:
        logger.warning(
            "Falha ao enviar para R2 (%s): %s - %s",
            nome_final,
            type(e).__name__,
            e,
            exc_info=True,
        )
        return None


def gerar_url_presignada(chave_r2: str, expiracao_segundos: int = 3600) -> str | None:
    """
    Gera URL temporária para download de arquivo privado no R2.
    chave_r2 deve ter formato 'r2:chamados/nome.pdf'.
    """
    if not chave_r2.startswith("r2:"):
        return None
    key = chave_r2[3:]

    s3, bucket, _ = _get_r2_client()
    if not s3 or not bucket:
        return None

    try:
        return s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expiracao_segundos,
        )
    except Exception as e:
        logger.warning("Falha ao gerar URL pré-assinada (%s): %s - %s", key, type(e).__name__, e)
        return None


def _upload_firebase_storage(arquivo: Any, nome_final: str) -> str | None:
    """
    Envia o arquivo para Firebase Storage em chamados/nome_final.
    Retorna a URL pública ou None em caso de falha.
    """
    try:
        from firebase_admin import storage

        bucket = storage.bucket()
    except Exception as e:
        logger.warning(
            "Firebase Storage indisponível (anexo usará disco local): %s - %s",
            type(e).__name__,
            e,
            exc_info=False,
        )
        return None

    try:
        blob = bucket.blob(f"chamados/{nome_final}")
        if hasattr(arquivo.stream, "seek"):
            arquivo.stream.seek(0)
        ext = arquivo.filename.rsplit(".", 1)[-1].lower() if "." in arquivo.filename else ""
        safe_content_type = _EXT_TO_MIME.get(ext, "application/octet-stream")
        blob.upload_from_file(arquivo.stream, content_type=safe_content_type)
        blob.make_public()
        url = blob.public_url
        logger.info("Anexo enviado ao Firebase Storage: %s", nome_final)
        return url
    except Exception as e:
        logger.warning(
            "Falha ao enviar anexo ao Firebase Storage (%s): %s - %s",
            nome_final,
            type(e).__name__,
            e,
            exc_info=True,
        )
        return None


def salvar_anexo(arquivo: Any) -> str | None:
    """
    Salva o anexo e retorna o identificador para guardar no chamado:
    - URL do Firebase Storage (https://...) quando Storage está disponível;
    - nome do arquivo quando salvo localmente (fallback).

    Args:
        arquivo: FileStorage do request.files

    Returns:
        str: URL pública ou nome do arquivo, ou None se não houver arquivo
    """
    if not arquivo or not arquivo.filename or arquivo.filename.strip() == "":
        return None

    if not _arquivo_permitido(arquivo.filename):
        ext_list = ", ".join(sorted(current_app.config.get("EXTENSOES_UPLOAD_PERMITIDAS", set())))
        raise ValueError(_t("upload_invalid_format_allowed", allowed=ext_list))

    # Validação por conteúdo (magic bytes) para evitar upload malicioso com extensão falsa
    ok, msg = _arquivo_conteudo_permitido(arquivo)
    if not ok:
        logger.warning("Upload rejeitado: conteúdo não corresponde à extensão: %s", msg)
        raise ValueError(msg or _t("upload_invalid_format_generic"))

    nome_seguro = secure_filename(arquivo.filename)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome_final = f"{timestamp}_{nome_seguro}"

    # 1) Tenta Cloudflare R2 (preferencial em produção)
    if hasattr(arquivo.stream, "seek"):
        arquivo.stream.seek(0)
    url = _upload_r2(arquivo, nome_final)
    if url:
        return url

    # 2) Fallback: Firebase Storage
    if hasattr(arquivo.stream, "seek"):
        arquivo.stream.seek(0)
    url = _upload_firebase_storage(arquivo, nome_final)
    if url:
        return url

    # 3) Em produção sem nenhum storage configurado: não salvar em disco (efêmero)
    if current_app.config.get("ENV") == "production":
        logger.error(
            "R2 e Firebase Storage falharam em produção. Anexo NÃO foi salvo. "
            "Configure R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, "
            "R2_BUCKET_NAME e R2_PUBLIC_URL nas variáveis de ambiente."
        )
        return None

    # 4) Fallback: armazenamento local apenas em desenvolvimento
    pasta_upload = current_app.config["UPLOAD_FOLDER"]
    if not os.path.exists(pasta_upload):
        os.makedirs(pasta_upload)
    caminho_completo = os.path.join(pasta_upload, nome_final)
    if hasattr(arquivo.stream, "seek"):
        arquivo.stream.seek(0)
    arquivo.save(caminho_completo)
    return nome_final
