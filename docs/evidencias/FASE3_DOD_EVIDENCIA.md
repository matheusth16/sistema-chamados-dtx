# Evidência Operacional — Fase 3 DoD (Transferir Área + Escalonar para Colega)

| Campo | Valor |
|---|---|
| **Escopo** | Fase 3 — `transferir_area`, `escalonar_colega`, notificações e-mail, UI modais, bug área destino no e-mail |
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
1 file reformatted, 164 files left unchanged
```

### 1.2 bandit

```
$ bandit -r app/ -ll

Test results:
    Total issues (by severity):
        High: 0 | Medium: 0 | Low: 16
```

> 16 low-severity são todos pré-existentes — nenhum introduzido pela Fase 3.

### 1.3 pytest — módulos Fase 3 (isolado)

```
$ pytest tests/test_services/test_escalonamento_service.py \
         tests/test_routes/test_api_escalonamento.py \
         -v --tb=short --no-cov

39 passed in 4.29s
```

### 1.4 pytest — notificações de escalonamento

```
$ pytest tests/test_services/test_notifications.py \
         -k "transferencia or escalonamento" -v --tb=short --no-cov

3 passed, 36 deselected in 2.41s
```

### 1.5 pytest — suite completa

```
$ pytest --tb=short -q --no-cov

1765 passed in 60.65s — 0 falhas
```

**Zero regressões. 1765 testes passando.**

### 1.6 Cobertura — escalonamento_service.py

```
$ pytest tests/test_services/test_escalonamento_service.py \
         tests/test_routes/test_api_escalonamento.py \
         --cov=app/services/escalonamento_service --cov-report=term-missing

app/services/escalonamento_service.py   63   1   98%   linha 155
```

> Linha 155: branch de log `logger.warning(...)` do `escalonar_colega` que não dispara nos testes — comportamento esperado.
> **98% > gate 85% ✓**

---

## 2. Bug corrigido — L1: área destino no e-mail de transferência

**Arquivo:** `app/routes/api.py` — `api_transferir_area` (linha ~861)

**Problema:** `dados_notif = {**dados_chamado, "motivo_ultima_escalacao": motivo}` usava o dict do doc Firestore **antes** do update, então `dados_notif.get("area")` retornava a área de **origem**, não a destino. O e-mail enviado ao novo responsável informava a área errada.

**Fix:**
```python
# Antes (bug):
dados_notif = {**dados_chamado, "motivo_ultima_escalacao": motivo}

# Depois (correto):
dados_notif = {**dados_chamado, "area": area, "motivo_ultima_escalacao": motivo}
```

**Teste TDD (escrito antes do fix):**
- `TestTransferirAreaRota::test_notificacao_transferir_usa_area_destino`
- Resultado antes do fix: `AssertionError: Esperado 'Planejamento' mas recebeu 'Manutencao'`
- Resultado após o fix: ✅ PASSED

---

## 3. Lacunas fechadas

| # | Lacuna | Severidade | Arquivo | Teste |
|---|---|---|---|---|
| 1 | Bug: área antiga no e-mail de transferência | 🔴 CRÍTICO | `app/routes/api.py:861` | `test_notificacao_transferir_usa_area_destino` |
| 2 | Teste notificação background para transferir | 🟡 MÉDIO | `test_api_escalonamento.py` | `test_notificacao_transferir_chamada_em_background` |
| 3a | Teste unitário `notificar_supervisor_transferencia_area` | 🟡 MÉDIO | `test_notifications.py` | `test_notificar_transferencia_area_chama_enviar_email_com_area_correta` |
| 3b | Teste unitário `notificar_supervisor_escalonamento_colega` | 🟡 MÉDIO | `test_notifications.py` | `test_notificar_escalonamento_colega_chama_enviar_email` |
| 3c | Fail-safe: sem e-mail destino não dispara | 🟡 MÉDIO | `test_notifications.py` | `test_notificar_transferencia_sem_email_destino_nao_dispara` |
| 4 | UX: filtrar owner atual do select de colegas | 🟢 BAIXO | `visualizar_chamado.html` | (visual — validação backend já existia) |
| 5 | `execute_with_retry` no serviço de escalonamento | 🟢 BAIXO | `escalonamento_service.py` | testes existentes continuam passando (21 verde) |

---

## 4. Smoke checklist de código

| Arquivo | Elemento esperado | Confirmado |
|---|---|---|
| `app/routes/api.py` | `dados_notif = {**dados_chamado, "area": area, "motivo_ultima_escalacao": motivo}` | ✅ |
| `app/routes/api.py` | `_notificar_escalonamento` chamado com dados_notif correto | ✅ `test_notificacao_transferir_usa_area_destino` |
| `app/routes/api.py` | thread daemon iniciada no transferir | ✅ `test_notificacao_transferir_chamada_em_background` |
| `app/services/escalonamento_service.py` | `from app.firebase_retry import execute_with_retry` | ✅ linha 14 |
| `app/services/escalonamento_service.py` | `execute_with_retry(db.collection(...).update, {...}, max_retries=3)` | ✅ linhas 88–97, 188–197 |
| `app/services/notifications.py` | `notificar_supervisor_transferencia_area` + `notificar_supervisor_escalonamento_colega` | ✅ linhas 728, 785 |
| `app/templates/visualizar_chamado.html` | `var CURRENT_USER_ID = {{ current_user.id \| tojson }};` | ✅ linha 524 |
| `app/templates/visualizar_chamado.html` | `filter(function(s) { return s.id !== CURRENT_USER_ID; })` no select de colegas | ✅ linha ~569 |

---

## 5. Checklist funcional (critérios de aceite Fase 3)

- [x] Transferência Eng→Planejamento: ex-owner Eng não vê; novo owner Planejamento vê — `test_transferir_area_ex_owner_perde_acesso`, `test_transferir_area_novo_owner_ganha_acesso`
- [x] Escalonamento Júlia→Matheus mesma área: `responsavel_id = id_matheus`; área inalterada — `test_escalonar_colega_troca_responsavel`, `test_escalonar_colega_area_permanece`
- [x] Motivo obrigatório nas duas ações — `test_transferir_area_motivo_vazio_lanca_erro`, `test_escalonar_colega_motivo_obrigatorio`
- [x] Histórico registrado — `test_transferir_area_registra_historico`, `test_escalonar_colega_registra_historico`
- [x] Invariante anti-órfão — `test_anti_orfao_supervisor_id_obrigatorio`
- [x] E-mail de transferência com área **destino** correta — `test_notificacao_transferir_usa_area_destino` (**bug L1 corrigido**)
- [x] E-mail mockado verificado nos testes — `test_notificar_transferencia_area_chama_enviar_email_com_area_correta`, `test_notificar_escalonamento_colega_chama_enviar_email`
- [x] Fail-safe: sem e-mail destino não dispara — `test_notificar_transferencia_sem_email_destino_nao_dispara`
- [x] Notificações background via thread — `test_notificacao_transferir_chamada_em_background`, `test_notificacao_escalonar_chamada_em_background`
- [x] Permissões: solicitante 403, não-owner 403, IDOR 403 — `test_transferir_area_solicitante_retorna_403`, `test_transferir_area_nao_owner_supervisor_retorna_403`, `test_transferir_area_idor_sem_acesso_retorna_403`
- [x] Admin pode transferir chamado alheio — `test_transferir_area_admin_pode_transferir_chamado_alheio`
- [x] `supervisor_ids_com_acesso` recalculado — `test_transferir_area_recalcula_supervisor_ids_com_acesso`, `test_escalonar_colega_recalcula_supervisor_ids_com_acesso`
- [x] UI: botões de escalonamento visíveis para owner/admin, modais funcionais, filtro owner do select colega
- [x] Invariante DTX Light: sem `backdrop-blur`, sem `shadow-xl` nos modais

**Checklist qualidade:**
- [x] `pytest --tb=short -q` verde — **1765 passed, 0 failed**
- [x] `ruff check` + `ruff format` limpos — `All checks passed!`
- [x] `bandit -r app/ -ll` limpo — `High: 0 | Medium: 0`
- [x] `escalonamento_service.py` cobertura — **98%** (gate: 85%)

---

## 6. Novos testes adicionados (Fase 3 — fechamento de lacunas)

| Arquivo | Teste | Lacuna |
|---|---|---|
| `tests/test_routes/test_api_escalonamento.py` | `test_notificacao_transferir_usa_area_destino` | L1 (bug fix) |
| `tests/test_routes/test_api_escalonamento.py` | `test_notificacao_transferir_chamada_em_background` | L2 |
| `tests/test_services/test_notifications.py` | `test_notificar_transferencia_area_chama_enviar_email_com_area_correta` | L3a |
| `tests/test_services/test_notifications.py` | `test_notificar_escalonamento_colega_chama_enviar_email` | L3b |
| `tests/test_services/test_notifications.py` | `test_notificar_transferencia_sem_email_destino_nao_dispara` | L3c |

---

## 7. Arquivos criados/alterados

| Arquivo | Ação | Lacuna |
|---|---|---|
| `app/routes/api.py` | Alterado — `dados_notif` com `"area": area` | L1 (bug) |
| `app/services/escalonamento_service.py` | Alterado — `execute_with_retry` no update Firestore | L5 |
| `app/templates/visualizar_chamado.html` | Alterado — `CURRENT_USER_ID` + filtro select colega | L4 |
| `tests/test_routes/test_api_escalonamento.py` | Alterado — +2 testes | L1, L2 |
| `tests/test_services/test_notifications.py` | Alterado — +3 testes | L3 |
| `docs/evidencias/FASE3_DOD_EVIDENCIA.md` | **Criado** | — |

---

## 8. Declaração final

> **Fase 3 (Transferir Área + Escalonar para Colega) — DoD 100% APROVADO.**
>
> 1765 testes passando (0 falhas). Cobertura escalonamento_service.py: 98%.
> Bug L1 corrigido com TDD (teste falhando → fix → verde).
> 5 lacunas de teste fechadas (L1–L3). 2 melhorias opcionais aplicadas (L4, L5).
> Ruff CLEAN, Bandit 0 HIGH/MEDIUM.
>
> **Próxima fase:** Fase 4 — Multi-setor com Participantes.
> Pré-requisito satisfeito: Fase 3 concluída.
