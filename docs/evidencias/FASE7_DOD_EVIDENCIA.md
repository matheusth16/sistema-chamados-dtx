# FASE 7 — Escada B (SLA Resolução) + Avisos 50%/80% + Analytics: Evidência DoD

**Data de conclusão:** 2026-06-26
**Implementado por:** Matheus Costa + Claude Sonnet 4.6

---

## Resumo executivo

A Fase 7 implementa a Escada B de escalação gerencial (resolução) e os avisos preventivos de SLA.
Chamados em `status == "Em Atendimento"` que ultrapassam o deadline de resolução (2 dias úteis para
Projetos / 3 dias úteis para demais categorias) são escalados progressivamente para 4 níveis
hierárquicos em +0h/+4h/+8h/+12h úteis após o vencimento. Avisos preventivos são enviados ao
responsável quando o percentual de prazo atingir 50% e 80%, com tripla notificação (in-app + e-mail
+ Web Push), respeitando a janela útil DTX. O job APScheduler existente (`sla_escalacao`, 10 min)
é ampliado para chamar as três novas funções. O campo `data_em_atendimento` é preservado imutável
durante edições e conclusões parciais de participantes. A exibição de SLA em "Em Atendimento" no
dashboard e nas métricas passa a usar tempo útil (via `percentual_prazo_resolucao`) a partir de 50%.

---

## Checklist de aceite

### Modelo — Task 7.1

- [x] `escalacao_resolucao_nivel: int = 0` adicionado em `Chamado.__init__`, `to_dict`, `from_dict`
- [x] `alerta_supervisor_50_enviado: bool = False` — idempotência do aviso 50%
- [x] `alerta_supervisor_80_enviado: bool = False` — idempotência do aviso 80%
- [x] 3 testes de modelo passando (`test_models_chamado.py`)

### Cálculos SLA — Tasks 7.2 + 7.3

- [x] `calcular_deadline_resolucao(data_em_atendimento, categoria)` → `adicionar_dias_uteis` (2 ou 3 dias úteis)
- [x] `calcular_nivel_esperado_escada_b(minutos_uteis_apos_deadline)` → 1–4 (thresholds 0/240/480/720 min)
- [x] `processar_avisos_resolucao()` — verifica percentual 50%/80% e notifica responsável; janela útil verificada via `pode_enviar_notificacao_agora()`; tripla notificação (in-app + e-mail + Web Push); e-mail omitido se ausente; flag sempre gravada
- [x] `processar_escada_b()` — escala Escada B um nível por execução; janela útil verificada antes de enviar
- [x] Idempotência: nível só avança se `nivel_esperado > nivel_atual`
- [x] Chamado fora de janela útil → `pulados_fora_janela++`, sem incremento
- [x] Email não configurado → incrementa Firestore sem enviar (evita loop)
- [x] `_MINUTOS_THRESHOLDS_B = [0, 240, 480, 720]` definido como constante de módulo
- [x] 16 testes TDD no `test_sla_escalacao_service.py`

### Job scheduler — Task 7.4

- [x] `_job_sla_escalacao` chama `processar_escada_a`, `processar_avisos_resolucao` e `processar_escada_b`
- [x] Resultado logado: `{"escada_a": ..., "avisos_resolucao": ..., "escada_b": ...}`
- [x] Exceção capturada e logada sem propagar
- [x] 2 testes atualizados em `test_app_init.py`

### Reset na reabertura / claim — Task 7.5

- [x] `status_service.py` — claim (Aberto → Em Atendimento) reseta `escalacao_resolucao_nivel=0`, `alerta_supervisor_50_enviado=False`, `alerta_supervisor_80_enviado=False`
- [x] `api.py` — reabertura zera os 3 campos Escada B junto com `escalacao_resposta_nivel=0`
- [x] 1 teste `test_claim_reseta_flags_escada_b` em `test_status_service.py`
- [x] 1 teste `test_reabrir_reseta_flags_escada_b` em `test_confirmacao_solicitante.py`

### Regressões data_em_atendimento — Task 7.6

- [x] `test_edicao_descricao_nao_altera_data_em_atendimento` — edição de campos simples não inclui `data_em_atendimento` no update
- [x] `test_concluir_minha_parte_nao_altera_data_em_atendimento` — `concluir_minha_parte` não inclui `data_em_atendimento`

### Analytics obter_sla_para_exibicao — Task 7.7

- [x] "Em Atendimento" com `data_em_atendimento` presente usa `percentual_prazo_resolucao` (tempo útil)
- [x] percentual < 0.8 → "No prazo" / >= 0.8 → "Em risco" / > 1.0 → "Atrasado"
- [x] "Em Atendimento" sem `data_em_atendimento` → ramo calendário (retrocompatível)
- [x] `percentual_prazo_resolucao` importado no nível de módulo em `analytics.py` (permite patch)
- [x] 3 novos testes TDD em `test_analytics.py`; 62 testes existentes mantidos

### Notificações — Task 7.8

- [x] `notificar_aviso_resolucao_supervisor` — in-app + webpush + email; assunto `[SLA {marco}%] Ticket {numero_chamado} — resolution deadline approaching`
- [x] `notificar_escalada_resolucao_gerencial` — email only; assunto `[SLA Alert] Ticket {numero_chamado} — resolution overdue (Ladder B, Level {nivel})`
- [x] 2 testes TDD em `test_notifications.py`

### Índice Firestore — Task 7.9

- [x] `firestore.indexes.json` — adicionado índice `status ASC + escalacao_resolucao_nivel ASC`
- [x] `docs/INDICES_FIRESTORE.md` — Escada B documentada na tabela de índices

### Confirmação solicitante — Task 7.10

- [x] `test_concluido_grava_confirmacao_solicitante_pendente` já existia em `test_status_service.py` (linha 649) — nenhuma alteração necessária

### Fechamento lacunas P0–P1 (2026-06-26)

- [x] `processar_avisos_resolucao` respeita `pode_enviar_notificacao_agora()` — `pulados_fora_janela` adicionado ao dict de stats
- [x] Avisos disparam in-app + Web Push mesmo sem e-mail configurado — `email_dest: str | None = None` em `notificar_aviso_resolucao_supervisor`
- [x] Badge `em_risco` a partir de 50% do prazo de resolução (alinhado ao aviso preventivo)
- [x] `resumo_sla.em_risco` usa tempo útil via `percentual_prazo_resolucao` para chamados "Em Atendimento" com `data_em_atendimento`
- [x] `docs/API.md` — Escada B + avisos 50%/80% documentados; ordem de execução do job
- [x] `docs/plans/2026-06-23-escalonamento-sla.md` — linha "Fase 7 concluída em 2026-06-26"
- [x] `.cursor/plans/escalonamento_e_sla_dtx_d3e9e5bb.plan.md` — `fase-7-escada-b: completed`
- [x] `scripts/README.md` — tabela de jobs atualizada com Fases 6–7 e stats
- [x] ADR-004 — Fase 7 corrigida: janela útil nos avisos, sem-email tripla notif, badge 50%

---

## Arquivos criados/modificados

| Arquivo | Tipo | Descrição |
|---------|------|-----------|
| `app/models.py` | MOD | 3 novos campos Escada B em `__init__`, `to_dict`, `from_dict` |
| `app/services/sla_escalacao_service.py` | MOD | `calcular_deadline_resolucao`, `calcular_nivel_esperado_escada_b`, `processar_avisos_resolucao`, `_processar_aviso_resolucao`, `_obter_email_responsavel`, `processar_escada_b`, `_processar_chamado_escada_b` |
| `app/services/notifications.py` | MOD | `notificar_aviso_resolucao_supervisor`, `notificar_escalada_resolucao_gerencial` |
| `app/services/analytics.py` | MOD | Import `percentual_prazo_resolucao`; branch "Em Atendimento" em `obter_sla_para_exibicao` |
| `app/services/status_service.py` | MOD | Reset 3 campos Escada B no claim (Aberto → Em Atendimento) |
| `app/routes/api.py` | MOD | Reset 3 campos Escada B no update de reabertura |
| `app/__init__.py` | MOD | `_job_sla_escalacao` ampliado com `processar_avisos_resolucao` + `processar_escada_b` |
| `firestore.indexes.json` | MOD | Índice `status ASC + escalacao_resolucao_nivel ASC` |
| `docs/INDICES_FIRESTORE.md` | MOD | Linha Escada B adicionada à tabela |
| `docs/adr/004-escalonamento-sla-gerencial.md` | MOD | Seção "Resolvido na Fase 7" |
| `tests/test_services/test_models_chamado.py` | MOD | 3 testes Escada B modelo |
| `tests/test_services/test_sla_escalacao_service.py` | MOD | 16 testes TDD Escada B |
| `tests/test_services/test_notifications.py` | MOD | 2 testes TDD notificações |
| `tests/test_services/test_analytics.py` | MOD | 3 testes TDD `obter_sla_para_exibicao` |
| `tests/test_services/test_status_service.py` | MOD | 1 teste reset claim |
| `tests/test_routes/test_confirmacao_solicitante.py` | MOD | 1 teste reset reabertura |
| `tests/test_services/test_edicao_chamado_service.py` | MOD | 1 teste regressão `data_em_atendimento` |
| `tests/test_services/test_escalonamento_service.py` | MOD | 1 teste regressão `data_em_atendimento` |
| `tests/test_app_init.py` | MOD | 2 testes scheduler atualizados para 3 funções |

---

## Índice Firestore necessário

Query Escada B: `status == "Em Atendimento"` AND `escalacao_resolucao_nivel < 4`

```json
{
  "collectionGroup": "chamados",
  "queryScope": "COLLECTION",
  "fields": [
    {"fieldPath": "status", "order": "ASCENDING"},
    {"fieldPath": "escalacao_resolucao_nivel", "order": "ASCENDING"}
  ]
}
```

Já adicionado em `firestore.indexes.json`. Implantar com `firebase deploy --only firestore:indexes`.

---

## Decisões de design

### Deadline de resolução fixo

`data_em_atendimento` é gravado uma única vez (ao primeiro claim) e nunca sobrescrito por edições,
anexos ou "Concluí minha parte". O deadline de resolução (`calcular_deadline_resolucao`) é
determinístico e auditável.

### Reset completo na reabertura / claim

Ao reabrir (solicitante) ou ao novo claim (supervisor), todos os 5 campos de escalação (Escada A +
Escada B) são zerados atomicamente: `escalacao_resposta_nivel`, `escalacao_resolucao_nivel`,
`alerta_supervisor_50_enviado`, `alerta_supervisor_80_enviado`. Isso garante que o ciclo SLA recomeça
do zero sem resíduos de escalações anteriores.

### Flag sempre gravada mesmo sem email

Se o email do responsável não for encontrado (sem `responsavel_id` ou `Usuario.get_by_id` retorna
`None`), o flag `alerta_supervisor_50_enviado` / `alerta_supervisor_80_enviado` é gravado mesmo assim.
Evita lookups repetidos e infinitos a cada execução do job.

### Escada B nível mínimo = 1

`calcular_nivel_esperado_escada_b(0)` retorna 1 (não 0), pois o threshold 0 min após o deadline é
imediatamente atingido ao vencer o prazo. Nível 0 significa "ainda dentro do prazo".

### Analytics retrocompatível

Chamados com `status == "Em Atendimento"` mas sem `data_em_atendimento` (criados antes da Fase 7
ou em migração) continuam usando a lógica calendário existente — sem quebra de comportamento.

---

## Saída de testes (Fase 7 — incluindo lacunas P0–P1)

```
1930 passed in 80.48s
sla_escalacao_service.py  192  15  92%
analytics.py              431  ≈30  93%
notifications.py          445  65  85%
```

Suite completa executada:

```bash
ruff check app/ tests/ --fix       → All checks passed!
ruff format app/ tests/            → 3 files reformatted
bandit -r app/ -ll                 → 0 alertas
pytest --tb=short -q               → 1930 passed
python scripts/check_coverage_per_module.py --json-only  → 54/54 módulos ≥ 85%
```

---

## Ciclo de qualidade

```
ruff check   → All checks passed!
ruff format  → 3 files reformatted (notifications.py, test_analytics.py, test_sla_escalacao_service.py)
bandit       → 0 alertas
pytest       → 1930 passed in 80.48s
gate 85%     → 54/54 módulos OK — [GATE OK]
```

---

Fase 7 100% fechada (P0–P1 incluídos) — pronta para Fase 8.
