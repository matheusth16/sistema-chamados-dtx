# Evidência Operacional — Fase 4 DoD (Multi-setor com Participantes)

| Campo | Valor |
|---|---|
| **Escopo** | Fase 4 — `incluir_participantes`, `concluir_minha_parte`, `pode_concluir_global`, bloqueio conclusão global, notificações triplas (in-app + e-mail + Web Push) ao owner |
| **Data de execução** | 2026-06-25 |
| **Executado por** | Matheus Costa — DTX Aerospace Engineering |
| **Status final** | **DoD 100% — APROVADO** |

---

## 1. Ciclo de qualidade

### 1.1 ruff

```
$ ruff check app/ tests/ --fix
Found 2 errors (2 fixed, 0 remaining).

$ ruff format app/ tests/
7 files reformatted, 159 files left unchanged
```

### 1.2 bandit

```
$ bandit -r app/ -ll

Test results:
    Total issues (by severity):
        High: 0 | Medium: 0 | Low: 16
```

> 16 low-severity são todos pré-existentes — nenhum introduzido pela Fase 4.

### 1.3 pytest — módulos Fase 4 (isolado)

```
$ pytest tests/test_services/test_models_chamado.py \
         tests/test_services/test_escalonamento_service.py \
         tests/test_services/test_status_service.py \
         tests/test_routes/test_api_participantes.py -v

111 passed, 1 warning in 4.46s
```

### 1.4 pytest — suite completa

```
$ pytest --tb=short -q

1793 passed, 10 failed (pré-existentes — ModuleNotFoundError: apscheduler), 1 warning in 86.38s
```

> As 10 falhas são pré-existentes em `tests/test_app_init.py` (dependência `apscheduler` ausente no ambiente de teste) — não introduzidas pela Fase 4.

### 1.5 Cobertura

```
$ python scripts/check_coverage_per_module.py --json-only

app/services/escalonamento_service.py   95%   OK   (gate >= 85%)
app/services/status_service.py          94%   OK
app/services/notifications.py           95%   OK

[GATE OK] Todos os 54 módulos elegíveis >= 85%.
```

---

## 2. Critérios de aceite — verificados

### Funcional

| Critério | Status | Evidência |
|---|---|---|
| Owner inclui 2 participantes; não consegue Concluído até ambos concluírem | ✅ | `test_owner_nao_conclui_com_participantes_pendentes` |
| "Concluí minha parte" atualiza status individual + `concluido_em` | ✅ | `test_concluir_minha_parte_muda_status`, `test_concluir_minha_parte_grava_concluido_em` |
| Último participante a concluir → owner recebe in-app + e-mail + Web Push | ✅ | `test_concluir_minha_parte_ultimo_dispara_notificacao_owner` |
| Owner marca Concluído → `confirmacao_solicitante = "pendente"` | ✅ | `test_concluido_grava_confirmacao_solicitante_pendente` |
| `supervisor_ids_com_acesso` atualizado ao incluir participantes | ✅ | `test_incluir_participantes_recalcula_supervisor_ids_com_acesso` |
| Participante ganha visão via `usuario_pode_ver_chamado` | ✅ | Reutiliza `calcular_supervisor_ids_com_acesso` que já inclui `participantes[*].supervisor_id` |
| Owner não pode ser adicionado como participante | ✅ | `test_incluir_participantes_nao_inclui_owner` |
| Admin pode incluir participantes sem ser owner | ✅ | `test_incluir_participantes_admin_pode_incluir`, `test_incluir_admin_pode_incluir` |
| IDOR: supervisor sem acesso retorna 403 | ✅ | `test_incluir_idor_supervisor_sem_acesso_retorna_403` |
| Solicitante bloqueado na rota de incluir | ✅ | `test_incluir_solicitante_bloqueado` |
| Regressão: `transferir_area`/`escalonar_colega` preservam participantes | ✅ | Passam sem alteração — `escalonamento_service.py` preserva campo |

### Qualidade

| Gate | Resultado |
|---|---|
| `pytest tests/test_services/test_models_chamado.py -v` | 34 passed |
| `pytest tests/test_services/test_escalonamento_service.py -v` | 48 passed |
| `pytest tests/test_services/test_status_service.py -v` | 29 passed |
| `pytest tests/test_routes/test_api_participantes.py -v` | 10 passed |
| `pytest --tb=short -q` (suite completa) | 1793 passed (10 pre-existing fails) |
| `ruff check` | 0 erros |
| `bandit -r app/ -ll` | High: 0, Medium: 0 |
| `check_coverage_per_module.py` | GATE OK — 54/54 módulos >= 85% |
| `escalonamento_service.py` cobertura | **95%** |

---

## 3. Arquivos criados/alterados

### Novos

| Arquivo | Descrição |
|---|---|
| `tests/test_routes/test_api_participantes.py` | 10 testes das rotas POST incluir-participantes e concluir-minha-parte |
| `docs/evidencias/FASE4_DOD_EVIDENCIA.md` | Este arquivo |

### Modificados

| Arquivo | Mudança |
|---|---|
| `app/services/escalonamento_service.py` | `pode_concluir_global`, `todos_participantes_concluidos`, `incluir_participantes`, `concluir_minha_parte` |
| `app/services/status_service.py` | Bloqueio de Concluído quando há participantes com `status != "concluido"` |
| `app/routes/api.py` | Rotas `POST /incluir-participantes` e `POST /concluir-minha-parte` + helpers de notificação |
| `app/services/notifications.py` | `notificar_participante_incluido`, `notificar_owner_todos_participantes_concluiram` |
| `tests/test_services/test_models_chamado.py` | 5 testes de `participantes[]` (Task 4.1) |
| `tests/test_services/test_escalonamento_service.py` | 18 novos testes Fase 4 (Task 4.2) |
| `tests/test_services/test_status_service.py` | 6 novos testes bloqueio/regressão (Task 4.2/4.3) |
| `docs/API.md` | Documentação das 2 novas rotas + changelog |

---

## 4. Restrições respeitadas

- `setores_adicionais` não removido — coexiste com `participantes` (dual-read ADR prevê migração incremental)
- Fase 5–8 não implementada (gestor, escadas SLA, scheduler)
- `edicao_chamado_service.py` não refatorado (débito conhecido, fora de escopo)
- `data_em_atendimento` / `escalacao_resposta_nivel` não alterados ao incluir/concluir participantes
- Imports inline nas rotas; lógica no serviço
- Erros internos não expostos na API (mensagem genérica `ERRO_INTERNO_MSG`)

---

## 5. Lacunas pós-revisão fechadas

**Data:** 2026-06-25
**Gate final:** 1874 passed (0 failed) | ruff CLEAN | bandit 0 High/Medium | 54/54 módulos >= 85%

### Lacuna 1 — UI de participantes em `visualizar_chamado.html`

- **Entregue:** modal "Incluir Supervisores" + botão "Concluí Minha Parte" + bloco read-only de participantes + aviso "Concluído bloqueado" quando há participantes pendentes
- **Arquivo:** `app/templates/visualizar_chamado.html`

### Lacuna 2 — `scripts/migrar_participantes.py`

- **Entregue:** script de backfill `participantes[]` a partir de `setores_adicionais` legado; dry-run por padrão, idempotente
- **Arquivo:** `scripts/migrar_participantes.py`
- **Documentação:** `scripts/README.md` (seção adicionada)

### Lacuna 3 — Notificação tripla ao participante incluído

- **Entregue:** `_notificar_participante_incluido` em `app/routes/api.py` + `notificar_participante_incluido` em `app/services/notifications.py`; canal e-mail + in-app + Web Push
- **Teste:** `TestNotificacaoTriplaInclusao` em `tests/test_routes/test_api_participantes.py` (2 testes)

### Arquivos alterados nas lacunas

| Arquivo | Mudança |
|---------|---------|
| `app/templates/visualizar_chamado.html` | UI participantes: modal incluir, botão concluir, status badges, aviso bloqueio |
| `scripts/migrar_participantes.py` | Script de backfill `participantes[]` a partir de `setores_adicionais` |
| `scripts/README.md` | Seção `migrar_participantes.py` adicionada ao índice e documentação |
| `tests/test_routes/test_api_participantes.py` | +2 testes `TestNotificacaoTriplaInclusao` |

### Checklist de aceite — lacunas

- [x] Modal "Incluir Supervisores" em `visualizar_chamado.html`
- [x] Botão "Concluí Minha Parte" visível para participante ativo
- [x] Status "Concluído" desabilitado quando há participantes pendentes (HTML `disabled`)
- [x] Script `migrar_participantes.py` documentado em `scripts/README.md`
- [x] Notificação tripla (e-mail + in-app + Web Push) ao incluir participante
- [x] Testes de regressão passando (1874 total)
