# FASE 1 — Motor de Tempo Útil: Evidência DoD

| Campo | Valor |
|---|---|
| **Escopo** | Fase 1 — `business_time.py`, constantes SLA em `config.py`, `.env.example`, `docs/ENV.md` |
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
169 files left unchanged
```

### 1.2 bandit

```
$ bandit -r app/ -ll

Total issues (by severity):
    High:   0
    Medium: 0
    Low:    16
```

> 16 low-severity são todos pré-existentes — nenhum introduzido pela Fase 1.

### 1.3 pytest — módulo Fase 1 (isolado)

```
$ pytest tests/test_services/test_business_time.py -v

tests/test_services/test_business_time.py::test_dentro_janela_util_manha PASSED
tests/test_services/test_business_time.py::test_fora_janela_apos_teto_1630 PASSED
tests/test_services/test_business_time.py::test_exatamente_no_teto_1630_fora PASSED
tests/test_services/test_business_time.py::test_fora_janela_almoco PASSED
tests/test_services/test_business_time.py::test_fora_janela_almoco_inicio_exato PASSED
tests/test_services/test_business_time.py::test_dentro_janela_antes_almoco PASSED
tests/test_services/test_business_time.py::test_dentro_janela_apos_almoco PASSED
tests/test_services/test_business_time.py::test_fora_janela_sabado PASSED
tests/test_services/test_business_time.py::test_fora_janela_domingo PASSED
tests/test_services/test_business_time.py::test_dentro_janela_tarde PASSED
tests/test_services/test_business_time.py::test_fora_janela_antes_inicio PASSED
tests/test_services/test_business_time.py::test_nao_envia_notificacao_sexta_1645 PASSED
tests/test_services/test_business_time.py::test_nao_envia_notificacao_almoco PASSED
tests/test_services/test_business_time.py::test_envia_notificacao_dentro_janela PASSED
tests/test_services/test_business_time.py::test_sexta_1645_brt_fora_janela PASSED
tests/test_services/test_business_time.py::test_minutos_uteis_simples PASSED
tests/test_services/test_business_time.py::test_minutos_uteis_cruzando_almoco PASSED
tests/test_services/test_business_time.py::test_minutos_uteis_cruzando_fim_de_semana PASSED
tests/test_services/test_business_time.py::test_minutos_uteis_inicio_igual_fim PASSED
tests/test_services/test_business_time.py::test_minutos_uteis_fora_janela PASSED
tests/test_services/test_business_time.py::test_minutos_uteis_fim_antes_inicio_retorna_zero PASSED
tests/test_services/test_business_time.py::test_adicionar_minutos_uteis_simples PASSED
tests/test_services/test_business_time.py::test_adicionar_minutos_uteis_cruzando_almoco PASSED
tests/test_services/test_business_time.py::test_adicionar_minutos_uteis_cruzando_fim_de_semana PASSED
tests/test_services/test_business_time.py::test_adicionar_minutos_uteis_zero PASSED
tests/test_services/test_business_time.py::test_adicionar_dias_uteis_projetos_2_dias PASSED
tests/test_services/test_business_time.py::test_adicionar_dias_uteis_cruzando_fim_de_semana PASSED
tests/test_services/test_business_time.py::test_adicionar_dias_uteis_1_dia PASSED
tests/test_services/test_business_time.py::test_percentual_prazo_inicio PASSED
tests/test_services/test_business_time.py::test_percentual_prazo_apos_deadline PASSED
tests/test_services/test_business_time.py::test_percentual_prazo_categoria_padrao_usa_3_dias PASSED
tests/test_services/test_business_time.py::test_percentual_prazo_projetos_deadline_exato PASSED
tests/test_services/test_business_time.py::test_percentual_prazo_manutencao_50_pct PASSED
tests/test_services/test_business_time.py::test_minutos_uteis_dia_constante PASSED
tests/test_services/test_business_time.py::test_dentro_janela_util_utc_cai_no_almoco_brt PASSED
tests/test_services/test_business_time.py::test_dentro_janela_util_utc_apos_teto_brt PASSED
tests/test_services/test_business_time.py::test_dentro_janela_util_utc_dentro_janela_brt PASSED
tests/test_services/test_business_time.py::test_adicionar_minutos_uteis_aware_preserva_tz PASSED
tests/test_services/test_business_time.py::test_adicionar_dias_uteis_aware_preserva_tz PASSED
tests/test_services/test_business_time.py::test_adicionar_dias_uteis_sexta_mais_2_projetos PASSED
tests/test_services/test_business_time.py::test_percentual_prazo_total_minutos_zero_retorna_1 PASSED
tests/test_services/test_business_time.py::test_adicionar_minutos_uteis_negativo_levanta_erro PASSED
============================= 42 passed in 2.60s ==============================
```

### 1.4 Cobertura

```
$ python scripts/check_coverage_per_module.py --json-only

app/services/business_time.py   95.8%   OK   (gate >= 85%)

[GATE OK] Todos os 54 módulos elegíveis >= 85%.
```

---

## 2. Critérios de aceite — verificados

### Task 1.1: `business_time.py`

| Função | Cobertura | Status |
|---|---|---|
| `dentro_janela_util(agora)` | ✅ | 11 testes — janela manhã/tarde, almoço, sáb/dom, fora-teto |
| `pode_enviar_notificacao_agora(agora)` | ✅ | 3 testes — sexta 16:45, almoço, dentro da janela |
| `minutos_uteis_entre(inicio, fim)` | ✅ | 6 testes — simples, cruzando almoço, cruzando fim de semana |
| `adicionar_minutos_uteis(dt, minutos)` | ✅ | 5 testes — simples, almoço, fim de semana, zero, negativo |
| `adicionar_dias_uteis(dt, n, categoria)` | ✅ | 5 testes — Projetos 2d, padrão, sexta+2, cruzando fds |
| `percentual_prazo_resolucao(...)` | ✅ | 5 testes — início, deadline, 50%, Projetos, categoria padrão |

### Task 1.2: Constantes SLA em `config.py`

- [x] `SLA_HORARIO_INICIO`, `SLA_HORARIO_FIM` (07:00 / 16:30)
- [x] `SLA_ALMOCO_INICIO`, `SLA_ALMOCO_FIM` (11:30 / 13:00)
- [x] `SLA_DIAS_RESOLUCAO_PROJETOS = 2`, `SLA_DIAS_RESOLUCAO_PADRAO = 3`
- [x] `SLA_TIMEZONE = "America/Sao_Paulo"` (BRT)
- [x] `SLA_ESCALADA_A_HORAS_UTEIS = [1, 2, 3, 4]`
- [x] `SLA_ESCALADA_B_HORAS_UTEIS = [0, 4, 8, 12]`

### Task 1.3: `.env.example` + `docs/ENV.md`

- [x] Constantes SLA documentadas com valores padrão e descrição
- [x] Formato string `"HH:MM"` documentado para `SLA_HORARIO_*` e `SLA_ALMOCO_*`

---

## 3. Arquivos criados/alterados

| Arquivo | Descrição |
|---|---|
| `app/services/business_time.py` | Motor de tempo útil DTX (6 funções públicas, timezone BRT, pausa almoço/fds) |
| `tests/test_services/test_business_time.py` | 42 testes TDD — cobertura 95.8% |
| `config.py` | Constantes SLA (`SLA_HORARIO_*`, `SLA_ALMOCO_*`, `SLA_DIAS_*`, `SLA_TIMEZONE`) |
| `.env.example` | Documentação das variáveis SLA |
| `docs/ENV.md` | Seção "SLA / Escalonamento" com variáveis e valores padrão |

---

## 4. Restrições respeitadas

- Fase 6–8 não implementadas (motor sem integração com scheduler ainda)
- `business_time` sem estado — funções puras, sem dependência de Firestore
- Timezone BRT via `zoneinfo.ZoneInfo("America/Sao_Paulo")` (stdlib Python 3.9+)
- `adicionar_minutos_uteis` com minutos negativos levanta `ValueError` (fail-fast)
