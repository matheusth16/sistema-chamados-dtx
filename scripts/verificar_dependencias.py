"""
Verificação de dependências e testes antes de commit/deploy.

Executa em sequência:
1. pip audit — verifica vulnerabilidades conhecidas nas dependências
2. pytest — roda a suíte de testes

Uso (a partir da raiz do projeto):
    python scripts/verificar_dependencias.py
    python scripts/verificar_dependencias.py --no-audit   # só testes
    python scripts/verificar_dependencias.py --no-tests   # só audit
    python scripts/verificar_dependencias.py --cov        # testes com cobertura
"""

import argparse
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description="Verifica dependências (pip audit) e roda testes (pytest)")
    parser.add_argument("--no-audit", action="store_true", help="Pular pip audit")
    parser.add_argument("--no-tests", action="store_true", help="Pular pytest")
    parser.add_argument("--cov", action="store_true", help="Rodar pytest com cobertura (pytest-cov)")
    args = parser.parse_args()

    failed = False

    if not args.no_audit:
        print("=" * 60)
        print("1. Verificando vulnerabilidades (pip audit)...")
        print("=" * 60)
        result = subprocess.run(
            [sys.executable, "-m", "pip", "audit"],
            capture_output=True,
            text=True,
        )
        if "unknown command" in (result.stderr or "").lower() or "unknown command" in (result.stdout or "").lower():
            print("AVISO: pip audit não disponível (pip muito antigo). Atualize com: pip install -U pip\n")
        elif result.returncode != 0:
            failed = True
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(result.stderr)
            print("AVISO: pip audit encontrou vulnerabilidades. Corrija antes de seguir.\n")
        else:
            print("OK: Nenhuma vulnerabilidade conhecida.\n")

    if not args.no_tests:
        print("=" * 60)
        print("2. Rodando testes (pytest)...")
        print("=" * 60)
        cmd = [sys.executable, "-m", "pytest", "tests/", "-v"]
        if args.cov:
            cmd.extend(["--cov=app", "--cov-report=term-missing"])
        r = subprocess.run(cmd)
        if r.returncode != 0:
            failed = True
            print("AVISO: Alguns testes falharam.\n")
        else:
            print("OK: Todos os testes passaram.\n")

    if failed:
        sys.exit(1)
    print("Verificação concluída com sucesso.")
    sys.exit(0)


if __name__ == "__main__":
    main()
