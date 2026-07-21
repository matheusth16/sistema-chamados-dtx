# k6 Load Tests — sistema_chamados

Testes de performance para validar o Cloud Run antes do go-live (deadline 19/06/2026).

## Instalação do k6

```powershell
# Windows (Chocolatey)
choco install k6

# Verificar
k6 version
```

## Scripts disponíveis

| Script | Objetivo | VUs | Duração |
|---|---|---|---|
| `smoke.js` | Sanidade — serviço está no ar? | 1 | 30s |
| `load.js` | Carga realista (10 usuários simultâneos) | 10 | ~4 min |
| `stress.js` | Encontrar ponto de ruptura | até 30 | ~7 min |

## Como rodar

### 1. Smoke test (antes de qualquer deploy)

```bash
k6 run -e BASE_URL=http://localhost:5000 scripts/qa/k6/smoke.js
```

### 2. Load test (antes do go-live)

```bash
k6 run \
  -e BASE_URL=https://SEU_DOMINIO \
  -e ADMIN_EMAIL=admin@dtx.aero \
  -e ADMIN_SENHA=SUA_SENHA \
  -e SUP_EMAIL=supervisor@dtx.aero \
  -e SUP_SENHA=SUA_SENHA \
  scripts/qa/k6/load.js
```

### 3. Stress test (encontrar limite do Cloud Run)

```bash
k6 run \
  -e BASE_URL=https://SEU_DOMINIO \
  scripts/qa/k6/stress.js
```

## SLOs esperados (Cloud Run: 1 CPU, 512Mi, 1 worker + 8 threads)

| Métrica | Alvo | Crítico |
|---|---|---|
| p95 latência HTML | < 1500ms | > 3000ms |
| p95 latência API JSON | < 800ms | > 2000ms |
| Taxa de erro | < 1% | > 5% |
| Health check p99 | < 500ms | > 1000ms |

## Interpretando os resultados

### Load test passou → pronto para go-live

```
✓ http_req_failed........: 0.00%   ✓ 0   ✗ 0
✓ http_req_duration......: avg=342ms p(95)=892ms
```

### Stress test — identificar gargalo

Observe em qual estágio o p95 cruza 3s:
- Se cruzar já em 10 VUs → problema no código (N+1, bloqueio)
- Se cruzar em 20-30 VUs → limite da config atual do Cloud Run (normal)
- Se health check degradar → problema sistêmico (CPU/memória)

### Após o stress test, verificar logs do Cloud Run:

```bash
gcloud run services logs read sistema-chamados \
  --region=southamerica-east1 \
  --limit=100
```

Sinais de alerta nos logs:
- `WORKER TIMEOUT` → Firestore query lenta (N+1 no dashboard)
- `Memory limit exceeded` → Aumentar para 1Gi
- `Too many connections` → Reduzir `--max-instances`
