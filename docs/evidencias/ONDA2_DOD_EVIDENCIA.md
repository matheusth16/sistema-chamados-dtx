# Evidência Operacional — Onda 2 DoD 100% (`ativo=false`)

| Campo | Valor |
|---|---|
| **Escopo** | Onda 2 — Desativação de usuários via `ativo=false` (baseline DTX) |
| **Data de execução** | 2026-06-22 |
| **Executado por** | Matheus Costa — DTX Aerospace Engineering |
| **Status final** | **DoD 100% — APROVADO** |

---

## 1. Ciclo de qualidade

### 1.1 ruff

```
$ ruff check app/ tests/ scripts/ --fix
All checks passed!

$ ruff format app/ tests/ scripts/
1 file reformatted, 175 files left unchanged
```

> **Nota:** 3 erros pré-existentes corrigidos durante este fechamento: E741 (`chamados_criacao_service.py:136,142` — variável ambígua `l` → `lnk`); F841 (`test_app_init.py:87` — `mock_sched` não utilizado → removido).

### 1.2 bandit

```
$ bandit -r app/ -ll

Test results:
    No issues identified.
    Total issues: High: 0 | Medium: 0 | Low: 15
```

### 1.3 pytest — Onda 2 (isolado)

```
$ pytest tests/test_routes/test_auth.py::{CT-AUTH-I1,I2,I3,I4} -v
4 passed in 6.30s

$ pytest tests/test_services/test_models_usuario.py -k "ativo"
7 passed, 27 deselected in 4.79s

$ pytest tests/test_routes/test_usuarios.py -k "desativar or ativar"
5 passed, 43 deselected in 5.01s
```

**Total Onda 2: 16 testes, 0 falhas.**

### 1.4 pytest — suite completa

```
$ pytest --tb=short -q
1487 passed in 62.51s
Cobertura geral: 94.79% (gate: 85%) — gate global OK; gate 52/52 módulos OK
```

---

## 2. Referências de código — Onda 2

| Arquivo | Função / Linha | Descrição |
|---|---|---|
| `app/models_usuario.py` | `__init__`, `to_dict`, `from_dict`, `update` | Campo `ativo: bool = True`; `from_dict` usa `data.get("ativo", True)` para retrocompat. |
| `app/routes/auth.py:79–83` | `login()` | Bloqueio pré-sessão para conta inativa; NÃO incrementa lockout de brute-force |
| `app/__init__.py:87–90` | `load_user()` | `user_loader` retorna `None` quando `ativo=False` — invalida sessão ativa |
| `app/routes/usuarios.py:279–305` | `desativar_usuario()` | POST `/admin/usuarios/<id>/desativar`; protege: não-próprio, não-root-admin |
| `app/routes/usuarios.py:308–327` | `ativar_usuario()` | POST `/admin/usuarios/<id>/ativar`; sem restrições além de existência |
| `app/routes/usuarios.py:172–175` | `editar_usuario()` POST | Checkbox `ativo` no formulário de edição |
| `app/templates/usuario_form.html` | bloco `{% if usuario %}` | Checkbox `name="ativo"` exibido apenas no modo edição |
| `app/translations.json` | 8 chaves novas | `account_disabled`, `user_deactivated_success`, `user_activated_success`, `cannot_deactivate_own_account`, `cannot_deactivate_root_admin`, `active_status_label`, `inactive_status_label`, `deactivate_account_help` — PT-BR / EN / ES |
| `scripts/migrar_usuarios_ativo.py` | `migrar()` | Backfill idempotente do campo `ativo` em docs legados |

---

## 3. Smoke dry-run — script de migração

```
$ python scripts/migrar_usuarios_ativo.py
============================================================
  migrar_usuarios_ativo.py  | modo: DRY-RUN
============================================================

  Use --apply para executar as alteracoes no Firestore.

=== usuarios - backfill campo ativo ===
  [DRY-RUN] 'admin@dtx.com' (doc=admin_001) -- sem campo ativo -> set ativo=true
  [DRY-RUN] 'novo@test.com' (doc=user_25321...) -- sem campo ativo -> set ativo=true
  [DRY-RUN] 'danillo.cunha@dtx.aero' (doc=user_587cdf...) -- sem campo ativo -> set ativo=true
  [DRY-RUN] 'matheus.costa@dtx.aero' (doc=user_71357...) -- sem campo ativo -> set ativo=true
  [DRY-RUN] 'matheus00237@gmail.com' (doc=user_bfd3bd...) -- sem campo ativo -> set ativo=true
  [DRY-RUN] 'julia.salgado@dtx.aero' (doc=user_c4197...) -- sem campo ativo -> set ativo=true
  [DRY-RUN] 'demo.solicitante@dtx.com' (doc=user_demo...) -- sem campo ativo -> set ativo=true

  Processados: 7 | Atualizados: 7 | Pulados: 0

=== Concluido (nenhuma alteracao gravada) ===
```

**Status `--apply`:** PENDENTE — não executado nesta sessão. Aguardando autorização explícita antes de backfillar os 7 documentos reais no Firestore de produção.

> **Retrocompatibilidade garantida:** `from_dict` usa `data.get("ativo", True)` — documentos sem o campo se comportam como contas ativas até a migração ser aplicada.

---

## 4. Review de segurança (R3)

A skill `review-security` foi executada sobre o diff completo da branch (incluindo todos os arquivos da Onda 2). Resultado: **CLEAN**.

| Severity | Location | Finding | Ação |
|---|---|---|---|
| — | `app/routes/auth.py:79–83` | Bloqueio de conta inativa antes de `login_user()` — fluxo correto | Sem achados |
| — | `app/__init__.py:87–90` | `user_loader` retorna `None` para `ativo=False` — padrão Flask-Login | Sem achados |
| — | `app/routes/usuarios.py` rotas `/desativar`, `/ativar` | `@requer_perfil("admin")`, proteção contra auto-desativação e `admin@dtx.aero` | Sem achados |
| — | `scripts/migrar_usuarios_ativo.py` | Dry-run por padrão; `--apply` obrigatório; operação idempotente | Sem achados |

**Achados HIGH:** 0
**Achados MEDIUM:** 0
**Achados LOW/INFO:** nenhum introduzido pela Onda 2

---

## 5. Checklist `docs/CHECKLIST_SEGURANCA.md` — seção 1.3

```
### 1.3 Sessão e autenticação

- [x] Usuários desativados não conseguem fazer login
      Arquivo: models_usuario.py (campo ativo); auth.py:79–83 (bloqueio pré-sessão);
               __init__.py:87–90 (user_loader invalida sessão ativa)
      Testes: CT-AUTH-I1 a I4 (test_auth.py); 7 testes de modelo; 5 testes admin
      Migração: scripts/migrar_usuarios_ativo.py — dry-run identificou 7 docs legados
      Resolvido 2026-06-22 — Onda 2 (desativação de usuários)
```

Verificado em `docs/CHECKLIST_SEGURANCA.md` linha 94–100 (marcado `[x]` com evidência inline).

---

## 6. Checklist manual de comportamento

| Cenário | Esperado | Evidência |
|---|---|---|
| Login senha OK + `ativo=False` | Não autentica; flash `account_disabled`; NÃO incrementa lockout | CT-AUTH-I1, CT-AUTH-I2, CT-AUTH-I3 (4 passed) |
| Login senha OK + `ativo=True` | Fluxo normal de autenticação | Testes existentes de login bem-sucedido |
| Sessão ativa + usuário desativado no Firestore | Próximo request desloga (`user_loader` → `None` → `@login_required` → redirect `/login`) | CT-AUTH-I4 (1 passed) |
| Admin POST `/admin/usuarios/<id>/desativar` | `usuario.update(ativo=False)`, cache invalidado, flash de sucesso | `test_admin_desativa_usuario` (passed) |
| Admin tenta desativar a si mesmo | Bloqueado, flash `cannot_deactivate_own_account` | `test_admin_nao_pode_desativar_si_mesmo` (passed) |
| Admin tenta desativar `admin@dtx.aero` | Bloqueado, flash `cannot_deactivate_root_admin` | `test_admin_nao_pode_desativar_root_admin` (passed) |
| Doc Firestore sem campo `ativo` (legado) | `from_dict` usa default `True` — conta ativa | `test_from_dict_sem_campo_ativo_usa_default_true` (passed) |

**Todos os cenários cobertos por testes automatizados — 16/16 passando.**

---

## 7. Declaração final

> **Onda 2 DoD 100% — baseline DTX atende.**
>
> Todos os critérios de aceitação estão implementados, testados (16 testes Onda 2 + 1487 suite completa, 0 falhas), verificados por ruff/bandit/review-security (CLEAN) e documentados (CHECKLIST_SEGURANCA.md §1.3 [x], scripts/README.md, este artefato).
>
> Único ponto pendente operacional: `--apply` na migração do Firestore (7 docs legados) aguarda autorização explícita.

---

## 8. Sugestão de commit (não executado)

```
docs(auth): Add Onda 2 operational evidence for ativo deactivation

- docs/evidencias/ONDA2_DOD_EVIDENCIA.md: artefato DoD completo
- docs/CHECKLIST_SEGURANCA.md §1.3: marcado [x] com evidência inline
- scripts/README.md: seção migrar_usuarios_ativo.py adicionada
- fix(ruff): E741 chamados_criacao_service.py lnk; F841 test_app_init.py

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```
