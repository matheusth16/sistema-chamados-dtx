# Encerramento — Plano Correção Matriz CWI v2

| Campo | Valor |
|---|---|
| **Projeto** | Correção Matriz CWI v2 — Sistema de Chamados DTX Aerospace |
| **Status** | **Encerrado** (código + rollout Fernet Firestore) |
| **Data** | 2026-06-23 |
| **Executado por** | Matheus Costa — DTX Aerospace Engineering |
| **Revisado por** | Matheus Costa — DTX Aerospace Engineering |

---

## 1. Resumo executivo

O plano Correção Matriz CWI v2 implementou, em 6 ondas, todos os 11 sub-itens do checklist CWI básico de segurança, o baseline DTX de desativação de usuários e a criptografia LGPD Fernet de PII em repouso. Em 2026-06-23 concluiu-se o rollout operacional Fernet: migração `--apply` de 2 usuários no Firestore, smoke test de lookup/login via `email_lookup_hash` e ativação de `ENCRYPT_PII_AT_REST=true` no ambiente local. A suite possui **1 592 testes passando** (94,14 % cobertura); falhas locais conhecidas: 10× `APScheduler` ausente no Python global + 1× CSS design system.

---

## 2. Metas atingidas

| Meta | Sub-itens | Status | Evidência |
|---|---|---|---|
| **CWI básico 11/11** | 1.1–4.2 | ✅ | `QA_MANUAL_CWI_EVIDENCIA.md` — 15 PASS / 0 FAIL / 2 SKIP ops |
| **Baseline DTX** — `ativo=false` | CWI 1.1 (espírito) | ✅ | `ONDA2_DOD_EVIDENCIA.md` |
| **LGPD Fernet (código)** | CWI 2.3 | ✅ | `ONDA4_DOD_EVIDENCIA.md` |
| **Rollout Fernet (ops)** | CWI 2.3 em repouso | ✅ | Migração 2026-06-23 — 2/2 usuários; smoke OK |

---

## 3. Evidências por onda

| Onda | Escopo | DoD | CWI coberto |
|---|---|---|---|
| **Onda 1** | Permissões centralizadas, IDOR URL+body+download | [`ONDA1_DOD_EVIDENCIA.md`](evidencias/ONDA1_DOD_EVIDENCIA.md) | 1.3 |
| **Onda 2** | Campo `ativo`, login bloqueado, UI admin, i18n, script migração | [`ONDA2_DOD_EVIDENCIA.md`](evidencias/ONDA2_DOD_EVIDENCIA.md) | baseline DTX |
| **Onda 3** | Fail-fast prod, Redis warning, HTTPS redirect | [`ONDA3_DOD_EVIDENCIA.md`](evidencias/ONDA3_DOD_EVIDENCIA.md) | 2.1 |
| **Onda 3b** | Hash Werkzeug, auditoria API, erros genéricos, injection, swagger | [`ONDA3B_DOD_EVIDENCIA.md`](evidencias/ONDA3B_DOD_EVIDENCIA.md) | 2.2 / 3.1 / 3.2 / 4.2 |
| **Onda 4** | Fernet PII, `email_lookup_hash`, migrador, índice | [`ONDA4_DOD_EVIDENCIA.md`](evidencias/ONDA4_DOD_EVIDENCIA.md) | 2.3 |
| **Onda 5** | Staging Basic Auth + VPN-first | [`ONDA5_DOD_EVIDENCIA.md`](evidencias/ONDA5_DOD_EVIDENCIA.md) | 4.1 |
| **QA Manual** | Playbook 11/11 | [`QA_MANUAL_CWI_EVIDENCIA.md`](evidencias/QA_MANUAL_CWI_EVIDENCIA.md) | todos |

---

## 4. Matriz CWI 11/11

Resultado completo em `docs/CHECKLIST_SEGURANCA.md §20`.

| Sub-item | Descrição | Status QA |
|---|---|---|
| 1.1 | Acesso anônimo → 302/401 | PASS |
| 1.2 | Permissão por perfil | PASS |
| 1.3 | IDOR (URL + body + download) | PASS |
| 2.1 | HTTPS redirect em produção | PASS |
| 2.2 | Senha com hash (Werkzeug scrypt) | PASS |
| 2.3 | PII minimizado/criptografado | PASS |
| 3.1 | NoSQL injection sem 500 | PASS |
| 3.2 | Erros genéricos sem stack/tecnologia | PASS |
| 4.1 | Ambiente HML inacessível fora VPN | PASS |
| 4.2 | Swagger inexistente → 404 | PASS |

Fonte: `docs/evidencias/QA_MANUAL_CWI_EVIDENCIA.md` — 15 PASS / 0 FAIL / 2 SKIP ops.

---

## 5. Rollout Fernet — executado 2026-06-23

Procedimento: `docs/DEPLOYMENT_PLAN.md §Criptografia PII (Onda 4)`.

- [ ] Backup da coleção `usuarios` (Firebase Console → Export) — **recomendado antes de novos ambientes**
- [ ] Deploy do índice: `firebase deploy --only firestore:indexes` — **pendente se ainda não deployado em prod**
- [x] Dry-run: 2 documentos elegíveis (`admin_001`, `user_0642960a27a14d08…`)
- [x] Apply: `ENCRYPT_PII_AT_REST=true` + `ENCRYPTION_KEY` → `--apply` — 2 atualizados, 0 erros
- [x] Idempotência: segundo dry-run → 2 SKIP
- [x] Smoke test: `get_by_email` + decrypt OK (`admin@dtx.aero`, `danillo.cunha@dtx.aero`)
- [x] Flag local: `ENCRYPT_PII_AT_REST=true` no `.env` de desenvolvimento
- [ ] Reiniciar app **em produção/HML** com mesma `ENCRYPTION_KEY` + flag `true` (se ainda não feito no servidor)

---

## 6. Backlog pós-projeto

Itens documentados, sem prazo — não bloqueiam encerramento.

| Item | Referência | Prioridade |
|---|---|---|
| Flash HTML com `str(e)` | `docs/CHECKLIST_SEGURANCA.md §8.5` | Baixa |
| Rotação automatizada de `ENCRYPTION_KEY` | `docs/adr/001-criptografia-pii-fernet.md` | Média |
| PII em `chamados.solicitante_nome` | escopo LGPD ampliado | Média |
| Over-fetch supervisor `areas=[]` | Onda 1 ressalva | Baixa |
| Early IDOR em `api_editar_chamado` | defense-in-depth | Baixa |
| Falha CSS `test_dtx_light_invariants` | design system | Baixa |
| `APScheduler` no Python global local | `pip install APScheduler>=3.10.0` | Baixa (env dev) |

---

## 7. Verificação final executada (2026-06-23)

| Comando | Resultado |
|---|---|
| `python scripts/executar_qa_manual_cwi.py` | ✅ 15 PASS / 0 FAIL / 2 SKIP |
| `pytest --tb=short -q` | 1592 passed, 11 failed (10 APScheduler + 1 CSS) — 94,14 % cov |
| `migrar_pii_criptografia.py --apply` | ✅ 2/2 migrados |
| Smoke `get_by_email` encryption ON | ✅ 2/2 usuários |

```bash
# Reproduzir verificação
python scripts/executar_qa_manual_cwi.py
pytest --tb=short -q
python scripts/migrar_pii_criptografia.py   # deve mostrar 2 SKIP
```

---

## 8. Aprovação

| Campo | Valor |
|---|---|
| **Projeto** | Correção Matriz CWI v2 |
| **Status** | **Encerrado** |
| **Executado por** | Matheus Costa — DTX Aerospace Engineering |
| **Revisado por** | Matheus Costa — DTX Aerospace Engineering |
| **Data** | 2026-06-23 |
