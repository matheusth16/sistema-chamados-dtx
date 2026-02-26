"""
Gera uma chave Fernet para criptografia de dados sensíveis em repouso (LGPD).
Execute: python scripts/gerar_chave_criptografia.py
Copie a linha gerada para o seu arquivo .env como ENCRYPTION_KEY.
"""
try:
    from cryptography.fernet import Fernet
except ImportError:
    print("Instale a dependência: pip install cryptography")
    raise SystemExit(1)

def main():
    key = Fernet.generate_key().decode("ascii")
    print("Adicione ao seu .env:")
    print(f"ENCRYPTION_KEY={key}")
    print("\nPara ativar criptografia do campo 'nome' em usuários:")
    print("ENCRYPT_PII_AT_REST=true")

if __name__ == "__main__":
    main()
