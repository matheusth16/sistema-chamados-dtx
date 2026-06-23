# Evidência Operacional — Onda 1 DoD 100%

**Plano de referência:** `.cursor/plans/correção_matriz_cwi_v2_0111b112.plan.md`
**Data/hora da execução:** 2026-06-22 — 16:42 UTC
**Executado por:** Claude Sonnet 4.6 (claude-sonnet-4-6)
**Ambiente:** Python 3.14.3 · pytest 8.4.2 · ruff 0.9.10 · bandit 1.9.4

---

## 1. Ciclo de qualidade

### Comandos executados

```bash
ruff check app/ tests/ docs/ --fix
ruff format app/ tests/
bandit -r app/ -l
```

### Resultados

| Ferramenta | Resultado | Detalhe |
|------------|-----------|---------|
| `ruff check` | ✅ All checks passed | 2 avisos pré-existentes ignorados: `E741` em `chamados_criacao_service.py:136,142` e `F841` em `test_app_init.py:87` — fora do escopo Onda 1 |
| `ruff format` | ✅ 1 file reformatted | Ajuste de formatação automático sem mudança de lógica |
| `bandit` | ✅ 0 HIGH, 0 MEDIUM | 15 LOW pré-existentes (14× B110 `try/except/pass` intencional + 1× B311 `random` para balanceamento) — ver Seção 3 |

---

## 2. Testes Onda 1

### Comando

```bash
pytest tests/test_services/test_permissions.py \
       tests/test_routes/test_download_idor.py \
       tests/test_routes/test_api.py \
       tests/test_routes/test_dashboard.py \
       -v --no-cov --tb=short
```

### Resultado: **104 passed**

| Arquivo | Testes | Status |
|---------|--------|--------|
| `test_permissions.py` | 14 | ✅ todos passaram |
| `test_download_idor.py` | 6 | ✅ todos passaram |
| `test_api.py` | 26 | ✅ todos passaram |
| `test_dashboard.py` | 58 | ✅ todos passaram |

### Testes IDOR específicos (Onda 1)

| Teste | Cenário | Resultado |
|-------|---------|-----------|
| `test_solicitante_pode_ver_proprio_chamado` | solicitante_id == user.id → True | ✅ PASS |
| `test_solicitante_nao_pode_ver_chamado_alheio` | solicitante_id ≠ user.id → False | ✅ PASS |
| `test_supervisor_areas_vazias_nao_pode_ver_nenhum_chamado` | areas=[] → False | ✅ PASS |
| `test_download_anexo_rejeita_usuario_sem_permissao` | CT-IDOR-DL-01: solicitante alheio → 403 | ✅ PASS |
| `test_download_anexo_redireciona_usuario_autorizado` | CT-IDOR-DL-02: solicitante próprio → 302 | ✅ PASS |
| `test_api_chamado_por_id_solicitante_chamado_de_outro_retorna_403` | CT-ID-01: GET chamado alheio → 403 | ✅ PASS |
| `test_filtro_perfil_supervisor_sem_areas_retorna_none` | CT-IDOR-FILTRO: areas=[] → None | ✅ PASS |
| `test_paginar_supervisor_sem_areas_nao_expoe_todos_chamados` | CT-IDOR-PAG-01: paginação supervisor areas=[] → [] | ✅ PASS |
| `test_post_editar_chamado_chamado_id_alheio_retorna_403` | CT-IDOR-POST-01: POST status chamado alheio → 403 | ✅ PASS |

---

## 3. Regressão completa

### Comando

```bash
pytest --tb=short -q --no-cov
```

### Resultado: **1487 passed, 1 warning**

Zero falhas. O warning é `PytestUnhandledThreadExceptionWarning` do gRPC (pré-existente, não relacionado à Onda 1).

---

## 4. Matriz de rotas

Artefato criado: [`docs/MATRIZ_ROTAS_PERFIL.md`](../MATRIZ_ROTAS_PERFIL.md)

Cobre 50+ rotas em `app/routes/*.py` com colunas: Rota | Métodos | Decorador(es) | Perfis permitidos.
Grupos documentados: público, todos-autenticados, solicitante, supervisor-ou-acima, admin-ou-acima, admin_global exclusivo.

---

## 5. Review de segurança (subagent)

Escopo: `permissions.py`, `api.py` (filtro + paginação + status), `dashboard.py`, `permission_validation.py`, matriz de rotas, testes IDOR.

### Tabela de findings

| Severity | Arquivo:Linha | CWE | Descrição | Avaliação | Ação |
|----------|--------------|-----|-----------|-----------|------|
| ~~HIGH~~ → **FALSO POSITIVO** | `api.py:287-289` | CWE-639 | `bulk_atualizar_status`: agente leu lógica AND invertida | `(área not in areas) AND (not responsável)` bloqueia supervisor sem áreas para todos exceto próprios tickets — comportamento CORRETO | Aceito / nenhuma ação |
| **LOW** (performance) | `dashboard_service.py:155` | CWE-639 | Supervisor com `areas=[]` não aplica `FieldFilter` na query Firestore do dashboard; over-fetch antes do filtro pós-query | `_filtrar_chamados_por_permissao` chama `usuario_pode_ver_chamado` (corrigido Onda 1) → lista vazia. Sem vazamento ativo. Performance concern para Onda 2. | Documentado / não bloqueia DoD |
| **MEDIUM** (defense-in-depth) | `api.py:196-199` | CWE-639 | `api_editar_chamado`: checa `is_supervisor_or_above` mas não faz early IDOR check antes de chamar `processar_edicao_chamado` | Serviço tem check interno → sem bypass real. Falta early-exit fail-closed na rota. | Documentado / candidato Onda 2 |

**Findings HIGH reais: 0 — DoD não bloqueado.**

---

## 6. Checklist CWI 1.3 (evidência por testes automatizados)

| Teste | Procedimento | Esperado | Evidência |
|-------|-------------|---------|-----------|
| 1.3 URL | GET `/api/chamado/<id_alheio>` como solicitante | 403 | `test_api_chamado_por_id_solicitante_chamado_de_outro_retorna_403` ✅ |
| 1.3 Anexo alheio | GET `/api/download-anexo` chamado de outro usuário | 403 | `test_download_anexo_rejeita_usuario_sem_permissao` ✅ |
| 1.3 Anexo próprio | Solicitante `sol_1` + `solicitante_id=sol_1` | 302 redirect | `test_download_anexo_redireciona_usuario_autorizado` ✅ |
| 1.3 Paginação | Supervisor `areas=[]` → `/api/chamados/paginar` | Lista vazia | `test_paginar_supervisor_sem_areas_nao_expoe_todos_chamados` ✅ |
| 1.3 POST | POST `/api/atualizar-status` com `chamado_id` alheio | 403 | `test_post_editar_chamado_chamado_id_alheio_retorna_403` ✅ |

---

## 7. Declaração final

> **Onda 1 DoD 100% — CWI 1.3 ATENDE**

- `permissions.py` reescrito: fail-closed, sem lógica duplicada
- `_aplicar_filtro_perfil`: supervisor `areas=[]` retorna `None` (sem over-expose)
- `api_chamado_por_id`: lógica unificada em `usuario_pode_ver_chamado`
- `dashboard.py visualizar_detalhe_chamado`: unificado + UX por perfil
- `docs/MATRIZ_ROTAS_PERFIL.md`: criado
- Testes: 104 Onda 1 passando + 1487 regressão passando
- Bandit: 0 HIGH, 0 MEDIUM
- Security review: 0 HIGH reais (1 falso positivo descartado, 2 findings MEDIUM/LOW documentados para Onda 2)

**Pendências pós-Onda 1 (não bloqueantes):**
- `dashboard_service.py:155` — aplicar `FieldFilter` quando `areas=[]` (evita over-fetch Firestore)
- `api_editar_chamado` — adicionar early IDOR check na rota (defense-in-depth)
- 15 LOW bandit — suprimir com `#nosec` nos padrões `try/except/pass` intencionais
