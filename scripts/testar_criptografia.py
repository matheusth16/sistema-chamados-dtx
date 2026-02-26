"""
Script para testar a criptografia de dados sensíveis (LGPD).

Como usar:
  1. Certifique-se de ter ENCRYPTION_KEY no .env (rode: python scripts/gerar_chave_criptografia.py)
  2. Na raiz do projeto: python scripts/testar_criptografia.py

O script mostra um texto em claro, o valor criptografado (como fica no banco) e a descriptografia.
"""
import os
import sys

# Garante que o projeto está no path
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, root)
os.chdir(root)  # Garante que o diretório de trabalho é a raiz do projeto (onde está o .env)

# Carrega .env da raiz do projeto e do diretório atual (override para garantir)
from dotenv import load_dotenv
env_path = os.path.join(root, ".env")
load_dotenv(env_path, override=True)
load_dotenv(".env", override=True)  # fallback: cwd (já é root após chdir)

# Fallback: se ENCRYPTION_KEY ainda não estiver no ambiente, tenta ler do arquivo .env
if not os.getenv("ENCRYPTION_KEY", "").strip() and os.path.isfile(env_path):
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("ENCRYPTION_KEY=") and not line.startswith("ENCRYPTION_KEY=#"):
                    valor = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if valor:
                        os.environ["ENCRYPTION_KEY"] = valor
                        break
    except Exception:
        pass

def testar_sem_app():
    """Testa só a biblioteca Fernet (não precisa do Flask rodando)."""
    from cryptography.fernet import Fernet
    chave_b64 = os.getenv("ENCRYPTION_KEY", "").strip()
    if not chave_b64:
        env_path = os.path.join(root, ".env")
        print("ERRO: Defina ENCRYPTION_KEY no .env")
        print(f"  Arquivo esperado: {env_path}")
        print("  Gere uma chave com: python scripts/gerar_chave_criptografia.py")
        return False
    try:
        f = Fernet(chave_b64.encode())
    except Exception as e:
        print(f"ERRO: ENCRYPTION_KEY inválida - {e}")
        return False
    texto_original = "Maria Silva Santos"
    criptografado = f.encrypt(texto_original.encode()).decode("ascii")
    descriptografado = f.decrypt(criptografado.encode()).decode("utf-8")
    print("--- Teste 1: Criptografia direta (Fernet) ---")
    print(f"  Texto original:     {texto_original}")
    print(f"  No banco (cript.):  {criptografado[:50]}...")
    print(f"  Descriptografado:   {descriptografado}")
    print("  OK!" if descriptografado == texto_original else "  FALHOU!")
    return descriptografado == texto_original

def testar_com_app():
    """Testa o serviço crypto do app (precisa das dependências do projeto)."""
    print("\n--- Teste 2: Serviço app.services.crypto ---")
    try:
        from app import create_app
        from app.services.crypto import encrypt_at_rest, decrypt_at_rest, is_encryption_available
    except ImportError as e:
        print(f"  Pulado (dependências do app): {e}")
        return True
    app = create_app()
    with app.app_context():
        if not is_encryption_available():
            print("  ENCRYPTION_KEY não está configurada ou é inválida no app.")
            return False
        nome = "João da Silva"
        enc = encrypt_at_rest(nome)
        dec = decrypt_at_rest(enc)
        print(f"  Nome original:      {nome}")
        print(f"  Criptografado:      {enc[:50]}..." if len(enc) > 50 else f"  Criptografado:      {enc}")
        print(f"  Descriptografado:   {dec}")
        ok = dec == nome
        print("  OK!" if ok else "  FALHOU!")
        return ok

def main():
    print("=" * 60)
    print("  TESTE DE CRIPTOGRAFIA (LGPD)")
    print("=" * 60)
    ok1 = testar_sem_app()
    ok2 = testar_com_app()
    print()
    if ok1 and ok2:
        print("Todos os testes passaram.")
        print("\nPara criptografar o campo 'nome' dos usuários no banco,")
        print("adicione no .env:  ENCRYPT_PII_AT_REST=true")
    else:
        print("Algum teste falhou. Verifique ENCRYPTION_KEY no .env.")
    return 0 if (ok1 and ok2) else 1

if __name__ == "__main__":
    sys.exit(main())
