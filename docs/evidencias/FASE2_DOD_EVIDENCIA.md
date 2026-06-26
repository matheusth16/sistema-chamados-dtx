# Evidência Operacional — Fase 2 DoD (Isolamento Supervisor + Claim + Supervisor Obrigatório)

| Campo | Valor |
|---|---|
| **Escopo** | Fase 2 — Isolamento por supervisor (`supervisor_ids_com_acesso`), claim `Aberto → Em Atendimento`, supervisor obrigatório na criação, 7 lacunas críticas fechadas |
| **Data de execução** | 2026-06-24 |
| **Executado por** | Matheus Costa — DTX Aerospace Engineering |
| **Status final** | **DoD 100% — APROVADO** |

---

## 1. Ciclo de qualidade

### 1.1 ruff

```
$ ruff check app/ tests/ --fix
All checks passed!

$ ruff format app/ tests/
162 files left unchanged
```

### 1.2 bandit

```
$ bandit -r app/ -ll

Test results:
    Total issues (by severity):
        High: 0 | Medium: 0 | Low: 16
```

> 16 low-severity são todos pré-existentes (subprocess, assert, hardcoded /tmp) — nenhum introduzido pela Fase 2.

### 1.3 pytest — módulos Fase 2 (isolado)

```
$ pytest tests/test_services/test_permissions.py \
         tests/test_services/test_status_service.py \
         tests/test_services/test_chamados_criacao_service.py \
         tests/test_services/test_edicao_chamado_service.py \
         -v --tb=short --no-cov

93 passed in 4.82s
```

### 1.4 pytest — rotas Fase 2 (filtrado)

```
$ pytest tests/test_routes/test_api_gaps.py \
         tests/test_routes/test_dashboard.py \
         -v --tb=short --no-cov \
         -k "bulk or supervisor or colega or claim or filtro_perfil or responsavel"

26 passed, 74 deselected in 7.31s
```

### 1.5 pytest — regressão supervisor

```
$ pytest tests/test_regression/ -k supervisor -v --no-cov

17 passed, 76 deselected in 8.77s
```

### 1.6 pytest — scripts migração

```
$ pytest tests/test_scripts/test_migrar_scripts.py -k supervisor_ids -v --no-cov

4 passed, 32 deselected in 1.37s
```

### 1.7 pytest — suite completa (sem regressão)

```
$ pytest --tb=short -q --no-cov

1723 passed in 73.61s — 0 falhas
```

**Zero regressões. 1723 testes passando.**

### 1.8 Cobertura dos módulos Fase 2

```
$ python scripts/check_coverage_per_module.py --json-only

app/services/permissions.py              90.9%   OK
app/services/status_service.py           94.1%   OK
app/services/chamados_criacao_service.py 88.1%   OK
app/services/edicao_chamado_service.py   91.3%   OK

Resultado: 54/54 módulos >= 85% | 0 abaixo do gate
[GATE OK] Todos os 54 módulos elegíveis >= 85%.
```

---

## 2. Smoke checklist de código

| Arquivo | Elemento esperado | Confirmado |
|---|---|---|
| `app/services/permissions.py` | `usuario_pode_ver_chamado` + `calcular_supervisor_ids_com_acesso` | ✅ linhas 21, 56 |
| `app/routes/api.py` | `_aplicar_filtro_perfil` → `array_contains supervisor_ids_com_acesso` | ✅ linha 503 |
| `app/routes/api.py` | `bulk_atualizar_status` → `usuario_pode_ver_chamado` + `atualizar_status_chamado` | ✅ linhas 172, 216 |
| `app/routes/dashboard.py` | alterar status → `usuario_pode_ver_chamado` (não só área) | ✅ linhas 93, 163, 229, 273 |
| `app/services/status_service.py` | claim + `data_em_atendimento` + `Config.SLA_TIMEZONE` + `supervisor_ids_com_acesso` | ✅ linhas 118–127 |
| `app/services/chamados_criacao_service.py` | supervisor obrigatório (`Selecione um supervisor`) + ID válido na área (`Supervisor inválido`) | ✅ linhas 156–167 |
| `app/services/edicao_chamado_service.py` | recalcula `supervisor_ids_com_acesso` ao trocar responsável | ✅ linhas 124–128 |
| `app/models.py` | campos `supervisor_ids_com_acesso`, `data_em_atendimento`, `participantes` | ✅ linhas 41–85 |
| `firestore.indexes.json` | índice `supervisor_ids_com_acesso` ARRAY_CONTAINS | ✅ linha 187 |
| `scripts/migrar_supervisor_ids_com_acesso.py` | `--dry-run` / `--apply` | ✅ linhas 13–18 |

---

## 3. Checklist funcional (critérios de aceite Fase 2)

- [x] Matheus não vê ticket da Júlia (mesma área, owner diferente) — `test_supervisor_nao_ve_ticket_atribuido_a_colega`, `test_regression_supervisor_colega_owner_nao_ve_na_fila`, `test_bulk_status_supervisor_nao_altera_ticket_de_colega_mesma_area`
- [x] Fila sem owner visível para supervisor da área — `test_supervisor_ve_fila_sem_owner_na_sua_area`, `test_bulk_status_em_atendimento_fila_delega_atualizar_status_chamado`
- [x] Participante vê ticket — `test_supervisor_ve_ticket_onde_e_participante`, regra em `permissions.py:56`
- [x] Claim: `Em Atendimento` + `responsavel_id=None` → atribui ao logado — `test_claim_atribui_owner_ao_em_atendimento`, `test_claim_atualiza_responsavel_nome`
- [x] `data_em_atendimento` gravado; Escada A congelada após Em Atendimento — `test_claim_data_em_atendimento_usa_config_sla_timezone`, `test_escada_a_congelada_ao_virar_em_atendimento`
- [x] Supervisor obrigatório na criação quando área tem supervisores — `test_criacao_falha_sem_supervisor_quando_area_tem_supervisores`, `test_criacao_falha_quando_responsavel_id_invalido_para_area`
- [x] `/api/bulk-status` respeita `usuario_pode_ver_chamado` — `test_bulk_status_supervisor_nao_altera_ticket_de_colega_mesma_area`
- [x] Dashboard POST respeita `usuario_pode_ver_chamado` — `test_dashboard_alterar_status_supervisor_colega_owner_negado`, `test_admin_post_status_change_supervisor_sem_permissao_redireciona`
- [x] `supervisor_ids_com_acesso` gravado na criação — `test_criacao_grava_supervisor_ids_com_acesso`
- [x] `supervisor_ids_com_acesso` recalculado no claim — `test_claim_atribui_owner_ao_em_atendimento` (via `calcular_supervisor_ids_com_acesso`)
- [x] `supervisor_ids_com_acesso` recalculado na edição de responsável — `test_edicao_troca_responsavel_atualiza_supervisor_ids_com_acesso`

**Checklist qualidade:**
- [x] `pytest --tb=short -q` verde — 1723 passed, 0 failed
- [x] `ruff check` + `ruff format` limpos — `All checks passed! 162 files left unchanged`
- [x] `bandit -r app/ -ll` limpo — `High: 0 | Medium: 0`
- [x] `check_coverage_per_module.py` — 54/54 módulos >= 85%

---

## 4. Lacunas críticas fechadas (7)

| # | Lacuna | Arquivo | Teste |
|---|---|---|---|
| 1 | `bulk-status` bypass supervisor isolation | `app/routes/api.py` | `test_bulk_status_supervisor_nao_altera_ticket_de_colega_mesma_area` |
| 2 | Dashboard POST usava `supervisor_pode_alterar_chamado` (só área) | `app/routes/dashboard.py` | `test_dashboard_alterar_status_supervisor_colega_owner_negado` |
| 3 | Criação aceitava `responsavel_id` inválido para a área | `app/services/chamados_criacao_service.py` | `test_criacao_falha_quando_responsavel_id_invalido_para_area` |
| 4 | Edição de responsável não recalculava `supervisor_ids_com_acesso` | `app/services/edicao_chamado_service.py` | `test_edicao_troca_responsavel_atualiza_supervisor_ids_com_acesso` |
| 5 | Claim não gravava campo `responsavel` (nome) | `app/services/status_service.py` | `test_claim_atualiza_responsavel_nome` |
| 6 | `data_em_atendimento` hardcoded `"America/Sao_Paulo"` em vez de `Config.SLA_TIMEZONE` | `app/services/status_service.py` | `test_claim_data_em_atendimento_usa_config_sla_timezone` |
| 7 | Sem testes unitários para `calcular_supervisor_ids_com_acesso` + regressão isolamento | `tests/test_services/test_permissions.py` | `TestCalcularSupervisorIdsComAcesso` (6 casos) + `test_regression_supervisor_colega_owner_nao_ve_na_fila` |

---

## 5. Documentação criada/atualizada

| Arquivo | Conteúdo | Status |
|---|---|---|
| `docs/INDICES_FIRESTORE.md` | Entrada `supervisor_ids_com_acesso` ARRAY_CONTAINS (Fase 2, ADR-004) | ✅ Atualizado |
| `scripts/README.md` | Seção `migrar_supervisor_ids_com_acesso.py` com dry-run/apply + ordem de deploy | ✅ Atualizado |
| `docs/plans/2026-06-23-escalonamento-sla.md` | Linha de conclusão Fase 2 ao final da seção | ✅ Atualizado |
| `.cursor/plans/escalonamento_e_sla_dtx_d3e9e5bb.plan.md` | `fase-2-permissoes` → `status: completed` | ✅ Atualizado |
| `docs/evidencias/FASE2_DOD_EVIDENCIA.md` | Este arquivo | ✅ Criado |

---

## 6. Ação operacional obrigatória pós-deploy (staging/prod)

```bash
# 1. Após deploy da Fase 2 no ambiente alvo:

# Verificar volume sem gravar nada
python scripts/migrar_supervisor_ids_com_acesso.py --dry-run

# Aplicar backfill (batches de 500 — seguro para coleções grandes)
python scripts/migrar_supervisor_ids_com_acesso.py --apply

# 2. Validar no console Firestore que chamados legados têm supervisor_ids_com_acesso preenchido
# 3. Confirmar que supervisores veem seus chamados no dashboard após migração
```

> **Atenção:** sem a migração, chamados criados antes da Fase 2 não têm o campo `supervisor_ids_com_acesso`
> e **não aparecem** no dashboard do supervisor (query `array_contains` retorna vazio para campo ausente).

---

## 7. Declaração final

> **Fase 2 (Isolamento Supervisor + Claim + Supervisor Obrigatório) — DoD 100% APROVADO.**
>
> 1723 testes passando (0 falhas). Cobertura: permissions.py 90.9%, status_service.py 94.1%,
> chamados_criacao_service.py 88.1%, edicao_chamado_service.py 91.3% — todos acima de 85%.
> 7 lacunas críticas fechadas com TDD (teste falhando → produção → verde).
> Ruff CLEAN, Bandit 0 HIGH/MEDIUM.
>
> **Próxima fase:** Fase 3 — Transferir Área + Escalonar para Colega (`escalonamento_service.py`).
> Pré-requisito satisfeito: Fase 2 concluída.
