# Checklist de Segurança — Sistema de Chamados DTX Aerospace

| Campo | Valor |
|---|---|
| **Documento** | Checklist de Segurança — Revisão de PR e Deploy |
| **Versão** | 3.4 |
| **Data** | 2026-06-22 |
| **Autor** | DTX Aerospace — Engenharia de Software |
| **Última auditoria** | 2026-06-23 (Sprint + F-81 + Onda A + Fase 0 + Onda B + Onda C wave 1 + Onda C wave 2 + Onda C wave 3 + Onda 2 — Segurança e API + Onda 3 — Negócio e relatórios + **Onda 4 — Infraestrutura** + **Gate Final — Cobertura** + **Desativação de usuários (ativo=false)** + **Onda 3 CWI — Hardening produção (CWI 2.1)** + **Onda 3b CWI — Auditoria API, injection, erros genéricos (CWI 2.2, 2.3-parcial, 3.1, 3.2, 4.2)** concluídos; **82/82 achados resolvidos**; gate **52/52**; global **94,98%**; 0 em backlog) |

---

## Como usar este checklist

Este documento deve ser consultado em **duas situações**:

1. **Antes de abrir um Pull Request:** Percorra as seções relevantes às áreas que você modificou. Marque cada item aplicável à sua mudança.
2. **Antes de cada deploy em produção:** Percorra o checklist completo. Itens não aplicáveis à release podem ser marcados como N/A com justificativa.

> **Atenção:** Não pule seções "por pressa". Uma única vulnerabilidade não verificada pode comprometer dados de todos os usuários. O checklist é rápido o suficiente para ser executado em 20–30 minutos.

> **Dica:** Se você adicionou código em área não coberta por este checklist, abra uma issue para expandir o documento antes de mergear.

---

## Índice

1. [Seção 1 — Autenticação e autorização](#seção-1--autenticação-e-autorização)
2. [Seção 2 — Uploads e arquivos](#seção-2--uploads-e-arquivos)
3. [Seção 3 — CSRF e sessão](#seção-3--csrf-e-sessão)
4. [Seção 4 — Rate limiting e brute-force](#seção-4--rate-limiting-e-brute-force)
5. [Seção 5 — Dados e Firestore](#seção-5--dados-e-firestore)
6. [Seção 6 — Secrets e variáveis de ambiente](#seção-6--secrets-e-variáveis-de-ambiente)
7. [Seção 7 — Headers HTTP e cookies](#seção-7--headers-http-e-cookies)
8. [Seção 8 — Logs e observabilidade](#seção-8--logs-e-observabilidade)
9. [Seção 9 — LGPD e PII](#seção-9--lgpd-e-pii)
10. [Seção 10 — Deploy e infra](#seção-10--deploy-e-infra)
11. [Seção 11 — Frontend e JavaScript](#seção-11--frontend-e-javascript)
12. [Seção 12 — Race conditions e concorrência](#seção-12--race-conditions-e-concorrência)
13. [Seção 13 — Scripts operacionais](#seção-13--scripts-operacionais)
14. [Seção 14 — Qualidade de testes](#seção-14--qualidade-de-testes)
15. [Seção 15 — CSS e design system](#seção-15--css-e-design-system)
16. [Achados ativos (F-01 a F-82)](#achados-ativos-f-01-a-f-82)
17. [Resultado da última auditoria](#resultado-da-última-auditoria-2026-06-16)
18. [Procedimento de resposta a incidente](#procedimento-de-resposta-a-incidente-de-segurança)
19. [Referências OWASP](#referências-owasp)

---

## Seção 1 — Autenticação e autorização

### 1.1 Decoradores de acesso

- [ ] **Toda rota nova tem um decorador de acesso adequado**
  - Arquivo de referência: `app/decoradores.py`
  - Como verificar: Procure rotas sem `@requer_*`: `grep -n "def " app/routes/*.py | grep -v "@requer"`
  - Decoradores disponíveis:
    - `@requer_solicitante` — permite solicitante, supervisor, admin, admin_global
    - `@requer_supervisor_area` — permite supervisor, admin, admin_global
    - `@requer_perfil('admin')` — permite admin e admin_global (expansão automática)
    - `@requer_admin_global` — exclusivo para o perfil `admin_global` (sem expansão para admin)
  - **Nota:** `admin_global` é automaticamente incluído quando `'admin'` está na lista de perfis de `@requer_perfil`. Rotas exclusivas do `admin_global` devem usar `@requer_admin_global` definido em `app/routes/admin_global.py`.

- [ ] **Nenhuma rota expõe dados de outro usuário sem verificação de permissão**
  - Arquivo de referência: `app/services/permissions.py`
  - Como verificar: Toda consulta por `chamado_id` deve passar por `usuario_pode_ver_chamado(usuario, chamado)`

- [ ] **Rotas de API (`/api/*`) também têm proteção de perfil**
  - Arquivo de referência: `app/routes/api.py`
  - Como verificar: `grep -n "route" app/routes/api.py` — verificar decorador em cada rota

### 1.2 Verificação de IDOR (Insecure Direct Object Reference)

- [ ] **Acesso a documentos específicos verifica se pertencem ao usuário/área**
  - Exemplo: `GET /chamado/<id>` deve verificar se o usuário tem permissão, não apenas se o ID existe
  - Arquivo de referência: `app/routes/dashboard.py`, `app/services/permissions.py`
  - Como verificar: Teste manual com ID de chamado de outro usuário — deve retornar 403, não os dados

- [ ] **Download de anexo verifica propriedade do chamado antes de gerar URL pré-assinada**
  - Arquivo de referência: `app/routes/api.py` — endpoint `/api/download-anexo`
  - Como verificar: Tentar baixar anexo de chamado de outro usuário com token de outro — deve retornar 403

### 1.3 Sessão e autenticação

- [ ] **`must_change_password` é verificado e redireciona corretamente**
  - Arquivo de referência: `app/routes/auth.py`
  - Como verificar: Criar usuário com `must_change_password=True` e tentar acessar qualquer rota protegida
  - **Nota:** `admin` e `admin_global` são isentos da troca obrigatória de senha via `is_admin_or_above` (`app/routes/auth.py:157`)

- [ ] **Logout automático por inatividade está ativo (15 minutos)**
  - Arquivo de referência: `app/routes/auth.py`, JS de inatividade
  - Como verificar: Configuração `PERMANENT_SESSION_LIFETIME` em `config.py`

- [x] **Usuários desativados não conseguem fazer login**
  - Arquivo de referência: `app/models_usuario.py` — campo `ativo`; `app/routes/auth.py:79–83` (bloqueio pré-sessão, sem incrementar lockout); `app/__init__.py:87–90` (`user_loader` invalida sessão ativa ao detectar `ativo=False`)
  - Testes: CT-AUTH-I1 a CT-AUTH-I4 (`tests/test_routes/test_auth.py`); 7 testes de modelo (`tests/test_services/test_models_usuario.py`); 5 testes admin desativar/ativar (`tests/test_routes/test_usuarios.py`)
  - Migração: `scripts/migrar_usuarios_ativo.py` — dry-run (2026-06-22) identificou 7 docs legados sem campo `ativo`; `--apply` backfilla com `ativo=true`
  - **Resolvido 2026-06-22 — Onda 2 (desativação de usuários)**

### 1.4 Algoritmo de hash de senhas — CWI 2.2

- [x] **Senhas armazenadas com algoritmo seguro (Werkzeug scrypt/pbkdf2) — não SHA1/MD5/Base64**
  - Arquivo de referência: `app/models_usuario.py:73–78` — `set_password()` usa `werkzeug.security.generate_password_hash`; `check_password()` usa `check_password_hash`
  - Formato gerado: `scrypt:<params>:<salt>:<hash>` ou `pbkdf2:sha256:<iterations>:<salt>:<hash>` (depende da versão Werkzeug)
  - **NÃO usar**: SHA1, MD5, Base64, bcrypt simples sem salt, reversível ou plaintext
  - Procedimento QA CWI 2.2: inspecionar Firestore `usuarios.senha_hash` — deve ter prefixo `scrypt:` ou `pbkdf2:`, não plaintext
  - Teste automatizado: `tests/test_services/test_models_usuario.py::test_senha_hash_usa_formato_werkzeug_nao_plaintext`
  - **Resolvido 2026-06-23 — Onda 3b (CWI 2.2)**

---

## Seção 2 — Uploads e arquivos

> **Atenção:** Upload de arquivo é uma das superfícies de ataque mais exploradas. Nunca relaxe nesta seção.

### 2.1 Validação de arquivo

- [ ] **Extensão do arquivo está na allowlist**
  - Arquivo de referência: `app/services/validators.py` — `EXTENSOES_PERMITIDAS`
  - Como verificar: Tentar upload de `.exe`, `.php`, `.sh` — deve ser rejeitado com erro 400

- [ ] **Magic bytes são verificados independentemente da extensão**
  - Arquivo de referência: `app/services/validators.py` e `app/services/upload.py`
  - Como verificar: Renomear um arquivo executável para `.pdf` e tentar fazer upload — deve ser rejeitado

- [ ] **Nome do arquivo é sanitizado antes de qualquer uso**
  - Como verificar: Tentar upload com nome `../../../etc/passwd.pdf` — deve ser sanitizado/rejeitado

- [ ] **Tamanho máximo do arquivo é respeitado**
  - Arquivo de referência: `config.py` — `MAX_CONTENT_LENGTH`
  - Como verificar: Verificar configuração; tentar upload acima do limite

### 2.2 Armazenamento e acesso

- [ ] **Arquivos no R2 estão em bucket privado (não público)**
  - Como verificar: Configuração do bucket no painel Cloudflare R2 — "Public Bucket" deve estar desativado

- [ ] **URLs de download são pré-assinadas com validade máxima de 1 hora**
  - Arquivo de referência: `app/routes/api.py` — parâmetro `ExpiresIn`
  - Como verificar: `grep -n "ExpiresIn\|generate_presigned_url" app/`

- [ ] **Cadeia de fallback (R2 → Firebase → disco) loga cada etapa adequadamente**
  - Arquivo de referência: `app/services/upload.py`
  - Como verificar: Simular falha no R2 e verificar se os logs registram o fallback

### 2.3 Cobertura de testes de upload

- [x] **Cobertura de `app/services/upload.py` >= 80%**
  - Como verificar: `pytest --cov=app/services/upload.py --cov-report=term-missing`
  - Status atual: **100%** — **Resolvido 2026-06-18** (S3-01 / F-06)

### 2.4 Cobertura de testes de notificações

- [x] **Cobertura de `app/services/notifications.py` >= 80%**
  - Como verificar: `pytest --cov=app/services/notifications.py --cov-report=term-missing`
  - Status atual: **98%** — **Resolvido 2026-06-18** (S3-02 / F-07)

---

## Seção 3 — CSRF e sessão

### 3.1 Proteção CSRF

- [ ] **Todo formulário POST/PUT/DELETE inclui token CSRF**
  - Arquivo de referência: `app/templates/base.html` (macro de formulário), Flask-WTF
  - Como verificar: `grep -n "csrf_token\|hidden_tag" app/templates/*.html`

- [ ] **Endpoints de API JSON verificam CSRF (ou usam autenticação stateless adequada)**
  - Arquivo de referência: `app/routes/api.py`
  - Como verificar: Tentar chamar endpoint POST `/api/status` sem token CSRF — deve retornar 400

- [ ] **Testes com CSRF desabilitado usam `app.config['WTF_CSRF_ENABLED'] = False`** (nunca em produção)
  - Arquivo de referência: `tests/conftest.py`
  - Como verificar: Verificar que nenhum código de produção desabilita CSRF

### 3.2 Configuração de sessão

- [x] **`SESSION_COOKIE_SECURE = True` em produção**
  - Arquivo de referência: `config.py` — `SESSION_COOKIE_SECURE = _to_bool(..., default=(_env == "production"))` → `True` quando `FLASK_ENV=production`
  - Teste: `tests/test_config_production.py::test_cwi21_cookies_secure_em_producao`, `test_import_config_producao_com_vars_validas_sobe`
  - Como verificar: `grep -n "SESSION_COOKIE_SECURE" config.py`
  - **Resolvido 2026-06-22 — Onda 3 (CWI 2.1)**

- [x] **`SESSION_COOKIE_HTTPONLY = True`** (impede acesso via JS)
  - Arquivo de referência: `config.py` — `SESSION_COOKIE_HTTPONLY = True` (hardcoded, não depende de env)
  - Como verificar: Inspecionar cookies no navegador — flag HttpOnly deve estar presente; `grep -n "HTTPONLY" config.py`
  - **Resolvido 2026-06-22 — Onda 3 (CWI 2.1)**

- [x] **`SESSION_COOKIE_SAMESITE = 'Lax'`**
  - Arquivo de referência: `config.py` — `SESSION_COOKIE_SAMESITE = "Lax"` (hardcoded)
  - **Resolvido 2026-06-22 — Onda 3 (CWI 2.1)**

---

## Seção 4 — Rate limiting e brute-force

### 4.1 Configuração de rate limiting

- [ ] **`/login` tem rate limit agressivo (ex: 5 tentativas por minuto por IP)**
  - Arquivo de referência: `app/routes/auth.py`, `app/__init__.py` (Flask-Limiter)
  - Como verificar: `grep -n "limiter\|@limiter" app/routes/auth.py`

- [ ] **Endpoints de API têm rate limit proporcional ao uso esperado**
  - Arquivo de referência: `app/routes/api.py`
  - Como verificar: `grep -n "@limiter\|rate_limit" app/routes/api.py`

- [ ] **Redis está configurado como backend de rate limit em produção**
  - Arquivo de referência: `app/__init__.py`, variável `REDIS_URL`
  - Como verificar: Sem Redis, o rate limit é por processo e não funciona com múltiplos workers

### 4.2 Lockout por brute-force

- [ ] **Lockout de IP está ativo após tentativas excessivas**
  - Arquivo de referência: `app/services/login_attempts.py`
  - Como verificar: 10+ tentativas falhas com mesmo IP devem resultar em 429

- [ ] **Lockout por e-mail está ativo (independente do IP)**
  - Arquivo de referência: `app/services/login_attempts.py`
  - Como verificar: 10+ tentativas com mesmo e-mail de IPs diferentes deve resultar em bloqueio

- [x] **`get_client_ip()` usa ProxyFix para obter IP real (não forjado via header)**
  - Arquivo de referência: `app/utils.py:87–95`, `app/__init__.py`
  - Como verificar: `grep -n "ProxyFix\|X-Forwarded-For" app/__init__.py app/utils.py`
  - Status atual: **Fechado 2026-06-17** — ProxyFix adicionado em `create_app()`; `get_client_ip()` lê apenas `remote_addr` (F-01 → S1-01)

---

## Seção 5 — Dados e Firestore

### 5.1 Queries seguras

- [ ] **Nenhuma query usa `db.collection().get()` sem paginação em coleção grande**
  - Como verificar: `grep -rn "\.get()" app/routes/ app/services/` — verificar se há `.limit()` antes
  - Arquivo de referência: `app/services/chamados_listagem_service.py` (exemplo correto)

- [ ] **Relatórios têm limite de 2000 documentos por operação**
  - Arquivo de referência: `app/services/analytics.py`
  - Como verificar: `grep -n "limit\|2000" app/services/analytics.py`

- [ ] **Dados sensíveis de usuário não são retornados em endpoints públicos ou de lista**
  - Como verificar: Verificar que endpoints de API não expõem `password_hash`, `encryption_key`, etc.

### 5.2 Validação de entrada

- [ ] **Dados de formulário são validados antes de serem gravados no Firestore**
  - Arquivo de referência: `app/services/validators.py`
  - Como verificar: Todo `POST` de criação/edição passa por `validar_*` antes de gravar

- [ ] **IDs de documento não são gerados a partir de input do usuário sem sanitização**
  - Como verificar: `grep -n "document_id\|doc_id" app/services/` — verificar origem do valor

- [ ] **Campos de texto livre não permitem HTML (XSS)**
  - Como verificar: Jinja2 escapa por padrão. Verificar uso de `| safe` em templates: `grep -rn "| safe" app/templates/`

### 5.3 Concorrência em escritas (novo — 2ª auditoria)

- [x] **Operações de read-then-write em campos contadores usam transação Firestore ou `Increment()`**
  - Arquivo de referência: `app/services/contadores_uso.py` (F-13), `gamification_service.py` (F-14)
  - Como verificar: `grep -rn "@firestore.transactional\|Increment" app/services/`
  - Status atual: **Fechado 2026-06-17** — `contadores_uso.py` usa `@firestore.transactional`; `gamification_service.py` usa `Increment(pontos)`

- [x] **Limites de uso (rate) são implementados com garantia de atomicidade**
  - Arquivo de referência: `app/services/contadores_uso.py`
  - Status atual: **Fechado 2026-06-17** — transação atômica implementada (S2-01)

### 5.4 Regressão injection — CWI 3.1

- [x] **Payloads SQL-like e NoSQL-like no parâmetro `search` não causam 500 nem vazam dados extras**
  - Mecanismo: Firestore SDK tipado + `filters.py` aplica `search` como filtro em memória (substring match) — não interpreta como query SQL/NoSQL
  - Payloads testados: `' OR 1=1--`, `%27%20OR%201%3D1%20--`, `{"$gt": ""}`, `'; return true;//`, `1; DROP TABLE chamados--`, `{$where: 'sleep(1000)'}`
  - Assert: status ∈ {200, 400, 403}; corpo sem "Firestore", "Traceback", "Exception", "senha_hash"
  - Assert: lista retornada não explode (mock controlado, 0 chamados)
  - Como verificar QA: `curl -s "https://host/api/chamados/paginar?search=%27+OR+1%3D1--"` — deve retornar JSON com chamados da área do supervisor, não todos os chamados do sistema
  - Testes automatizados: `tests/test_security/test_injection_regression.py` (13 testes CWI 3.1)
  - **Resolvido 2026-06-23 — Onda 3b (CWI 3.1)**

---

## Seção 6 — Secrets e variáveis de ambiente

> **Atenção:** Uma credencial exposta no git é um incidente de segurança. Nunca commite `.env` ou arquivos JSON de credenciais.

### 6.1 Gestão de secrets

- [ ] **Nenhuma credencial ou chave hardcoded no código-fonte**
  - Como verificar: `grep -rn "password\|secret\|key\|token" app/ config.py --include="*.py" | grep -v "os.environ\|config\.\|#"` — investigar hits

- [ ] **`.env` e arquivos de credenciais Firebase estão no `.gitignore`**
  - Como verificar: `cat .gitignore | grep -E "\.env|serviceAccount|credentials"`

- [ ] **`SECRET_KEY` tem pelo menos 32 caracteres aleatórios em produção**
  - Como verificar: Verificar nas variáveis de ambiente — não deve ser um valor padrão como `'dev'` ou `'secret'`

- [ ] **`ENCRYPTION_KEY` está definido se `ENCRYPT_PII_AT_REST=true`**
  - Arquivo de referência: `config.py`, `app/models_usuario.py`
  - Como verificar: Variáveis consistentes entre si nas variáveis de ambiente

### 6.2 Rotação de secrets

- [ ] **Procedimento de rotação da `ENCRYPTION_KEY` está documentado**
  - Status: Pendente de documentação

- [ ] **Chaves VAPID (Web Push) estão em variáveis de ambiente, não no código**
  - Arquivo de referência: `scripts/gerar_vapid_keys.py`
  - Como verificar: `grep -n "VAPID" config.py` — deve referenciar `os.environ.get()`

---

## Seção 7 — Headers HTTP e cookies

### 7.1 Headers de segurança

- [ ] **`Content-Security-Policy` está configurado**
  - Arquivo de referência: `app/__init__.py` (after_request)
  - Como verificar: `curl -I https://seu-dominio.com/ | grep -i "content-security"`

- [ ] **`X-Frame-Options: DENY` ou `SAMEORIGIN` está configurado** (proteção clickjacking)
  - Como verificar: `curl -I https://seu-dominio.com/ | grep -i "x-frame"`

- [ ] **`X-Content-Type-Options: nosniff` está configurado** (impede MIME sniffing)
  - Como verificar: `curl -I https://seu-dominio.com/ | grep -i "x-content-type"`

- [ ] **`Referrer-Policy` está configurado**
  - Valor recomendado: `strict-origin-when-cross-origin`

- [ ] **Cabeçalho `Server` não expõe versão do servidor**
  - Como verificar: `curl -I https://seu-dominio.com/ | grep -i "server"` — não deve mostrar versão do Gunicorn/Python

### 7.2 HTTPS — CWI 2.1

- [x] **Toda comunicação usa HTTPS — redirect 301 automático em produção**
  - Arquivo de referência: `app/__init__.py:_forcar_https()` — verifica `request.is_secure` e `X-Forwarded-Proto`
  - Testes: `tests/test_app_init.py::test_forcar_https_redireciona_em_producao`, `tests/test_config_production.py::test_cwi21_https_redirect_em_producao`
  - Como verificar QA: `curl -I http://<host>/login` → `HTTP/1.1 301` + `Location: https://...`
  - **Resolvido 2026-06-22 — Onda 3 (CWI 2.1)**

- [x] **Cookies de sessão têm flag `Secure`** (só transmitidos via HTTPS)
  - Arquivo de referência: `config.py` — `SESSION_COOKIE_SECURE = True` em produção (padrão); `REMEMBER_COOKIE_SECURE` idem
  - Testes: `tests/test_config_production.py::test_cwi21_cookies_secure_default_em_config_producao`, `test_import_config_producao_com_vars_validas_sobe`
  - Como verificar QA: DevTools → Application → Cookies → flag Secure presente
  - **Resolvido 2026-06-22 — Onda 3 (CWI 2.1)**

- [x] **`APP_BASE_URL` e `HEALTH_SECRET` são obrigatórias em produção (fail-fast no boot)**
  - Arquivo de referência: `config.py:_validar_config_producao()` — `ValueError` se ausentes
  - Testes: `tests/test_config_production.py` (17 testes — prod sem APP_BASE_URL, sem HEALTH_SECRET, http://, reload isolado etc.)
  - ADR: `docs/adr/003-fail-fast-config-producao.md`
  - **Resolvido 2026-06-22 — Onda 3 (CWI 2.1 / hardening prod)**

- [x] **HEALTH_SECRET autenticado via header `X-Health-Token` (token fora da URL)**
  - Finding anterior: `MEDIUM` — token `?token=<HEALTH_SECRET>` aparecia em access logs do Gunicorn/nginx
  - Solução: `app/routes/api.py:_obter_health_token_request()` — lê header `X-Health-Token` (primário), cai para `?token=` apenas como fallback deprecado (compat UptimeRobot legado)
  - Comparação: `hmac.compare_digest(provided, secret)` — timing-safe (previne timing attacks)
  - Testes: CT-HEALTH-10 a 13 (`tests/test_routes/test_health_sw.py`)
  - Monitoramento: `curl -H "X-Health-Token: $HEALTH_SECRET" "https://host/health?deep=1"`
  - **Resolvido 2026-06-22 — Ressalvas Onda 3 (R1)**

### 7.3 Swagger e documentação de API — CWI 4.2

- [x] **Rotas de documentação automática (Swagger/OpenAPI) não estão expostas ao público**
  - Rotas testadas: `/swagger`, `/docs`, `/openapi.json`, `/swagger.json`, `/api-docs` → todas retornam 404
  - Como verificar QA: `curl -o /dev/null -s -w "%{http_code}" https://host/swagger` → 404
  - O projeto não usa Flask-RESTX, Flasgger ou similar — ausência é a proteção
  - Teste automatizado: `tests/test_security/test_injection_regression.py::test_swagger_routes_retornam_404`
  - **Resolvido 2026-06-23 — Onda 3b (CWI 4.2)**

---

## Seção 8 — Logs e observabilidade

### 8.1 O que deve ser logado

- [ ] **Tentativas de login (sucesso e falha) são logadas com IP e timestamp**
  - Arquivo de referência: `app/routes/auth.py`, `app/services/login_attempts.py`
  - Como verificar: Fazer login com senha errada e verificar logs da aplicação

- [ ] **Acessos a dados sensíveis são logados (download de anexos, visualização de chamados)**
  - Arquivo de referência: `app/routes/api.py` — endpoint `/api/download-anexo`

- [ ] **Erros internos são logados com traceback mas a resposta ao cliente é genérica**
  - Como verificar: `grep -rn "except.*Exception" app/routes/ app/services/` — verificar se o erro é logado e se a resposta ao cliente não expõe detalhes

- [ ] **Service Worker (`sw.js`) loga erros de push (não usa catch silencioso)**
  - Arquivo de referência: `app/static/sw.js:10` *(arquivo está em `app/static/`, não em `app/static/js/`)*
  - Status atual: **ABERTO** — catch silencioso `catch (e) {}` (F-43)
  - Como verificar: `grep -n "catch" app/static/sw.js` — verificar se há log no catch

### 8.2 O que NÃO deve ser logado

- [ ] **Senhas nunca aparecem nos logs (mesmo mascaradas)**
  - Como verificar: `grep -rn "password\|senha" app/ --include="*.py" | grep "log\|print"` — nenhum resultado deve mostrar valor real

- [ ] **Tokens de sessão e chaves de API não aparecem nos logs**
  - Como verificar: Inspeção manual dos logs da aplicação — buscar por `token`, `key`, `secret`

- [ ] **`print()` de debug foi removido do código de produção**
  - Como verificar: `grep -rn "^    print\|^print" app/` — nenhum resultado em código de produção
  - Status atual: **ABERTO** — `app/models_historico.py:86` tem `print()` ativo (F-05)

### 8.3 Auditoria de ações admin

- [ ] **Criação/edição/desativação de usuários são registradas no histórico**
  - Arquivo de referência: `app/routes/usuarios.py`

- [ ] **Mudanças de status de chamados têm registro de quem fez e quando**
  - Arquivo de referência: `app/models_historico.py`, `app/services/status_service.py`

### 8.4 Respostas de erro genéricas — CWI 3.2

- [x] **Handlers 500 em `api.py` usam `ERRO_INTERNO_MSG` — não expõem `str(exception)`, Firestore, traceback ou nome de tecnologia**
  - Arquivo de referência: `app/routes/api.py:38` — `ERRO_INTERNO_MSG = "Erro interno. Tente novamente."`
  - Handlers corrigidos (Onda 3b): `api_notificacoes_marcar_lida:L393`, `api_notificacoes_ler_todas:L405`, `api_push_subscribe:L438`
  - Fix específico: `bulk_atualizar_status:L331` — `str(e)` substituído por `"Erro ao processar chamado"` (evita vazar nome de exceção Firestore)
  - Padrão: erros 400/403 de negócio podem ter mensagens específicas ("Chamado não encontrado" — ok); erros 500 SEMPRE genéricos
  - Fora de escopo: rotas HTML com `flash_t(..., error=str(e))` em `usuarios.py`, `categorias.py`, `dashboard.py` — backlog Onda futura
  - Como verificar: `grep -n 'str(e)' app/routes/api.py` → sem ocorrências em handlers de erro
  - Testes automatizados: `tests/test_routes/test_api_security_responses.py` (6 testes CWI 3.2)
  - **Resolvido 2026-06-23 — Onda 3b (CWI 3.2)**

---

## Seção 9 — LGPD e PII

> **Dica:** LGPD exige que dados pessoais sejam tratados com propósito claro, minimização e proteção adequada. Ver `docs/POLITICA_SEGURANCA_LGPD.md` para a política completa.

### 9.1 Minimização de dados

- [ ] **Apenas dados necessários para a funcionalidade são coletados**
  - Como verificar: Revisar campos do formulário de criação de chamado e do cadastro de usuário

- [ ] **Dados pessoais não são armazenados em logs ou cache desnecessariamente**
  - Como verificar: Verificar que logs não contêm CPF, telefone ou dados sensíveis além do necessário

### 9.2 Proteção de dados em repouso

- [ ] **`ENCRYPT_PII_AT_REST` está configurado corretamente em produção**
  - Arquivo de referência: `config.py`, `app/models_usuario.py`
  - Como verificar: Variável de ambiente `ENCRYPT_PII_AT_REST`; verificar se campos são criptografados antes de gravar

- [ ] **Dados de usuário deletado/desativado são tratados conforme política**
  - Arquivo de referência: `docs/POLITICA_SEGURANCA_LGPD.md`
  - Como verificar: Fluxo de desativação de usuário em `app/routes/usuarios.py`

### 9.3 Direito de acesso e portabilidade

- [ ] **Usuário pode visualizar seus próprios dados**
  - Como verificar: Existe funcionalidade de "Meus dados" ou equivalente

- [ ] **Existe procedimento documentado para atender solicitação de exclusão (direito ao esquecimento)**
  - Arquivo de referência: `docs/POLITICA_SEGURANCA_LGPD.md`

### 9.4 Auditoria de respostas HTTP — CWI 2.3 (parcial)

- [x] **Endpoints JSON não expõem `senha_hash`, `encryption_key`, stack trace ou nome de exceção interna**
  - Arquivo de referência: `app/models_usuario.py:101` — `to_public_dict()` é a serialização segura para HTTP
  - `GET /api/chamado/<id>`: retorna whitelist explícita de campos (id, numero, categoria, tipo, gate, responsavel, descricao, data_abertura, status, sla_info) — sem campos internos
  - `GET /api/supervisores/lista`: usa campos seguros (id, nome, email) — sem senha_hash
  - `Usuario.to_dict()` inclui senha_hash — **uso exclusivo para Firestore**, nunca em respostas HTTP
  - `Usuario.to_public_dict()` é a versão segura para HTTP — sem senha_hash
  - Mascaramento UI: `app/utils.py:mask_email_for_log` + filtro Jinja `mask_email` em `app/__init__.py` (navbar)
  - Testes: `tests/test_routes/test_api_security_responses.py::test_to_public_dict_nao_contem_senha_hash`, `::test_api_chamado_por_id_resposta_sem_campos_internos`
  - **Resolvido 2026-06-23 — Onda 3b (CWI 2.3 parcial; Fernet PII fecha na Onda 4)**

---

## Seção 10 — Deploy e infra

### 10.1 Antes do deploy

- [ ] **`pytest --tb=short -q` passa com 100% dos testes**
  - Como verificar: Rodar localmente antes do push

- [ ] **Cobertura geral >= 85%**
  - Como verificar: `pytest --cov=app --cov-report=term-missing -q`
  - Gate por módulo: `python scripts/check_coverage_per_module.py` (cada `app/**/*.py` >= 85%)

- [ ] **`ruff check app/ tests/` — zero erros**
  - Como verificar: Rodar e confirmar `All checks passed`

- [ ] **`bandit -r app/ -ll` — zero High, sem Medium novos**
  - Como verificar: Comparar com resultado da última auditoria (1 Medium B310 é o baseline atual)

- [ ] **Nenhuma variável de ambiente crítica foi removida da configuração de produção**
  - Como verificar: Lista de variáveis em `docs/ENV.md` — verificar cada uma nas variáveis de ambiente do servidor

- [ ] **Billing do Firebase/GCP está ativo (necessário para Firestore)**
  - Como verificar: [console.cloud.google.com](https://console.cloud.google.com) — verificar status do projeto
  - Status atual: **VERIFICAR** — alerta de billing com prazo vencido identificado em `INCIDENT_RUNBOOK.md:138` (F-40)

### 10.2 Scripts de manutenção

- [ ] **Scripts perigosos (`apagar_todos_chamados.py`) não são executados em produção sem revisão explícita**
  - Arquivo de referência: `scripts/apagar_todos_chamados.py`
  - Como verificar: O script exige flag `--confirm` — nunca automatize essa flag

- [ ] **Scripts de migração já executados não serão re-executados**
  - Arquivo de referência: `scripts/migrar_*.py`
  - Como verificar: Documentar data de execução em cada script (comentário ou log)

### 10.3 Verificação pós-deploy

- [ ] **Healthcheck responde com 200 após deploy**
  - Como verificar: `curl https://seu-dominio.com/health`

- [ ] **Login funciona com usuário de teste (não admin real)**
  - Como verificar: Login manual pós-deploy com conta de teste

- [ ] **Criação de chamado funciona end-to-end (incluindo upload)**
  - Como verificar: Criar chamado de teste com anexo e verificar se aparece em Meus Chamados

- [ ] **Logs não mostram erros 500 nas primeiras requisições**
  - Como verificar: `docker logs -f <container>` nos primeiros minutos após deploy

---

## Seção 11 — Frontend e JavaScript

> Esta seção foi adicionada na 2ª rodada de auditoria (2026-06-16) após identificação de achados F-33 a F-48.

### 11.1 Interação com o usuário

- [x] **Nenhum `window.prompt()` usado para captura de dados críticos**
  - Arquivo de referência: `dashboard_otimizacoes.js` — modal `#modal-cancelamento` em `dashboard.html`
  - Como verificar: `grep -rn "window.prompt\|window.confirm\|window.alert" app/static/js/`
  - Status atual: **RESOLVIDO 2026-06-17** — `<dialog>` nativo acessível substitui `window.prompt` (F-33 / S2-05)
  - Alternativa obrigatória: `<dialog>` nativo ou modal HTML acessível

- [ ] **Nenhum handler de evento `onmouseover/onmouseout` inline em elementos gerados por JS**
  - Arquivo de referência: `onboarding.js:608-617`
  - Como verificar: `grep -rn "onmouseover\|onmouseout" app/static/js/ app/templates/`
  - Status atual: ✅ **Resolvido** (F-48 — Onda C wave 1 2026-06-18) — handlers removidos; hover via `mouseenter`/`mouseleave` em `bindCardEvents()`

### 11.2 URLs de API não hardcoded

- [ ] **URLs de API no JavaScript vêm de `window.DTX_URLS` (injetado pelo template), não hardcoded**
  - Arquivo de referência: `dashboard_otimizacoes.js:132`
  - Como verificar: `grep -n "'/api/" app/static/js/` — qualquer hit é uma URL hardcoded
  - Status atual: **ABERTO** — `/api/atualizar-status` hardcoded (F-36)
  - Padrão correto: `window.DTX_URLS?.atualizar_status || '/api/atualizar-status'` (com fallback)

### 11.3 Strings de UI internacionalizadas

- [ ] **Strings de UI em JavaScript passam por `window.DTX_MSGS` (injetado pelo template), não hardcoded em PT-BR**
  - Arquivo de referência: `dashboard_otimizacoes.js:13-23` (MSGS), `table-filters.js:244,249`
  - Como verificar: `grep -rn "pt-BR\|'Filtrar'\|'Todos'\|'Cancelando'" app/static/js/`
  - Status atual: **ABERTO** — múltiplas strings hardcoded em PT-BR (F-34, F-37, F-46)

- [ ] **`localeCompare` no JavaScript usa o locale do usuário, não PT-BR fixo**
  - Arquivo de referência: `table-filters.js:114`
  - Status atual: **ABERTO** — `localeCompare('pt-BR')` hardcoded (F-44)

### 11.4 Logs de debug

- [ ] **`console.warn/log/error` em arquivos JS de produção são protegidos por `window.DTX_DEBUG`**
  - Arquivo de referência: `table-filters.js:39, 50`
  - Como verificar: `grep -n "console\." app/static/js/*.js` — verificar se há proteção
  - Status atual: **ABERTO** — console.warn sem proteção em table-filters.js (F-38)
  - Exceção permitida: `console.error` em Service Worker (sw.js) para erros de push — esses devem ser logados sempre

### 11.5 Injeção de CSS

- [x] **CSS injetado dinamicamente por JavaScript verifica duplicatas antes de inserir `<style>`**
  - Arquivo de referência: `dashboard_otimizacoes.js`
  - Como verificar: `grep -n "getElementById.*dtx-dashboard-fade-keyframes" app/static/js/dashboard_otimizacoes.js`
  - Status atual: **Resolvido** 2026-06-19 — guard `getElementById('dtx-dashboard-fade-keyframes')` + `style.id` adicionados (F-41, Onda C wave 2)
  - Padrão aplicado: `if (!document.getElementById('dtx-dashboard-fade-keyframes')) { ... }`

### 11.6 Service Worker

- [ ] **Service Worker (`sw.js`) não suprime erros silenciosamente**
  - Arquivo de referência: `app/static/sw.js:10` *(arquivo está em `app/static/`, não em `app/static/js/`)*
  - Como verificar: `grep -n "catch" app/static/sw.js` — verificar se há log no catch
  - Status atual: **ABERTO** — `catch (e) {}` sem log (F-43)

---

## Seção 12 — Race conditions e concorrência

> Esta seção foi adicionada na 2ª rodada de auditoria (2026-06-16) após identificação de F-13 a F-16 e F-21.

### 12.1 Operações atômicas no Firestore

- [x] **Operações de read-then-write em contadores usam transação Firestore ou `Increment()` atômico**
  - Arquivo de referência: `contadores_uso.py` (F-13)
  - Como verificar: `grep -n "@firestore.transactional" app/services/contadores_uso.py`
  - Status atual: **Fechado 2026-06-17** — `_verificar_incrementar_tx` usa `@firestore.transactional` (S2-01)

- [x] **Campos de pontuação/gamificação são incrementados com `Increment()` atômico**
  - Arquivo de referência: `gamification_service.py` (F-14)
  - Como verificar: `grep -n "Increment" app/services/gamification_service.py`
  - Status atual: **Fechado 2026-06-17** — `_adicionar_exp` usa `Increment(pontos)` para `exp_total`/`exp_semanal` (S2-02)

- [ ] **Novos serviços que implementam contadores verificam o padrão de atomicidade antes de commitar**
  - Regra: Qualquer campo numérico que é lido e depois atualizado DEVE usar `Increment()` ou transação

### 12.2 Estado global mutável em multi-thread

- [x] **Dicionários e listas globais mutáveis em serviços são protegidos com `threading.Lock()`**
  - Arquivo de referência: `translation_service.py` — `_translation_map_lock` (RLock) protege `TRANSLATION_MAP` (F-16)
  - Como verificar: `grep -rn "^[A-Z_]* = \{\}\|^[A-Z_]* = \[\]" app/services/` — identificar globals mutáveis
  - Status atual: **RESOLVIDO 2026-06-17** (F-16 / S2-04)
  - Padrão correto:
    ```python
    import threading
    _lock = threading.Lock()
    _mapa_global: dict = {}

    def atualizar(chave, valor):
        with _lock:
            _mapa_global[chave] = valor
    ```

### 12.3 Contador de atribuição em multi-worker

- [x] **Contadores de round-robin de atribuição usam Redis (compartilhado entre workers) em vez de memória local** ✅ F-21 Resolvido 2026-06-18
  - Arquivo de referência: `assignment.py` — Redis INCR com fallback em memória (Onda B)
  - Como verificar: `grep -n "redis_lib.from_url" app/services/assignment.py`

### 12.4 APScheduler em multi-worker

- [x] **Jobs do APScheduler usam Redis distributed lock para evitar execução N vezes em N workers**
  - Arquivo de referência: `app/services/scheduler_lock.py`, `app/__init__.py` (`executar_job_com_lock`)
  - Como verificar: `grep -n "executar_job_com_lock" app/__init__.py`
  - Status atual: **Resolvido 2026-06-18** (S4-01 / F-02)

---

## Seção 13 — Scripts operacionais

> Esta seção foi adicionada na 3ª rodada de auditoria (2026-06-16) após identificação de achados F-71 a F-76.

### 13.1 Proteção contra execução destrutiva acidental

- [ ] **Scripts destrutivos têm modo dry-run por padrão — requerem `--apply` (ou equivalente) para executar de fato**
  - Arquivo de referência: `scripts/atualizar_firebase.py` (F-71), `scripts/atualizar_setores_from_print.py` (F-72)
  - Como verificar: Executar o script sem argumentos — não deve alterar dados, apenas listar o que seria feito

- [ ] **Scripts destrutivos exibem prompt de confirmação interativo antes de executar**
  - Padrão mínimo: `input("Confirmar? [s/N]: ")` antes de qualquer operação destrutiva
  - Como verificar: Executar com `--apply` e confirmar que o script pede confirmação antes de prosseguir

- [ ] **`atualizar_firebase.py` está marcado como obsoleto / removido em favor de `migrar_setores_catalogo.py`**
  - Achado: F-71, F-74 — três scripts com funções sobrepostas para seeding
  - Como verificar: Cabeçalho do arquivo deve conter `DEPRECATED` com referência ao substituto

- [ ] **Nenhum script perigoso sem documentação explícita de risco**
  - Como verificar: Todo script em `scripts/` que altera ou apaga dados deve ter docstring ou comentário de cabeçalho descrevendo o risco

- [ ] **`confirmacao-solicitante.md` não está na raiz do projeto (F-78)**
  - Como verificar: `ls *.md` na raiz — não deve existir arquivo `.md` fora de `docs/`

### 13.2 Dependências de scripts

- [ ] **`python-dotenv` está listado em `requirements.txt` ou `requirements-dev.txt` se usado por scripts**
  - Achado: F-76 — `dotenv` não listado explicitamente
  - Como verificar: `grep -n "dotenv\|python-dotenv" requirements*.txt`

- [ ] **Scripts com sobreposição de função têm README ou comentário explicando qual usar em cada situação**
  - Achado: F-73, F-74 — `scripts/` sem README; três scripts de seeding sobrepostos
  - Como verificar: Existe `scripts/README.md` ou cada script tem docstring que esclarece seu propósito

---

## Seção 14 — Qualidade de testes

> Esta seção foi adicionada na 3ª rodada de auditoria (2026-06-16) após identificação de achados F-50 a F-63.

### 14.1 Correção dos asserts

- [ ] **Sem tautologias em asserts — expressão como `A or not A` (always-true) nunca deve aparecer em test_*.py**
  - Achado: F-50 — `tests/test_i18n.py:29`: `assert result != "back" or result == "back"`
  - Como verificar: `grep -rn "or not\|!= .* or .* ==" tests/` — investigar cada hit
  - Impacto: Tautologia dá falsa garantia de qualidade; o teste nunca falha

- [x] **Sem `assert status_code in (X, Y)` onde apenas um código é o correto para o contrato da rota**
  - Achado: F-55, F-56 — asserts permissivos mascaram 404 como sucesso
  - Como verificar: `grep -rn "in (200\|in (200," tests/` — substituir por assert exato
  - Status atual: **Resolvido 2026-06-18** (S3-06, S3-07)

### 14.2 Fixtures e mocks

- [ ] **URLs nos testes E2E usam fixture `base_url` ou variável de ambiente, nunca string hardcoded**
  - Achado: F-51 (`test_fluxo_supervisor.py:34,60`), F-52 (`test_fluxo_admin.py:53`) — `/relatorios` em vez de `/admin/relatorios`
  - Achado: F-53 (`test_solicitante.py`) — `BASE_URL` hardcoded
  - Como verificar: `grep -rn "BASE_URL\s*=\|http://localhost" tests/e2e/`

- [x] **Mocks inertes removidos; patch no módulo que usa o símbolo**
  - Achado: C-01, C-04, F-54 — `patch("app.routes.api.db")` é inerte quando o serviço importa `db` diretamente
  - Regra: `patch("app.services.X.db")` — quando o serviço importa `db`; `patch("app.routes.api.db")` — válido quando a rota usa `db` diretamente (ex.: `/api/atualizar-status`)
  - Status atual: **Resolvido 2026-06-18** — 3 mocks inertes removidos (S3-05)

- [ ] **Sem arquivos de teste legados coexistindo com seus substitutos ativos**
  - Achado: F-53 — `test_solicitante.py` legado coexiste com `test_fluxo_solicitante.py`
  - Como verificar: `ls tests/` — identificar pares de arquivos com nomes sobrepostos; remover ou marcar com `@pytest.mark.skip`

- [ ] **`_usuario_mock()` (ou equivalente) seta todos os campos do modelo, não apenas o mínimo**
  - Achado: F-62 — mock incompleto pode mascarar KeyError em atributos opcionais
  - Como verificar: Comparar campos de `_usuario_mock()` com `models_usuario.py` — nenhum campo obrigatório deve estar ausente

### 14.3 Cobertura de cenários críticos

- [x] **Existe teste para supervisor acessando `/admin/relatorios`**
  - Achado: F-57 — zero testes para esse fluxo de supervisor
  - Como verificar: `grep -rn "admin/relatorios" tests/`
  - Status atual: **Resolvido 2026-06-18** — `test_supervisor_pode_ver_relatorios` e `test_solicitante_nao_pode_ver_relatorios` (S3-08)

- [x] **Existe teste de race condition para `gerar_numero_chamado`**
  - Achado: F-58 — função sem teste de concorrência
  - Como verificar: `grep -rn "gerar_numero_chamado" tests/`
  - Status atual: **Resolvido 2026-06-18** — `test_gerar_numero_chamado_concorrencia_gera_numeros_unicos` em `test_utils.py` (Onda A)

- [x] **Existe teste para CSV injection via `/exportar`**
  - Achado: F-59 — endpoint de exportação sem teste de injeção
  - Como verificar: `grep -rn "exportar\|csv.injection" tests/`
  - Status atual: **Resolvido 2026-06-18** — `test_exportar_neutraliza_formula_injection_em_xlsx` em `test_dashboard.py`; `_safe_cell()` em `dashboard.py:336` (Onda A)

---

## Seção 15 — CSS e design system

> Esta seção foi adicionada na 3ª rodada de auditoria (2026-06-16) após identificação de achados F-64 a F-70.

> **Nota positiva:** `firestore.rules` está corretamente configurado com `allow read, write: if false` — acesso direto ao banco bloqueado por padrão (deny-all). Manter esse estado.

### 15.1 Tokens de design

- [ ] **CSS usa `var(--color-dtx-*)` em vez de valores hexadecimais hardcoded**
  - Achado: F-64 — `table-filters.css` contém `#1e4a8c`, `#E5E7EB` e outros valores hardcoded
  - Como verificar: `grep -n "#[0-9a-fA-F]\{3,6\}" app/static/css/table-filters.css`
  - Referência: `docs/plans/2026-06-12-dtx-light-design-system.md` — fonte de verdade dos tokens

- [ ] **Tokens locais `--dash-*` e `--reports-*` referenciam os tokens globais `--color-dtx-*` em vez de duplicá-los**
  - Achado: F-65 — tokens locais duplicam valores em vez de referenciar a variável global
  - Padrão correto: `--dash-primary: var(--color-dtx-blue-700);` em vez de `--dash-primary: #1e4a8c;`

- [ ] **`tailwind.config.js` e `input.css` permanecem 100% consistentes com o design system documentado**
  - Status atual: **OK** — consistência confirmada na 3ª rodada; monitorar a cada PR que altere tokens

### 15.2 Sintaxe CSS

- [ ] **Sem sintaxe CSS legada `rgba(r, g, b, a)` com vírgula — usar `rgb()` ou `color-mix()` modernos**
  - Achado: F-66 — `relatorios.css` usa `rgba()` com vírgula (sintaxe de nível 3, depreciada)
  - Como verificar: `grep -n "rgba(" app/static/css/relatorios.css`

- [ ] **Focus ring usa padrão único definido em `input.css`, não três variantes divergentes**
  - Achado: F-67 — três padrões distintos de focus ring nos arquivos CSS
  - Como verificar: `grep -rn "focus.*ring\|:focus" app/static/css/` — todos devem referenciar a mesma variável

- [x] **Cor de borda consistente com os tokens do design system (sem divergências entre arquivos)**
  - Achado: F-68 — cor de borda diverge entre arquivos CSS
  - Status atual: **Resolvido** 2026-06-19 — `rgb(234 234 234)` hardcoded substituído por `var(--color-surface-border)` em `dashboard.css` e `relatorios.css`; invariante `test_no_e5e7eb_in_layout_css` e paridade `input.css ↔ tailwind.config.js` adicionadas (Onda C wave 2)

### 15.3 Artefatos de build

- [ ] **`app/static/dist/` está no `.gitignore` (bundle SPA gerado automaticamente)**
  - Achado: F-70 — bundle não referenciado pelos templates Flask e não documentado; possivelmente não deveria estar no repositório
  - Como verificar: `cat .gitignore | grep "dist/"` — deve existir entrada

- [x] **Artefatos de build CSS (`tailwind.min.css`) são gerados pelo Dockerfile, não commitados manualmente**
  - Achado: F-11 — `tailwind.min.css` commitado E re-gerado no Dockerfile (duplicação)
  - Como verificar: `.gitignore` deve incluir `app/static/css/tailwind.min.css`
  - Status atual: **Resolvido 2026-06-18** (S4-10 / F-11)

---

## Achados ativos (F-01 a F-82)

> **Atenção:** Itens com status "Aberto" representam riscos conhecidos em produção. Cada achado tem uma tarefa correspondente no `docs/PLANO_SPRINT.md`.

### Achados de Alta Severidade

| ID | Achado | Arquivo | Status | Tarefa |
|---|---|---|---|---|
| F-01 | `get_client_ip()` confia em `X-Forwarded-For` sem ProxyFix — IP spoofing possível | `app/utils.py`, `app/__init__.py` | **Resolvido** 2026-06-17 — ProxyFix adicionado; `get_client_ip()` usa `remote_addr` | S1-01 |
| F-02 | APScheduler sem distributed lock — jobs disparam N vezes com múltiplos workers | `app/__init__.py:161–219` | **Resolvido** 2026-06-18 — `scheduler_lock.py` + jobs wrapeados; fallback sem Redis (S4-01) | S4-01 |
| F-13 | Race condition em `contadores_uso.py`: read-then-write sem transação — limite diário pode ser burlado | `contadores_uso.py` | **Resolvido** 2026-06-17 — `@firestore.transactional` em `_verificar_incrementar_tx` | S2-01 |
| F-14 | Race condition em gamification: `_adicionar_exp` lê EXP e escreve sem transação — pontos perdidos/duplicados | `gamification_service.py` | **Resolvido** 2026-06-17 — `Increment(pontos)` para `exp_total`/`exp_semanal` | S2-02 |
| F-15 | HTML injection em relatório semanal: `_tabela_html` inseria valores de chamados sem escaping | `report_service.py:148-151` | **Resolvido** 2026-06-17 — `html.escape()` adicionado em todos os campos | S2-03 |
| F-16 | `TRANSLATION_MAP` (dict global mutável) sem lock em ambiente multi-thread — escritas concorrentes podem corromper traduções | `translation_service.py` | **Resolvido** 2026-06-17 — `threading.RLock` em leituras/escritas | S2-04 |
| F-33 | `window.prompt()` para capturar motivo de cancelamento — bloqueado por popup blockers, não acessível a leitores de tela | `dashboard_otimizacoes.js`, `dashboard.html` | **Resolvido** 2026-06-17 — modal `<dialog>` acessível | S2-05 |
| F-34 | Strings de fallback em `dashboard_otimizacoes.js` hardcoded em PT-BR | `MSGS` objeto, linhas 13-23 | **Resolvido** 2026-06-17 — `DTX_MSGS`/`DTX_URLS`/`DTX_STATUS_VALIDOS` injetados via servidor | S3-03 |
| F-35 | `ANALISE_COMPLETA_SISTEMA.md` desatualizado em 12+ pontos | Doc inteiro | **Resolvido** 2026-06-17 — doc reescrito (Docker, Flask-Login, Graph API) | S5-02 |
| F-40 | `INCIDENT_RUNBOOK.md` linha 138: aviso billing vencido (prazo 19/06/2026, já vencido) | `INCIDENT_RUNBOOK.md:138` | **Resolvido** 2026-06-17 — seção de billing GCP removida; runbook migrado para Docker | S1-06 |
| **F-50** | **Tautologia em `test_i18n.py:29`: `assert result != "back" or result == "back"` — o teste nunca falha** | `tests/test_i18n.py:29` | **Resolvido** 2026-06-17 — assert corrigido para valor esperado real | S0-01 |
| **F-51** | **URL E2E `/relatorios` em `test_fluxo_supervisor.py:34,60` — rota real é `/admin/relatorios`** | `tests/e2e/test_fluxo_supervisor.py` | **Resolvido** 2026-06-17 — URLs corrigidas | S0-02 |
| **F-52** | **URL E2E `/relatorios` em `test_fluxo_admin.py:53` — rota real é `/admin/relatorios`** | `tests/e2e/test_fluxo_admin.py` | **Resolvido** 2026-06-17 — URL corrigida | S0-02 |
| **F-71** | **`atualizar_firebase.py` apaga coleções inteiras sem dry-run, sem confirmação e sem checar ambiente** | `scripts/atualizar_firebase.py` | **Resolvido** 2026-06-17 — flags `--dry-run` e `--apply`; marcado obsoleto em `scripts/README.md` | S1-07 |
| **F-72** | **`atualizar_setores_from_print.py` apaga `categorias_setores` sem dry-run nem confirmação** | `scripts/atualizar_setores_from_print.py` | **Resolvido** 2026-06-17 — flags `--dry-run` e `--apply` | S1-08 |

### Achados de Média Severidade

| ID | Achado | Arquivo | Status | Tarefa |
|---|---|---|---|---|
| F-03 | `# noqa: S310` não suprime bandit (correto: `# nosec B310`) | `translation_service.py:27` | **Resolvido** 2026-06-17 — `# nosec B310` aplicado | S1-04 |
| F-04 | `datetime.utcnow()` depreciado em Python 3.12+ — ocorre em duas linhas | `analytics.py:87, 216` | **Resolvido** 2026-06-17 — substituído por `datetime.now(UTC).replace(tzinfo=None)` | S1-02 |
| F-05 | `print()` de debug em código de produção | `models_historico.py:85` | **Resolvido** 2026-06-17 — substituído por `logger.debug()` | S1-03 |
| F-06 | `upload.py` com 47% de cobertura (caminho crítico de segurança) | `app/services/upload.py` | **Resolvido** 2026-06-18 — cobertura 47% → 100% (+13 testes) | S3-01 |
| F-07 | `notifications.py` com 53% de cobertura | `app/services/notifications.py` | **Resolvido** 2026-06-18 — cobertura 72% → 98% (+19 testes) | S3-02 |
| F-17 | `obter_inscricoes` Web Push sem limite — acúmulo de centenas de inscrições | `webpush_service.py:69` | **Resolvido** 2026-06-18 — `MAX_INSCRICOES=20`, `.limit()` + warning quando atingido (S4-04) | S4-04 |
| F-18 | `area` em `assignment.atribuir()` não validado contra lista de áreas conhecidas | `assignment.py:92` | **Resolvido** 2026-06-18 — retorno `sucesso=False` para área vazia/whitespace (S4-08) | S4-08 |
| F-19 | `CategoriaImpacto.save()` sem `@firebase_retry` | `models_categorias.py:319` | **Resolvido** 2026-06-18 — `@firebase_retry(max_retries=3)` adicionado (S4-05) | S4-05 |
| F-20 | Estratégia `aleatorio` em `AtribuidorAutomatico` seleciona sempre o primeiro supervisor | `assignment.py:123` | **Resolvido** 2026-06-18 — `random.choice(supervisores_com_carga)` substituindo acesso fixo ao índice 0 (Onda A) | Onda A |
| F-21 | `contador_round_robin` em memória — multi-worker não funciona | `assignment.py:49` | **Resolvido** 2026-06-18 — Redis INCR com fallback em memória (Onda B) | Onda B |
| F-22 | `is_gate_valido` faz full-scan em `categorias_gates` a cada chamada, sem cache | `gates_service.py:43` | **Resolvido** 2026-06-18 — `get_static_cached("gates_validos_set", ttl=300)` + invalidação em `_invalidar_cache_gates()` (Onda B) | Onda B |
| F-23 | `_aplicar_filtros_em_memoria` chama `doc.to_dict()` 5x por documento | `filters.py:143-149` | **Resolvido** 2026-06-18 — `d = doc.to_dict()` chamado uma vez; lookups subsequentes via `d.get(...)` (Onda A) | Onda A |
| F-24 | `_enviar_resumo_admins` faz `Usuario.get_by_id()` dentro de loop — N+1 | `report_service.py:365-366` | **Resolvido** 2026-06-18 — `Usuario.get_by_ids(ids)` 1× antes do loop (Onda B) | Onda B |
| F-36 | URL `/api/atualizar-status` hardcoded em `dashboard_otimizacoes.js` | `dashboard_otimizacoes.js:132` | **Resolvido** 2026-06-17 — URL via `DTX_URLS.atualizarStatus` | S3-03 |
| F-37 | Strings `'Filtrar'` e `'Todos'` hardcoded em PT-BR nos dropdowns | `table-filters.js:244, 249` | **Resolvido** 2026-06-17 — strings via `DTX_MSGS` do servidor | S3-04 |
| F-38 | `console.warn` em `table-filters.js` não protegido por `DTX_DEBUG` | `table-filters.js:39, 50` | **Resolvido** 2026-06-17 — logs condicionados a `window.DTX_DEBUG` | S3-04 |
| F-39 | `INCIDENT_RUNBOOK.md` baseado em Cloud Run/GCP — deploy atual é Docker | Doc inteiro | **Resolvido** 2026-06-17 — runbook reescrito para Docker + R2 | S5-01 |
| F-41 | CSS injetado dinamicamente sem verificar duplicatas | `dashboard_otimizacoes.js` | **Resolvido** 2026-06-19 — guard `getElementById` + `style.id` (Onda C wave 2) | Onda C w2 |
| F-42 | `ANALISE_COMPLETA_SISTEMA.md` documenta `SESSION_LIFETIME = 86400` sem contextualizar relação com 15 min de inatividade | Ambos docs | **Fechado** S5-02 (2026-06-17) — contexto de inatividade (15 min) adicionado |
| F-53 | `test_solicitante.py` legado com `BASE_URL` hardcoded coexiste com `test_fluxo_solicitante.py` | `tests/e2e/test_solicitante.py` | **Fechado** S0-03 (2026-06-17) — marcado com `pytest.mark.skip` (legado) |
| **F-54** | **Mock `patch("app.routes.api.db")` é inerte quando serviço importa `db` diretamente — falsa impressão de isolamento** | `tests/test_routes/` | **Resolvido** 2026-06-18 — 3 mocks inertes removidos de test_api.py, test_api_contract.py, test_regression_suite.py | S3-05 |
| **F-55** | **`assert status_code in (200, 404)` mascara 404 como sucesso em testes de contrato** | `tests/` | **Resolvido** 2026-06-18 — asserts exatos; rota inexistente asserta `== 404` | S3-06 |
| **F-56** | **Variante adicional de assert permissivo — mesmo problema que F-55** | `tests/` | **Resolvido** 2026-06-18 — `test_api_status.py:93` corrigido para `== 404` com mock `doc.exists=False` | S3-07 |
| **F-57** | **Zero testes para supervisor acessando `/admin/relatorios`** | `tests/e2e/` | **Resolvido** 2026-06-18 — 2 testes adicionados em test_dashboard.py (supervisor 200, solicitante 302/403) | S3-08 |
| **F-58** | **Race condition em `gerar_numero_chamado` não testada** | `tests/` | **Resolvido** 2026-06-18 — `test_gerar_numero_chamado_concorrencia_gera_numeros_unicos` em `test_utils.py`; 5 threads com mock serializado; assert uniqueness (Onda A) | Onda A |
| **F-59** | **CSV injection via `/exportar` não testada** | `tests/` | **Resolvido** 2026-06-18 — `_safe_cell()` aplicado em `exportar()` (dashboard.py); `test_exportar_neutraliza_formula_injection_em_xlsx` verifica que `=CMD` e `+123` são neutralizados (Onda A) | Onda A |
| F-64 | `table-filters.css` com valores de cor hardcoded em vez de tokens DTX | `app/static/css/table-filters.css` | **Fechado** S3-08 (2026-06-17) — cores de marca/estruturais migradas para `var(--color-*)`; cinzas de texto neutros sem token documentados |
| F-65 | Tokens locais `--dash-*`/`--reports-*` duplicam valores dos tokens globais em vez de referenciar | `app/static/css/` | **Fechado** S3-08 (2026-06-17) — aliases agora referenciam tokens globais |
| F-66 | Sintaxe `rgba()` com vírgula (CSS nível 3 depreciada) em `relatorios.css` | `app/static/css/relatorios.css` | **Fechado** S3-09 (2026-06-17) — migrado para `color-mix()` |
| F-67 | Três padrões divergentes de focus ring entre os arquivos CSS | `app/static/css/` | **Fechado** S3-08 (2026-06-17) — unificado em `outline` (igual `input.css`) |
| F-77 | `DEPLOYMENT_PLAN.md` descrevia Cloud Run e limite incorreto — limite real é **10 MB/arquivo** (config.py) | `docs/DEPLOYMENT_PLAN.md` | **Fechado** S5-03 (2026-06-17) — doc migrada para Docker; limite corrigido para 10 MB |

### Achados de Baixa Severidade / Info / Dívida Técnica

| ID | Achado | Arquivo | Status | Tarefa |
|---|---|---|---|---|
| F-08 | `docs/SLO.md` healthcheckTimeout divergia da configuração real | `docs/SLO.md` | **Fechado** S4-09 (2026-06-17) |
| F-09 | `run.py` usa host `localhost` quando não em debug | `run.py:27` | **Fechado** S1-05 (2026-06-17) — host `0.0.0.0` em produção (Docker) com `# nosec B104` |
| F-10 | `docs/ANALISE_COMPLETA_SISTEMA.md` referencia Firebase Authentication (não implementado) | `docs/ANALISE_COMPLETA_SISTEMA.md` | **Fechado** S5-02 (2026-06-17) — corrigido para Flask-Login |
| F-11 | `tailwind.min.css` commitado E re-gerado no Dockerfile | `Dockerfile`, `.gitignore` | **Resolvido** 2026-06-18 — adicionado ao `.gitignore`; DEV_SETUP.md documenta `npm run build:css` obrigatório (S4-10) | S4-10 |
| F-12 | `Usuario.get_all()` sem cache em `visualizar_detalhe_chamado` | `app/routes/dashboard.py:159` | **Resolvido** 2026-06-18 — substituído por `get_static_cached("usuarios_all", ...)` TTL 300s em 2 locais (S4-03) | S4-03 |
| F-25 | `max_len = 3000` definido mas `nova_descricao` salva sem truncamento no Firestore | `edicao_chamado_service.py:126-129` | **Resolvido** 2026-06-18 — `[:3000]` aplicado após `bleach.clean()` antes de persistir (Onda A) | Onda A |
| F-26 | `cursor_prev` retornado em `listar_meus_chamados` é o parâmetro de entrada (string vazia) | `chamados_listagem_service.py:241` | **Resolvido** 2026-06-18 — `cursor_prev = docs[0].id if docs and cursor else None` (Onda A) | Onda A |
| F-27 | `exp_semanal` acumulado mas nunca zerado — ranking semanal não reflete semana atual | `gamification_service.py:80` | **Resolvido** 2026-06-18 — `GamificationService.resetar_ranking_semanal()` agendado domingo 23h59 BRT (S4-02) | S4-02 |
| F-28 | `cor="#gray"` como valor padrão é CSS inválido (deveria ser `"gray"` ou `"#808080"`) | `models_categorias.py:272` | **Resolvido** 2026-06-17 — padrão `"gray"` (S4-06) | S4-06 |
| F-29 | `Increment` importado com fallback `None` — se ImportError silencioso, limite de rate é ignorado | `contadores_uso.py:15-17, 54` | **Resolvido** 2026-06-18 — import direto `from google.cloud.firestore_v1 import Increment` + `@firestore.transactional` eliminam o fallback (Onda A) | Onda A |
| F-30 | `SETOR_PARA_AREA` com apenas 2 mapeamentos hardcoded — novo setor requer deploy | `utils_areas.py:7-10` | **Resolvido** 2026-06-19 — Firestore `config/setor_para_area` é a fonte de verdade; fallback estático + cache TTL 5 min + `invalidar_cache_setor_area()`; script `migrar_setor_area.py`; 8 testes em `test_utils_areas.py` + 4 em `test_migrar_scripts.py` (Onda C wave 3) | Onda C w3 |
| F-31 | Documentos `contadores_uso` acumulam sem cleanup — crescimento indefinido | `contadores_uso.py` | **Resolvido** 2026-06-19 — `limpar_contadores_antigos(dias=90)`, job APScheduler domingo 02h00 BRT, script CLI `scripts/limpar_contadores_uso.py`, 6 testes (Onda C wave 2) | Onda C w2 |
| F-32 | Chaves `edit_*_soon` em `translations.json` expõem ao usuário que funcionalidade não está implementada | `translations.json:1467-1481` | **Resolvido** 2026-06-17 — chaves removidas | S5-06 |
| F-43 | `catch (e) {}` silencioso no Service Worker — falhas no parse do payload Push perdem contexto de erro | `app/static/sw.js:10` | **Resolvido** 2026-06-17 — `console.error` no catch (S4-07) | S4-07 |
| F-44 | `localeCompare('pt-BR')` hardcoded no sort de tabela | `table-filters.js:114` | **Resolvido** 2026-06-17 — locale via `DTX_MSGS.locale` | S3-04 |
| F-45 | `ENV.md` não documenta `ITENS_POR_PAGINA_DASHBOARD` | Ambos docs | **Resolvido** 2026-06-17 — variável documentada em `ENV.md` | S5-03 |
| F-46 | `statusValidos` array hardcoded em PT-BR em `dashboard_otimizacoes.js` | `dashboard_otimizacoes.js:87` | **Resolvido** 2026-06-17 — `DTX_STATUS_VALIDOS` via servidor | S3-03 |
| F-47 | `API.md` — URL `/api/confirmar-resolucao` inconsistente entre seção de erros e índice | `API.md` linhas 761 vs 79 | **Resolvido** 2026-06-17 — índice alinhado | S5-05 |
| F-48 | `onmouseover`/`onmouseout` inline nos botões do card de onboarding gerado por JS | `onboarding.js:588,608-609,616,632,643-644` | **Resolvido** 2026-06-18 — handlers removidos; hover via `mouseenter`/`mouseleave` em `bindCardEvents()` (Onda C wave 1) | Onda C w1 |
| F-49 | `DEV_SETUP.md` não menciona Node.js como pré-requisito para build Tailwind | `DEV_SETUP.md` | **Resolvido** 2026-06-17 — Node.js 20+ e `npm run build:css` documentados | S5-04 |
| **F-60** | **Sem teste para contagem exata de passos de onboarding por perfil (5/6/7)** | `tests/` | **Resolvido** 2026-06-18 — 9 testes em `test_dtx_onboarding_js.py` (Onda C wave 1) | Onda C w1 |
| **F-61** | **Sem teste para idioma inválido em `?lang=xyz`** | `tests/` | **Resolvido** 2026-06-18 — `antes_da_requisicao()` validado via `get_language_code(raw)`; fallback `pt_BR`; 4 testes HTTP em `test_i18n_lang.py` (Onda A) | Onda A |
| **F-62** | **`_usuario_mock()` não seta todos os campos do modelo — pode mascarar KeyError** | `tests/` | **Resolvido** 2026-06-17 — `onboarding_completo` e `onboarding_passo` adicionados | S3-09 |
| **F-63** | **Sem teste para transições de status inválidas (ex: Concluido → Aberto)** | `tests/` | **Resolvido** 2026-06-18 — `test_atualizar_status_transicao_invalida_retorna_400` em `test_api_status.py`; rota retorna 400 via `resultado.get("codigo")` (Onda A) | Onda A |
| **F-68** | **Cor de borda diverge entre arquivos CSS em relação aos tokens do design system** | `app/static/css/` | **Resolvido** 2026-06-19 — token `var(--color-surface-border)` em dashboard.css + relatorios.css; invariantes de regressão adicionadas (Onda C wave 2) | Onda C w2 |
| **F-69** | **`.insight-card` possivelmente morto — não referenciado nos templates Flask ativos** | `app/static/css/` | **Resolvido** 2026-06-18 — verificado em uso: 8 instâncias em `relatorios.html` (Fase 0) | Fase 0 |
| **F-70** | **`app/static/dist/` contém bundle SPA não documentado — possivelmente não deveria estar no repositório** | `app/static/dist/` | **Resolvido** 2026-06-17 — `app/static/dist/` adicionado ao `.gitignore` | S0-05 |
| **F-73** | **`scripts/` sem README explicando qual script usar em cada situação** | `scripts/` | **Resolvido** 2026-06-17 — `scripts/README.md` criado | S5-11 |
| **F-74** | **Três scripts sobrepostos para seeding de categorias** | `scripts/` | **Resolvido** 2026-06-17 — matriz de scripts documentada em `scripts/README.md` | S5-11 |
| **F-75** | **Script de migração sem transação — falha parcial deixa dados em estado inconsistente** | `scripts/migrar_*.py` | **Resolvido** 2026-06-18 (hardening completo) — `--apply` obrigatório; default `dry_run=True`; batch writes ≤500 ops em todos os scripts (`migrar_catalogo`, `migrar_chamados`, `migrar_usuarios`, `migrar_gates`, `migrar_grupos_rl`, `migrar_setor_area`); checkpoint JSON por fase em `scripts/.checkpoints/` (no `.gitignore`); paginação `limit/start_after` em `migrar_chamados`, `migrar_usuarios`, `migrar_grupos_rl` (sem OOM); helpers compartilhados em `scripts/_migration_utils.py`; rollback manual documentado em README | Onda C w1/w3 |
| **F-76** | **`python-dotenv` não listado explicitamente como dependência dos scripts** | `requirements*.txt` | **Resolvido** 2026-06-18 — `python-dotenv==1.0.1` em `requirements.txt:33` (Fase 0) | Fase 0 |
| **F-78** | **`confirmacao-solicitante.md` na raiz do projeto — deveria estar em `docs/plans/`** | `confirmacao-solicitante.md` | **Resolvido** 2026-06-17 — movido para `docs/plans/` | S0-04 |
| **F-79** | **`TESTES_API.md` aponta para `test_api_contract.py` que não existe no projeto** | `docs/TESTES_API.md` | **Resolvido** 2026-06-17 — doc alinhado com `tests/test_routes/test_api_contract.py` | S5-09 |
| **F-80** | **`PLANO_DE_TESTES.md` cita Python "3.8+" e "E2E fora do escopo" — contradiz realidade do projeto** | `docs/PLANO_DE_TESTES.md` | **Resolvido** 2026-06-17 — Python 3.12+ e E2E no escopo | S5-10 |
| **F-81** | **`AB_TEST_PLAN.md` descreve `ab_service.py` não implementado, sem issue linkada** | `docs/AB_TEST_PLAN.md` | **Resolvido** 2026-06-18 — `ab_service.py` + integração em `chamados.py` + template A/B + logging AB em `validators.py` + 7 testes | F-81 |
| **F-82** | **Divergência de campo em índice Firestore documentado vs. índice real** | `docs/` | **Resolvido** 2026-06-17 — `firestore.indexes.json` e docs sincronizados | S5-10 |

### Como atualizar este quadro

Quando um achado for resolvido:

1. Altere o status para **Resolvido**
2. Adicione a data de resolução na coluna
3. Commite com `fix(security): Resolver achado F-XX — descrição`

---

## Resultado da última auditoria (2026-06-22 — pós-Gate Final)

### pytest

```
1487 passed, 0 failed in ~62s
Cobertura geral: 94,79% (gate: 85%) — gate global OK; gate 52/52 módulos OK
```
> **Nota (2026-06-22 — Desativação de usuários — Onda 2):** +52 testes (Onda 2 desativação): 4 auth, 7 modelos, 5 admin, 1 user_loader; ruff CLEAN; bandit 0 High/0 Medium; review-security CLEAN nos novos endpoints desativar/ativar e bloqueio de login.
> **Nota (2026-06-22 — Gate Final — Cobertura):** CI alinhado (`.github/workflows/ci.yml` `--cov-fail-under=85` + step `check_coverage_per_module.py --json-only`); bugbot: 2 MEDIUM resolvidos; review-security CLEAN; docs sync: README, PLANO_SPRINT, RELATORIO_EXECUTIVO, GUIA_ONBOARDING, melhorias-sprint.
> **Nota (2026-06-22 — Onda 4 — Infraestrutura):** Onda 4 concluída — `database.py` 52% → 100%, `__init__.py` 72% → 98%; gate 52/52; global 93,04% → 94,98%; +53 testes (test_database.py 11, test_app_init.py 42). Fix i18n: `get_language_code` retorna `pt_BR` como padrão (era `en`); sessão padrão corrigida — 1435/1435 passando. ADR criado em `docs/plans/adr-database-testabilidade.md`.
> **Nota (2026-06-19 — Onda 3):** Onda 3 concluída — analytics.py 64% → 94%, dashboard.py 69% → 93%; +73 testes analytics, +37 testes dashboard; global 89,35% → 93,04%.
> **Nota (2026-06-19 — Onda 2):** Onda 2 concluída — 3 módulos de segurança elevados a ≥85%, +69 testes (+12 vs Onda 1), global 86,18% → 89,35%.
> **Nota (2026-06-19 — Onda 1):** Onda 1 concluída — 6 módulos elevados a ≥85%, +57 testes, global 84,38% → 86,18%.
> Baseline Onda 0 (2026-06-19): 1183 testes, 84,38%, gate recém-elevado de 80% → 85%.

### ruff

```
All checks passed OK
```

### bandit

```
Test results:
    No issues identified with HIGH severity.
    0 issues identified with MEDIUM severity (F-03 resolvido — # nosec B310)
    12 issues identified with LOW severity.
```

> **Nota sobre notifications.py:** As linhas equivalentes em `notifications.py` já usam `# nosec B310` corretamente. O baseline de Medium foi eliminado com a correção de F-03.

### Resumo de achados por rodada de auditoria

| Rodada | Data | Achados identificados | Achados em aberto |
|---|---|---|---|
| 1ª Rodada | 2026-06-16 | F-01 a F-12 (12 achados) | 0 *(todos resolvidos no sprint)* |
| 2ª Rodada | 2026-06-16 | F-13 a F-49 (37 novos achados) | 15 *(backlog F-20–F-31, F-41, F-48)* |
| 3ª Rodada | 2026-06-16 | F-50 a F-82 (33 novos achados) | 9 *(F-58–F-63, F-68, F-69, F-75, F-76)* |
| Sprint 2026-06-17/18 | 2026-06-17–18 | Grupos 0–7 + F-81 (61 achados resolvidos) | — |
| Onda A 2026-06-18 | 2026-06-18 | F-20, F-23, F-25, F-26, F-29, F-58, F-59, F-61, F-63 (9 resolvidos) | — |
| Fase 0 2026-06-18 | 2026-06-18 | F-69, F-76 (2 verificados/resolvidos) | — |
| Onda B 2026-06-18 | 2026-06-18 | F-21, F-22, F-24 (3 resolvidos) | — |
| Onda C wave 1 2026-06-18 | 2026-06-18 | F-75, F-48, F-60 (3 resolvidos) | — |
| Onda C wave 2 2026-06-19 | 2026-06-19 | F-31, F-41, F-68 (3 resolvidos) | — |
| Onda C wave 3 2026-06-19 | 2026-06-19 | F-30 (1 resolvido) | — |
| **Onda 2 — Segurança e API 2026-06-19** | **2026-06-19** | **3 módulos → ≥85%; bug cache TDD** | **—** |
| **Onda 3 — Negócio e relatórios 2026-06-19** | **2026-06-19** | **analytics.py 64%→94%, dashboard.py 69%→93%; +110 testes** | **—** |
| **Onda 4 — Infraestrutura 2026-06-22** | **2026-06-22** | **database.py 52%→100%, __init__.py 72%→98%; +53 testes; ADR** | **—** |
| **Gate Final — Cobertura 2026-06-22** | **2026-06-22** | **i18n fix pt_BR, CI 85%+script, docs sync, 1435 testes, 52/52** | **—** |
| **Desativação de usuários (ativo=false) — 2026-06-22** | **2026-06-22** | **campo `ativo`, bloqueio auth, user_loader, rotas /desativar+/ativar, migração, 16 novos testes** | **—** |
| **Total** | **2026-06-22** | **82 achados** | **0** |

### Distribuição por severidade (total acumulado — atualizado 2026-06-19)

| Severidade | Quantidade | Abertos |
|---|---|---|
| Alto | 15 | **0** |
| Médio | 31 | **0** |
| Baixo / Info / Dívida | 36 | **0** |
| **Total** | **82** | **0** |

### Módulos abaixo de 85% — status pós-Onda 4 (2026-06-22)

Gate: **85%** (`pytest.ini --cov-fail-under=85`).
Gate por módulo: `python scripts/check_coverage_per_module.py` — **52/52 módulos OK**, **0 pendentes**.

> **Cobertura global:** 94,98% — ~1435 testes, 2026-06-22 (Onda 4 concluída — baseline 13/13 resolvido).
> **Removidos da lista (2026-06-18 — Grupo 4):** `upload.py` 100%, `notifications.py` 98% — F-06, F-07 resolvidos.

#### Resolvidos na Onda 1 — 2026-06-19 ✅

| Módulo | Camada | % antes | % depois | Arquivo de teste |
|---|---|---:|---:|---|
| `app/exceptions.py` | Core | 69% | **100%** | `tests/test_exceptions.py` |
| `app/cache.py` | Infra | 63% | **99%** | `tests/test_cache.py` |
| `app/routes/categorias.py` | Admin | 81% | **90%** | `tests/test_routes/test_categorias.py` |
| `app/services/chamados_criacao_service.py` | Negócio | 83% | **87%** | `tests/test_services/test_chamados_criacao_service.py` |
| `app/services/dashboard_service.py` | Negócio | 83% | **98%** | `tests/test_services/test_dashboard_service.py` |
| `app/services/webpush_service.py` | Notificações | 83% | **99%** | `tests/test_services/test_webpush_service.py` |

> Bug corrigido via TDD: `dashboard_service.ordenar_metricas_supervisores` — SLA com `asc=False` ordenava `None` primeiro.

#### Resolvidos na Onda 2 — Segurança e API — 2026-06-19 ✅

| Módulo | Camada | % antes | % depois | Arquivo de teste |
|---|---|---:|---:|---|
| `app/routes/admin_global.py` | Segurança | 49% | **100%** | `tests/test_routes/test_admin_global.py` |
| `app/routes/usuarios.py` | Segurança | 68% | **96%** | `tests/test_routes/test_usuarios.py` |
| `app/routes/api.py` | Segurança | 78% | **99%** | `tests/test_routes/test_api_gaps.py` |

> Bug corrigido via TDD (Red→Green): `app/routes/api.py` L81 — `from app.cache import cache` (símbolo inexistente) → `cache_set(...)`. Health check deep sempre marcava cache como `"degraded:ImportError"`.

#### Resolvidos na Onda 3 — Negócio e relatórios — 2026-06-19 ✅

| Módulo | Camada | % antes | % depois | Arquivo de teste |
|---|---|---:|---:|---|
| `app/services/analytics.py` | Negócio | 64% | **94%** | `tests/test_services/test_analytics.py` |
| `app/routes/dashboard.py` | Negócio | 69% | **93%** | `tests/test_routes/test_dashboard.py` |

> Funções cobertas: `_sla_dias_por_categoria`, `_to_datetime`, `_dentro_sla`, `obter_sla_para_exibicao`, `obter_analise_atribuicao` (82 linhas inteiras), `obter_insights`, `obter_metricas_supervisores/areas/periodo_anterior`, `_carregar_chamados_analytics`, `obter_relatorio_completo`; `exportar_avancado`, `_same_origin`, `FailedPrecondition → 503`, múltiplas branches de `relatorios` e `editar_chamado_pagina`.

#### Resolvidos na Onda 4 — Infraestrutura — 2026-06-22 ✅

| Módulo | Camada | % antes | % depois | Arquivo de teste |
|---|---|---:|---:|---|
| `app/database.py` | Infra | 52% | **100%** | `tests/test_database.py` |
| `app/__init__.py` | Infra | 72% | **98%** | `tests/test_app_init.py` |

> Estratégia ADR Opção A: `importlib.reload` + mocks; zero mudança de produção em database. +53 testes.

> 6 (Onda 1) + 3 (Onda 2) + 2 (Onda 3) + 2 (Onda 4) = 13/13 módulos baseline Onda 0 resolvidos. Gate total app/: 52/52 (inclui módulos novos pós-baseline).

#### Gate Final — Cobertura 2026-06-22 ✅

| Indicador | Resultado |
|---|---|
| pytest | **1487 passed, 0 failed** |
| Cobertura global | **94,79%** (gate: 85%) |
| Gate por módulo | **52/52** (`python scripts/check_coverage_per_module.py`) |
| CI `.github/workflows/ci.yml` | `--cov-fail-under=85` + step gate por módulo |
| Fix i18n (F-61) | `get_language_code` retorna `pt_BR` como padrão; session defaults corrigidos |
| ruff | **All checks passed** |
| bandit | **0 Medium, 0 High** |
| Bugbot | Executado — 2 MEDIUM resolvidos (`_restaurar_database` → `try/finally`; `app_context` redundante removido dos job tests) |
| review-security | CLEAN — sem achados bloqueantes (Origin/Referer, HTTPS, CSP, CSRF inalterados; desativar/ativar, bloqueio auth e user_loader revisados sem findings HIGH/MEDIUM) |

### Pontos positivos confirmados na 3ª rodada

| Item | Observação |
|---|---|
| `firestore.rules` | `allow read, write: if false` — deny-all correto, acesso externo direto bloqueado |
| `tailwind.config.js` + `input.css` | 100% consistentes com o design system documentado |
| `docs/QA_DEBUG_PLAYBOOK.md` | Documento excelente, totalmente atual |
| `tests/test_dtx_*` | Suite sofisticada que lê arquivos-fonte reais — diferencial de qualidade |
| **F-15 resolvido** (2026-06-17) | `_tabela_html` em `report_service.py` — `html.escape()` adicionado em categoria, tipo, solicitante e data |
| Sprint Grupos 0–7 + F-81 (2026-06-18) | 61 achados resolvidos; zero Alta severidade aberta; 1093 testes, 83,93% cobertura |
| `ab_service.py` (F-81) | A/B test AB-001 no formulário de chamados — split determinístico por UID |
| `scheduler_lock.py` | Redis distributed lock em jobs APScheduler — F-02 resolvido |
| `upload.py` / `notifications.py` | Cobertura 100% / 98% — F-06, F-07 resolvidos |
| Perfil `admin_global` | Hierarquia de acesso documentada em `decoradores.py`; auto-expansão de `admin` → `admin_global` implementada |
| `notifications.py` refatorado | Removido Brevo/SMTP; exclusivamente Microsoft Graph API — `# nosec B310` aplicado corretamente |

---

## Procedimento de resposta a incidente de segurança

> **Atenção:** Execute este procedimento imediatamente ao confirmar um incidente. Não espere por aprovações — a velocidade de resposta é crítica.

### Passo 1 — Contenção imediata (0–15 minutos)

1. **Se credenciais foram expostas:** Rotacionar nas variáveis de ambiente do servidor e invalidar a chave no serviço correspondente (Firebase, Azure, Cloudflare).
2. **Se usuário malicioso detectado:** Desativar conta no painel admin (`/admin/usuarios`).
3. **Se brecha ativa em produção:** Parar o container para modo de manutenção (`docker stop <container>`).

### Passo 2 — Investigação (15–60 minutos)

1. Acessar logs: `docker logs --tail 1000 <container>` (ou painel do provedor)
2. Identificar: qual o vetor de ataque, quais dados foram acessados, por quanto tempo
3. Verificar logs de autenticação para acessos anômalos (horário incomum, IPs suspeitos)
4. Verificar histórico do Firestore — todos os documentos têm `updated_at` e `updated_by`

### Passo 3 — Remediação (1–4 horas)

1. Corrigir a vulnerabilidade no código
2. Executar ciclo de qualidade completo (ruff → bandit → pytest)
3. Deploy da correção: `git push origin main` + redeploy via CI/CD
4. Verificar que o vetor explorado não existe mais

### Passo 4 — Documentação e comunicação (até 24 horas)

1. Documentar o incidente em `docs/` (arquivo `INCIDENTE_YYYY-MM-DD.md`)
2. Atualizar este checklist com o achado identificado
3. Atualizar `docs/PLANO_SPRINT.md` com tarefa de remediação definitiva
4. Se dados de usuários foram comprometidos: acionar procedimento LGPD (notificação à ANPD em até 72h)

### Comandos Docker de resposta a incidente

```bash
# Ver logs em tempo real
docker logs -f <container>

# Ver status dos containers
docker ps

# Forçar redeploy (ex: após rotacionar credenciais)
docker compose up -d --force-recreate

# Modo de manutenção (parar o container)
docker stop <container>
```

### Contatos de escalada

| Situação | Responsável |
|---|---|
| Incidente técnico (brecha, dados expostos) | Dev responsável pelo projeto |
| Dados pessoais comprometidos (LGPD) | DPO / Jurídico DTX Aerospace |
| Indisponibilidade de infra (servidor/VPS) | Suporte do provedor de hospedagem |
| Credenciais Firebase comprometidas | [Console Firebase](https://console.firebase.google.com) — revogar service account |
| Credenciais R2 comprometidas | [Painel Cloudflare](https://dash.cloudflare.com) — revogar API token |
| Problema de billing GCP/Firebase | [Console GCP](https://console.cloud.google.com) — verificar billing |

---

## Referências OWASP

Os itens deste checklist mapeiam para o OWASP Top 10 (2021):

| OWASP | Categoria | Seções deste checklist |
|---|---|---|
| A01 | Broken Access Control | Seções 1, 2.2, 5 |
| A02 | Cryptographic Failures | Seções 6, 9.2 |
| A03 | Injection | Seções 5.2, 8, 11 (HTML injection — F-15 **resolvido**; CSV injection — F-59 **resolvido** 2026-06-18) |
| A04 | Insecure Design | Seções 1, 4, 9, 12 (race conditions), 13 (scripts destrutivos) |
| A05 | Security Misconfiguration | Seções 3, 7, 10 |
| A06 | Vulnerable and Outdated Components | Ciclo de qualidade (ruff/bandit) |
| A07 | Identification and Authentication Failures | Seções 1.3, 4 |
| A08 | Software and Data Integrity Failures | Seções 10.1, 13 (scripts sem dry-run) |
| A09 | Security Logging and Monitoring Failures | Seção 8 (inclui `app/static/sw.js` catch silencioso — F-43) |
| A10 | Server-Side Request Forgery (SSRF) | Seção 2.2, achado F-03 |

### Referências adicionais

- [OWASP Top 10 2021](https://owasp.org/Top10/)
- [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP HTML Injection Prevention](https://cheatsheetseries.owasp.org/cheatsheets/HTML_Injection_Prevention_Cheat_Sheet.html)
- [LGPD — Lei 13.709/2018](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm)
- [Web Push Protocol (IETF RFC 8030)](https://tools.ietf.org/html/rfc8030)
- [VAPID Authentication (IETF RFC 8292)](https://tools.ietf.org/html/rfc8292)

---

*Documento atualizado em 2026-06-17 — DTX Aerospace, Engenharia de Software*
*Versão 3.4 — Gate Final 2026-06-22: i18n fix pt_BR padrão, CI 85%+gate por módulo, 1435 testes, 52/52 OK, docs sync concluído.*
*Versão 3.3 — Onda 4 Infraestrutura 2026-06-22: database.py 52%→100%, __init__.py 72%→98%, +53 testes, ADR.*
*Versão 3.1 — Sprint 2026-06-17: F-15 resolvido (html.escape em report_service); perfil admin_global documentado; path sw.js corrigido; F-04 ampliado para analytics.py:87*
*Próxima revisão: após conclusão do sprint (2026-07-18)*
