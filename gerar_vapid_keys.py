"""
Gera chaves VAPID para Web Push. Execute: python gerar_vapid_keys.py
Copie as linhas geradas para o seu arquivo .env
"""
import base64
import os

try:
    from py_vapid import Vapid
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        PrivateFormat,
        PublicFormat,
        NoEncryption,
    )
except ImportError as e:
    print("Erro:", e)
    print("Instale: pip install py-vapid")
    raise SystemExit(1)


def base64url(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def main():
    v = Vapid()
    v.generate_keys()
    pub = getattr(v, 'public_key', None)
    priv = getattr(v, 'private_key', None)
    if pub is None and hasattr(v, 'key_pair') and v.key_pair:
        pub = getattr(v.key_pair, 'public_key', None)
        priv = getattr(v.key_pair, 'private_key', None)

    if pub is None or priv is None:
        print("Não foi possível obter as chaves do Vapid.")
        return

    # Chave privada: PEM (pywebpush aceita PEM no .env)
    if hasattr(priv, 'private_bytes'):
        priv_pem = priv.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.PKCS8,
            encryption_algorithm=NoEncryption(),
        ).decode("utf-8")
    else:
        priv_pem = str(priv) if isinstance(priv, (str, bytes)) else ""
        if isinstance(priv_pem, bytes):
            priv_pem = priv_pem.decode("utf-8")

    # Chave pública: formato para o navegador (base64url do ponto não comprimido)
    if hasattr(pub, 'public_bytes'):
        pub_raw = pub.public_bytes(
            encoding=Encoding.X962,
            format=PublicFormat.UncompressedPoint,
        )
        pub_b64 = base64url(pub_raw)
    else:
        pub_b64 = str(pub).strip() if isinstance(pub, str) else ""

    if not priv_pem or not pub_b64:
        print("Não foi possível serializar as chaves.")
        return

    print("Adicione ao .env:")
    print("VAPID_PUBLIC_KEY=" + pub_b64)
    # Em .env, quebras de linha como \\n para não quebrar a variável
    print("VAPID_PRIVATE_KEY=" + priv_pem.strip().replace("\r\n", "\n").replace("\n", "\\n"))


if __name__ == "__main__":
    main()
