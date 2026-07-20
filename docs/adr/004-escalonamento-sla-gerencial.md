# ADR-004 — Escalonamento Multi-setor e SLA Gerencial (Onda 6)

| Campo | Valor |
|---|---|
| **Status** | Accepted |
| **Data** | 2026-06-24 |
| **Autores** | Matheus Costa — DTX Aerospace Engineering |
| **Relacionado** | ADR-003 (fail-fast / APScheduler); ADR-001 (criptografia PII); `docs/plans/2026-06-23-escalonamento-sla.md` |

---

## Contexto

O Sistema de Chamados DTX opera com supervisores agrupados por área (`area`). O modelo atual apresenta quatro lacunas operacionais:

### 1. Isolamento por supervisor inexistente

A consulta de dashboard filtra por `area in areas_do_usuario`, expondo todos os tickets da área para qualquer supervisor daquela área. Dois supervisores da mesma área (ex.: Júlia e Matheus em Engenharia) veem mutuamente os chamados um do outro — violando o princípio de responsabilidade individual e o isolamento operacional.

### 2. Colaboração multi-setor rudimentar

O campo `setores_adicionais: list[str]` permite marcar áreas adicionais envolvidas, mas não rastreia **quem** respondeu, **qual status** cada participante tem, nem bloqueia o encerramento enquanto partes pendentes existem. Não há visibilidade de "Concluí minha parte" individual por participante.

### 3. SLA em dias corridos, sem tempo útil

A lógica atual de SLA (`analytics.py`, `report_service.py`) calcula prazos em dias corridos (24h). DTX opera Seg–Sex 07:00–11:30 / 13:00–16:30 (450 minutos úteis/dia), com pausa de almoço e sem operação nos fins de semana. Prazos corridos geram alertas fora do expediente e métricas imprecisas para o contexto fabril.

### 4. Job de escalada diário e único

O APScheduler dispara uma vez por dia às 08:00h. Escalonamentos que deveriam ocorrer a cada hora útil acumulam um dia inteiro de atraso. Não existe distinção entre escalada de **resposta** (ticket sem atendimento) e escalada de **resolução** (ticket em atendimento além do prazo).

---

## Decision Drivers

- **Responsabilidade individual:** supervisor deve ver e gerenciar apenas os chamados sob sua responsabilidade direta — atribuídos a ele, fila da área sem owner, ou onde é participante ativo.
- **Colaboração auditada:** inclusão de outros supervisores em chamados deve ser rastreada por participante, com status próprio e histórico de ações formais.
- **SLA realista:** prazos calculados em tempo útil DTX (07:00–11:30 / 13:00–16:30, seg–sex) — sem alertas fora de janela, sem contagem de almoço ou fins de semana.
- **Escalonamento progressivo:** degraus horários (Escada A para resposta) e diários (Escada B para resolução) com destinatários gerenciais fixos e configuráveis.
- **Conformidade com fluxo existente:** `confirmacao_solicitante = "pendente"` ao Concluído; reabertura reinicia SLA; histórico auditável no Firestore.
- **Zero spam gerencial:** e-mails somente dentro da janela útil e fora do almoço; flags de idempotência por nível de escalada.

---

## Opções Consideradas

### Opção 1A: `setores_adicionais` estendido vs `participantes` estruturado

**Estendido (`setores_adicionais`):** adicionar campos auxiliares (`setores_status`, `setores_concluidos`) ao modelo atual.

- Pró: menor refactor de modelo e templates
- Contra: lista de strings não carrega metadados por participante (quem, quando, status individual); dificulta queries Firestore por `supervisor_id`; migração incremental inviável — documentos acumulam campos extras inconsistentes

**`participantes` estruturado** (adotada): lista de objetos `{supervisor_id, area, status, concluido_em}` no documento Firestore.

- Pró: status individual por participante; auditável; migração via script com dual-read retrocompatível
- **Limitação Firestore:** `array_contains` filtra por valor escalar — `supervisor_id` aninhado em `participantes[]` **não** é indexável diretamente pelo Firestore. Estratégia adotada: campo desnormalizado **`supervisor_ids_com_acesso: list[str]`** atualizado atomicamente em toda mutação de owner, transferência de área e inclusão/remoção de participantes. Permite `array_contains` nativo nas queries de dashboard. Alternativa: duas queries separadas (owner por `responsavel_id` + fila por `area`) com merge em Python — mantida como fallback.
- Contra: script de migração de `setores_adicionais` legado necessário; `supervisor_ids_com_acesso` exige update atômico em toda operação que altera owner ou participantes

**Decisão:** `participantes` estruturado com desnormalização `supervisor_ids_com_acesso`. Clareza de dados e queries eficientes superam o custo de manutenção do campo desnormalizado.

---

### Opção 1B: Tempo 24/7 vs tempo útil DTX

**24/7:** manter SLA em horas corridas, ignorar horário de expediente.

- Pró: simples; sem dependência de config de horário
- Contra: prazos atingidos às 02:00h disparam e-mails fora de expediente; gerentes recebem alertas no fim de semana; SLA incorreto (ex.: +1h útil às 16:00 expiraria às 17:00, quando a fábrica já está fechada)

**Tempo útil DTX** (adotada): `business_time.py` com janela 07:00–11:30 / 13:00–16:30, almoço excluído, seg–sex.

- Pró: alertas apenas quando destinatários estão presentes; prazo real para o contexto fabril; teto 16:30 evita notificação após saída da produção
- Contra: implementação mais complexa; testes de borda obrigatórios (sexta 16:45, abertura 11:00 → +1h útil = 13:30, não 12:30)

**Decisão:** tempo útil DTX. Alertas inúteis fora de expediente geram fadiga e são ignorados.

> **Timezone:** todos os cálculos de SLA e escalada usam **`America/Sao_Paulo` (BRT)**, alinhado ao APScheduler configurado em `app/__init__.py`. Datetimes naive nos testes são interpretados como horário local DTX — nunca UTC. Implementação via `zoneinfo.ZoneInfo` (stdlib Python 3.9+); constante `SLA_TIMEZONE=America/Sao_Paulo` em `config.py` e `.env.example`.

---

### Opção 1C: Escalada gerencial batch (1×/dia) vs sequencial horária

**Batch diária:** manter job único às 08:00h, agrupando todos os chamados vencidos.

- Pró: simples; sem overhead de scheduler
- Contra: chamado aberto às 07:30h só escalaria no dia seguinte; CWI exige resposta em horas, não dias; acúmulo de níveis pulados em uma única execução

**Sequencial horária** (adotada): job a cada 10–15 min; um nível por execução por chamado; flags de idempotência `escalacao_resposta_nivel` e `escalacao_resolucao_nivel`; e-mail adiado se fora de janela.

- Pró: escalada proporcional ao tempo real; sem spam (idempotência por nível); gerentes notificados na ordem correta
- Contra: pressão no APScheduler; risco de jobs paralelos sem lock → mitigado por `scheduler_lock.py` (ADR-003)

**Decisão:** sequencial horária com lock. ADR-003 já endereça o mecanismo de lock para 1 worker DTX.

---

## Decisão

Implementar a **Onda 6 — Escalonamento Multi-setor e SLA Gerencial** com os seguintes elementos:

1. **Isolamento por supervisor:** query de dashboard reformulada — supervisor vê apenas `(responsavel_id == me) OR (area in areas AND sem owner) OR participante ativo`.
2. **Participantes estruturados:** substituir `setores_adicionais` por `participantes[{supervisor_id, area, status, concluido_em}]`; script de migração incremental com dual-read.
3. **Motor de tempo útil (`business_time.py`):** janela 07:00–11:30 / 13:00–16:30, seg–sex; teto 16:30; pausa almoço; `pode_enviar_notificacao_agora()` utilizada por todos os serviços de notificação.
4. **Escada A (resposta):** +1h, +2h, +3h, +4h úteis → Gerente Setor → Gerente Produção → Assistente GM → GM; corte imediato ao virar `Em Atendimento` (campo `data_em_atendimento`); **mesma regra para categoria Projetos e demais** — Escada A não distingue categoria (4 degraus iguais, +1h útil cada).
5. **Escada B (resolução):** deadline **fixo** desde `data_em_atendimento` — nada reseta (edições, anexos e "Concluí minha parte" não alteram o prazo); Projetos = fim do 2º dia útil às 16:30; demais = fim do 3º dia útil às 16:30; avisos 50%/80% ao responsável; pós-estouro: escalada gerencial +0h/+4h/+8h/+12h úteis.
6. **Perfil gestor (`nivel_gestao`):** `gestor_setor | gerente_producao | assistente_gm | gm`; dashboard read-only; recebe e-mails de escalada; não edita tickets.
7. **Notificações completas:** in-app + e-mail (Graph API) + Web Push (`webpush_service.py`) para todas as escaladas e mudanças de participantes.
8. **Invariante anti-órfão:** transferência de área sempre resulta em ≥ 1 supervisor com acesso de edição; update atômico Firestore garante que ex-owner perde visão operacional e novo owner ganha imediatamente.

---

## Consequências

### Positivas

- Supervisores isolados: Júlia não vê tickets de Matheus mesmo na mesma área
- Colaboração auditada com status por participante e botão "Concluí minha parte"
- SLA calculado em tempo útil real — prazos e alertas fazem sentido operacional no contexto fabril DTX
- Escalada progressiva: responsáveis corretos notificados na hora e canal certos
- Conformidade com fluxo de confirmação do solicitante após Concluído (integração com fluxo existente)

### Negativas / Riscos mitigados

| Risco | Mitigação |
|---|---|
| Índices Firestore para query owner+fila | Atualizar `firestore.indexes.json` na Fase 2; ver `docs/INDICES_FIRESTORE.md` |
| Jobs paralelos sem Redis | `scheduler_lock.py` (ADR-003); deploy DTX com 1 worker |
| `setores_adicionais` legado | Script `scripts/migrar_participantes.py` + `from_dict` dual-read retrocompatível |
| Spam de e-mail por job repetido | Flags `*_enviado_em` por nível; `pode_enviar_notificacao_agora()` no job |
| Chamado órfão pós-transferência | Update atômico Firestore + teste de regressão anti-órfão (Fase 3) |
| Firestore sem OR entre campos distintos (query dashboard) | Campo desnormalizado `supervisor_ids_com_acesso` + `array_contains`; update atômico em toda mutação de owner/participante |
| Cobertura 85% por módulo | `check_coverage_per_module.py` a cada fase; gates no ciclo CLAUDE.md |

### Neutras

- `confirmacao_solicitante` já implementado em `status_service.py` — apenas integrado ao fluxo de Concluído
- `webpush_service.py` já existe — escopo ampliado para escaladas operacionais
- Job interval 10 min substitui job diário 08:00h — alteração localizada em `app/__init__.py`

---

## Campos de modelo a adicionar (Firestore `chamados`)

```python
data_em_atendimento           # datetime — set ao 1º Em Atendimento; nada reseta
escalacao_resposta_nivel      # int 0–4 — Escada A (congelado ao virar Em Atendimento)
escalacao_resolucao_nivel     # int 0–4 — Escada B pós-estouro deadline
alerta_supervisor_50_enviado  # bool | datetime — idempotência aviso 50%
alerta_supervisor_80_enviado  # bool | datetime — idempotência aviso 80%
participantes                 # list[dict] — {supervisor_id, area, status, concluido_em}
motivo_ultima_escalacao       # str — motivo da última ação formal de escalonamento
supervisor_ids_com_acesso     # list[str] — desnormalizado; inclui owner + participantes ativos; permite array_contains no dashboard
```

Variáveis de ambiente (`config.py` + `.env.example`):

```
SLA_HORARIO_INICIO=07:00
SLA_HORARIO_FIM=16:30
SLA_ALMOCO_INICIO=11:30
SLA_ALMOCO_FIM=13:00
SLA_DIAS_RESOLUCAO_PROJETOS=2
SLA_DIAS_RESOLUCAO_PADRAO=3
SLA_INCLUI_FIM_DE_SEMANA=false        # flag v2 para sáb/dom excepcionais
SLA_TIMEZONE=America/Sao_Paulo        # fuso para cálculo de janela útil

# Destinatários gerenciais — Opção A: env JSON (v1, e-mails fixos por nível)
GESTOR_EMAILS='{"gestor_setor":"gerente.setor@dtx.com","gerente_producao":"gerente.producao@dtx.com","assistente_gm":"assistente.gm@dtx.com","gm":"gm@dtx.com"}'
# Opção B (v2): coleção Firestore `gestores` com campo `nivel_gestao` — GESTOR_EMAILS não definida
```

Mapeamento nível → destinatário (Escadas A e B):

| Nível | Chave `GESTOR_EMAILS` | Cargo |
|-------|-----------------------|-------|
| 1 | `gestor_setor` | Gerente do Setor |
| 2 | `gerente_producao` | Gerente de Produção |
| 3 | `assistente_gm` | Assistente GM |
| 4 | `gm` | General Manager |

---

## Addendum — 7 correções alinhadas em 2026-06-23

| # | Decisão | Regra técnica |
|---|---------|---------------|
| 1 | Teto horário unificado | `SLA_HORARIO_FIM=16:30` — evita e-mail ao gerente quando supervisor já saiu |
| 2 | Visibilidade pós-transferência | Ex-owner não vê; novo owner vê imediatamente; invariante anti-órfão |
| 3 | Prazo resolução | Fixo desde `data_em_atendimento`; **nada reseta** (edições, anexos, participantes) |
| 4 | Web Push | Supervisor/owner/participante: in-app + e-mail + Web Push em todas as escaladas |
| 5 | Confirmação solicitante | Obrigatória ao Concluído (fluxo existente `status_service.py`) |
| 6 | Sábado/domingo | Excluídos v1; flag `SLA_INCLUI_FIM_DE_SEMANA` para exceções raras futuras |
| 7 | Almoço 11:30–13:00 | Relógio pausa; `pode_enviar_notificacao_agora()` retorna `False` nesse intervalo |

---

## Decisões Relacionadas

- **ADR-003** — Fail-fast e APScheduler/Redis: define `scheduler_lock.py` e política 1-worker que esta ADR herda
- **ADR-001** — Criptografia PII: `supervisor_id` em `participantes` é ID interno Firestore, não PII direta; sem impacto no Fernet
- **Plano de implementação:** `docs/plans/2026-06-23-escalonamento-sla.md`
- **Plano-mãe:** `.cursor/plans/escalonamento_e_sla_dtx_d3e9e5bb.plan.md`

---

## Resolvido na Fase 6 (2026-06-25)

- **Escada A + job 10 min** (`sla_escalacao`): chamados `Aberto` sem atendimento escalam a cada degrau de 1h útil (60/120/180/240 min) via `processar_escada_a()`.
- **Filtro gestor `aberto_sem_resposta`**: `gestor_dashboard_service._is_aberto_sem_resposta` substituído por `business_time.minutos_uteis_entre` — elimina wall-clock de 60 min.
- **Reabertura reseta `escalacao_resposta_nivel`**: `api_confirmar_resolucao` zera o campo ao reabrir (ADR-004, Task 6.4).
- **Índice Firestore**: `status ASC + escalacao_resposta_nivel ASC` documentado em `docs/INDICES_FIRESTORE.md`.
- **`test_app_init.py` alinhado**: testes de scheduler atualizados para `sla_escalacao` (substitui `alerta_prazo_24h`).

---

## Resolvido na Fase 7 (2026-06-26)

- **Escada B + job 10 min**: chamados `Em Atendimento` escalados a cada degrau de +0h/+4h/+8h/+12h úteis via `processar_escada_b()`.
- **Avisos preventivos 50%/80%**: `processar_avisos_resolucao()` envia alerta ao responsável quando `percentual_prazo_resolucao` atinge 50% e 80%; flags de idempotência gravadas mesmo sem email configurado.
- **Janela útil nos avisos**: `processar_avisos_resolucao` verifica `pode_enviar_notificacao_agora()` antes de disparar — threshold atingido fora do expediente é adiado (`pulados_fora_janela++`) e reprocessado na próxima execução dentro da janela (mesmo comportamento da Escada A/B).
- **Tripla notificação sem e-mail**: quando o responsável não tem e-mail cadastrado, in-app + Web Push disparam normalmente; e-mail omitido; flag de idempotência gravada. Sem e-mail nunca bloqueia a notificação.
- **Badge `em_risco` a partir de 50%**: `obter_sla_para_exibicao` em "Em Atendimento" retorna `"Em risco"` quando `percentual_prazo_resolucao >= 0.5` (alinhado ao primeiro aviso preventivo). Antes era `>= 0.8`.
- **`resumo_sla.em_risco` com tempo útil**: o loop de métricas gerais (`AnalisadorChamados.obter_metricas_gerais`) usa `percentual_prazo_resolucao` para classificar chamados "Em Atendimento" com `data_em_atendimento` como `em_risco` ou `atrasado`, em vez de timedelta de calendário.
- **Reset completo na reabertura / claim**: `escalacao_resolucao_nivel`, `alerta_supervisor_50_enviado` e `alerta_supervisor_80_enviado` zerados junto com `escalacao_resposta_nivel` em toda reabertura ou novo claim.
- **`data_em_atendimento` imutável**: testes de regressão confirmam que edições e `concluir_minha_parte` não sobrescrevem o campo.
- **Índice Firestore**: `status ASC + escalacao_resolucao_nivel ASC` adicionado em `firestore.indexes.json` e documentado em `docs/INDICES_FIRESTORE.md`.

---

## Débitos v1 aceitos — pós Fases 0–6

Registrados em 2026-06-25 após encerramento das lacunas de revisão. Estes débitos são **intencionais** para v1 e devem ser resolvidos conforme planejado.

| Débito | Decisão v1 | Fase de resolução |
|--------|------------|-------------------|
| `edicao_chamado_service` — `novo_responsavel_id` bypassa fluxo formal transferir/escalonar | Manter; usar rotas formais na UI; refatoração futura | Fase 6+ |
| `setores_adicionais` vs `participantes[]` | Dual-path; migração via `migrar_participantes.py` incremental | Fase 6 (remover legado) |
| Status `em_atendimento` em participantes | Fluxo principal: `pendente` → `concluido`; `em_atendimento` não implementado | Fase 6+ |
| ~~Filtro gestor "Aberto sem resposta"~~ | ~~60 min corridos (wall-clock), não tempo útil~~ | ~~Fase 6 (`business_time`)~~ — **RESOLVIDO** |
| `pode_abrir_chamado` | Perfil composto futuro; não implementado v1 | Fase 6+ |
| Gestor acessa `/admin/relatorios` e `/exportar` | Intencional — read-only analítico | Manter |

---

## Referências

- `CLAUDE.md` — TDD obrigatório, ciclo de qualidade, imports inline nas rotas
- `app/services/scheduler_lock.py` — lock de job distribuído (ADR-003)
- `docs/SLO.md` — metas de tempo de resposta existentes (baseline para Escada A/B)
- `docs/INDICES_FIRESTORE.md` — índices existentes; novos índices compostos a adicionar na Fase 2
- `app/services/status_service.py` — fluxo `confirmacao_solicitante` existente a integrar
- `app/services/webpush_service.py` — serviço de Web Push a reutilizar nas escaladas
