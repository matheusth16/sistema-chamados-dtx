# SLOs — DTX Digital Andon System

> Definições de Service Level Objectives para o ambiente de produção no Railway.
> Revisão: 2026-06-10

---

## Contexto

Sistema interno da DTX Aerospace utilizado por 3 perfis (solicitante, supervisor, admin).
Deploy: Railway (instância única, Firestore como banco, Brevo para e-mail, R2 para anexos).
Público-alvo: equipes internas — tolerância a downtime em horário fora-de-expediente é maior.

---

## SLO-01 — Disponibilidade (Uptime)

| Janela | Meta | Budget de erro |
|--------|------|----------------|
| Mensal | 99,5% | 3h 36min/mês |
| Semanal | 99,0% | 1h 40min/semana |

**Medição:** UptimeRobot (gratuito) monitora `GET /health` a cada 5 minutos.
- Configurar alerta por e-mail quando down por > 2 checks consecutivos (10 min).
- URL: `https://<seu-domínio>.up.railway.app/health`

**Horário com peso:** dias úteis 07h–19h BRT têm peso 2× no orçamento.

---

## SLO-02 — Latência de Resposta

| Percentil | Rota | Meta |
|-----------|------|------|
| p95 | Páginas HTML (dashboard, meus-chamados) | < 2 000 ms |
| p95 | API AJAX (atualizar-status, carregar-mais) | < 500 ms |
| p99 | Qualquer rota | < 5 000 ms |

**Medição:** log `app.performance` — cada linha tem `duration_ms`.
- No Railway: filtrar logs por `duration_ms` para detectar regressões.
- Query Railway log drain: `duration_ms > 2000 status=200`

---

## SLO-03 — Taxa de Erros

| Métrica | Meta |
|---------|------|
| Taxa de respostas 5xx | < 1% das requisições/hora |
| Erros não tratados (500) | 0 em janela de 24h |

**Medição:** log `app.errors` — linha por 5xx com `status=`, `path=`, `duration_ms=`.
- No Railway: buscar `http_error` nos logs. Qualquer ocorrência é alarme.

---

## SLO-04 — Conectividade com Firestore

| Métrica | Meta |
|---------|------|
| Latência Firestore p95 | < 300 ms |
| Falhas de conexão | 0 em janela de 1h |

**Medição:** `GET /health?deep=1` — campo `checks.firestore` e `duration_ms`.
- Configurar monitor separado em UptimeRobot para `/health?deep=1`.
- Resposta `"status": "degraded"` = alerta imediato.

---

## SLO-05 — Jobs Agendados (Scheduler)

| Job | Frequência | Meta |
|-----|-----------|------|
| Relatório semanal | Sexta 10h BRT | Executar dentro de ±5 min |
| Alerta prazo 24h | Diário 08h BRT | Executar dentro de ±10 min |

**Medição:** `app.logger.info("Relatório semanal concluído: ...")` nos logs Railway.
- Ausência da linha de log na janela esperada = job não executou.

---

## Setup de Monitoramento no Railway

### 1. Health Check Railway (nativo)

No `railway.toml` ou via painel Railway:
```toml
[deploy]
healthcheckPath = "/health"
healthcheckTimeout = 300
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 3
```

### 2. UptimeRobot (gratuito)

1. Criar conta em uptimerobot.com
2. Adicionar monitor HTTP(s):
   - URL: `https://<domínio>/health`
   - Intervalo: 5 minutos
   - Alerta: e-mail para matheus00237@gmail.com
3. Adicionar segundo monitor:
   - URL: `https://<domínio>/health?deep=1`
   - Keyword: `"status": "ok"` (falha se não encontrar)
   - Intervalo: 15 minutos

### 3. Log Drain Railway (opcional, nível seguinte)

No painel Railway → Settings → Observability → Log Drain:
- Destino: Logtail (gratuito, 1GB/mês) ou Datadog
- Filtros importantes para criar alertas no destino:
  - `http_error` → alerta Slack/e-mail
  - `health_check status=degraded` → alerta crítico
  - `duration_ms > 3000` → alerta de performance

---

## Runbook de Incidentes

> Ver também: `docs/INCIDENT_RUNBOOK.md`

### App não responde (SLO-01 violado)

1. Verificar Railway dashboard → Deployments → logs do deploy atual
2. Verificar se `GET /health` retorna 200 (curl ou browser)
3. Se 502/503: Railway pode estar reiniciando — aguardar 2 min
4. Se persiste: `railway redeploy` via CLI

### Firestore degraded (SLO-04 violado)

1. `GET /health?deep=1` → ver `checks.firestore`
2. Verificar Firebase Console → Firestore → Usage → quotas
3. Verificar `GOOGLE_CREDENTIALS_JSON` no Railway (Settings → Variables)
4. Ver logs: filtrar por `health_check firestore falhou`

### Latência alta (SLO-02 violado)

1. Filtrar logs: `duration_ms > 2000`
2. Identificar rotas lentas (N+1 no dashboard é suspeito habitual)
3. Ver `app/services/dashboard_service.py` — busca em Firestore sem índice
4. Verificar se Redis está disponível (`checks.cache` no `/health?deep=1`)

---

## Alertas específicos — eventos de `app.metrics`

O módulo `app/services/metrics.py` emite eventos estruturados via logger `app.metrics`.
Filtre esses padrões no Railway log drain ou Cloud Logging para criar alertas.

| Evento | Filtro no log | Alerta |
|--------|--------------|--------|
| Erro HTTP 5xx | `http_error` | Imediato — 1 ocorrência em 5 min |
| Lockout de login | `login_lockout` | Alerta se > 5/hora (brute-force) |
| Falha Web Push | `webpush_falha` | Alerta se > 20% das entregas falharem |
| SLA vencido | `sla_vencido` | Informativo — sem alerta automático |
| Job agendado ausente | (ausência de linha) | Ver SLO-05 |

### Configurar alertas no Railway (Log Drain → Logtail)

```bash
# Criar alerta no Logtail para 5xx
# Filtro: event=http_error
# Condição: qualquer ocorrência → e-mail imediato

# Criar alerta para lockout excessivo
# Filtro: event=login_lockout
# Condição: count > 5 em janela 60 min → e-mail

# Criar alerta para falhas Web Push
# Filtro: event=webpush_falha
# Condição: count > 10 em janela 60 min → e-mail
```

### Emitir evento de lockout no auth

Em `app/routes/auth.py`, após bloquear usuário:
```python
from app.services.metrics import login_lockout
login_lockout()  # não inclui email para não persistir PII em logs
```

Em `app/services/webpush_service.py`, após falha de entrega push:
```python
from app.services.metrics import webpush_falha
webpush_falha(user_id=user_id, motivo=str(e)[:80])
```

---

## Revisão e Ajuste

Revisar SLOs a cada 3 meses ou após mudança significativa no volume de uso.
Baseline atual: sistema com < 50 usuários ativos. Ajustar metas ao crescer.
