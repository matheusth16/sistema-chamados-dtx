"""
Serviço de upload de anexos.

Em produção (e quando o Firebase Storage está disponível): envia o arquivo para
Firebase Storage (pasta chamados/) e retorna a URL pública.
Caso contrário: salva em disco local (app/static/uploads) e retorna o nome do arquivo.
No Cloud Run o disco é efêmero; anexos devem usar Firebase Storage.
"""
import os
import logging
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import current_app

logger = logging.getLogger(__name__)


def _upload_firebase_storage(arquivo, nome_final: str):
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
            type(e).__name__, e, exc_info=False
        )
        return None

    try:
        blob = bucket.blob(f"chamados/{nome_final}")
        if hasattr(arquivo.stream, 'seek'):
            arquivo.stream.seek(0)
        blob.upload_from_file(
            arquivo.stream,
            content_type=arquivo.content_type or 'application/octet-stream'
        )
        blob.make_public()
        url = blob.public_url
        logger.info("Anexo enviado ao Firebase Storage: %s", nome_final)
        return url
    except Exception as e:
        logger.warning(
            "Falha ao enviar anexo ao Firebase Storage (%s): %s - %s",
            nome_final, type(e).__name__, e, exc_info=True
        )
        return None


def salvar_anexo(arquivo):
    """
    Salva o anexo e retorna o identificador para guardar no chamado:
    - URL do Firebase Storage (https://...) quando Storage está disponível;
    - nome do arquivo quando salvo localmente (fallback).

    Args:
        arquivo: FileStorage do request.files

    Returns:
        str: URL pública ou nome do arquivo, ou None se não houver arquivo
    """
    if not arquivo or not arquivo.filename or arquivo.filename.strip() == '':
        return None

    nome_seguro = secure_filename(arquivo.filename)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome_final = f"{timestamp}_{nome_seguro}"

    # 1) Tenta Firebase Storage primeiro
    if hasattr(arquivo.stream, 'seek'):
        arquivo.stream.seek(0)
    url = _upload_firebase_storage(arquivo, nome_final)
    if url:
        return url

    # 2) Em produção (ex.: Cloud Run): não usar disco — é efêmero e o anexo some após reinício/outra instância.
    if current_app.config.get('ENV') == 'production':
        logger.error(
            "Firebase Storage falhou em produção. Anexo NÃO foi salvo. "
            "Defina FIREBASE_STORAGE_BUCKET (ex: seu-projeto.appspot.com) e garanta que a conta de serviço do Cloud Run tenha permissão no bucket (Storage Object Admin)."
        )
        return None

    # 3) Fallback: armazenamento local apenas em desenvolvimento
    pasta_upload = current_app.config['UPLOAD_FOLDER']
    if not os.path.exists(pasta_upload):
        os.makedirs(pasta_upload)
    caminho_completo = os.path.join(pasta_upload, nome_final)
    if hasattr(arquivo.stream, 'seek'):
        arquivo.stream.seek(0)
    arquivo.save(caminho_completo)
    return nome_final
