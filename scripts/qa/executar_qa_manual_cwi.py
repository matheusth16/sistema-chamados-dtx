#!/usr/bin/env python3
"""Executa o playbook QA manual CWI (11 sub-itens) contra a app local via test client.

Uso:
    python scripts/qa/executar_qa_manual_cwi.py
    python scripts/qa/executar_qa_manual_cwi.py --json

Itens que exigem infra externa (VPN em HML real, Firestore prod, host HTTPS prod)
são marcados como SKIP com motivo — não falham a execução local.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Literal
from unittest.mock import MagicMock, patch

# Garante import do projeto
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.environ.setdefault("FLASK_ENV", "testing")

Status = Literal["PASS", "FAIL", "SKIP"]


@dataclass
class Resultado:
    id_cwi: str
    descricao: str
    status: Status
    detalhe: str
    tipo: str  # local | ops


def _basic_header(user: str, senha: str) -> dict[str, str]:
    cred = base64.b64encode(f"{user}:{senha}".encode()).decode()
    return {"Authorization": f"Basic {cred}"}


def _criar_app_testing():
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SECRET_KEY"] = "qa-manual-cwi-secret"
    app.config["APP_BASE_URL"] = ""
    return app


def _criar_app_staging(staging_env: dict[str, str]):
    """App com ENV=staging e Basic Auth ativo (mesmo padrão de test_staging_auth.py)."""
    env_patch = {
        "FLASK_ENV": "staging",
        "STAGING_AUTH_ENABLED": staging_env.get("STAGING_AUTH_ENABLED", "true"),
        "STAGING_AUTH_USER": staging_env.get("STAGING_AUTH_USER", ""),
        "STAGING_AUTH_PASSWORD": staging_env.get("STAGING_AUTH_PASSWORD", ""),
    }
    with patch.dict(os.environ, env_patch, clear=False):
        from app import create_app

        app = create_app()
    app.config["TESTING"] = False
    app.config["ENV"] = "staging"
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SECRET_KEY"] = "qa-manual-cwi-secret"
    app.config["APP_BASE_URL"] = ""
    return app


def _criar_app_producao_simulada():
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    app.config["ENV"] = "production"
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SECRET_KEY"] = "qa-manual-cwi-secret-min-32-chars!!"
    app.config["APP_BASE_URL"] = "https://chamados.example.com"
    return app


def _usuario_mock(uid, email, nome, perfil, area="Geral"):
    u = MagicMock()
    u.id = uid
    u.email = email
    u.nome = nome
    u.perfil = perfil
    u.area = area
    u.areas = [area]
    u.is_authenticated = True
    u.check_password = MagicMock(return_value=True)
    u.get_id = lambda: str(uid)
    u.must_change_password = False
    u.is_admin_or_above = perfil in ("admin", "admin_global")
    u.is_supervisor_or_above = perfil in ("supervisor", "admin", "admin_global")
    u.onboarding_completo = True
    u.onboarding_passo = 0
    u.ativo = True
    return u


def executar_checks() -> list[Resultado]:
    resultados: list[Resultado] = []
    app = _criar_app_testing()
    client = app.test_client()

    # ── 1.1 Acesso anônimo ───────────────────────────────────────────────────
    r = client.get("/meus-chamados")
    if r.status_code in (302, 401):
        resultados.append(
            Resultado(
                "1.1",
                "Usuario anonimo -> 302/401",
                "PASS",
                f"GET /meus-chamados -> {r.status_code}",
                "local",
            )
        )
    else:
        resultados.append(
            Resultado(
                "1.1",
                "Usuario anonimo -> 302/401",
                "FAIL",
                f"GET /meus-chamados -> {r.status_code} (esperado 302/401)",
                "local",
            )
        )

    r2 = client.get("/api/notificacoes")
    if r2.status_code in (302, 401, 403):
        resultados.append(
            Resultado(
                "1.1b",
                "API anônima /api/notificacoes -> 302/401/403",
                "PASS",
                f"GET /api/notificacoes -> {r2.status_code}",
                "local",
            )
        )
    else:
        resultados.append(
            Resultado(
                "1.1b",
                "API anônima /api/notificacoes",
                "FAIL",
                f"GET /api/notificacoes -> {r2.status_code}",
                "local",
            )
        )

    # ── 1.2 Permissão por perfil ─────────────────────────────────────────────
    user_sol = _usuario_mock("sol_1", "sol@test.com", "Sol", "solicitante", "Planejamento")
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=user_sol),
        patch("app.models_usuario.Usuario.get_by_id", return_value=user_sol),
    ):
        c2 = app.test_client()
        c2.post("/login", data={"email": "sol@test.com", "senha": "ok"})
        r = c2.get("/admin/categorias")
    if r.status_code in (302, 403):
        resultados.append(
            Resultado(
                "1.2",
                "Solicitante em /admin/categorias -> 302/403",
                "PASS",
                f"status={r.status_code}",
                "local",
            )
        )
    else:
        resultados.append(
            Resultado(
                "1.2",
                "Solicitante em /admin-categorias",
                "FAIL",
                f"status={r.status_code} (esperado 302/403)",
                "local",
            )
        )

    # ── 1.3 IDOR ─────────────────────────────────────────────────────────────
    chamado_doc = MagicMock()
    chamado_doc.exists = True
    chamado_doc.to_dict.return_value = {
        "titulo": "Outro",
        "solicitante_id": "outro_user",
        "area": "TI",
        "status": "Aberto",
    }
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=user_sol),
        patch("app.models_usuario.Usuario.get_by_id", return_value=user_sol),
        patch("app.routes.api.db") as mock_db,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = chamado_doc
        c3 = app.test_client()
        c3.post("/login", data={"email": "sol@test.com", "senha": "ok"})
        r = c3.get("/api/chamado/chamado_alheio")
    if r.status_code == 403:
        resultados.append(
            Resultado(
                "1.3",
                "IDOR GET /api/chamado/<id_alheio> -> 403",
                "PASS",
                f"status={r.status_code}",
                "local",
            )
        )
    else:
        resultados.append(
            Resultado(
                "1.3",
                "IDOR GET /api/chamado/<id_alheio>",
                "FAIL",
                f"status={r.status_code} (esperado 403)",
                "local",
            )
        )

    # ── 2.1 HTTPS redirect (simulado prod) ───────────────────────────────────
    app_prod = _criar_app_producao_simulada()
    with app_prod.test_client() as c_prod:
        r = c_prod.get("/login")
    if r.status_code == 301 and (r.location or "").startswith("https://"):
        resultados.append(
            Resultado(
                "2.1",
                "HTTP→HTTPS redirect em produção simulada",
                "PASS",
                f"status={r.status_code} Location={r.location}",
                "local",
            )
        )
    else:
        resultados.append(
            Resultado(
                "2.1",
                "HTTP→HTTPS redirect",
                "FAIL",
                f"status={r.status_code} location={r.location!r}",
                "local",
            )
        )

    # ── 2.2 Senha hash (unitário — proxy do Firestore manual) ────────────────
    from app.models_usuario import Usuario

    with patch("app.models_usuario.db"):
        u = Usuario(id="qa_cwi22", email="qa@cwi.test", nome="QA", perfil="solicitante")
        u.set_password("SenhaCWI2_2!")
    if u.senha_hash and (u.senha_hash.startswith("scrypt:") or u.senha_hash.startswith("pbkdf2:")):
        resultados.append(
            Resultado(
                "2.2",
                "senha_hash Werkzeug scrypt:/pbkdf2: (proxy Firestore manual)",
                "PASS",
                f"prefixo={u.senha_hash.split(':')[0]}:",
                "local",
            )
        )
    else:
        resultados.append(
            Resultado(
                "2.2",
                "senha_hash Werkzeug",
                "FAIL",
                f"hash inválido: {u.senha_hash!r}",
                "local",
            )
        )

    resultados.append(
        Resultado(
            "2.2-ops",
            "Inspeção Firestore usuarios.senha_hash em prod/HML",
            "SKIP",
            "Requer acesso ao console Firebase — validar manualmente no deploy",
            "ops",
        )
    )

    # ── 2.3 PII ──────────────────────────────────────────────────────────────
    chamado_pii = MagicMock()
    chamado_pii.exists = True
    chamado_pii.to_dict.return_value = {
        "titulo": "Meu",
        "solicitante_id": "sol_1",
        "area": "Planejamento",
        "status": "Aberto",
        "senha_hash": "nao_deve_vazar",
    }
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=user_sol),
        patch("app.models_usuario.Usuario.get_by_id", return_value=user_sol),
        patch("app.routes.api.db") as mock_db,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = chamado_pii
        c4 = app.test_client()
        c4.post("/login", data={"email": "sol@test.com", "senha": "ok"})
        r = c4.get("/api/chamado/meuchamado")
    body = r.get_json(silent=True) or {}
    dados = body.get("dados") or body
    leaked = "senha_hash" in json.dumps(dados)
    if r.status_code == 200 and not leaked:
        resultados.append(
            Resultado(
                "2.3",
                "Resposta API sem senha_hash / campos internos",
                "PASS",
                "GET /api/chamado/<id> sem senha_hash na resposta",
                "local",
            )
        )
    elif not leaked and r.status_code in (200, 403):
        resultados.append(
            Resultado(
                "2.3",
                "Resposta API sem vazamento senha_hash",
                "PASS",
                f"status={r.status_code}, sem senha_hash no JSON",
                "local",
            )
        )
    else:
        resultados.append(
            Resultado(
                "2.3",
                "PII na resposta API",
                "FAIL",
                f"status={r.status_code}, vazou senha_hash={leaked}",
                "local",
            )
        )

    # ── 3.1 Injection ────────────────────────────────────────────────────────
    user_sup = _usuario_mock("sup_1", "sup@test.com", "Sup", "supervisor", "Manutencao")
    payload = "' OR 1=1--"
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=user_sup),
        patch("app.models_usuario.Usuario.get_by_id", return_value=user_sup),
        patch(
            "app.routes.api.aplicar_filtros_dashboard_com_paginacao",
            return_value={"docs": [], "proximo_cursor": None, "tem_proxima": False},
        ),
    ):
        c5 = app.test_client()
        c5.post("/login", data={"email": "sup@test.com", "senha": "ok"})
        r = c5.get(f"/api/chamados/paginar?search={payload}")
    if r.status_code != 500:
        resultados.append(
            Resultado(
                "3.1",
                "Injection search=' OR 1=1-- -> sem 500",
                "PASS",
                f"status={r.status_code}",
                "local",
            )
        )
    else:
        resultados.append(
            Resultado(
                "3.1",
                "Injection search",
                "FAIL",
                "Retornou 500 — possível vazamento ou erro não tratado",
                "local",
            )
        )

    # ── 3.2 Erros genéricos ──────────────────────────────────────────────────
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=user_sup),
        patch("app.models_usuario.Usuario.get_by_id", return_value=user_sup),
        patch("app.routes.api.db") as mock_db,
    ):
        mock_db.collection.return_value.document.return_value.get.side_effect = RuntimeError(
            "Firestore connection timeout — credenciais inválidas"
        )
        c6 = app.test_client()
        c6.post("/login", data={"email": "sup@test.com", "senha": "ok"})
        r = c6.get("/api/chamado/ch_teste_erro")
    body = r.get_json(silent=True) or {}
    texto = json.dumps(body)
    bad = any(x in texto for x in ("Firestore", "Traceback", "Python"))
    if r.status_code == 500 and body.get("erro") == "Erro interno. Tente novamente." and not bad:
        resultados.append(
            Resultado(
                "3.2",
                "Erro genérico sem Firestore/traceback",
                "PASS",
                f"status={r.status_code} body={texto[:120]}",
                "local",
            )
        )
    else:
        resultados.append(
            Resultado(
                "3.2",
                "Erro genérico",
                "FAIL",
                f"Resposta contém termo proibido: {texto[:200]}",
                "local",
            )
        )

    # ── 4.1 Staging Basic Auth (camada app — local) ──────────────────────────
    staging_vars = {
        "STAGING_AUTH_ENABLED": "true",
        "STAGING_AUTH_USER": "hml_qa",
        "STAGING_AUTH_PASSWORD": "SenhaHML_QA_2026!",
    }
    app_stg = _criar_app_staging(staging_vars)
    rota_protegida = "/admin"
    with patch.dict(os.environ, staging_vars, clear=False):
        cs = app_stg.test_client()
        r_no_auth = cs.get(rota_protegida)
        r_health = cs.get("/health")
        r_auth = cs.get(
            rota_protegida,
            headers=_basic_header("hml_qa", "SenhaHML_QA_2026!"),
        )
    www_no = r_no_auth.headers.get("WWW-Authenticate", "")
    www_health = r_health.headers.get("WWW-Authenticate", "")
    if r_no_auth.status_code == 401 and "Basic" in www_no:
        resultados.append(
            Resultado(
                "4.1-app",
                "Staging: sem credencial -> 401 Basic",
                "PASS",
                f"status={r_no_auth.status_code} WWW-Authenticate={www_no[:60]}",
                "local",
            )
        )
    else:
        resultados.append(
            Resultado(
                "4.1-app",
                "Staging sem credencial",
                "FAIL",
                f"status={r_no_auth.status_code} www={www_no!r}",
                "local",
            )
        )

    if r_health.status_code == 200 and "Basic" not in www_health:
        resultados.append(
            Resultado(
                "4.1-health",
                "Staging: /health excluído do Basic Auth",
                "PASS",
                f"status={r_health.status_code}",
                "local",
            )
        )
    else:
        resultados.append(
            Resultado(
                "4.1-health",
                "Staging /health excluído",
                "FAIL",
                f"status={r_health.status_code} www={www_health!r}",
                "local",
            )
        )

    if r_auth.status_code != 401 and "Basic" not in r_auth.headers.get("WWW-Authenticate", ""):
        resultados.append(
            Resultado(
                "4.1-cred",
                "Staging: credencial correta passa Basic Auth",
                "PASS",
                f"status={r_auth.status_code}",
                "local",
            )
        )
    else:
        resultados.append(
            Resultado(
                "4.1-cred",
                "Staging credencial correta",
                "FAIL",
                f"status={r_auth.status_code}",
                "local",
            )
        )

    resultados.append(
        Resultado(
            "4.1-vpn",
            "HML fora da VPN -> bloqueio firewall (camada primária CWI)",
            "SKIP",
            "Requer host HML real acessível da internet — executar ops manualmente",
            "ops",
        )
    )

    # ── 4.2 Swagger ──────────────────────────────────────────────────────────
    for path in ("/swagger", "/docs", "/openapi.json"):
        r = client.get(path)
        if r.status_code == 404:
            resultados.append(
                Resultado(
                    "4.2",
                    f"Swagger oculto {path} -> 404",
                    "PASS",
                    f"GET {path} -> 404",
                    "local",
                )
            )
        else:
            resultados.append(
                Resultado(
                    "4.2",
                    f"Swagger {path}",
                    "FAIL",
                    f"GET {path} -> {r.status_code} (esperado 404)",
                    "local",
                )
            )
            break

    return resultados


def main() -> int:
    parser = argparse.ArgumentParser(description="QA manual CWI — playbook local")
    parser.add_argument("--json", action="store_true", help="Saída JSON")
    args = parser.parse_args()

    resultados = executar_checks()
    passed = sum(1 for r in resultados if r.status == "PASS")
    failed = sum(1 for r in resultados if r.status == "FAIL")
    skipped = sum(1 for r in resultados if r.status == "SKIP")
    total = len(resultados)

    if args.json:
        print(
            json.dumps(
                {
                    "executado_em": datetime.now(UTC).isoformat(),
                    "resumo": {"pass": passed, "fail": failed, "skip": skipped, "total": total},
                    "resultados": [asdict(r) for r in resultados],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print("=" * 60)
        print("QA MANUAL CWI — Playbook local (test client)")
        print(f"Executado em: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print("=" * 60)
        for r in resultados:
            icon = {"PASS": "OK", "FAIL": "FALHA", "SKIP": "SKIP"}[r.status]
            print(f"[{icon}] CWI {r.id_cwi} — {r.descricao}")
            print(f"       {r.detalhe}")
        print("-" * 60)
        print(f"Resumo: {passed} PASS | {failed} FAIL | {skipped} SKIP | {total} checks")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
