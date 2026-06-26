"""
Gera uma chave Fernet para criptografia de dados sensíveis em repouso (LGPD).
Execute: python scripts/gerar_chave_criptografia.py
Copie a linha gerada para o seu arquivo .env como ENCRYPTION_KEY.
"""

try:
    from cryptography.fernet import Fernet
except ImportError as err:
    print("Instale a dependência: pip install cryptography")
    raise SystemExit(1) from err


def main():
    key = Fernet.generate_key().decode("ascii")
    print("Adicione ao seu .env:")
    print(f"ENCRYPTION_KEY={key}")
    print("\nPara ativar criptografia dos campos 'nome' e 'email' em usuários (LGPD):")
    print("ENCRYPT_PII_AT_REST=true")
    print("\nDepois rode a migração de dados existentes:")
    print("  python scripts/migrar_pii_criptografia.py           # dry-run")
    print("  python scripts/migrar_pii_criptografia.py --apply   # aplica")


if __name__ == "__main__":
    main()
