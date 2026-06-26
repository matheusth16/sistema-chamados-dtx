"""Gate de cobertura por módulo.

Executa pytest com --cov=app --cov-report=json, lê coverage.json e verifica
que cada arquivo .py em app/ com statements > 0 atinge o threshold (padrão 85%).

Uso:
    python scripts/check_coverage_per_module.py
    python scripts/check_coverage_per_module.py --threshold 85
    python scripts/check_coverage_per_module.py --threshold 90
    python scripts/check_coverage_per_module.py --json-only   # não re-executa pytest

Exit 0 — todos os módulos elegíveis >= threshold.
Exit 1 — um ou mais módulos abaixo do threshold (ou pytest falhou).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COVERAGE_JSON = ROOT / "coverage.json"

# Módulos triviais (0 statements) a ignorar sem avisos
_TRIVIAIS = {
    "app/routes/__init__.py",
    "app/services/__init__.py",
}


def _normalizar_path(raw: str) -> str:
    """Converte separadores para forward-slash e remove prefixos de drive Windows."""
    return raw.replace("\\", "/").lstrip("/")


def _rodar_pytest(threshold: int) -> bool:
    """Executa pytest gerando coverage.json. Retorna True se exit code == 0."""
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "--cov=app",
        "--cov-report=json",
        "--cov-report=term-missing:skip-covered",
        f"--cov-fail-under={threshold}",
        "-q",
    ]
    result = subprocess.run(cmd, cwd=ROOT)
    return result.returncode == 0


def _carregar_cobertura() -> dict:
    if not COVERAGE_JSON.exists():
        print(f"[ERRO] {COVERAGE_JSON} não encontrado. Execute sem --json-only primeiro.")
        sys.exit(2)
    with open(COVERAGE_JSON, encoding="utf-8") as f:
        return json.load(f)


def _verificar_modulos(data: dict, threshold: int) -> tuple[list, list]:
    """Retorna (oks, fails) onde cada item é (modulo, pct, stmts, misses)."""
    files = data.get("files", {})
    oks: list[tuple[str, float, int, int]] = []
    fails: list[tuple[str, float, int, int]] = []

    for raw_path, info in sorted(files.items()):
        norm = _normalizar_path(raw_path)

        # Apenas módulos em app/
        if not norm.startswith("app/"):
            continue

        summary = info.get("summary", {})
        stmts = summary.get("num_statements", 0)
        misses = summary.get("missing_lines", 0)
        pct = summary.get("percent_covered", 0.0)

        # Ignorar triviais e módulos sem statements
        if stmts == 0 or norm in _TRIVIAIS:
            continue

        entry = (norm, pct, stmts, misses)
        if pct >= threshold:
            oks.append(entry)
        else:
            fails.append(entry)

    return oks, fails


def _imprimir_tabela(oks: list, fails: list, threshold: int) -> None:
    col_mod = max(
        (len(m) for m, *_ in oks + fails),
        default=40,
    )
    col_mod = max(col_mod, 40)
    header = f"{'Módulo':<{col_mod}}  {'Cover':>6}  {'Stmts':>6}  {'Misses':>6}  Status"
    sep = "-" * len(header)

    print()
    print(header)
    print(sep)

    for modulo, pct, stmts, misses in fails:
        tag = f"FAIL (<{threshold}%)"
        print(f"{modulo:<{col_mod}}  {pct:>5.1f}%  {stmts:>6}  {misses:>6}  {tag}")

    for modulo, pct, stmts, misses in oks:
        tag = "OK"
        print(f"{modulo:<{col_mod}}  {pct:>5.1f}%  {stmts:>6}  {misses:>6}  {tag}")

    print(sep)
    total = len(oks) + len(fails)
    print(
        f"\nResultado: {len(oks)}/{total} módulos >= {threshold}%  |  {len(fails)} abaixo do gate"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verifica cobertura >= threshold por módulo em app/."
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=85,
        metavar="N",
        help="Porcentagem mínima por módulo (padrão: 85)",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Não re-executa pytest; lê coverage.json existente",
    )
    args = parser.parse_args()

    threshold = args.threshold
    pytest_ok = True

    if not args.json_only:
        print(f"Executando pytest (threshold global: {threshold}%)…")
        pytest_ok = _rodar_pytest(threshold)

    data = _carregar_cobertura()
    oks, fails = _verificar_modulos(data, threshold)
    _imprimir_tabela(oks, fails, threshold)

    if fails:
        print(f"\n[GATE FALHOU] {len(fails)} módulo(s) abaixo de {threshold}%:")
        for modulo, pct, _stmts, misses in fails:
            print(f"  {modulo}: {pct:.1f}%  ({misses} linhas descobertas)")
        sys.exit(1)

    if not pytest_ok:
        print(
            f"\n[GATE FALHOU] cobertura global abaixo de {threshold}% (ver saída do pytest acima)."
        )
        sys.exit(1)

    print(f"\n[GATE OK] Todos os {len(oks)} módulos elegíveis >= {threshold}%.")


if __name__ == "__main__":
    main()
