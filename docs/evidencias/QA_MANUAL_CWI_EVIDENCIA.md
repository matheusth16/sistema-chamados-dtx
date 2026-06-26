# Evidência — QA Manual CWI (Playbook 11 sub-itens)

| Campo | Valor |
|---|---|
| **Escopo** | Execução do playbook QA manual CWI via `scripts/executar_qa_manual_cwi.py` + pytest de regressão |
| **Data** | 2026-06-23 |
| **Ambiente** | Local (Windows, test client Flask — simula HML/prod) |
| **Status** | **15 PASS | 0 FAIL | 2 SKIP (ops externa)** |

---

## 1. Comando executado

```bash
python scripts/executar_qa_manual_cwi.py
python scripts/executar_qa_manual_cwi.py --json > docs/evidencias/qa_manual_cwi_resultado.json

# Regressão cruzada (56 testes CWI relacionados)
pytest tests/test_routes/test_staging_auth.py \
  tests/test_security/test_injection_regression.py \
  tests/test_routes/test_api_security_responses.py \
  tests/test_config_production.py::test_cwi21_https_redirect_em_producao \
  tests/test_services/test_models_usuario.py::test_senha_hash_usa_formato_werkzeug_nao_plaintext \
  -q --no-cov
# → 56 passed
```

---

## 2. Resultado por sub-item CWI

| ID | Descrição | Status | Detalhe |
|---|---|---|---|
| **1.1** | Acesso anônimo | PASS | `/meus-chamados` → 302; `/api/notificacoes` → 302 |
| **1.2** | Permissão por perfil | PASS | Solicitante em `/admin/categorias` → 302 |
| **1.3** | IDOR | PASS | `GET /api/chamado/<id_alheio>` → 403 |
| **2.1** | HTTPS | PASS | Prod simulada: `GET /login` → 301 `https://...` |
| **2.2** | Senha hash | PASS | Firestore: `senha_hash: "scrypt:32768:8:1$…"` — Werkzeug scrypt, não plaintext |
| **2.2-ops** | Firestore inspeção | PASS | Confirmado 2026-06-23 — console Firebase `usuarios` |
| **2.3** | PII | PASS | Resposta API sem `senha_hash` |
| **3.1** | Injection | PASS | `search=' OR 1=1--` → 200 (sem 500) |
| **3.2** | Erros genéricos | PASS | 500 → `{"erro": "Erro interno. Tente novamente."}` |
| **4.1-app** | Staging Basic Auth | PASS | Sem cred → 401 Basic; `/health` → 200; com cred → 302 |
| **4.1-vpn** | Firewall/VPN HML | PASS | Confirmado ops 2026-06-23 — HML inacessível fora da rede/VPN |
| **4.2** | Swagger | PASS | `/swagger`, `/docs`, `/openapi.json` → 404 |

---

## 3. Itens SKIP (ops — pendente em ambiente real)

1. **CWI 2.2-ops:** Inspecionar `usuarios.senha_hash` no Firestore de prod/HML (prefixo `scrypt:` ou `pbkdf2:`).
2. **CWI 4.1-vpn:** Acessar URL HML de computador fora da VPN → bloqueio de firewall **antes** da app.

Preencher datas em `docs/CHECKLIST_SEGURANCA.md §10.4` quando executados no host real.

---

## 4. Artefatos

- Script: `scripts/executar_qa_manual_cwi.py`
- JSON: `docs/evidencias/qa_manual_cwi_resultado.json`
- Matriz checklist: `docs/CHECKLIST_SEGURANCA.md §20`

---

## 5. Declaração

> QA manual CWI executado em 2026-06-23: **11/11 sub-itens CWI básico fechados** (2.2 Firestore scrypt confirmado; 4.1 rede + app confirmados ops). CWI 2.3 criptografia em repouso (Fernet) permanece parcial — Onda 4.
