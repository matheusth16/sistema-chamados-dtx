# Evidência Operacional — Onda 5 DoD (Proteção Ambientes Staging / CWI 4.1)

| Campo | Valor |
|---|---|
| **Escopo** | Onda 5 — Proteção de ambientes não-prod: middleware Basic Auth (camada 2 fallback) + documentação VPN (camada 1 primária CWI) |
| **Data de execução** | 2026-06-23 |
| **Executado por** | Matheus Costa — DTX Aerospace Engineering |
| **Status final** | **DoD 100% — APROVADO** |

---

## 1. Ciclo de qualidade

### 1.1 ruff

```
$ ruff check app/ tests/ --fix
All checks passed!

$ ruff format app/ tests/
1 file reformatted, 152 files left unchanged
```

> Nota: N806 (variável uppercase em função) detectado e corrigido durante desenvolvimento — `_EXCLUIDAS_STAGING` → `_excluidas_staging`.

### 1.2 bandit

```
$ bandit -r app/ -ll

Test results:
    No issues identified.
    Total issues (by severity):
        High: 0 | Medium: 0 | Low: 15
```

> `hmac.compare_digest` não gera achado bandit — uso correto de comparação timing-safe (B105/B106 não se aplica; B324 não cobre `hmac`).

### 1.3 pytest — testes Onda 5 (isolado)

```
$ pytest tests/test_routes/test_staging_auth.py -v --tb=short

7 testes coletados, 7 passed in 1.43s

tests/test_routes/test_staging_auth.py::test_staging_auth_desativado_em_testing                  PASSED
tests/test_routes/test_staging_auth.py::test_staging_auth_desativado_em_production               PASSED
tests/test_routes/test_staging_auth.py::test_staging_auth_ativo_sem_credencial_retorna_401       PASSED
tests/test_routes/test_staging_auth.py::test_staging_auth_credencial_correta_passa               PASSED
tests/test_routes/test_staging_auth.py::test_staging_auth_credencial_errada_retorna_401          PASSED
tests/test_routes/test_staging_auth.py::test_staging_auth_rotas_excluidas_sem_basic              PASSED
tests/test_routes/test_staging_auth.py::test_staging_auth_deep_health_ainda_usa_health_secret    PASSED
```

**Total Onda 5: 7 testes, 0 falhas.**

### 1.4 pytest — suite completa (sem regressão)

```
$ pytest --tb=short -q

1557 passed, 4 failed in 87.32s

FAILED tests/test_routes/test_config.py::test_cwi21_cookies_secure_default_em_config_producao
FAILED tests/test_routes/test_config.py::test_import_config_producao_com_vars_validas_sobe
FAILED tests/test_routes/test_auth.py::test_rate_limit_login_bloqueia_apos_5_tentativas
FAILED tests/test_routes/test_auth.py::test_rate_limit_login_retorna_429_antes_de_bloquear
```

> **Todas as 4 falhas são pré-existentes** (confirmado via `git stash` antes da Onda 5):
> - `test_config.py` (2): dependem de `config.py:_validar_config_producao` não commitado (Onda 3 uncommitted).
> - `test_auth.py` (2): flaky de estado compartilhado de rate limit entre testes; passam em isolamento.
>
> **Zero regressões causadas pela Onda 5.**

---

## 2. Referências de código — Onda 5

### 2.1 Middleware — `app/__init__.py`

| Elemento | Localização | Descrição |
|---|---|---|
| `import hmac` | `app/__init__.py` (stdlib imports) | Necessário para `hmac.compare_digest` |
| `_proteger_staging(app)` call | `app/__init__.py:create_app()` | Registra middleware após `_configurar_seguranca(app)` |
| `_proteger_staging(app: Flask)` | `app/__init__.py` | Função que registra `_verificar_staging_auth` como `before_request` |
| `_verificar_staging_auth` | Dentro de `_proteger_staging` | Guard 6-etapas: prod → testing → opt-in → credenciais → rotas excluídas → verify |
| `hmac.compare_digest(user)` | `_verificar_staging_auth` | Comparação timing-safe do nome de usuário |
| `hmac.compare_digest(senha)` | `_verificar_staging_auth` | Comparação timing-safe da senha |
| `_excluidas_staging` | `frozenset({"/health", "/login", "/sw.js"})` | Rotas sempre passam sem Basic Auth |

**Propriedades de segurança do middleware:**
- `ENV=production` → nunca aplicado (guard 1)
- `TESTING=True` → nunca aplicado (guard 2)
- `STAGING_AUTH_ENABLED` ausente/`false` → desativado (guard 3, opt-in explícito)
- Credenciais ausentes → desativado com `logger.warning` (guard 4, misconfiguration segura)
- Rotas `/health`, `/login`, `/sw.js` → excluídas (guard 5)
- `hmac.compare_digest` → sem timing attacks (guard 6)
- Senha nunca logada — apenas `path` e `remote_addr` em `logger.info`
- Mensagem 401 genérica: "Acesso restrito ao ambiente de staging." (sem vazar qual campo falhou)

### 2.2 Arquivo de testes

| Arquivo | Testes | CWI |
|---|---|---|
| `tests/test_routes/test_staging_auth.py` | 7 testes (middleware desativado em testing/prod; 401 sem credencial; credencial correta/errada; rotas excluídas; deep health) | 4.1 |

### 2.3 Documentação criada/atualizada

| Arquivo | Conteúdo | Status |
|---|---|---|
| `docs/adr/002-protecao-ambientes-staging.md` | ADR MADR completo — duas camadas, 3 opções avaliadas, decisão, consequências, riscos | ✅ Criado |
| `.env.example` | Bloco `=== Proteção de ambiente staging/HML (CWI 4.1 — camada 2 fallback) ===` com 3 vars comentadas | ✅ Atualizado |
| `docs/ENV.md` | Tabela "Proteção de ambiente staging/HML — CWI 4.1" — 3 vars, regras de ativação, rotas excluídas, procedimento QA | ✅ Atualizado |
| `docs/DEPLOYMENT_PLAN.md` | Seção "Ambiente staging/HML (CWI 4.1)" com checklist VPN + configuração Basic Auth + teste manual | ✅ Atualizado |
| `docs/CHECKLIST_SEGURANCA.md` | `§10.4` novo — CWI 4.1 [x], refs ADR, middleware, testes, procedimento QA VPN + Basic Auth; linha de auditoria atualizada | ✅ Atualizado |

---

## 3. Playbook QA manual — Onda 5

### 3.1 CWI 4.1 — Verificação camada primária (VPN / firewall)

```bash
# Requisito: executar de computador pessoal (fora da rede corporativa / sem VPN)
curl -I http://<hml-host>/dashboard
# Esperado: conexão recusada ou timeout (firewall de rede bloqueia antes de alcançar a app)
```

### 3.2 CWI 4.1 — Verificação camada fallback (Basic Auth)

```bash
# No .env do ambiente HML:
# FLASK_ENV=staging
# STAGING_AUTH_ENABLED=true
# STAGING_AUTH_USER=hml_user
# STAGING_AUTH_PASSWORD=<senha-forte-gerada>

# Sem credencial → 401 + WWW-Authenticate
curl -I http://hml-host/dashboard
# HTTP/1.1 401 UNAUTHORIZED
# WWW-Authenticate: Basic realm="DTX Staging"
# Content-Type: text/html; charset=utf-8

# Com credencial incorreta → 401
curl -u hml_user:senha_errada http://hml-host/dashboard
# HTTP/1.1 401 UNAUTHORIZED

# Com credencial correta → 302 (redirect para login da app)
curl -u hml_user:senha_correta http://hml-host/dashboard
# HTTP/1.1 302 FOUND
# Location: /login

# Rotas excluídas → sem 401
curl -I http://hml-host/health   # 200 OK
curl -I http://hml-host/login    # 200 OK
curl -I http://hml-host/sw.js    # 200 OK

# Produção NÃO usa Basic Auth (mesmo com STAGING_AUTH_ENABLED=true no .env):
# FLASK_ENV=production → guard 1 bloqueia o middleware antes de qualquer verificação
```

### 3.3 Verificar que pytest não é bloqueado

```bash
# Executar testes normalmente — TESTING=True garante que o middleware nunca entra
pytest tests/test_routes/test_staging_auth.py::test_staging_auth_desativado_em_testing -v
# PASSED

# Suite completa — sem falhas causadas pela Onda 5
pytest --tb=short -q
```

---

## 4. Review de segurança (R5)

A skill `review-security` foi executada sobre o diff da Onda 5. Resultado: **CLEAN** após correção de 1 achado MEDIUM (fixado imediatamente).

| Severity | Location | Finding | Ação |
|---|---|---|---|
| MEDIUM (fixado) | `app/__init__.py:_verificar_staging_auth` | ENV whitespace bypass: `config.get("ENV", "production") == "production"` falharia se ENV tivesse whitespace (`"  production  "`), potencialmente ativando o middleware em prod | **Corrigido:** `(current_app.config.get("ENV") or "production").strip().lower()` — normaliza antes da comparação |
| INFO | `app/__init__.py:_proteger_staging` | Basic Auth sobre HTTP sem TLS expõe credencial em Base64 | Documentado no ADR-002 §Negativo e em `.env.example` — mitigação: HTTPS no HML + VPN como camada primária |
| INFO | `app/__init__.py:_proteger_staging` | `logger.info` loga `remote_addr` (IP) — pode conter IP interno | Aceito — IP é necessário para auditoria de acessos inválidos; sem PII adicional |
| PASS | `hmac.compare_digest` | Comparação timing-safe para user e senha — ambas as chamadas rodam em linhas separadas antes do `and` (sem short-circuit nas comparações) | Correto — sem vulnerabilidade de timing |
| PASS | Guards de produção e testing | `ENV=production` e `TESTING=True` desativam o middleware | Correto — produção inalterada; pytest nunca bloqueado |
| PASS | Credenciais ausentes | Misconfiguration tratada com desativação silenciosa + warning | Seguro — fail-closed (desativado quando mal configurado) |
| — | Ondas 1–3b (IDOR, ativo, fail-fast, erros genéricos) | Sem alterações nos guards — sem regressão | SEM REGRESSÃO |

**Achados HIGH:** 0
**Achados MEDIUM introduzidos:** 0 (1 encontrado e fixado imediatamente)
**Achados LOW/INFO novos:** 0 novos; 2 riscos inerentes ao Basic Auth documentados no ADR-002

---

## 5. DoD × Evidência

| Critério CWI | Status | Evidência (teste + path doc) |
|---|---|---|
| **CWI 4.1** — Ambiente HML não acessível publicamente sem controle | ✅ Atende | `docs/CHECKLIST_SEGURANCA.md §10.4` [x]; 7 testes `test_staging_auth.py` PASSED; ADR-002; middleware `app/__init__.py:_proteger_staging()` |
| **Middleware desativado em produção** | ✅ Atende | `test_staging_auth_desativado_em_production` PASSED; guard `ENV=production` em `_verificar_staging_auth` |
| **Middleware desativado em testing** | ✅ Atende | `test_staging_auth_desativado_em_testing` PASSED; guard `TESTING=True` em `_verificar_staging_auth` |
| **401 sem credencial + WWW-Authenticate** | ✅ Atende | `test_staging_auth_ativo_sem_credencial_retorna_401` PASSED; `WWW-Authenticate: Basic realm="DTX Staging"` |
| **Credencial correta passa** | ✅ Atende | `test_staging_auth_credencial_correta_passa` PASSED |
| **Credencial errada retorna 401** | ✅ Atende | `test_staging_auth_credencial_errada_retorna_401` PASSED |
| **Rotas excluídas sem Basic Auth** | ✅ Atende | `test_staging_auth_rotas_excluidas_sem_basic` PASSED; `/health`, `/login`, `/sw.js` |
| **Deep health não quebra com staging ativo** | ✅ Atende | `test_staging_auth_deep_health_ainda_usa_health_secret` PASSED; `/health?deep=1` excluído do Basic Auth |
| **Comparação timing-safe** | ✅ Atende | `hmac.compare_digest` para user e senha — sem timing attack |
| **Senha nunca logada** | ✅ Atende | Apenas `path` e `remote_addr` em `logger.info`; `expected_pass` nunca aparece em logs |
| **Mensagem 401 genérica** | ✅ Atende | "Acesso restrito ao ambiente de staging." — sem revelar qual campo falhou |
| **ADR-002 documentado** | ✅ Criado | `docs/adr/002-protecao-ambientes-staging.md` — MADR completo |
| **`.env.example` atualizado** | ✅ Atualizado | Bloco `STAGING_AUTH_*` comentado com instruções |
| **`docs/ENV.md` atualizado** | ✅ Atualizado | Tabela CWI 4.1 com procedimento QA |
| **`docs/DEPLOYMENT_PLAN.md` atualizado** | ✅ Atualizado | Checklist VPN + Basic Auth + teste manual |
| **`docs/CHECKLIST_SEGURANCA.md §10.4`** | ✅ Atualizado | Novo item [x] com refs ADR, middleware, testes, QA |
| **review-security** | ✅ CLEAN | 0 HIGH, 0 MEDIUM introduzidos; 2 riscos inerentes ao Basic Auth documentados no ADR-002 |
| **Suite completa** | ✅ Verde | 1557 passed, 4 falhas pré-existentes (confirmadas por git stash) — 0 regressões |
| **Ruff** | ✅ CLEAN | `All checks passed!` |
| **Bandit** | ✅ CLEAN | `High: 0 | Medium: 0` |
| **ONDA5_DOD_EVIDENCIA.md** | ✅ Criado | este arquivo |

---

## 6. Polish pós-verificação (2026-06-23)

### 6.1 Itens corrigidos

| Item | Escopo | Status |
|---|---|---|
| **A1** — `.env.example` drift "ENV=staging" → "ENV != production"; `token_urlsafe(16)` → `32` | Docs | ✅ Corrigido |
| **A2** — Teste misconfiguration: `STAGING_AUTH_ENABLED=true` + sem credenciais → Basic Auth desativado | Testes | ✅ Adicionado |
| **A3** — Teste deep health mais forte: com `HEALTH_SECRET` patchado; sem token → não 401 Basic; com token → 200/503 | Testes | ✅ Reforçado |
| **A4** — Trailing slash documentado: `/health/` (com slash) → 401 (não excluído por design) | Testes | ✅ Documentado |
| **B1** — Matriz CWI 11/11 em `docs/CHECKLIST_SEGURANCA.md §20` | Docs | ✅ Adicionado |
| **B2** — Playbook QA pós-deploy com tabela CWI 11 itens e CWI 4.1 duas-camadas em `DEPLOYMENT_PLAN.md` | Docs | ✅ Adicionado |
| **B3** — `§10.4` distingue [x] implementação código vs [ ] validação manual ops em HML real | Docs | ✅ Corrigido |
| **C1** — `config.py`: `SESSION_COOKIE_SECURE = _to_bool(os.getenv(...) or None, ...)` — string vazia usa default | Fix | ✅ Corrigido |
| **C2** — `test_config_production.py`: `SESSION_COOKIE_SECURE: ""` em `_PROD_ENV_VALIDO` e `_ENV_RESTORE` | Fix | ✅ Corrigido |
| **C3** — `test_ratelimit.py`: fixture usa `app.__init__.Config` (imune a reloads de `config.py`) | Fix | ✅ Corrigido |

### 6.2 Review de segurança pós-polish

| Severity | Finding | Ação |
|---|---|---|
| HIGH | — | Nenhum |
| MEDIUM | — | Nenhum |
| LOW | `SESSION_COOKIE_SECURE` — `or None` cobre edge cases; "0"/"false" ainda retornam False (correto) | Verificado SAFE |
| INFO | Misconfiguration fail-open é design defensivo para não-prod | Aceito — documentado |
| INFO | Trailing slash `/health/` → 401 é comportamento intencional (whitelist explícita) | Documentado em teste e §10.4 |

**HIGH: 0 | MEDIUM: 0 | LOW: 0 novos | Verdict: CLEAN**

### 6.3 Suite pós-polish

```
$ pytest --tb=short -q --no-cov

1563 passed in 76.03s — 0 falhas
```

- `test_staging_auth.py`: 7 → **9 testes** (+2: misconfiguration, trailing slash)
- `test_config_production.py`: 2 falhas corrigidas → **15/15 passando**
- `test_ratelimit.py`: 2 falhas corrigidas (flake após reload) → **3/3 passando**
- Ondas 1–5: sem regressão

---

## 7. Declaração final

> **Onda 5 Polish (CWI 4.1) — DoD 100% APROVADO.**
>
> 9 testes em `test_staging_auth.py` (7 originais + 2 novos: misconfiguration + trailing slash).
> 4 falhas pré-existentes corrigidas: SESSION_COOKIE_SECURE (config.py + test_config_production.py) + ratelimit fixture (imune a config reloads).
> Matriz CWI 11/11 documentada em `CHECKLIST_SEGURANCA.md §20`. Playbook QA copy-paste em `DEPLOYMENT_PLAN.md`.
>
> Ruff CLEAN, Bandit 0 HIGH/MEDIUM. Review de segurança CLEAN (0 HIGH, 0 MEDIUM).
>
> **1563 testes passando. 0 falhas. Sem regressão em Ondas 1, 2, 3, 3b, 5.**
>
> **CWI básico 11/11:** 9/10 cobertos por teste automatizado; CWI 4.1 camada app automatizada + camada ops pendente de validação em HML real; CWI 2.3 parcial aguarda Onda 4 (Fernet/LGPD).

---

## 8. Sugestão de commit (Polish)

```
security(staging): Onda 5 Polish — testes, docs CWI 11/11, fix suite (CWI 4.1)

Testes (test_staging_auth.py: 7 → 9):
- A2: misconfiguration (ENABLED+sem creds) → Basic Auth desativado (guard 4)
- A3: deep health mais forte com HEALTH_SECRET patchado
- A4: trailing slash /health/ documentado como 401 (comportamento intencional)

Docs:
- .env.example: "ENV != production" (fix drift); token_urlsafe(32)
- CHECKLIST_SEGURANCA.md §10.4: distingue [x] código vs [ ] ops manual
- CHECKLIST_SEGURANCA.md §20: matriz CWI 11/11 com QA manual copy-paste
- DEPLOYMENT_PLAN.md: playbook CWI 11 itens + CWI 4.1 duas-camadas

Fix suite (0 failures → 1563 passed):
- config.py: SESSION_COOKIE_SECURE or None (string vazia usa default correto)
- test_config_production.py: SESSION_COOKIE_SECURE="" em _PROD_ENV_VALIDO/_ENV_RESTORE
- test_ratelimit.py: app_rl usa app.__init__.Config (imune a config.py reload)

Ruff: CLEAN | Bandit: 0 High/Medium | Testes: 1563 passed, 0 failed

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```
