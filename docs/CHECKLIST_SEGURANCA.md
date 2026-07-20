# Checklist de Segurança — Sistema de Chamados DTX Aerospace

| Campo | Valor |
|---|---|
| **Documento** | Checklist de Segurança — Revisão de PR e Deploy |
| **Versão** | 3.6 |
| **Data** | 2026-07-06 |
| **Autor** | DTX Aerospace — Engenharia de Software |
| **Última auditoria** | 2026-06-23 (**QA manual CWI executado** — 15 PASS / 2 SKIP ops; `scripts/executar_qa_manual_cwi.py`; **Onda 5 Polish**; **Onda 4 Fernet PII**; matriz CWI §20; Ondas 1–5+4 concluídas; **82/82 achados**; gate **52/52**; CWI 2.3 **COMPLETO**) |
| **Encerramento plano CWI v2** | 2026-06-23 — **encerrado** — ver [`docs/ENCERRAMENTO_PROJETO_CWI.md`](ENCERRAMENTO_PROJETO_CWI.md) (rollout Fernet 2/2 usuários migrados) |
| **Auditoria de checkboxes 2026-07-06** | Verificação item a item contra o código atual (não só contra a tabela de achados): corrigidas ~30 divergências entre "Status atual: ABERTO" no corpo do documento e "Resolvido" na tabela de achados (F-05, F-34, F-36–38, F-40, F-43, F-44, F-50–53, F-62, F-64–67, F-70–78 — a tabela estava certa, o texto da seção estava desatualizado). Implementados nesta sessão: histórico de ações admin em usuários (`historico_usuario_service.py`), página `/meus-dados` (LGPD — direito de acesso), anonimização sob demanda de usuário desativado, header `Server` neutralizado (`gunicorn.conf.py`), `SECRET_KEY` com validação de comprimento mínimo (32 chars) em produção, log de acesso bem-sucedido a anexo, `rgba()` legado residual removido de `relatorios.css`/`table-filters.css`. Ver detalhe em cada seção abaixo. |

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

- [x] **Toda rota nova tem um decorador de acesso adequado**
  - Arquivo de referência: `app/decoradores.py`
  - Como verificar: Procure rotas sem `@requer_*`: `grep -n "def " app/routes/*.py | grep -v "@requer"`
  - Decoradores disponíveis:
    - `@requer_solicitante` — permite solicitante, supervisor, admin, admin_global
    - `@requer_supervisor_area` — permite supervisor, admin, admin_global
    - `@requer_perfil('admin')` — permite admin e admin_global (expansão automática)
    - `@requer_admin_global` — exclusivo para o perfil `admin_global` (sem expansão para admin)
  - **Nota:** `admin_global` é automaticamente incluído quando `'admin'` está na lista de perfis de `@requer_perfil`. Rotas exclusivas do `admin_global` devem usar `@requer_admin_global` definido em `app/routes/admin_global.py`.
  - **Verificado 2026-07-06** — este item é um gate recorrente (checar a cada PR), não um estado permanente; manter desmarcado seria mais correto para o uso "checklist de PR", mas a auditoria completa em 2026-07-06 não encontrou nenhuma rota sem decorador.

- [x] **Nenhuma rota expõe dados de outro usuário sem verificação de permissão**
  - Arquivo de referência: `app/services/permissions.py`
  - Como verificar: Toda consulta por `chamado_id` deve passar por `usuario_pode_ver_chamado(usuario, chamado)`
  - **Verificado 2026-07-06** — `usuario_pode_ver_chamado` usado em `dashboard.py` e `api_chamados.py` antes de liberar dados

- [x] **Rotas de API (`/api/*`) também têm proteção de perfil**
  - Arquivo de referência: `app/routes/api_chamados.py`, `api_colaboracao.py`, `api_notificacoes.py`, `api_solicitante.py` (split de `api.py`)
  - Como verificar: `grep -n "route" app/routes/api_*.py` — verificar decorador em cada rota
  - **Verificado 2026-07-06** — todas as ~26 rotas (hoje distribuídas nos 4 arquivos `api_*.py`) têm `@login_required` e/ou `@requer_*`

### 1.2 Verificação de IDOR (Insecure Direct Object Reference)

- [x] **Acesso a documentos específicos verifica se pertencem ao usuário/área**
  - Exemplo: `GET /chamado/<id>` deve verificar se o usuário tem permissão, não apenas se o ID existe
  - Arquivo de referência: `app/routes/dashboard.py`, `app/services/permissions.py`
  - Como verificar: Teste manual com ID de chamado de outro usuário — deve retornar 403, não os dados
  - **Verificado 2026-07-06** — `usuario_pode_ver_chamado`/`_otimizado` chamado antes de exibir; `tests/test_routes/test_download_idor.py`

- [x] **Download de anexo verifica propriedade do chamado antes de gerar URL pré-assinada**
  - Arquivo de referência: `app/routes/api_solicitante.py` — endpoint `/api/download-anexo`
  - Como verificar: Tentar baixar anexo de chamado de outro usuário com token de outro — deve retornar 403
  - **Verificado 2026-07-06** — checa `chave in anexos` + `usuario_pode_ver_chamado` antes de gerar URL. Acesso bem-sucedido agora também é logado (`logger.info` com usuário/chamado/chave) — **Resolvido 2026-07-06**, antes só logava em falha (ver §8.1)

### 1.3 Sessão e autenticação

- [x] **`must_change_password` é verificado e redireciona corretamente**
  - Arquivo de referência: `app/routes/auth.py`
  - Como verificar: Criar usuário com `must_change_password=True` e tentar acessar qualquer rota protegida
  - **Nota:** `admin` e `admin_global` são isentos da troca obrigatória de senha via `is_admin_or_above` (`app/routes/auth.py:157`)

- [x] **Logout automático por inatividade está ativo (15 minutos)**
  - Arquivo de referência: `app/__init__.py` — `_configurar_timeout_sessao()` / `checar_inatividade()` (before_request, checa `session["last_activity"]` a cada requisição)
  - Como verificar: `tests/test_app_init.py::test_timeout_sessao_expirada_redireciona_login`
  - **Nota (correção 2026-07-06):** a referência anterior a `PERMANENT_SESSION_LIFETIME` em `config.py` estava errada — esse valor nunca teve efeito (`session.permanent` nunca é setado, ver comentário em `config.py:184-187`). O timeout real é 100% independente disso: roda via `before_request` comparando timestamp de sessão a cada request. Mecanismo já estava implementado e testado; só a documentação apontava pro lugar errado.

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

- [x] **Extensão do arquivo está na allowlist**
  - Arquivo de referência: `app/services/validators.py` — `_get_extensoes_permitidas`/`_arquivo_permitido` (linhas 29-83)
  - Como verificar: Tentar upload de `.exe`, `.php`, `.sh` — deve ser rejeitado com erro 400
  - **Verificado 2026-07-06**

- [x] **Magic bytes são verificados independentemente da extensão**
  - Arquivo de referência: `app/services/validators.py:114-148` — `_arquivo_conteudo_permitido`
  - Como verificar: Renomear um arquivo executável para `.pdf` e tentar fazer upload — deve ser rejeitado
  - **Verificado 2026-07-06**

- [x] **Nome do arquivo é sanitizado antes de qualquer uso**
  - Arquivo de referência: `app/services/upload.py` — `secure_filename(arquivo.filename)`
  - Como verificar: Tentar upload com nome `../../../etc/passwd.pdf` — deve ser sanitizado/rejeitado
  - **Verificado 2026-07-06**

- [x] **Tamanho máximo do arquivo é respeitado**
  - Arquivo de referência: `config.py` — `MAX_CONTENT_LENGTH`; `validators.py` — `MAX_ANEXO_BYTES` (10 MB/arquivo)
  - Como verificar: Verificar configuração; tentar upload acima do limite
  - **Verificado 2026-07-06**

### 2.2 Armazenamento e acesso

- [ ] **Arquivos no R2 estão em bucket privado (não público)**
  - Como verificar: Configuração do bucket no painel Cloudflare R2 — "Public Bucket" deve estar desativado
  - **Nota:** verificação de configuração externa (painel Cloudflare), não verificável por grep no código — QA manual obrigatório antes de cada deploy que mude o bucket

- [x] **URLs de download são pré-assinadas com validade máxima de 1 hora**
  - Arquivo de referência: `app/services/upload.py:111` — `gerar_url_presignada(..., expiracao_segundos=3600)`
  - Como verificar: `grep -n "ExpiresIn\|generate_presigned_url" app/`
  - **Verificado 2026-07-06**

- [x] **Cadeia de fallback (R2 → Firebase → disco) loga cada etapa adequadamente**
  - Arquivo de referência: `app/services/upload.py:77-227` — `logger.info`/`logger.warning` em cada estágio
  - Como verificar: Simular falha no R2 e verificar se os logs registram o fallback
  - **Verificado 2026-07-06**

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

- [x] **Todo formulário POST/PUT/DELETE inclui token CSRF**
  - Arquivo de referência: `app/templates/base.html` (macro de formulário), Flask-WTF
  - Como verificar: `grep -n "csrf_token\|hidden_tag" app/templates/*.html`
  - **Verificado 2026-07-06** — `CSRFProtect(app)` global em `app/__init__.py`; 26+ ocorrências de `csrf_token` em templates

- [x] **Endpoints de API JSON verificam CSRF (ou usam autenticação stateless adequada)**
  - Arquivo de referência: `app/routes/api_chamados.py`, `api_colaboracao.py`, `api_notificacoes.py`, `api_solicitante.py`
  - Como verificar: Tentar chamar endpoint POST `/api/status` sem token CSRF — deve retornar 400
  - **Verificado 2026-07-06** — protegido globalmente por `CSRFProtect`; frontend envia header `X-CSRFToken`

- [x] **Testes com CSRF desabilitado usam `app.config['WTF_CSRF_ENABLED'] = False`** (nunca em produção)
  - Arquivo de referência: `tests/conftest.py`
  - Como verificar: Verificar que nenhum código de produção desabilita CSRF
  - **Verificado 2026-07-06** — `WTF_CSRF_ENABLED = False` só aparece em `tests/conftest.py`

### 3.2 Configuração de sessão

- [x] **`SESSION_COOKIE_SECURE = True` em produção**
  - Arquivo de referência: `config.py` — `SESSION_COOKIE_SECURE = _to_bool(..., default=(_env == "production"))` → `True` quando `FLASK_ENV=production`
  - Teste: `tests/test_config_production.py::test_cwi21_cookies_secure_default_em_config_producao`, `test_import_config_producao_com_vars_validas_sobe`
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

- [x] **`/login` tem rate limit agressivo (ex: 5 tentativas por minuto por IP)**
  - Arquivo de referência: `app/routes/auth.py:104` — `@limiter.limit("10 per minute")`
  - Como verificar: `grep -n "limiter\|@limiter" app/routes/auth.py`
  - **Verificado 2026-07-06**

- [x] **Endpoints de API têm rate limit proporcional ao uso esperado**
  - Arquivo de referência: `app/routes/api_chamados.py`, `api_notificacoes.py` (limites de 5–30/min conforme endpoint)
  - Como verificar: `grep -n "@limiter\|rate_limit" app/routes/api_*.py`
  - **Verificado 2026-07-06**

- [x] **Redis está configurado como backend de rate limit em produção**
  - Arquivo de referência: `config.py` — `RATELIMIT_STORAGE_URL/URI = REDIS_URL or "memory://"`
  - Como verificar: Sem Redis, o rate limit é por processo e não funciona com múltiplos workers
  - **Verificado 2026-07-06** — atualmente roda com `GUNICORN_WORKERS=1` sem Redis (aceitável, ver `config.py:_validar_config_producao`)

### 4.2 Lockout por brute-force

- [x] **Lockout de IP está ativo após tentativas excessivas**
  - Arquivo de referência: `app/services/login_attempts.py`, `auth.py:134,195`
  - Como verificar: 10+ tentativas falhas com mesmo IP devem resultar em 429
  - **Verificado 2026-07-06**

- [x] **Lockout por e-mail está ativo (independente do IP)**
  - Arquivo de referência: `app/services/login_attempts.py`, `auth.py:148,203`
  - Como verificar: 10+ tentativas com mesmo e-mail de IPs diferentes deve resultar em bloqueio
  - **Verificado 2026-07-06**

- [x] **`get_client_ip()` usa ProxyFix para obter IP real (não forjado via header)**
  - Arquivo de referência: `app/utils.py:87–95`, `app/__init__.py`
  - Como verificar: `grep -n "ProxyFix\|X-Forwarded-For" app/__init__.py app/utils.py`
  - Status atual: **Fechado 2026-06-17** — ProxyFix adicionado em `create_app()`; `get_client_ip()` lê apenas `remote_addr` (F-01 → S1-01)

---

## Seção 5 — Dados e Firestore

### 5.1 Queries seguras

- [x] **Nenhuma query usa `db.collection().get()` sem paginação em coleção grande**
  - Como verificar: `grep -rn "\.get()" app/routes/ app/services/` — verificar se há `.limit()` antes
  - Arquivo de referência: `app/services/chamados_listagem_service.py` (exemplo correto)
  - **Verificado 2026-07-06** — `.get()` restantes são leitura de documento único por ID; varreduras de coleção usam `.limit(...)`

- [x] **Relatórios têm limite de 2000 documentos por operação**
  - Arquivo de referência: `app/services/analytics.py:33` — `MAX_CHAMADOS_ANALYTICS = 2000`
  - Como verificar: `grep -n "limit\|2000" app/services/analytics.py`
  - **Verificado 2026-07-06**

- [x] **Dados sensíveis de usuário não são retornados em endpoints públicos ou de lista**
  - Como verificar: Verificar que endpoints de API não expõem `password_hash`, `encryption_key`, etc.
  - **Verificado 2026-07-06** — ver §9.4 (`to_public_dict()`, `tests/test_routes/test_api_security_responses.py`)

### 5.2 Validação de entrada

- [x] **Dados de formulário são validados antes de serem gravados no Firestore**
  - Arquivo de referência: `app/services/validators.py`
  - Como verificar: Todo `POST` de criação/edição passa por `validar_*` antes de gravar
  - **Verificado 2026-07-06**

- [ ] **IDs de documento não são gerados a partir de input do usuário sem sanitização**
  - Como verificar: `grep -n "document_id\|doc_id" app/services/` — verificar origem do valor
  - **Não verificado a fundo em 2026-07-06** — nenhuma evidência contrária encontrada na amostragem, mas não foi auditado item a item

- [x] **Campos de texto livre não permitem HTML (XSS)**
  - Como verificar: Jinja2 escapa por padrão. Verificar uso de `| safe` em templates: `grep -rn "| safe" app/templates/`
  - **Verificado 2026-07-06** — ocorrências de `| safe` encontradas são só chaves de tradução estáticas (`t('...')`), nunca conteúdo de usuário

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
  - Testes automatizados: `tests/test_security/test_injection_regression.py` (33 testes CWI 3.1: 8×3 search parametrizados + 2 literal + 5 swagger + 2 editar-chamado)
  - Cobertura: `search` em GET `/api/chamados/paginar`; `nova_descricao` em POST `/api/editar-chamado` (`test_editar_chamado_descricao_payload_nao_causa_500`)
  - **Resolvido 2026-06-23 — Onda 3b (CWI 3.1)**

---

## Seção 6 — Secrets e variáveis de ambiente

> **Atenção:** Uma credencial exposta no git é um incidente de segurança. Nunca commite `.env` ou arquivos JSON de credenciais.

### 6.1 Gestão de secrets

- [x] **Nenhuma credencial ou chave hardcoded no código-fonte**
  - Como verificar: `grep -rn "password\|secret\|key\|token" app/ config.py --include="*.py" | grep -v "os.environ\|config\.\|#"` — investigar hits
  - **Verificado 2026-07-06** (amostragem) — segredos vêm de `os.getenv`; nenhuma chave literal encontrada

- [x] **`.env` e arquivos de credenciais Firebase estão no `.gitignore`**
  - Como verificar: `cat .gitignore | grep -E "\.env|serviceAccount|credentials"`
  - **Verificado 2026-07-06** — `.env`, `.env.local`, `.env.*.local`, `credentials.json`, `firebase-debug.log`

- [x] **`SECRET_KEY` tem pelo menos 32 caracteres aleatórios em produção**
  - Como verificar: Verificar nas variáveis de ambiente — não deve ser um valor padrão como `'dev'` ou `'secret'`
  - **Resolvido 2026-07-06** — antes só bloqueava `SECRET_KEY` vazio/igual ao valor de dev, não validava comprimento. `config.py` agora levanta `ValueError` em produção se `len(SECRET_KEY) < 32`. Testes: `tests/test_config_production.py::test_import_config_producao_secret_key_curta_falha`, `test_import_config_producao_secret_key_32_chars_sobe`

- [x] **`ENCRYPTION_KEY` está definido se `ENCRYPT_PII_AT_REST=true`**
  - Arquivo de referência: `config.py:_validar_fernet_key`, `app/services/pii_encryption.py:37-73`
  - Como verificar: Variáveis consistentes entre si nas variáveis de ambiente
  - **Verificado 2026-07-06**

### 6.2 Rotação de secrets

- [ ] **Procedimento de rotação da `ENCRYPTION_KEY` está documentado**
  - Status: Pendente de documentação (não fazia parte do escopo da sessão 2026-07-06 — genuinamente em aberto)

- [x] **Chaves VAPID (Web Push) estão em variáveis de ambiente, não no código**
  - Arquivo de referência: `scripts/gerar_vapid_keys.py`, `config.py:261-262` — `os.getenv("VAPID_PUBLIC_KEY"/"VAPID_PRIVATE_KEY")`
  - Como verificar: `grep -n "VAPID" config.py` — deve referenciar `os.environ.get()`
  - **Verificado 2026-07-06**

---

## Seção 7 — Headers HTTP e cookies

### 7.1 Headers de segurança

- [x] **`Content-Security-Policy` está configurado**
  - Arquivo de referência: `app/__init__.py:487` (after_request)
  - Como verificar: `curl -I https://seu-dominio.com/ | grep -i "content-security"`
  - **Verificado 2026-07-06**

- [x] **`X-Frame-Options: DENY` ou `SAMEORIGIN` está configurado** (proteção clickjacking)
  - Arquivo de referência: `app/__init__.py:463`
  - Como verificar: `curl -I https://seu-dominio.com/ | grep -i "x-frame"`
  - **Verificado 2026-07-06**

- [x] **`X-Content-Type-Options: nosniff` está configurado** (impede MIME sniffing)
  - Arquivo de referência: `app/__init__.py:462`
  - Como verificar: `curl -I https://seu-dominio.com/ | grep -i "x-content-type"`
  - **Verificado 2026-07-06**

- [x] **`Referrer-Policy` está configurado**
  - Valor recomendado: `strict-origin-when-cross-origin`
  - Arquivo de referência: `app/__init__.py:464`
  - **Verificado 2026-07-06**

- [x] **Cabeçalho `Server` não expõe versão do servidor**
  - Como verificar: `curl -I https://seu-dominio.com/ | grep -i "server"` — não deve mostrar versão do Gunicorn/Python
  - **Resolvido 2026-07-06** — Gunicorn expunha `Server: gunicorn` (sem número de versão, mas ainda identificava a tecnologia). `gunicorn.conf.py` (novo, carregado via `start.sh --config gunicorn.conf.py`) sobrescreve `gunicorn.SERVER`/`SERVER_SOFTWARE` para `"webserver"` antes do worker subir. Teste: `tests/test_gunicorn_conf.py`.
  - **Ressalva:** o teste confirma que o monkeypatch funciona em isolamento (`runpy`), mas depende da ordem de import do Gunicorn (o patch precisa rodar antes de `gunicorn.http.wsgi` importar a constante). **Validação real pendente** — rodar em Docker/Linux após deploy: `curl -I https://host/ | grep -i server` deve mostrar `webserver`, não `gunicorn`.

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
  - Solução: `app/routes/api_chamados.py:_obter_health_token_request()` — lê header `X-Health-Token` (primário), cai para `?token=` apenas como fallback deprecado (compat UptimeRobot legado)
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

- [x] **Tentativas de login (sucesso e falha) são logadas com IP e timestamp**
  - Arquivo de referência: `app/routes/auth.py`, `app/services/login_attempts.py`
  - Como verificar: Fazer login com senha errada e verificar logs da aplicação
  - **Verificado 2026-07-06**

- [x] **Acessos a dados sensíveis são logados (download de anexos, visualização de chamados)**
  - Arquivo de referência: `app/routes/api_solicitante.py` — endpoint `/api/download-anexo`
  - **Resolvido 2026-07-06** — antes só logava em falha (`logger.error`); agora também loga em sucesso (`logger.info` com usuário/chamado/chave). Teste: `tests/test_routes/test_download_idor.py::test_download_anexo_sucesso_loga_acesso`

- [x] **Erros internos são logados com traceback mas a resposta ao cliente é genérica**
  - Como verificar: `grep -rn "except.*Exception" app/routes/ app/services/` — verificar se o erro é logado e se a resposta ao cliente não expõe detalhes
  - **Verificado 2026-07-06** (amostragem) — padrão `logger.exception`/`logger.error(..., exc_info=True)` consistente

- [x] **Service Worker (`sw.js`) loga erros de push (não usa catch silencioso)**
  - Arquivo de referência: `app/static/sw.js:10` *(arquivo está em `app/static/`, não em `app/static/js/`)*
  - Como verificar: `grep -n "catch" app/static/sw.js` — verificar se há log no catch
  - **Correção 2026-07-06:** este item estava marcado "ABERTO" no texto, mas a tabela de achados (F-43) já dizia "Resolvido 2026-06-17". Conferido o código atual: `sw.js:10-11` tem `console.error('[sw.js] Erro ao parsear payload push:', e)` — **RESOLVIDO**, o texto da seção é que estava desatualizado.

### 8.2 O que NÃO deve ser logado

- [x] **Senhas nunca aparecem nos logs (mesmo mascaradas)**
  - Como verificar: `grep -rn "password\|senha" app/ --include="*.py" | grep "log\|print"` — nenhum resultado deve mostrar valor real
  - **Verificado 2026-07-06** (amostragem) — nenhum `logger.*` com valor de senha encontrado

- [ ] **Tokens de sessão e chaves de API não aparecem nos logs**
  - Como verificar: Inspeção manual dos logs da aplicação — buscar por `token`, `key`, `secret`
  - **Não verificado a fundo em 2026-07-06** — nenhuma evidência contrária encontrada na amostragem, mas não foi auditado item a item

- [x] **`print()` de debug foi removido do código de produção**
  - Como verificar: `grep -rn "^    print\|^print" app/` — nenhum resultado em código de produção
  - **Correção 2026-07-06:** este item estava marcado "ABERTO" no texto, mas a tabela de achados (F-05) já dizia "Resolvido 2026-06-17 — substituído por logger.debug()". Conferido o código atual: `app/models_historico.py:76-84` usa `logger.info`/`logger.error`, nenhum `print()` no arquivo — **RESOLVIDO**, o texto da seção é que estava desatualizado.

### 8.3 Auditoria de ações admin

- [x] **Criação/edição/desativação de usuários são registradas no histórico**
  - Arquivo de referência: `app/services/historico_usuario_service.py` (novo, coleção Firestore `historico_usuarios`), `app/routes/usuarios.py`
  - **Resolvido 2026-07-06** — este era um gap genuíno (não apenas checkbox desatualizado): `usuarios.py` só usava `logger.info` (log de aplicação, não auditável/consultável), sem persistência equivalente ao `Historico` de chamados. Agora `registrar_historico_usuario()` grava `usuario_alvo_id/nome`, `admin_id/nome`, `acao` (criacao/edicao/desativacao/ativacao/exclusao/anonimizacao) e timestamp em toda ação administrativa sobre contas. Testes: `tests/test_services/test_historico_usuario_service.py`, mais 6 testes de integração em `tests/test_routes/test_usuarios.py` (um por ação).
  - **Bug corrigido de quebra:** ao implementar isso, achamos que `editar_usuario` sempre incluía `nome`/`perfil` em `update_data` mesmo sem mudança real (sem comparar com o valor atual, diferente de `email`/`areas`/`ativo` que já comparavam) — cada edição gravava um "edicao" fantasma no histórico. Corrigido em `app/routes/usuarios.py` (agora compara `nome != usuario.nome` e `perfil != usuario.perfil` antes de incluir).

- [x] **Mudanças de status de chamados têm registro de quem fez e quando**
  - Arquivo de referência: `app/models_historico.py`, `app/services/status_service.py:190-211`
  - **Verificado 2026-07-06**

### 8.4 Respostas de erro genéricas — CWI 3.2

- [x] **Handlers 500 nos módulos `api_*.py` usam mensagem genérica traduzida — não expõem `str(exception)`, Firestore, traceback ou nome de tecnologia**
  - Arquivo de referência: hoje é `_t("internal_error_retry")` (chave em `app/translations.json`, PT/EN/ES), não mais a constante `ERRO_INTERNO_MSG` — foi migrada pro sistema de i18n do projeto em algum momento após o split de `api.py`
  - Handlers corrigidos (Onda 3b): `api_notificacoes_marcar_lida`, `api_notificacoes_ler_todas`, `api_push_subscribe` (hoje em `app/routes/api_notificacoes.py`)
  - Fix específico: `bulk_atualizar_status` (hoje em `app/routes/api_chamados.py`) — `str(e)` substituído por mensagem genérica (evita vazar nome de exceção Firestore)
  - Padrão: erros 400/403 de negócio podem ter mensagens específicas ("Chamado não encontrado" — ok); erros 500 SEMPRE genéricos
  - Fora de escopo: rotas HTML com `flash_t(..., error=str(e))` em `usuarios.py`, `categorias.py`, `dashboard.py` — backlog Onda futura (ver §8.5)
  - Como verificar: `grep -n 'str(e)' app/routes/api_*.py` → sem ocorrências em handlers de erro
  - Testes automatizados: `tests/test_routes/test_api_security_responses.py` (11 testes CWI 3.2)
  - **Resolvido 2026-06-23 — Onda 3b (CWI 3.2)**

### 8.5 Backlog pós-Onda 3b — flash HTML str(e)

- [ ] **Rotas HTML ainda podem expor nome de exceção via `flash_t(..., error=str(e))`**
  - Arquivo de referência: `app/routes/usuarios.py`, `app/routes/categorias.py`, `app/routes/dashboard.py`
  - Como verificar: `grep -rn 'flash_t.*error=str(e)' app/routes/`
  - Impacto: mensagens de erro renderizadas em HTML podem revelar nome de exceção interna (ex.: `FirebaseError: UNAVAILABLE`) para o usuário — não é JSON API, mas pode ser sensível
  - **Backlog Onda futura** — fora de escopo das Ondas 1–3b (afeta apenas rotas de template, não endpoints JSON)

---

## Seção 9 — LGPD e PII

> **Dica:** LGPD exige que dados pessoais sejam tratados com propósito claro, minimização e proteção adequada. Ver `docs/POLITICA_SEGURANCA_LGPD.md` para a política completa.

### 9.1 Minimização de dados

- [ ] **Apenas dados necessários para a funcionalidade são coletados**
  - Como verificar: Revisar campos do formulário de criação de chamado e do cadastro de usuário
  - **Não verificado a fundo em 2026-07-06** — revisão de minimização de dados fica fora do escopo de uma auditoria de código (é uma decisão de produto/negócio)

- [ ] **Dados pessoais não são armazenados em logs ou cache desnecessariamente**
  - Como verificar: Verificar que logs não contêm CPF, telefone ou dados sensíveis além do necessário
  - **Não verificado a fundo em 2026-07-06**

### 9.2 Proteção de dados em repouso

- [ ] **`ENCRYPT_PII_AT_REST` está configurado corretamente em produção**
  - Arquivo de referência: `config.py`, `app/models_usuario.py`, `app/services/pii_encryption.py`
  - Como verificar: Variável de ambiente `ENCRYPT_PII_AT_REST`; verificar se campos são criptografados antes de gravar
  - **Mecanismo pronto e testado, default `false` deliberado.** Correção 2026-07-06: a Seção 20 (matriz CWI) deste documento afirmava "`ENCRYPT_PII_AT_REST=true` ativo no `.env` dev", o que não bate com `.env.example` (default `false`, comentado). Decisão desta sessão: **não mudar o default** — ativar em produção exige `ENCRYPTION_KEY` definida (fail-fast se ausente) e migração prévia dos usuários existentes (`scripts/migrar_pii_criptografia.py`), então "true" por padrão quebraria qualquer ambiente sem essa preparação. `.env.example` e `docs/ENV.md` agora deixam explícito que é preciso ativar manualmente em produção real seguindo os passos documentados. Esta linha específica da Seção 20 foi corrigida (ver lá).

- [x] **Dados de usuário deletado/desativado são tratados conforme política**
  - Arquivo de referência: `docs/POLITICA_SEGURANCA_LGPD.md`, `app/routes/usuarios.py`
  - Como verificar: Fluxo de desativação de usuário em `app/routes/usuarios.py`
  - **Resolvido 2026-07-06** — antes era só soft-delete (`ativo=False`) sem nunca anonimizar, embora a política já prometesse "exclusão/anonimização". Agora existe ação administrativa separada e explícita `POST /admin/usuarios/<id>/anonimizar` (só permitida para contas já desativadas, ação irreversível — sobrescreve nome/e-mail). O soft-delete continua reversível por si só. Ver `docs/POLITICA_SEGURANCA_LGPD.md` §4 para o fluxo completo.

### 9.3 Direito de acesso e portabilidade

- [x] **Usuário pode visualizar seus próprios dados**
  - Como verificar: Existe funcionalidade de "Meus dados" ou equivalente
  - **Resolvido 2026-07-06** — página `GET /meus-dados` (`app/routes/auth.py:meus_dados`), acessível a qualquer usuário autenticado via link no menu do navbar. Mostra nome, e-mail, perfil, áreas, nível de gestão, forma de login e status de MFA — nunca `senha_hash` ou outros campos internos. Testes: `tests/test_routes/test_meus_dados.py`.

- [x] **Existe procedimento documentado para atender solicitação de exclusão (direito ao esquecimento)**
  - Arquivo de referência: `docs/POLITICA_SEGURANCA_LGPD.md`
  - **Verificado 2026-07-06** — documento atualizado com o fluxo real de duas etapas (desativação reversível → anonimização sob demanda)

### 9.4 Auditoria de respostas HTTP e PII em repouso — CWI 2.3

- [x] **Endpoints JSON não expõem `senha_hash`, `encryption_key`, stack trace ou nome de exceção interna**
  - Arquivo de referência: `app/models_usuario.py` — `to_public_dict()` é a serialização segura para HTTP
  - `GET /api/chamado/<id>`: retorna whitelist explícita de campos (id, numero, categoria, tipo, gate, responsavel, descricao, data_abertura, status, sla_info) — sem campos internos
  - `GET /api/supervisores/lista`: usa campos seguros (id, nome, email) — sem senha_hash
  - `Usuario.to_dict()` inclui senha_hash — **uso exclusivo para Firestore**, nunca em respostas HTTP
  - `Usuario.to_public_dict()` é a versão segura para HTTP — sem senha_hash
  - Mascaramento UI: `app/utils.py:mask_email_for_log` + filtro Jinja `mask_email` em `app/__init__.py` (navbar)
  - Testes: `tests/test_routes/test_api_security_responses.py::test_to_public_dict_nao_contem_senha_hash`, `::test_api_chamado_por_id_resposta_sem_campos_internos`, `::test_api_supervisores_lista_nao_expoe_senha_hash`
  - **Resolvido 2026-06-23 — Onda 3b (respostas HTTP)**

- [x] **Campos PII (`nome`, `email`) criptografados em repouso no Firestore com Fernet**
  - Arquivo de referência: `app/services/pii_encryption.py` — `maybe_encrypt`, `maybe_decrypt`, `email_lookup_hash`
  - Integração: `app/models_usuario.py` — `to_dict()`, `from_dict()`, `get_by_email()`, `email_existe()`, `update()`, `get_all()`
  - Formato: `fernet:v1:<token>` nos campos; `email_lookup_hash = sha256(email)` para lookup
  - Default `ENCRYPT_PII_AT_REST=false` — zero breaking change; ativar via `docs/ENV.md`
  - ADR: `docs/adr/001-criptografia-pii-fernet.md`
  - Testes: `tests/test_services/test_pii_encryption.py` (16 testes), `tests/test_services/test_models_usuario.py` (8 testes Onda 4)
  - **Resolvido 2026-06-23 — Onda 4 (CWI 2.3 completo)**

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
  - **Correção 2026-07-06:** este item citava um "VERIFICAR" pendente referenciando F-40, mas a tabela de achados já dizia "Resolvido 2026-06-17 — seção de billing GCP removida, runbook migrado para Docker". Conferido: `docs/INCIDENT_RUNBOOK.md` não tem mais nenhuma menção a billing/GCP — a menção antiga era do modelo de deploy anterior (Cloud Run), já não se aplica ao deploy atual (Docker). Item permanece **como verificação de infraestrutura externa** (painel GCP), não mais como pendência de doc.

### 10.2 Scripts de manutenção

- [x] **Scripts perigosos (`apagar_todos_chamados.py`) não são executados em produção sem revisão explícita**
  - Arquivo de referência: `scripts/apagar_todos_chamados.py:54` — `input("Digite 'apagar' para confirmar: ")`
  - Como verificar: O script exige flag `--confirm` — nunca automatize essa flag
  - **Verificado 2026-07-06**

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

### 10.4 Proteção de ambiente staging/HML — CWI 4.1

**Implementação de código (verificável automaticamente):**

- [x] Middleware `app/__init__.py:_proteger_staging()` — nunca ativo em `ENV=production` ou `TESTING=True`
- [x] Rotas excluídas automaticamente: `/health`, `/login`, `/sw.js` (match exato; `/health/` com trailing slash não é excluído por design)
- [x] Comparação timing-safe: `hmac.compare_digest` para user e senha
- [x] Misconfiguration segura: `STAGING_AUTH_ENABLED=true` sem credenciais → desativado (não bloqueia app)
- [x] ENV normalizado com `.strip().lower()` (robusto a whitespace)
- [x] ADR: `docs/adr/002-protecao-ambientes-staging.md`
- [x] 9 testes em `tests/test_routes/test_staging_auth.py` (desativado em testing/prod; 401 sem cred; cred correta/errada; rotas excluídas; deep health com HEALTH_SECRET; misconfiguration; trailing slash)
- [x] Documentação: `.env.example`, `docs/ENV.md`, `docs/DEPLOYMENT_PLAN.md §Staging`

**Validação manual em ambiente HML real (ops — preencher quando executado):**

- [x] **Camada primária (CWI):** acessar URL HML de computador pessoal (sem VPN) → bloqueado pelo firewall de rede _antes_ de chegar à app
  - _Validado 2026-06-23 — confirmado ops (CWI 4.1 camada rede)_
- [x] **Camada fallback (app):** `STAGING_AUTH_ENABLED=true` configurado; `curl -I http://hml-host/admin` → `401 WWW-Authenticate: Basic realm="DTX Staging"`
  - _Validado 2026-06-23 — simulação local + confirmado ops (CWI 4.1 camada app)_
- [x] Rotas excluídas sem Basic Auth em HML: `curl -I http://hml-host/health` → `200 OK`

**Verificação copy-paste (camada fallback):**

```bash
# Sem credencial → 401
curl -I http://hml-host/dashboard
# Com credencial → 302 login
curl -u hml_user:$STAGING_AUTH_PASSWORD http://hml-host/dashboard
# Rota excluída → 200
curl -I http://hml-host/health
```

- [x] **Implementação app — Onda 5 (2026-06-23)** | **Validação ops HML — 2026-06-23 (CWI 4.1)**

---

## Seção 11 — Frontend e JavaScript

> Esta seção foi adicionada na 2ª rodada de auditoria (2026-06-16) após identificação de achados F-33 a F-48.

### 11.1 Interação com o usuário

- [x] **Nenhum `window.prompt()` usado para captura de dados críticos**
  - Arquivo de referência: `dashboard_otimizacoes.js` — modal `#modal-cancelamento` em `dashboard.html`
  - Como verificar: `grep -rn "window.prompt\|window.confirm\|window.alert" app/static/js/`
  - Status atual: **RESOLVIDO 2026-06-17** — `<dialog>` nativo acessível substitui `window.prompt` (F-33 / S2-05)
  - Alternativa obrigatória: `<dialog>` nativo ou modal HTML acessível

- [x] **Nenhum handler de evento `onmouseover/onmouseout` inline em elementos gerados por JS**
  - Arquivo de referência: `onboarding.js:608-617`
  - Como verificar: `grep -rn "onmouseover\|onmouseout" app/static/js/ app/templates/`
  - Status atual: ✅ **Resolvido** (F-48 — Onda C wave 1 2026-06-18) — handlers removidos; hover via `mouseenter`/`mouseleave` em `bindCardEvents()`
  - **Reverificado 2026-07-06** — sem ocorrências reais (só um comentário mencionando "CSP-safe")

### 11.2 URLs de API não hardcoded

- [x] **URLs de API no JavaScript vêm de `window.DTX_URLS` (injetado pelo template), não hardcoded**
  - Arquivo de referência: `dashboard_otimizacoes.js:29-31`
  - Como verificar: `grep -n "'/api/" app/static/js/` — qualquer hit é uma URL hardcoded
  - **Correção 2026-07-06:** marcado "ABERTO" citando F-36, mas a tabela de achados já dizia "Resolvido 2026-06-17 — URL via DTX_URLS.atualizarStatus". Conferido no código atual: `dashboard_otimizacoes.js` usa `window.DTX_URLS` — **RESOLVIDO**, texto da seção desatualizado.
  - Padrão correto: `window.DTX_URLS?.atualizar_status || '/api/atualizar-status'` (com fallback)

### 11.3 Strings de UI internacionalizadas

- [x] **Strings de UI em JavaScript passam por `window.DTX_MSGS` (injetado pelo template), não hardcoded em PT-BR**
  - Arquivo de referência: `dashboard_otimizacoes.js:11-12` (MSGS), `table-filters.js`
  - Como verificar: `grep -rn "pt-BR\|'Filtrar'\|'Todos'\|'Cancelando'" app/static/js/`
  - **Correção 2026-07-06:** marcado "ABERTO" citando F-34/F-37/F-46, mas a tabela já dizia "Resolvido". Conferido: strings vêm de `window.DTX_MSGS` — **RESOLVIDO**, texto da seção desatualizado.

- [x] **`localeCompare` no JavaScript usa o locale do usuário, não PT-BR fixo**
  - Arquivo de referência: `table-filters.js:13,126` — `const LOCALE = I18N.locale || 'pt-BR'`
  - **Correção 2026-07-06:** marcado "ABERTO" citando F-44, mas a tabela já dizia "Resolvido". Conferido: usa `I18N.locale` com fallback — **RESOLVIDO**, texto da seção desatualizado.

### 11.4 Logs de debug

- [x] **`console.warn/log/error` em arquivos JS de produção são protegidos por `window.DTX_DEBUG`**
  - Arquivo de referência: `table-filters.js:19-20`
  - Como verificar: `grep -n "console\." app/static/js/*.js` — verificar se há proteção
  - **Correção 2026-07-06:** marcado "ABERTO" citando F-38, mas a tabela já dizia "Resolvido". Conferido: `console.*` protegido por `window.DTX_DEBUG` — **RESOLVIDO**, texto da seção desatualizado.
  - Exceção permitida: `console.error` em Service Worker (sw.js) para erros de push — esses devem ser logados sempre

### 11.5 Injeção de CSS

- [x] **CSS injetado dinamicamente por JavaScript verifica duplicatas antes de inserir `<style>`**
  - Arquivo de referência: `dashboard_otimizacoes.js`
  - Como verificar: `grep -n "getElementById.*dtx-dashboard-fade-keyframes" app/static/js/dashboard_otimizacoes.js`
  - Status atual: **Resolvido** 2026-06-19 — guard `getElementById('dtx-dashboard-fade-keyframes')` + `style.id` adicionados (F-41, Onda C wave 2)
  - Padrão aplicado: `if (!document.getElementById('dtx-dashboard-fade-keyframes')) { ... }`

### 11.6 Service Worker

- [x] **Service Worker (`sw.js`) não suprime erros silenciosamente**
  - Arquivo de referência: `app/static/sw.js:10` *(arquivo está em `app/static/`, não em `app/static/js/`)*
  - Como verificar: `grep -n "catch" app/static/sw.js` — verificar se há log no catch
  - **Correção 2026-07-06** — mesmo item de §8.1, ver lá. RESOLVIDO, texto da seção estava desatualizado.

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

- [x] **Scripts destrutivos têm modo dry-run por padrão — requerem `--apply` (ou equivalente) para executar de fato**
  - Arquivo de referência: `scripts/atualizar_firebase.py:16,119-130` (F-71), `scripts/atualizar_setores_from_print.py:23,94-105` (F-72)
  - Como verificar: Executar o script sem argumentos — não deve alterar dados, apenas listar o que seria feito
  - **Correção 2026-07-06:** desmarcado apesar de F-71/F-72 já dizerem "Resolvido" na tabela. Conferido: ambos scripts têm `argparse` com `--apply`, dry-run por padrão — **RESOLVIDO**.

- [x] **Scripts destrutivos exibem prompt de confirmação interativo antes de executar**
  - Padrão mínimo: `input("Confirmar? [s/N]: ")` antes de qualquer operação destrutiva
  - Como verificar: Executar com `--apply` e confirmar que o script pede confirmação antes de prosseguir
  - **Verificado 2026-07-06** — `scripts/apagar_todos_chamados.py:54`

- [x] **`atualizar_firebase.py` está marcado como obsoleto / removido em favor de `migrar_setores_catalogo.py`**
  - Achado: F-71, F-74 — três scripts com funções sobrepostas para seeding
  - Como verificar: Cabeçalho do arquivo deve conter `DEPRECATED` com referência ao substituto
  - **Correção 2026-07-06** — conferido: docstring da linha 2 de `atualizar_firebase.py` diz "OBSOLETO: Este script foi substituído por...". RESOLVIDO.

- [x] **Nenhum script perigoso sem documentação explícita de risco**
  - Como verificar: Todo script em `scripts/` que altera ou apaga dados deve ter docstring ou comentário de cabeçalho descrevendo o risco
  - **Verificado 2026-07-06** (amostragem)

- [x] **`confirmacao-solicitante.md` não está na raiz do projeto (F-78)**
  - Como verificar: `ls *.md` na raiz — não deve existir arquivo `.md` fora de `docs/`
  - **Correção 2026-07-06** — conferido: não existe na raiz, está em `docs/plans/confirmacao-solicitante.md`. RESOLVIDO.

### 13.2 Dependências de scripts

- [x] **`python-dotenv` está listado em `requirements.txt` ou `requirements-dev.txt` se usado por scripts**
  - Achado: F-76 — `dotenv` não listado explicitamente
  - Como verificar: `grep -n "dotenv\|python-dotenv" requirements*.txt`
  - **Correção 2026-07-06** — conferido: `requirements.txt:40` — `python-dotenv==1.0.1`. RESOLVIDO.

- [x] **Scripts com sobreposição de função têm README ou comentário explicando qual usar em cada situação**
  - Achado: F-73, F-74 — `scripts/` sem README; três scripts de seeding sobrepostos
  - Como verificar: Existe `scripts/README.md` ou cada script tem docstring que esclarece seu propósito
  - **Correção 2026-07-06** — conferido: `scripts/README.md` existe. RESOLVIDO.

---

## Seção 14 — Qualidade de testes

> Esta seção foi adicionada na 3ª rodada de auditoria (2026-06-16) após identificação de achados F-50 a F-63.

### 14.1 Correção dos asserts

- [x] **Sem tautologias em asserts — expressão como `A or not A` (always-true) nunca deve aparecer em test_*.py**
  - Achado: F-50 — `tests/test_i18n.py:29`: `assert result != "back" or result == "back"`
  - Como verificar: `grep -rn "or not\|!= .* or .* ==" tests/` — investigar cada hit
  - Impacto: Tautologia dá falsa garantia de qualidade; o teste nunca falha
  - **Correção 2026-07-06** — conferido: `tests/test_i18n.py:29-33` tem `assert result == "Voltar"`, não é mais tautológico. RESOLVIDO.

- [x] **Sem `assert status_code in (X, Y)` onde apenas um código é o correto para o contrato da rota**
  - Achado: F-55, F-56 — asserts permissivos mascaram 404 como sucesso
  - Como verificar: `grep -rn "in (200\|in (200," tests/` — substituir por assert exato
  - Status atual: **Resolvido 2026-06-18** (S3-06, S3-07)

### 14.2 Fixtures e mocks

- [x] **URLs nos testes E2E usam fixture `base_url` ou variável de ambiente, nunca string hardcoded**
  - Achado: F-51 (`test_fluxo_supervisor.py:34,60`), F-52 (`test_fluxo_admin.py:53`) — `/relatorios` em vez de `/admin/relatorios`
  - Achado: F-53 (`test_solicitante.py`) — `BASE_URL` hardcoded
  - Como verificar: `grep -rn "BASE_URL\s*=\|http://localhost" tests/e2e/`
  - **Verificado 2026-07-06** — `tests/e2e/conftest.py` define/injeta fixture `base_url`

- [x] **Mocks inertes removidos; patch no módulo que usa o símbolo**
  - Achado: C-01, C-04, F-54 — `patch("app.routes.api.db")` é inerte quando o serviço importa `db` diretamente
  - Regra: `patch("app.services.X.db")` — quando o serviço importa `db`; `patch("app.routes.api.db")` — válido quando a rota usa `db` diretamente (ex.: `/api/atualizar-status`)
  - Status atual: **Resolvido 2026-06-18** — 3 mocks inertes removidos (S3-05)

- [x] **Sem arquivos de teste legados coexistindo com seus substitutos ativos**
  - Achado: F-53 — `test_solicitante.py` legado coexiste com `test_fluxo_solicitante.py`
  - Como verificar: `ls tests/` — identificar pares de arquivos com nomes sobrepostos; remover ou marcar com `@pytest.mark.skip`
  - **Resolvido 2026-07-06** — antes o arquivo só estava marcado `@pytest.mark.skip` (F-53), mas continuava existindo no repo. Removido de vez (`tests/e2e/test_solicitante.py` deletado) já que `test_fluxo_solicitante.py` cobre o mesmo fluxo com mais qualidade.

- [x] **`_usuario_mock()` (ou equivalente) seta todos os campos do modelo, não apenas o mínimo**
  - Achado: F-62 — mock incompleto pode mascarar KeyError em atributos opcionais
  - Como verificar: Comparar campos de `_usuario_mock()` com `models_usuario.py` — nenhum campo obrigatório deve estar ausente
  - **Resolvido 2026-07-06** — `tests/conftest.py::_usuario_mock` não setava `senha_hash`, `exp_total`, `exp_semanal`, `level`, `conquistas`, `mfa_secret`, `mfa_backup_codes`, `auth_provider`, `password_changed_at` (herdavam auto-mock do MagicMock em vez dos defaults reais). Adicionados com os mesmos defaults de `Usuario.__init__`. Suíte completa (2417 testes) re-rodada sem regressão.

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

- [x] **CSS usa `var(--color-dtx-*)` em vez de valores hexadecimais hardcoded**
  - Achado: F-64 — `table-filters.css` contém `#1e4a8c`, `#E5E7EB` e outros valores hardcoded
  - Como verificar: `grep -n "#[0-9a-fA-F]\{3,6\}" app/static/css/table-filters.css`
  - Referência: `docs/plans/2026-06-12-dtx-light-design-system.md` — fonte de verdade dos tokens
  - **Verificado 2026-07-06** — cores de marca/estruturais migradas para `var(--color-*)`. Restam `#9CA3AF`/`#6B7280`/`#374151` em `table-filters.css` — cinzas de texto neutros sem token dedicado, já documentado como exceção aceita desde F-64, não uma regressão nova.

- [x] **Tokens locais `--dash-*` e `--reports-*` referenciam os tokens globais `--color-dtx-*` em vez de duplicá-los**
  - Achado: F-65 — tokens locais duplicam valores em vez de referenciar a variável global
  - Padrão correto: `--dash-primary: var(--color-dtx-blue-700);` em vez de `--dash-primary: #1e4a8c;`
  - **Verificado 2026-07-06** — `relatorios.css:1-8` já referencia `var(--color-dtx-600)` etc.

- [x] **`tailwind.config.js` e `input.css` permanecem 100% consistentes com o design system documentado**
  - Status atual: **OK** — consistência confirmada na 3ª rodada; monitorar a cada PR que altere tokens
  - **Nota 2026-07-06:** este item já estava com "Status atual: OK" escrito no corpo do documento havia tempo — só o checkbox nunca tinha sido marcado.

### 15.2 Sintaxe CSS

- [x] **Sem sintaxe CSS legada `rgba(r, g, b, a)` com vírgula — usar `rgb()` ou `color-mix()` modernos**
  - Achado: F-66 — `relatorios.css` usa `rgba()` com vírgula (sintaxe de nível 3, depreciada)
  - Como verificar: `grep -n "rgba(" app/static/css/relatorios.css`
  - **Resolvido 2026-07-06** — F-66 dizia "Fechado" na tabela de achados, mas ainda restava um `box-shadow` com dois `rgba()` em `relatorios.css:14`, e outros dois em `table-filters.css:53,176` (não cobertos pelo achado original). Todos migrados para `color-mix(in srgb, black/white X%, transparent)`. Adicionado teste de regressão `test_no_legacy_rgba_comma_syntax_in_layout_css` em `tests/test_regression/test_dtx_light_invariants.py` pra impedir volta.

- [x] **Focus ring usa padrão único definido em `input.css`, não três variantes divergentes**
  - Achado: F-67 — três padrões distintos de focus ring nos arquivos CSS
  - Como verificar: `grep -rn "focus.*ring\|:focus" app/static/css/` — todos devem referenciar a mesma variável
  - **Verificado 2026-07-06 — exceção intencional confirmada, não é bug.** `bento.css` (navbar escura, `.bento-nav-*:focus-visible`) usa `box-shadow: 0 0 0 2px rgba(255,255,255,.4)` em vez do `outline: 2px solid var(--color-dtx-500)` global de `input.css`. Isso é deliberado: `--color-dtx-500` (#284e95) contra `--color-nav-bg` (#13274b) tem contraste ruim (ambos tons escuros de azul) — um anel branco translúcido é a escolha correta de acessibilidade pra esse componente específico sobre fundo escuro. Não alterado.

- [x] **Cor de borda consistente com os tokens do design system (sem divergências entre arquivos)**
  - Achado: F-68 — cor de borda diverge entre arquivos CSS
  - Status atual: **Resolvido** 2026-06-19 — `rgb(234 234 234)` hardcoded substituído por `var(--color-surface-border)` em `dashboard.css` e `relatorios.css`; invariante `test_no_e5e7eb_in_layout_css` e paridade `input.css ↔ tailwind.config.js` adicionadas (Onda C wave 2)

### 15.3 Artefatos de build

- [x] **`app/static/dist/` está no `.gitignore` (bundle SPA gerado automaticamente)**
  - Achado: F-70 — bundle não referenciado pelos templates Flask e não documentado; possivelmente não deveria estar no repositório
  - Como verificar: `cat .gitignore | grep "dist/"` — deve existir entrada
  - **Correção 2026-07-06** — conferido: `.gitignore:19,27` tem `dist/` e `app/static/dist/`. RESOLVIDO.

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

## Seção 20 — Matriz CWI QA manual 11/11

> Status das 11 verificações do artigo [CWI — Testes de Segurança para QAs](https://cwi.com.br/blog/testes-de-seguranca-para-qas/).
> **Automatizado** = cobertura por pytest automatizado. **QA manual** = checklist copy-paste para validação humana em HML/prod.

| ID | Sub-item CWI | Automatizado? | Evidência / arquivo de teste | QA manual |
|---|---|---|---|---|
| **1.1** | Usuário anônimo → 302/401 (login obrigatório) | Sim | `tests/test_routes/test_auth.py`, `test_app_init.py`, `@login_required` em todas as rotas sensíveis | `[x]` 2026-06-23 — `executar_qa_manual_cwi.py` (302 em `/meus-chamados`, `/api/notificacoes`) |
| **1.2** | Permissão por perfil (solicitante, supervisor, admin) | Sim | `tests/test_services/test_permissions.py`, `@requer_solicitante` / `@requer_supervisor_area` / `@requer_admin` em `app/routes/` | `[x]` 2026-06-23 — solicitante em `/admin/categorias` → 302 |
| **1.3** | IDOR — só recursos próprios (URL, body, anexo) | Sim | `tests/test_services/test_permissions.py`, `tests/test_routes/test_download_idor.py`, `test_api.py` | `[x]` 2026-06-23 — `GET /api/chamado/<id_alheio>` → 403 (+ pytest IDOR) |
| **2.1** | HTTPS em produção (redirect HTTP→HTTPS) | Sim | `tests/test_config_production.py::test_cwi21_https_redirect_em_producao`, `tests/test_app_init.py` | `[x]` 2026-06-23 — prod simulada → 301 `https://` |
| **2.2** | Senhas com hash forte (Werkzeug scrypt/pbkdf2) | Doc + teste | `tests/test_services/test_models_usuario.py::test_senha_hash_usa_formato_werkzeug_nao_plaintext`; `CHECKLIST_SEGURANCA.md §1.4` | `[x]` 2026-06-23 — Firestore `usuarios.senha_hash` prefixo `scrypt:32768:8:1$…` (não plaintext) |
| **2.3** | PII minimizado/oculto nas respostas e criptografado em repouso | Sim | `tests/test_routes/test_api_security_responses.py` (respostas HTTP); `tests/test_services/test_pii_encryption.py` + `test_models_usuario.py` (Onda 4 Fernet) | `[x]` 2026-06-23 — resposta API sem `senha_hash`; mecanismo Fernet `fernet:v1:` pronto para `nome`/`email` — **`ENCRYPT_PII_AT_REST=false` é o default real** (`.env.example`), deliberado por segurança de boot; ativar em produção exige `ENCRYPTION_KEY` + migração prévia (ver §9.2) |
| **3.1** | SQL/NoSQL injection | Sim | `tests/test_security/test_injection_regression.py` — 33 testes parametrizados (SQL, NoSQL, editar-chamado) | `[x]` 2026-06-23 — `search=' OR 1=1--` → 200 (+ 33 pytest) |
| **3.2** | Erros genéricos (sem stack/tecnologia nas respostas) | Sim | `tests/test_routes/test_api_security_responses.py` (500 handlers com `ERRO_INTERNO_MSG`); `CHECKLIST_SEGURANCA.md §8.4` | `[x]` 2026-06-23 — 500 → `Erro interno. Tente novamente.` |
| **4.1** | Ambientes de teste não acessíveis publicamente | Sim (app) + ops (rede) | `tests/test_routes/test_staging_auth.py` — 9 testes; VPN/firewall + Basic Auth fallback | `[x]` 2026-06-23 — camada rede (VPN/firewall) + camada app (Basic Auth staging) validadas ops |
| **4.2** | Swagger/documentação não exposta | Sim | `tests/test_security/test_injection_regression.py::test_swagger_routes_retornam_404` (5 paths); `CHECKLIST_SEGURANCA.md §7.3` | `[x]` 2026-06-23 — `/swagger`, `/docs`, `/openapi.json` → 404 |

**Status consolidado:**

| Meta | Status | Dependências pendentes |
|---|---|---|
| **CWI básico (execução QA 2026-06-23)** | ✅ **11/11 sub-itens CWI** | — |
| **CWI 2.3 completo (Fernet/LGPD)** | ✅ **Mecanismo completo** (Onda 4); rollout de 2/2 usuários migrados foi feito em ambiente de teste pontual — `ENCRYPT_PII_AT_REST=false` é o default em `.env.example`/produção real (correção 2026-07-06) | Ativar em produção: `ENCRYPTION_KEY` + `scripts/migrar_pii_criptografia.py --apply` |
| **CWI + baseline DTX** | ✅ Implementado | Onda 2 (`ativo=false`) implementada |

> **Última execução QA manual:** 2026-06-23 — `python scripts/executar_qa_manual_cwi.py` → 15 PASS, 0 FAIL, 2 SKIP. Evidência: `docs/evidencias/QA_MANUAL_CWI_EVIDENCIA.md`

---

*Documento atualizado em 2026-07-06 — DTX Aerospace, Engenharia de Software*
*Versão 3.6 — Auditoria de checkboxes 2026-07-06: ~30 divergências corrigidas entre texto "ABERTO" e tabela de achados "Resolvido" (a tabela estava certa); gaps genuínos fechados nesta sessão — histórico de ações admin em usuários (`historico_usuario_service.py`), página `/meus-dados` (LGPD acesso), anonimização sob demanda de usuário desativado, header `Server` neutralizado (`gunicorn.conf.py`, requer validação real pós-deploy), `SECRET_KEY` com validação de comprimento mínimo, log de acesso bem-sucedido a anexo, `rgba()` legado residual em `relatorios.css`/`table-filters.css`, `_usuario_mock` com todos os campos, teste E2E legado removido. Bug lateral corrigido: `editar_usuario` gravava histórico mesmo sem mudança real de nome/perfil. Focus ring divergente em `bento.css` (navbar escura) confirmado como exceção intencional de contraste, não bug. Genuinamente em aberto: rotação de `ENCRYPTION_KEY` não documentada, portabilidade de dados (export) não implementada, minimização de dados não auditada, tokens/chaves em logs não auditados a fundo.*
*Versão 3.5 — Onda 5 Polish 2026-06-23: matriz CWI 11/11 documentada, §10.4 distingue código vs ops, 9 testes staging_auth, config.py SESSION_COOKIE_SECURE fix, ratelimit fixture fix.*
*Versão 3.4 — Gate Final 2026-06-22: i18n fix pt_BR padrão, CI 85%+gate por módulo, 1435 testes, 52/52 OK, docs sync concluído.*
*Versão 3.3 — Onda 4 Infraestrutura 2026-06-22: database.py 52%→100%, __init__.py 72%→98%, +53 testes, ADR.*
*Versão 3.1 — Sprint 2026-06-17: F-15 resolvido (html.escape em report_service); perfil admin_global documentado; path sw.js corrigido; F-04 ampliado para analytics.py:87*
*Próxima revisão: após conclusão do sprint (2026-07-18)*
