# FASE 6 — Escada A (Resposta Gerencial) + Job Scheduler 10 min: Evidência DoD

**Data de conclusão:** 2026-06-25
**Implementado por:** Matheus Costa + Claude Sonnet 4.6

---

## Resumo executivo

A Fase 6 implementa a Escada A de escalação gerencial: um job APScheduler executando a cada 10 minutos verifica chamados `status == "Aberto"` sem resposta e escalona para até 4 níveis hierárquicos (+60/+120/+180/+240 minutos úteis desde a abertura). Substitui o job diário de alerta de prazo (desativado). Integra `business_time.minutos_uteis_entre` no `gestor_dashboard_service` (substituindo `_minutos_desde` wall-clock). Adiciona reset de `escalacao_resposta_nivel` na reabertura de chamado (ADR-004).

---

## Checklist de aceite

### Funcional

- [x] `calcular_nivel_esperado_escada_a(minutos_uteis)` — limites 60/120/180/240 min úteis
- [x] `processar_escada_a()` — query Firestore `status=="Aberto"` AND `escalacao_resposta_nivel<4`
- [x] Um único incremento de nível por execução (idempotência: nível vai de `nivel_atual` para `nivel_atual + 1`)
- [x] Threshold atingido mas fora de janela útil → `pulados_fora_janela++`, sem incremento (deferred)
- [x] Email via `notificar_escalada_resposta_gerencial` enviado para destinatário do nível (`gestor_setor`, `gerente_producao`, `assistente_gm`, `gm`)
- [x] `Config.get_gestor_email` retorna `None` → incrementa Firestore sem enviar email (evita loop infinito)
- [x] Exceção em um chamado não interrompe processamento dos demais
- [x] Estatísticas retornadas: `{processados, escalados, emails, erros, pulados_fora_janela}`
- [x] Job `sla_escalacao` a cada 10 min com `executar_job_com_lock` (Redis lock)
- [x] `notificar_escalada_resposta_gerencial` adicionada em `notifications.py`
- [x] `escalacao_resposta_nivel = 0` no update de reabertura (`api_confirmar_resolucao`) — ADR-004
- [x] `_is_aberto_sem_resposta` em `gestor_dashboard_service` usa `minutos_uteis_entre` (Task 6.4)
- [x] `obter_contexto_gestor_dashboard` aceita `agora` opcional para testabilidade
- [x] `_minutos_desde` removido de `gestor_dashboard_service` (wall-clock eliminado)

### Cobertura

- [x] `sla_escalacao_service.py` — **95%** (13 testes, todos passando)
- [x] `gestor_dashboard_service.py` — coberto pelos testes existentes (23 testes, todos passando)

### Qualidade

- [x] `ruff check` — 0 erros nos arquivos Fase 6
- [x] `bandit -r app/services/sla_escalacao_service.py app/services/gestor_dashboard_service.py -ll` — 0 issues
- [x] 47 testes passando (test_sla_escalacao_service + test_gestor_dashboard_service + test_confirmacao_solicitante)

---

## Arquivos criados/modificados

| Arquivo | Tipo | Descrição |
|---------|------|-----------|
| `app/services/sla_escalacao_service.py` | NOVO | `processar_escada_a`, `calcular_nivel_esperado_escada_a`, `_processar_chamado_escada_a` |
| `tests/test_services/test_sla_escalacao_service.py` | NOVO | 13 testes TDD — limites, disparo, janela, idempotência, erros |
| `app/services/notifications.py` | MOD | `notificar_escalada_resposta_gerencial` (email Escada A) |
| `app/__init__.py` | MOD | Job `sla_escalacao` a cada 10 min (substitui `alerta_prazo_24h`) |
| `app/routes/api.py` | MOD | `escalacao_resposta_nivel: 0` no update de reabertura |
| `app/services/gestor_dashboard_service.py` | MOD | `_is_aberto_sem_resposta` + `obter_contexto_gestor_dashboard` com `agora` opcional; `_minutos_desde` removido |
| `tests/test_services/test_gestor_dashboard_service.py` | MOD | Todos os testes atualizados com `agora=_AGORA_FIXED`; teste de regressão weekend adicionado |
| `tests/test_routes/test_confirmacao_solicitante.py` | MOD | `test_reabrir_reseta_escalacao_resposta_nivel` (ADR-004) |

---

## Decisões de design

### ADR-004: Reset na reabertura
`escalacao_resposta_nivel = 0` quando solicitante reabre chamado — reinicia a Escada A do zero, permitindo nova escalação gerencial caso o problema persista.

### Sem email → incrementa mesmo assim
Se `Config.get_gestor_email(chave)` retornar `None` (email não configurado), o nível é incrementado normalmente. Isso evita que um chamado fique preso no mesmo nível indefinidamente por configuração ausente (loop infinito). Log de warning emitido.

### Uma execução = um nível
Mesmo que `nivel_esperado > nivel_atual + 1`, só um nível é incrementado por execução do job. A próxima execução (10 min) avançará mais se ainda elegível.

### Job `alerta_prazo_24h` desativado
O job cron das 08h foi desativado (comentado) pois a Escada A cobre a função de alerta gerencial com granularidade superior (10 min vs. 24h). A função `enviar_alertas_prazo_24h` permanece disponível para reativação.

---

## Índice Firestore necessário

Query: `status == "Aberto"` AND `escalacao_resposta_nivel < 4`

```json
{
  "collectionGroup": "chamados",
  "queryScope": "COLLECTION",
  "fields": [
    {"fieldPath": "status", "order": "ASCENDING"},
    {"fieldPath": "escalacao_resposta_nivel", "order": "ASCENDING"}
  ]
}
```

Adicionar em `firestore.indexes.json` antes de deploy em produção.

---

## Saída de testes (entrega inicial)

```
47 passed in 5.30s
sla_escalacao_service.py   66      3    95%
```

---

## Lacunas pós-revisão fechadas (2026-06-25)

### P0 — Regressão `tests/test_app_init.py` (CRÍTICO → RESOLVIDO)

- `test_iniciar_scheduler_registra_quatro_jobs`: substituído `assert "alerta_prazo_24h"` por `assert "sla_escalacao"`.
- `test_job_alerta_prazo_executa` + `test_job_alerta_prazo_excecao_logada` → substituídos por `test_job_sla_escalacao_executa` + `test_job_sla_escalacao_excecao_logada`.
- Patch correto: `app.services.sla_escalacao_service.processar_escada_a` (import inline no `_job_sla_escalacao`).
- `_capturar_jobs_scheduler` sem alterações — já populava corretamente via `executar_job_com_lock(app, "sla_escalacao", fn)`.

### P1 — Documentação atualizada

| Arquivo | Mudança |
|---------|---------|
| `docs/API.md` | +seção "Jobs em background / SLA Escada A"; atualizado aviso gestor dashboard; +2 linhas changelog |
| `docs/ENV.md` | `GESTOR_EMAILS` atualizado: "futuras (Fase 6+)" → "destinatários da Escada A (Fase 6)" |
| `docs/adr/004-escalonamento-sla-gerencial.md` | +seção "Resolvido na Fase 6"; linha filtro gestor riscada; tabela de débitos renomeada para "pós Fases 0–6" |
| `docs/evidencias/FASE5_DOD_EVIDENCIA.md` | Limitação `_is_aberto_sem_resposta` marcada como RESOLVIDA na Fase 6 |
| `scripts/README.md` | +seção "Jobs APScheduler" com `sla_escalacao`, dependências e aviso de índice |

### Ciclo de qualidade final

```
ruff check app/ tests/ --fix   → 0 violações
ruff format app/ tests/        → 2 arquivos reformatados (test_sla + test_app_init)
bandit -r app/ -ll             → 0 High, 0 Medium
pytest tests/test_app_init.py  → 45 passed (0 failed)
pytest tests/test_services/test_sla_escalacao_service.py → 13 passed (0 failed)
pytest --tb=short -q           → 1893 passed (0 failed)
python scripts/check_coverage_per_module.py --json-only → 54/54 OK
  sla_escalacao_service.py 91% (91 > 85 ✓)
```

**Bug colateral corrigido:** 4 patches em `test_sla_escalacao_service.py` usavam `config.Config.get_gestor_email` mas `test_config_production.py` faz `importlib.reload(config_mod)`, criando uma nova classe `Config` no módulo. O serviço mantém referência à classe original (via `from config import Config`). Patch correto: `app.services.sla_escalacao_service.Config.get_gestor_email` — aponta diretamente para a classe que o serviço usa.

### Checklist final P0–P2

- [x] `test_app_init.py` — 0 falhas relacionadas a scheduler (45 passed)
- [x] Suite completa — **1893 passed, 0 failed**
- [x] Gate 85% — **54/54 módulos OK**
- [x] `sla_escalacao_service.py` >= 85% (91%)
- [x] docs/API.md — seção Escada A adicionada
- [x] docs/ENV.md — GESTOR_EMAILS atualizado
- [x] docs/adr/004 — seção "Resolvido na Fase 6" adicionada
- [x] docs/evidencias/FASE5_DOD_EVIDENCIA.md — limitação marcada resolvida
- [x] scripts/README.md — jobs APScheduler documentados
- [x] Bug colateral: patch flaky `config.Config` → `app.services.sla_escalacao_service.Config`

---

Fase 6 fechada — pronta para Fase 7.
