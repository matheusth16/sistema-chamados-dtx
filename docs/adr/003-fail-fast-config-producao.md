# ADR-003: Fail-Fast em Configuração de Produção

## Status

Accepted — 2026-06-22

---

## Context

O sistema de chamados DTX executa em um único container Docker com **1 worker Gunicorn** (gthread). Antes desta decisão, a ausência de variáveis de ambiente críticas em produção resultava em comportamento silenciosamente degradado:

- `APP_BASE_URL` ausente → links em e-mails e notificações push quebrados (URLs relativas inválidas)
- `HEALTH_SECRET` ausente → endpoint `/health?deep=1` exposto sem autenticação, vazando status interno (Firestore, Redis)
- `SECRET_KEY` padrão → sessões forjáveis (já resolvido antes desta ADR)
- `REDIS_URL` ausente → rate limit por memória local (aceitável com 1 worker, problemático com múltiplos)

O padrão fail-fast (crash no boot com mensagem clara) é preferível ao fail-silent (crash em runtime sem contexto), especialmente em deploys containerizados onde o healthcheck detecta imediatamente a falha.

---

## Decision Drivers

- **CWI 2.1:** HTTPS obrigatório em produção (APP_BASE_URL deve ser `https://`)
- **Operacional:** HEALTH_SECRET protege endpoint que expõe estado interno do sistema
- **Escalabilidade controlada:** Redis é opcional no cenário atual DTX (1 worker), mas obrigatório se escalar
- **Dev UX:** validação deve ser transparente em development/testing (sem vars obrigatórias)

---

## Considered Options

### Opção A: Fail-fast para tudo (incluindo Redis)

Exigir `REDIS_URL` sempre em produção.

- **Contra:** Quebra o deploy atual DTX (1 worker, sem Redis provisionado)
- **Contra:** Força infra adicional desnecessária para o cenário atual

### Opção B: Warning-only para Redis, fail-fast apenas para vars CWI/ops (escolhida)

- `APP_BASE_URL` e `HEALTH_SECRET` → `ValueError` no import
- `REDIS_URL` ausente + 1 worker → `warnings.warn` (não quebra boot)
- `REDIS_URL` ausente + `GUNICORN_WORKERS > 1` → `ValueError`
- `REDIS_URL` ausente + `REQUIRE_REDIS=true` → `ValueError`

- **A favor:** Cenário atual DTX continua funcionando
- **A favor:** Operador tem opt-in explícito via `REQUIRE_REDIS=true`
- **A favor:** Scale-out protegido automaticamente via `GUNICORN_WORKERS`

### Opção C: Validação apenas via documentação (sem código)

- **Contra:** Histórico do projeto mostra que docs são ignorados sob pressão de deploy
- **Contra:** Sem evidência verificável por CI

---

## Decision

Adotar **Opção B**: fail-fast seletivo, implementado em `config.py:_validar_config_producao()`.

### Regras em produção (`FLASK_ENV=production`)

| Variável | Comportamento se ausente/inválida |
|---|---|
| `SECRET_KEY` (pré-existente) | `ValueError` no import |
| `APP_BASE_URL` | `ValueError` — obrigatória, deve ser `https://` |
| `HEALTH_SECRET` | `ValueError` — obrigatória, mínimo 16 chars |
| `REDIS_URL` + 1 worker + `REQUIRE_REDIS=false` | `warnings.warn` — boot prossegue |
| `REDIS_URL` ausente + `GUNICORN_WORKERS > 1` | `ValueError` |
| `REDIS_URL` ausente + `REQUIRE_REDIS=true` | `ValueError` |

### Por que APP_BASE_URL e HEALTH_SECRET são obrigatórias

- **APP_BASE_URL:** links em e-mails, notificações push e validação Origin/Referer dependem desta URL. Sem ela, todas as notificações produzem links quebrados. O valor deve ser `https://` para satisfazer CWI 2.1 (sem mixed-content, sem downgrade).

- **HEALTH_SECRET:** `/health?deep=1` expõe latência Firestore, status Redis e contagem de documentos — informações de reconhecimento. Sem token, qualquer agente externo pode verificar o estado interno. Mínimo de 16 chars previne brute-force trivial.

### Por que Redis é warning com 1 worker

O deploy atual DTX usa `start.sh --workers 1` (ver `docs/DEPLOYMENT_PLAN.md`). Com 1 worker (multi-thread gthread), o rate limit em memória local funciona corretamente — todos os threads compartilham o mesmo processo. Adicionar Redis obrigatório aumentaria a complexidade operacional sem ganho para o cenário atual.

Quando o operador escalar para múltiplos workers/containers, basta definir `GUNICORN_WORKERS=N` (N > 1) ou `REQUIRE_REDIS=true` — o boot falhará com mensagem clara exigindo `REDIS_URL`.

---

## Consequences

### Positivas

- Deploy em produção sem vars obrigatórias falha imediatamente com mensagem acionável
- CI pode detectar config inválida antes do rollout
- Cenário 1-worker DTX continua operacional sem Redis
- Escalonamento futuro protegido automaticamente

### Negativas / Mitigações

- Desenvolvedor em modo produção local precisa definir `APP_BASE_URL` e `HEALTH_SECRET`
  - Mitigação: `.env.example` documenta os valores; `FLASK_ENV=development` bypassa a validação
- `warnings.warn` para Redis pode ser ignorado silenciosamente
  - Mitigação: `REQUIRE_REDIS=true` no `.env` de produção como opt-in explícito

---

## Implementation

- `config.py:_validar_config_producao()` — função pura testável, chamada no import
- `tests/test_config_production.py` — 17 testes unitários, integração e reload isolado
- `.env.example` — `HEALTH_SECRET`, `REQUIRE_REDIS`, `GUNICORN_WORKERS` documentados
- `docs/ENV.md` — seção "Produção (obrigatórias)" atualizada

### Autenticação do endpoint deep health (Ressalva R1 — pós ADR)

O finding MEDIUM identificado pós-implementação (HEALTH_SECRET em query string `?token=` visível em access logs) foi resolvido em `app/routes/api_chamados.py`:

- Canal primário: header `X-Health-Token` (não aparece em access logs do Gunicorn/nginx)
- Canal deprecado: `?token=` mantido para compatibilidade UptimeRobot/BetterUptime legado
- Comparação: `hmac.compare_digest()` — timing-safe, previne timing attacks
- Testes: CT-HEALTH-10 a 13 (`tests/test_routes/test_health_sw.py`)

## Related Decisions

- ADR-001 (planejado): Criptografia PII Fernet — Onda 4
- ADR-002 (planejado): Proteção ambientes staging — Onda 5
- `docs/CHECKLIST_SEGURANCA.md` Seção 7.2 — CWI 2.1 evidências

## References

- [CWI Testes de Segurança para QAs](https://cwi.com.br/blog/testes-de-seguranca-para-qas/) — CWI 2.1
- OWASP A05:2021 — Security Misconfiguration
- `app/__init__.py:_forcar_https()` — redirect 301 HTTP→HTTPS
- `tests/test_app_init.py::test_forcar_https_redireciona_em_producao` — evidência HTTPS
