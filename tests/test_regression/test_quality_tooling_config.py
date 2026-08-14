"""Contratos estáticos do lote dependências, axe e k6."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
K6_DIR = ROOT / "scripts" / "qa" / "k6"


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_node_dependencies_are_synced_and_tailwind_stays_on_v3() -> None:
    package = json.loads(_read("package.json"))
    lock = json.loads(_read("package-lock.json"))
    root_lock = lock["packages"][""]

    assert package.get("dependencies", {}) == root_lock.get("dependencies", {})
    assert "docx" not in package.get("dependencies", {})
    assert package["devDependencies"] == root_lock["devDependencies"]
    assert package["devDependencies"]["tailwindcss"].startswith("^3.4.")
    assert package["devDependencies"]["axe-core"][0].isdigit()


def test_k6_scripts_apply_shared_target_guard() -> None:
    shared = _read("scripts/qa/k6/_shared.js")
    assert "K6_CONFIRM_PROD" in shared
    assert "localhost" in shared
    assert "127.0.0.1" in shared
    assert "throw new Error" in shared

    for script_name in ("smoke.js", "load.js", "stress.js", "spike.js", "soak.js"):
        script = (K6_DIR / script_name).read_text(encoding="utf-8")
        assert 'from "./_shared.js"' in script
        assert "assertSafeTarget(" in script


def test_k6_spike_and_soak_have_safe_profiles() -> None:
    spike = _read("scripts/qa/k6/spike.js")
    soak = _read("scripts/qa/k6/soak.js")

    assert "target: 15" in spike
    assert "3m" in spike
    assert "vus: 3" in soak
    assert '__ENV.K6_DURATION || "15m"' in soak


def test_a11y_marker_ci_and_fake_e2e_environment_are_configured() -> None:
    pytest_ini = _read("pytest.ini")
    ci = _read(".github/workflows/ci.yml")
    e2e = _read(".github/workflows/e2e.yml")
    env_example = _read(".env.test.example")

    assert "a11y:" in pytest_ini
    assert "npm ci" in ci
    assert "npm audit --audit-level=high" in ci
    assert "pytest tests/e2e -m a11y" in e2e
    assert "FLASK_E2E_STUB=1" in env_example
    for profile in ("SOLICITANTE", "SUPERVISOR", "ADMIN"):
        assert f"TEST_{profile}_TOTP_SECRET=" in env_example


def test_k6_production_workflow_requires_explicit_confirmation() -> None:
    workflow = _read(".github/workflows/k6-smoke.yml")

    assert "K6_CONFIRM_PROD" in workflow
    assert "confirm_production" in workflow
