# Variáveis de ambiente

Referência das variáveis de ambiente usadas pelo Sistema de Chamados DTX.
Copie `.env.example` para `.env` e preencha conforme o ambiente (desenvolvimento ou produção).

---

## Obrigatórias em produção

> **Fail-fast:** a aplicação **não sobe** se qualquer uma das variáveis abaixo estiver ausente ou inválida quando `FLASK_ENV=production`. Mensagem de erro clara no boot. Ver [ADR-003](adr/003-fail-fast-config-producao.md).

| Variável | Descrição | Validação | Exemplo |
|---|---|---|---|
| `FLASK_ENV` | Ambiente da aplicação. | `production` ativa validações abaixo. | `production` |
| `SECRET_KEY` | Chave secreta do Flask (sessões, CSRF, cookies). | Obrigatória, não pode ser o valor padrão de dev. | `openssl rand -hex 32` |
| `APP_BASE_URL` | URL pública da aplicação. Usada em e-mails, push e validação Origin/Referer. | Obrigatória; **deve** começar com `https://`. | `https://chamados.dtx.aero` |
| `HEALTH_SECRET` | Token para proteger `/health?deep=1` (expõe status Firestore/Redis). Canal primário: header `X-Health-Token` (não exposto em logs). Canal deprecado: `?token=` (compat legado). | Obrigatório; mínimo **16 caracteres**. | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |

**Gerar valores:**
```bash
# SECRET_KEY
openssl rand -hex 32

# HEALTH_SECRET
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## Redis — warning vs fail-fast

| Cenário | Comportamento |
|---|---|
| `REDIS_URL` definida | Sem aviso — rate limit e cache compartilhados entre workers |
| `REDIS_URL` ausente + `GUNICORN_WORKERS=1` + `REQUIRE_REDIS=false` | `warnings.warn` — boot prossegue (cenário DTX atual) |
| `REDIS_URL` ausente + `GUNICORN_WORKERS > 1` | `ValueError` — rate limit não funciona entre processos sem Redis |
| `REDIS_URL` ausente + `REQUIRE_REDIS=true` | `ValueError` — opt-in explícito do operador |

| Variável | Descrição | Padrão | Exemplo |
|---|---|---|---|
| `REDIS_URL` | URL do Redis para rate limiting e cache. Se vazia, usa memória local por processo. | `memory://` | `redis://localhost:6379/0` |
| `GUNICORN_WORKERS` | Número de workers Gunicorn. Se > 1, `REDIS_URL` torna-se obrigatória. | `1` | `2` |
| `REQUIRE_REDIS` | Se `true`, força fail-fast se `REDIS_URL` ausente. | `false` | `true` |

---

## Servidor (run.py)

| Variável      | Descrição | Padrão | Exemplo |
|---------------|-----------|--------|---------|
| `PORT`        | Porta HTTP em que o servidor sobe. No container Docker é `8080` (mapeado para `5000` no host pelo compose). | `5000` (run.py) / `8080` (Docker) | `8080` |
| `FLASK_HOST`  | Host de bind. Dev usa `127.0.0.1`; produção usa `0.0.0.0` (aceita conexões externas). | `127.0.0.1` (dev) / `0.0.0.0` (prod) | `0.0.0.0` |
| `ENV`         | Alternativa a `FLASK_ENV` (usa-se se `FLASK_ENV` não estiver definida). | — | `production` |

---

## Segurança e sessão

| Variável               | Descrição | Padrão | Exemplo |
|------------------------|-----------|--------|---------|
| `SESSION_COOKIE_SECURE` | Se o cookie de sessão deve ser enviado apenas em HTTPS. | `True` | `True` (produção) / `False` (dev local HTTP) |

---

## URL base e validação de origem

| Variável        | Descrição | Padrão | Exemplo |
|-----------------|-----------|--------|---------|
| `APP_BASE_URL`  | URL pública da aplicação (ex.: para links em e-mails e notificações). Quando definida, POSTs sensíveis (`/api/atualizar-status`, `/api/bulk-status`, etc.) validam `Origin`/`Referer` contra esta URL. | (vazio) | `https://chamados.empresa.com` |

---

## E-mail (notificações)

O envio de e-mail usa **exclusivamente a Microsoft Graph API** (não há mais SMTP).
Requer um *app registration* no Azure AD com a permissão **`Mail.Send` (Application)**.
Configure as variáveis abaixo (ver `app/services/notifications.py`).

| Variável              | Descrição | Padrão | Exemplo |
|-----------------------|-----------|--------|---------|
| `GRAPH_TENANT_ID`     | Directory (tenant) ID — Azure > App Registrations > Overview. | (vazio) | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `GRAPH_CLIENT_ID`     | Application (client) ID — Azure > App Registrations > Overview. | (vazio) | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `GRAPH_CLIENT_SECRET` | Client secret **Value** (não o Secret ID). **Mantenha secreto.** | (vazio) | `dad8Q~...` |
| `GRAPH_SENDER_EMAIL`  | Caixa remetente que enviará os e-mails. | (vazio) | `dtxls.support@dtx.aero` |

Se as variáveis `GRAPH_*` não estiverem completas, o envio por e-mail fica desabilitado
(o sistema continua funcionando com notificações in-app e Web Push).

| Variável | Descrição | Padrão | Exemplo |
|----------|-----------|--------|---------|
| `NOTIFY_SOLICITANTE_EMAIL` | Ativa e-mail ao solicitante em mudança de status para *Em Atendimento* ou *Concluído*. Requer `GRAPH_*` configurado. | `false` | `true` |
| `NOTIFY_RELAY_EMAIL` | Caixa relay monitorada (ex.: por automações externas) para gatilhos de notificação. | (vazio) | `dtxls.support@dtx.aero` |

**Azure AD:** conceda e dê *admin consent* à permissão `Mail.Send` do tipo *Application*.
O `GRAPH_CLIENT_SECRET` expira — renove-o no Azure (Certificates & secrets) quando
ocorrerem erros `401 Unauthorized`. Retentativas com backoff em `app/services/notify_retry.py`.

---

## Web Push (notificações no navegador)

| Variável            | Descrição | Padrão | Exemplo |
|---------------------|-----------|--------|---------|
| `VAPID_PUBLIC_KEY`  | Chave pública VAPID para Web Push. Gere com: `python scripts/gerar_vapid_keys.py`. | (vazio) | (string longa base64) |
| `VAPID_PRIVATE_KEY` | Chave privada VAPID. **Não exponha em repositórios.** | (vazio) | (string longa base64) |

Se ambas estiverem vazias, a inscrição/Web Push fica desabilitada.

---

## Proteção de ambiente staging/HML — CWI 4.1

> **Camada 2 (fallback app):** o controle primário é VPN / firewall de rede. Basic Auth é fallback para quando o controle de rede não está disponível. Ver [ADR-002](adr/002-protecao-ambientes-staging.md).

| Variável | Descrição | Padrão | Exemplo |
|---|---|---|---|
| `STAGING_AUTH_ENABLED` | `true` ativa Basic Auth quando `ENV != production` e `TESTING != True`. Opt-in explícito — default desativado. | `false` | `true` |
| `STAGING_AUTH_USER` | Usuário para o Basic Auth do ambiente HML. Obrigatório quando `STAGING_AUTH_ENABLED=true`. | (vazio) | `hml_user` |
| `STAGING_AUTH_PASSWORD` | Senha para o Basic Auth. **Gere com** `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Nunca use plaintext fraco. | (vazio) | (string aleatória forte) |

**Regras de ativação:**
- `ENV=production` → Basic Auth **nunca** aplicado (produção protegida por VPN + login da app)
- `TESTING=True` → Basic Auth **nunca** aplicado (pytest não é bloqueado)
- Credenciais ausentes → Basic Auth desativado (misconfiguration silenciosa, segura)

**Rotas sempre excluídas:** `/health`, `/login`, `/sw.js`

**Procedimento QA (CWI 4.1):**
1. Acessar URL do ambiente HML de computador pessoal (sem VPN corporativa)
2. **Esperado:** Bloqueado pelo firewall de rede (camada 1) antes de chegar à app
3. Com `STAGING_AUTH_ENABLED=true` + credenciais: `curl -I http://hml-host/dashboard` → `401 WWW-Authenticate: Basic realm="DTX Staging"`
4. `curl -u hml_user:senha http://hml-host/dashboard` → `302 /login` (passou pelo Basic Auth)

---

## Criptografia de PII em repouso (LGPD — Onda 4 / CWI 2.3)

> **Implementado.** Criptografia Fernet dos campos `nome` e `email` no Firestore. Default `ENCRYPT_PII_AT_REST=false` — zero breaking change até ops ativar.
> ADR: [`docs/adr/001-criptografia-pii-fernet.md`](adr/001-criptografia-pii-fernet.md)

| Variável               | Descrição | Padrão | Exemplo |
|------------------------|-----------|--------|---------|
| `ENCRYPTION_KEY`       | Chave Fernet (base64url, 32 bytes) para criptografia dos campos `nome` e `email` em usuários. Gere com `python scripts/gerar_chave_criptografia.py`. | (vazio) | (string base64url 44 chars) |
| `ENCRYPT_PII_AT_REST`  | Quando `true` e `ENCRYPTION_KEY` válida: criptografa `nome`/`email` ao salvar; descriptografa ao ler; usa `email_lookup_hash` para login. **Em produção com `true`: a app não sobe sem `ENCRYPTION_KEY` válida.** | `false` | `true` |

### Procedimento de ativação

> **Ordem crítica:** migração 100% ANTES de definir `ENCRYPT_PII_AT_REST=true`.
> Usuários sem `email_lookup_hash` não conseguem logar com flag ativo.
> O índice `email_lookup_hash` já está em `firestore.indexes.json` (`fieldOverrides`).

```bash
# 1. Gerar chave
python scripts/gerar_chave_criptografia.py
# Copiar ENCRYPTION_KEY para o .env (manter ENCRYPT_PII_AT_REST=false por ora)

# 2. Criar índice Firestore (OBRIGATÓRIO antes de --apply)
firebase deploy --only firestore:indexes
#    OU Firebase Console > Firestore > Indexes > Single-field: usuarios / email_lookup_hash (ASC)

# 3. Dry-run (sem alterar dados)
ENCRYPTION_KEY=<chave> python scripts/migrar_pii_criptografia.py

# 4. Aplicar migração (app pode continuar rodando durante a migração)
ENCRYPT_PII_AT_REST=true ENCRYPTION_KEY=<chave> python scripts/migrar_pii_criptografia.py --apply

# 5. Smoke test: login com usuário migrado

# 6. Somente após 100% migrado: ativar flag e reiniciar
#    ENCRYPT_PII_AT_REST=true no .env → docker compose up -d --build
```

Ver checklist completo em `docs/DEPLOYMENT_PLAN.md §Criptografia PII`.

### Fail-fast em produção

Com `FLASK_ENV=production` + `ENCRYPT_PII_AT_REST=true`: a aplicação **não sobe** se `ENCRYPTION_KEY` estiver ausente ou inválida (ValueError no boot). Em dev/testing: apenas warning.

---

## Armazenamento de Anexos — Cloudflare R2 (alternativo ao Firebase Storage)

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `R2_ACCOUNT_ID` | ID da conta Cloudflare. | (vazio) |
| `R2_ACCESS_KEY_ID` | Access Key ID do R2. | (vazio) |
| `R2_SECRET_ACCESS_KEY` | Secret Access Key do R2. **Mantenha secreta.** | (vazio) |
| `R2_BUCKET_NAME` | Nome do bucket R2. | (vazio) |
| `R2_PUBLIC_URL` | URL pública do bucket (se acesso público habilitado). | (vazio) |

Quando o R2 não está configurado ou indisponível, o sistema cai no **Firebase Storage** (ver abaixo).

---

## Limites de uso por usuário

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `RELATORIO_MAX_POR_USUARIO_POR_DIA` | Máximo de relatórios gerados por usuário por dia. `0` = sem limite. | `0` |
| `EXPORT_EXCEL_MAX_POR_USUARIO_POR_DIA` | Máximo de exportações Excel por usuário por dia. `0` = sem limite. | `0` |

---

## Logging

| Variável         | Descrição | Padrão | Exemplo |
|------------------|-----------|--------|---------|
| `LOG_LEVEL`      | Nível do log: `DEBUG`, `INFO`, `WARNING`, `ERROR`. Em produção use `INFO` ou `WARNING`. | `INFO` | `INFO` |
| `LOG_MAX_BYTES`  | Tamanho máximo por arquivo de log antes de rotação (bytes). | `2097152` (2 MB) | `5242880` |
| `LOG_BACKUP_COUNT` | Quantidade de arquivos de log rotacionados mantidos. | `5` | `10` |

Logs são gravados em `logs/sistema_chamados.log` (formato JSON com rotação). Em produção, e-mails em logs são mascarados (ex.: `u***@dominio.com`).

---

## SLA / Tempo útil DTX

> **Implementado na Fase 1.** Motor de tempo útil em `app/services/business_time.py`.
> ADR: [`docs/adr/004-escalonamento-sla-gerencial.md`](adr/004-escalonamento-sla-gerencial.md)

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `SLA_HORARIO_INICIO` | Início do expediente DTX (seg–sex). | `07:00` |
| `SLA_HORARIO_FIM` | Teto do expediente (exclusivo — `>= 16:30` está fora). Evita escaladas após saída da produção. | `16:30` |
| `SLA_ALMOCO_INICIO` | Início da pausa do almoço (relógio pausa; notificações não são enviadas neste intervalo). | `11:30` |
| `SLA_ALMOCO_FIM` | Fim da pausa do almoço (13:00 volta a contar como útil). | `13:00` |
| `SLA_DIAS_RESOLUCAO_PROJETOS` | Prazo de resolução em dias úteis para chamados da categoria **Projetos**. | `2` |
| `SLA_DIAS_RESOLUCAO_PADRAO` | Prazo de resolução em dias úteis para todas as demais categorias. | `3` |
| `SLA_INCLUI_FIM_DE_SEMANA` | Incluir sábado e domingo no cálculo de tempo útil. **Na v1 esta flag existe em `config.py` mas não está conectada à lógica** — sáb/dom são sempre excluídos. Reservada para v2. | `false` |
| `SLA_TIMEZONE` | Timezone IANA usado em todos os cálculos de SLA. Deve corresponder ao timezone do APScheduler configurado em `app/__init__.py`. | `America/Sao_Paulo` |

**Constantes fixas em `config.py` (não configuráveis via env):**

- `SLA_ESCALADA_A_HORAS_UTEIS = [1, 2, 3, 4]` — degraus da Escada A (resposta gerencial) em horas úteis.
- `SLA_ESCALADA_B_HORAS_UTEIS = [0, 4, 8, 12]` — degraus da Escada B (resolução pós-estouro) em horas úteis após o deadline.

---

## Perfil Gestor — E-mails gerenciais

Não há variável de ambiente para os e-mails de escalonamento gerencial. O
destinatário de cada nível (`gestor_setor`, `gerente_producao`, `assistente_gm`,
`gm`) é resolvido em tempo real a partir do cadastro real de usuários — campo
Nível de Gestão em `/admin/usuarios` — via `app/services/gestor_escalonamento_service.py`.
Cadastrar ou desativar um usuário nesse painel já reflete no próximo job, sem
precisar reiniciar a aplicação ou alterar configuração.

> **Escadas de escalonamento:** o job `sla_escalacao` roda a cada 10 min e chama três funções em sequência:
> - **Escada A** (`processar_escada_a`) — notifica por atraso de *resposta* (+1h/+2h/+3h/+4h úteis após abertura sem atendimento).
> - **Escada B** (`processar_escada_b`) — notifica por estouro do prazo de *resolução* (+0h/+4h/+8h/+12h úteis após deadline de 2 ou 3 dias úteis).
> - **Avisos preventivos** (`processar_avisos_resolucao`) — alerta o responsável ao atingir 50%/80% do prazo de resolução.
>
> `gestor_setor` é resolvido por área (`construir_mapa_gestor_setor`); os demais níveis são company-wide (`construir_mapa_niveis_superiores`). Nível sem usuário ativo cadastrado → incrementa sem enviar e-mail, com `WARNING` no log. O broadcast imediato de abertura de AOG (`notificar_abertura_aog_todos_gestores`) usa a mesma fonte.

---

## Auditoria de dependências

Execute periodicamente para verificar vulnerabilidades conhecidas nas dependências Python:

```bash
pip audit
```

Recomenda-se integrar `pip audit` no pipeline de CI e corrigir vulnerabilidades reportadas. Ver também `requirements.txt` na raiz do projeto.

---

## Firebase

O Firebase é inicializado em `app/database.py`:

- **Produção (Azure Container Apps):** variável de ambiente `GOOGLE_CREDENTIALS_JSON` (conteúdo do JSON da conta de serviço), lida primeiro por `app/database.py`.
- **Desenvolvimento local (docker-compose):** arquivo `credentials.json` na raiz do projeto, montado no container via volume — usado como segunda opção se `GOOGLE_CREDENTIALS_JSON` não estiver definida.
- **Application Default Credentials (ADC):** suportado como último fallback se nem a env var nem `credentials.json` estiverem presentes e o ambiente fornecer credenciais padrão.

| Variável | Descrição | Obrigatório em produção |
|----------|-----------|-------------------------|
| `FIREBASE_STORAGE_BUCKET` | Nome **exato** do bucket do Firebase Storage (Firebase Console > Storage: use o valor do bucket, ex. `projeto.firebasestorage.app` ou `projeto.appspot.com`). Usado para anexos quando o R2 não está configurado. Sem isso, em produção os uploads via Firebase falham. | **Recomendado** (fallback de anexos) |

---

## Resumo rápido (.env de desenvolvimento)

```env
# Mínimo para rodar em desenvolvimento
FLASK_ENV=development
SECRET_KEY=dev-secret-key-change-in-production

# Opcional: Redis (se quiser rate limit compartilhado)
# REDIS_URL=redis://localhost:6379/0
```

## Resumo rápido (.env de produção)

```env
FLASK_ENV=production
SECRET_KEY=<valor de openssl rand -hex 32>
APP_BASE_URL=https://seu-dominio.com

# Anexos: Cloudflare R2 (preferencial) com fallback Firebase Storage
# R2_ACCOUNT_ID=...
# R2_ACCESS_KEY_ID=...
# R2_SECRET_ACCESS_KEY=...
# R2_BUCKET_NAME=...
# R2_PUBLIC_URL=...
# FIREBASE_STORAGE_BUCKET=seu-projeto.firebasestorage.app

# Recomendado se escalar para múltiplos workers/containers
# REDIS_URL=redis://:senha@redis-host:6379/0

# E-mail via Microsoft Graph API (opcional, mas recomendado)
# GRAPH_TENANT_ID=...
# GRAPH_CLIENT_ID=...
# GRAPH_CLIENT_SECRET=...
# GRAPH_SENDER_EMAIL=dtxls.support@dtx.aero

# Opcionais: Web Push, logging
# VAPID_PUBLIC_KEY=...
# VAPID_PRIVATE_KEY=...
# LOG_LEVEL=INFO
```
