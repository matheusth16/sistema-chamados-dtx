"""
Serviço de upload de anexos.
Hoje salva em disco local; preparado para trocar por Firebase Storage quando necessário.
"""
import os
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import current_app


def salvar_anexo(arquivo):
    """
    Salva o anexo e retorna o identificador para guardar no chamado
    (nome do arquivo local ou, no futuro, URL do Firebase Storage).

    Args:
        arquivo: FileStorage do request.files

    Returns:
        str: nome do arquivo salvo, ou None se não houver arquivo
    """
    if not arquivo or not arquivo.filename or arquivo.filename.strip() == '':
        return None

    nome_seguro = secure_filename(arquivo.filename)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome_final = f"{timestamp}_{nome_seguro}"

    # Armazenamento local (pasta app/static/uploads)
    pasta_upload = current_app.config['UPLOAD_FOLDER']
    if not os.path.exists(pasta_upload):
        os.makedirs(pasta_upload)
    caminho_completo = os.path.join(pasta_upload, nome_final)
    arquivo.save(caminho_completo)

    # Para usar Firebase Storage no futuro:
    # from firebase_admin import storage
    # bucket = storage.bucket()
    # blob = bucket.blob(f"chamados/{nome_final}")
    # blob.upload_from_file(arquivo.stream, content_type=arquivo.content_type)
    # return blob.public_url  # ou blob.make_authenticated_url(...)
    return nome_final
