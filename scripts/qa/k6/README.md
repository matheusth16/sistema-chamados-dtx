# k6 — testes de performance

Os scripts validam o serviço Flask em desenvolvimento, staging e, quando
explicitamente autorizado, no servidor on-premise de produção.

## Proteção contra execução acidental

`_shared.js` bloqueia qualquer `BASE_URL` que não seja `localhost` ou
`127.0.0.1`. Para um alvo remoto, a confirmação precisa estar no mesmo comando:

```powershell
k6 run -e BASE_URL=https://staging.example.com -e K6_CONFIRM_PROD=1 scripts/qa/k6/smoke.js
```

Use `K6_CONFIRM_PROD=1` somente após conferir URL, janela e tipo de teste.
Nunca use credenciais reais na linha de comando ou em arquivos versionados.

## Instalação no Windows

```powershell
winget install --id GrafanaLabs.k6 --exact --accept-package-agreements --accept-source-agreements
# alternativa:
choco install k6 -y

k6 version
```

## Scripts

- `smoke.js`: 1 VU por 30 segundos; verifica `/health` e `/login`.
- `load.js`: rampa até 10 VUs por cerca de 4 minutos.
- `stress.js`: rampa até 30 VUs; use apenas em janela controlada.
- `spike.js`: pico moderado de 15 VUs por 3 minutos.
- `soak.js`: 3 VUs por 15 minutos; altere com `K6_DURATION`.

Todos usam alvo local por padrão e aplicam o guard compartilhado.

## Smoke local automatizado

O runner inicia um stub Flask sem banco e sem secrets, espera `/health`, executa
o smoke e encerra o processo no bloco `finally`:

```powershell
.\scripts\qa\k6\run_local_smoke.ps1
```

Execução direta:

```powershell
k6 run -e BASE_URL=http://127.0.0.1:5000 scripts/qa/k6/smoke.js
k6 run -e BASE_URL=http://127.0.0.1:5000 scripts/qa/k6/spike.js
k6 run -e BASE_URL=http://127.0.0.1:5000 -e K6_DURATION=30m scripts/qa/k6/soak.js
```

## CI e produção

`.github/workflows/k6-smoke.yml` mantém o smoke semanal contra
`PRODUCTION_URL`. O workflow define a confirmação explícita para esse schedule.
Em execução manual, é obrigatório marcar `confirm_production`; sem isso o job e
o próprio script bloqueiam o alvo remoto.

Após testes remotos, consulte os logs on-premise conforme
`docs/INCIDENT_RUNBOOK.md`. Alertas principais: timeout de worker, aumento
contínuo de latência, esgotamento de memória e conexões PostgreSQL.
