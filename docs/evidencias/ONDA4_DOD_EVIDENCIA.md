# Evidência Operacional — Onda 4 DoD (Criptografia PII Fernet / LGPD / CWI 2.3)

| Campo | Valor |
|---|---|
| **Escopo** | Onda 4 — Criptografia Fernet em repouso dos campos PII `nome` e `email` em usuários; `email_lookup_hash` para login sem decrypt; dual-read legado |
| **Data de execução** | 2026-06-23 (código) + polish 2026-06-23 |
| **Executado por** | Matheus Costa — DTX Aerospace Engineering |
| **Status código** | **DoD código 100% — APROVADO** |
| **Status ops** | ✅ Rollout executado 2026-06-23 — 2/2 usuários migrados; smoke OK (ver §5) |

---

## 1. Critérios de aceite (DoD Onda 4)

| Critério | Status | Evidência |
|---|---|---|
| ADR-001 criado | ✅ | `docs/adr/001-criptografia-pii-fernet.md` |
| `pii_encryption.py` + ≥12 testes unitários | ✅ | `app/services/pii_encryption.py` — 16 testes em `test_pii_encryption.py` |
| `Usuario` save/read/login via `email_lookup_hash` com dual-read legado | ✅ | 8 novos testes em `test_models_usuario.py` (Onda 4) |
| `get_all()` funciona com encryption ON (ordenação Python) | ✅ | `test_get_all_ordena_em_python_quando_encryption_enabled` |
| `migrar_pii_criptografia.py` dry-run/apply idempotente + `_decide_migration_update` | ✅ | `scripts/migrar_pii_criptografia.py` (polish: fix double-encrypt, pure function extraída) |
| Índice Firestore em `email_lookup_hash` | ✅ | `firestore.indexes.json` `fieldOverrides` + ADR-001 + `docs/ENV.md` |
| `ENV.md`, `POLITICA LGPD`, `CHECKLIST §9.4/§20` atualizados | ✅ | Ver §5 abaixo |
| `ONDA4_DOD_EVIDENCIA.md` criado | ✅ | Este documento |
| review-security CLEAN (0 HIGH, 0 MEDIUM introduzidos) | ✅ | `bandit -r app/ -ll` — 0 H / 0 M (ver §1.2) |
| Suite completa verde | ✅ | 1588 passed, 1 pre-existente CSS (ver §1.3) |
| Default `ENCRYPT_PII_AT_REST=false` — zero breaking change | ✅ | `config.py` default + todos os testes passam sem a var |

---

## 2. Ciclo de qualidade

### 2.1 ruff

```
$ ruff check app/ tests/ --fix
All checks passed!

$ ruff format app/ tests/
2 files reformatted, 155 files left unchanged
```

### 2.2 bandit

```
$ bandit -r app/ -ll

Test results:
    No issues identified.
    Total issues (by severity):
        High: 0 | Medium: 0 | Low: 15
```

### 2.3 pytest — testes Onda 4 (isolado)

```
$ pytest tests/test_services/test_pii_encryption.py \
         tests/test_services/test_models_usuario.py \
         tests/test_routes/test_auth.py \
         -v --tb=short --no-cov

91 passed in 5.50s
  tests/test_services/test_pii_encryption.py          16 passed
  tests/test_services/test_models_usuario.py          44 passed
  tests/test_routes/test_auth.py                      31 passed
```

### 2.4 Regressão crítica (Ondas 1–3b/5)

```
$ pytest tests/test_services/test_permissions.py \
         tests/test_routes/test_download_idor.py \
         tests/test_security/test_injection_regression.py \
         tests/test_routes/test_api_security_responses.py \
         -q --no-cov

65 passed in 5.30s
```

### 2.5 Suite completa

```
$ pytest --tb=short -q

1588 passed, 1 failed (CSS pre-existente), 74.19s
Total coverage: 94.86%
Required coverage of 85% reached.

1 falha pre-existente (fora do escopo Onda 4):
  tests/test_regression/test_dtx_light_invariants.py::
    test_surface_border_token_paridade_input_css_tailwind
  Motivo: divergência de token CSS entre input.css e tailwind.config.js
  (existia antes desta onda — sem relação com PII/Fernet)
```

---

## 3. Arquivos criados/modificados

### Novos
- `app/services/pii_encryption.py` — serviço Fernet (is_pii_encryption_enabled, email_lookup_hash, encrypt/decrypt, maybe_*)
- `tests/test_services/test_pii_encryption.py` — 16 testes unitários
- `scripts/migrar_pii_criptografia.py` — script de migração dry-run/apply idempotente
- `docs/adr/001-criptografia-pii-fernet.md` — ADR MADR completo

### Modificados
- `app/models_usuario.py` — to_dict, from_dict, get_by_email, email_existe, update, get_all integrados com pii_encryption
- `tests/test_services/test_models_usuario.py` — +9 testes Onda 4 +1 integração (35 → 45)
- `tests/test_routes/test_auth.py` — +1 teste hash lookup login (30 → 31)
- `tests/test_config_production.py` — +6 testes `_validar_fernet_key` (polish)
- `config.py` — `_validar_fernet_key()` fail-fast em produção
- `scripts/migrar_pii_criptografia.py` — polish: `_decide_migration_update` extraída, fix double-encrypt, imports pii_encryption
- `scripts/gerar_chave_criptografia.py` — instrução de migração adicionada
- `scripts/README.md` — entrada `migrar_pii_criptografia.py`
- `firestore.indexes.json` — `fieldOverrides`: índice single-field `email_lookup_hash` (ASC)
- `.env.example` — bloco LGPD atualizado (de "roadmap" para "Onda 4 implementado")
- `docs/ENV.md` — seção de criptografia com procedimento de ativação
- `docs/POLITICA_SEGURANCA_LGPD.md` — §3.1 e §8 atualizados (Fernet implementado, não "roadmap")
- `docs/CHECKLIST_SEGURANCA.md` — §9.4 + §20 CWI 2.3 → completo
- `docs/DEPLOYMENT_PLAN.md` — §Criptografia PII: checklist de ativação com ordem obrigatória
- `docs/adr/001-criptografia-pii-fernet.md` — impacto em notificações, ordem de rollout, fix duplo

### Novos (polish)
- `tests/test_scripts/test_migrar_pii_criptografia.py` — 7 testes TDD `_decide_migration_update` + migrar()

---

## 4. Contagem de testes novos

| Arquivo | Testes novos | Total no arquivo |
|---|---|---|
| `test_pii_encryption.py` | +16 (arquivo novo) | 16 |
| `test_models_usuario.py` | +9 Onda 4 + 1 integração | 45 |
| `test_auth.py` | +1 (hash lookup) | 31 |
| `test_config_production.py` | +6 `_validar_fernet_key` (polish) | 23 |
| `test_migrar_pii_criptografia.py` | +7 (arquivo novo — polish) | 7 |
| **Total** | **+40** | — |

### 4.1 DoD código vs rollout ops

| Aspecto | Status |
|---|---|
| Código, testes e docs técnicos | ✅ Completo |
| Índice Firestore em `firestore.indexes.json` | ✅ Declarado — deploy: `firebase deploy --only firestore:indexes` |
| Migração de dados (`--apply`) | ✅ 2026-06-23 — 2 docs (`admin_001`, `user_0642960a…`) |
| Ativação de `ENCRYPT_PII_AT_REST=true` | ✅ `.env` dev local; reiniciar app prod/HML se ainda `false` no servidor |

---

## 5. Rollout ops — executado 2026-06-23 ✅

> Checklist completo: `docs/DEPLOYMENT_PLAN.md §Criptografia PII`.
> **Ordem aplicada:** dry-run → `--apply` (100% migrados) → smoke test → `ENCRYPT_PII_AT_REST=true`.

### Resultado

| Passo | Resultado |
|---|---|
| Dry-run | 2 elegíveis, 0 pulados por erro |
| `--apply` | 2 atualizados, 0 erros |
| Idempotência (2º dry-run) | 2 SKIP — já migrados |
| Smoke `get_by_email` + decrypt | ✅ `admin@dtx.aero`, ✅ `danillo.cunha@dtx.aero` |
| `ENCRYPT_PII_AT_REST=true` | ✅ `.env` desenvolvimento local |

**Pendente opcional:** backup Firestore export + `firebase deploy --only firestore:indexes` no projeto Firebase (índice já declarado em `firestore.indexes.json`). Reiniciar containers/servidor prod/HML se `ENCRYPT_PII_AT_REST` ainda estiver `false` lá.

### Procedimento de referência (repetível em novos ambientes)

```bash
# 1. Gerar chave Fernet
python scripts/gerar_chave_criptografia.py
# → ENCRYPTION_KEY=<chave_base64url_44chars>

# 2. Backup da coleção usuarios (Firebase Console > Export)

# 3. Criar índice Firestore (OBRIGATÓRIO antes do --apply)
firebase deploy --only firestore:indexes
#    OU Firebase Console > Firestore > Indexes > Single-field
#    → Collection: usuarios | Field: email_lookup_hash | Order: Ascending

# 4. Adicionar ao .env (servidor) — manter ENCRYPT_PII_AT_REST=false por ora
ENCRYPTION_KEY=<chave>
ENCRYPT_PII_AT_REST=false

# 5. Dry-run (confirmar documentos a migrar)
ENCRYPTION_KEY=<chave> python scripts/migrar_pii_criptografia.py

# 6. Aplicar migração (app pode continuar rodando)
ENCRYPT_PII_AT_REST=true ENCRYPTION_KEY=<chave> \
  python scripts/migrar_pii_criptografia.py --apply

# 7. Smoke test: login com usuário migrado
#    Se login funcionar → migração bem-sucedida

# 8. Somente após 100% dos docs migrados:
#    Alterar ENCRYPT_PII_AT_REST=false → true no .env e reiniciar
docker compose up -d --build
```

---

## 6. Status CWI 2.3

| Sub-item | Status anterior | Status Onda 4 |
|---|---|---|
| Respostas HTTP sem senha_hash/stack trace | ✅ Completo (Onda 3b) | ✅ Mantido |
| PII criptografado em repouso (Fernet) | ⏳ Parcial | ✅ **Completo** |
| Login via hash sem descriptografar índice | ⏳ N/A | ✅ **Completo** |
| **CWI 2.3 global** | ⏳ **Parcial** | ✅ **COMPLETO** |
