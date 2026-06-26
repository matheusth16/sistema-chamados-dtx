# Onda 6 — Escalonamento e SLA Gerencial: Evidência DoD (Fase 8)

**Data de conclusão:** 2026-06-26
**Implementado por:** Matheus Costa + Claude Sonnet 4.6
**Status global:** 10 PASS | 0 FAIL | 0 SKIP

---

## Resumo executivo

A Onda 6 (Fases 1–7 + aceite Fase 8) implementa o épico completo de Escalonamento/SLA Gerencial
(ADR-004). Inclui: motor de tempo útil DTX (business_time), isolamento de supervisor por
`supervisor_ids_com_acesso`, claim ao primeiro Em Atendimento, transferência entre áreas
(anti-órfão), escalonamento entre colegas, multi-setor com participantes, conclusão parcial,
perfil Gestor read-only, Escada A (notificação gerencial por atraso de resposta), Escada B
(notificação pós-estouro de prazo de resolução) e avisos preventivos 50%/80%.

A Fase 8 fecha o épico com aceite formal: script QA automatizado (10 cenários ESC-01..ESC-10),
documentação consolidada e gate de cobertura 54/54 módulos ≥ 85%.

---

## Metadados

| Campo | Valor |
|-------|-------|
| Data | 2026-06-26 |
| Ambiente | Local (test client + mocks, sem Firestore real) |
| Python | 3.14 |
| pytest | 8.4.2 |
| Status global | **10 PASS \| 0 FAIL \| 0 SKIP** |
| Baseline | Fase 7 DoD: 1930 passed, gate 54/54 |
| Regressão cruzada | 180 passed (suite ESC + permissões + confirmação) |

---

## Comandos executados (Task 1 — Ciclo de qualidade)

```bash
# 1. Lint + format
ruff check app/ tests/ --fix
# Saída: All checks passed! (1 arquivo reformatado em format)

ruff format app/ tests/
# Saída: 1 file reformatted, 170 files left unchanged

# 2. Segurança
bandit -r app/ -ll
# Saída: No issues identified. (Severity: Low=16, Confidence: High=16 — todos Low/High, sem Medium/High severity)

# 3. Testes completos
pytest --tb=short -q
# Saída: 1930 passed in 75.41s (0:01:15)

# 4. Gate de cobertura por módulo
python scripts/check_coverage_per_module.py --json-only
# Saída: Resultado: 54/54 módulos >= 85% | 0 abaixo do gate
#        [GATE OK] Todos os 54 módulos elegíveis >= 85%.
```

### Cobertura dos módulos-chave da Onda 6

| Módulo | Cobertura | Status |
|--------|-----------|--------|
| `app/services/business_time.py` | 100.0% | OK |
| `app/services/escalonamento_service.py` | ≥ 85% | OK |
| `app/services/sla_escalacao_service.py` | 92.0% | OK |
| `app/services/permissions.py` | 90.9% | OK |
| `app/services/status_service.py` | 94.1% | OK |
| `app/services/dashboard_service.py` | ≥ 85% | OK |

---

## Tabela ESC-01..ESC-10 (script QA)

Script executado: `python scripts/executar_qa_escalonamento.py`

| ID | Cenário | Status | Detalhe |
|----|---------|--------|---------|
| ESC-01 | Isolamento supervisor: sup_a não vê chamado de sup_b | **PASS** | `usuario_pode_ver_chamado(sup_a, chamado_sup_b) = False` |
| ESC-02 | Fila da área: supervisor vê chamado sem owner | **PASS** | `usuario_pode_ver_chamado(sup_a, fila_TI) = True` |
| ESC-03 | Claim: responsavel_id = current_user.id | **PASS** | `responsavel_id='sup_a' + data_em_atendimento setado` |
| ESC-04 | Transferir área: ex-owner perde visão; novo owner ganha | **PASS** | `supervisor_ids_com_acesso=['sup_dest']` (sem sup_orig, com sup_dest) |
| ESC-05 | Escalonar colega: motivo obrigatório + troca responsavel_id | **PASS** | `motivo_vazio_rejeita=True, responsavel_id='sup_b'` |
| ESC-06 | Multi-setor: pendente bloqueia; todos concluídos libera | **PASS** | `pendente→pode_concluir_global=False, todos_concluidos→True` |
| ESC-07 | Tempo útil: 60 min atingidos às 13:30 (não 12:30 — pula almoço) | **PASS** | `min(11h→12h30)=30 (<60), min(11h→13h30)=60 (≥60)` |
| ESC-08 | Fora da janela: 16:45 e sábado bloqueados; 14:00 liberado | **PASS** | `16h45=False, 14h00=True, sábado=False` |
| ESC-09 | Deadline imutável: edição de descrição não altera data_em_atendimento | **PASS** | `data_em_atendimento ausente no payload; update_payload.keys=['descricao']` |
| ESC-10 | Gestor read-only: dashboard 200 + mudança status negada | **PASS** | `GET /gestor/dashboard=200, verificar_permissao_mudanca_status=False` |

**Resumo: 10 PASS | 0 FAIL | 0 SKIP**

---

## Ciclo de qualidade completo

### ruff check + format
```
ruff check app/ tests/ --fix → All checks passed!
ruff format app/ tests/ → 1 file reformatted, 170 files left unchanged
```

### bandit -r app/ -ll
```
Total issues (by severity):
    Undefined: 0   Low: 16   Medium: 0   High: 0
Total issues (by confidence):
    Undefined: 0   Low: 0    Medium: 0   High: 16
Files skipped: 0
```
Todos os 16 itens são Low severity / High confidence (assertions e random em contextos não-criptográficos — conhecidos e aceitos).

### pytest --tb=short -q
```
1930 passed in 75.41s (0:01:15)
```

### Gate de cobertura
```
Resultado: 54/54 módulos >= 85%  |  0 abaixo do gate
[GATE OK] Todos os 54 módulos elegíveis >= 85%.
```

---

## Regressão cruzada (Task 6)

```bash
pytest tests/test_routes/test_api_escalonamento.py \
  tests/test_services/test_escalonamento_service.py \
  tests/test_services/test_sla_escalacao_service.py \
  tests/test_services/test_business_time.py \
  tests/test_services/test_permissions.py \
  tests/test_routes/test_confirmacao_solicitante.py \
  tests/test_scripts/test_executar_qa_escalonamento.py \
  -q --no-cov
```
**Resultado: 180 passed in 6.63s**

---

## DoD produto — 9 critérios

| # | Critério global | Status | Evidência |
|---|-----------------|--------|-----------|
| 1 | Supervisor isolado (Júlia ≠ Matheus) | ✅ | ESC-01 PASS + `tests/test_services/test_permissions.py` |
| 2 | Claim atribui owner | ✅ | ESC-03 PASS + `test_api_escalonamento.py` |
| 3 | Multi-setor / Concluí minha parte | ✅ | ESC-06 PASS + `test_escalonamento_service.py` (concluir_minha_parte) |
| 4 | Transferência + anti-órfão | ✅ | ESC-04 PASS + `test_escalonamento_service.py` (transferir_area) |
| 5 | Escada A + janela útil | ✅ | ESC-07/08 PASS + `test_sla_escalacao_service.py` + `test_business_time.py` |
| 6 | Escada B + avisos 50/80% | ✅ | ESC-09 PASS (deadline imutável) + `test_sla_escalacao_service.py` (16 testes) |
| 7 | Gestor read-only | ✅ | ESC-10 PASS + `test_routes/test_api_escalonamento.py` (gestor_dashboard) |
| 8 | confirmacao_solicitante pendente | ✅ | `tests/test_routes/test_confirmacao_solicitante.py` + `status_service.py:114` |
| 9 | pytest verde + gate 85% + docs | ✅ | 1930 passed, 54/54 gate, seção 15 CASOS_DE_TESTE.md, evidência presente |

---

## Artefatos gerados

| Artefato | Localização |
|----------|-------------|
| JSON de resultados QA | `docs/evidencias/qa_escalonamento_resultado.json` |
| Evidência Fase 7 (baseline) | `docs/evidencias/FASE7_DOD_EVIDENCIA.md` |
| Plano técnico | `docs/plans/2026-06-23-escalonamento-sla.md` |
| ADR-004 | `docs/adr/004-escalonamento-sla-gerencial.md` |
| Casos de teste (seção 15) | `docs/CASOS_DE_TESTE.md` |
| Matriz rotas × perfil | `docs/MATRIZ_ROTAS_PERFIL.md` |

---

## Ops pós-deploy

- [ ] `firebase deploy --only firestore:indexes` em staging e produção
  - Índices: `status ASC + escalacao_resposta_nivel ASC` (Escada A)
  - Índices: `status ASC + escalacao_resolucao_nivel ASC` (Escada B)
  - Index: `supervisor_ids_com_acesso ARRAY_CONTAINS` (Fase 2)
- [ ] `GESTOR_EMAILS` configurado em produção (`.env` ou secret manager)
- [ ] Job `sla_escalacao` ativo e funcional (interval 10 min, APScheduler)
- [ ] Smoke test pós-deploy: criar chamado, avançar status, verificar notificações
