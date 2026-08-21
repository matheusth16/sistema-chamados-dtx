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
| `HEALTH_SECRET` | Token para proteger `/health?deep=1` (expõe status Postgres/Redis). Canal primário: header `X-Health-Token` (não exposto em logs). Canal deprecado: `?token=` (compat legado). | Obrigatório; mínimo **16 caracteres**. | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |

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

## LibreTranslate (tradução automática de conteúdo dinâmico dos chamados)

Self-hosted via Docker (serviço `libretranslate` em `docker-compose.yml`/`docker-compose.prod.yml`)
— traduz descrição, histórico e conversa pro idioma selecionado por quem está
vendo, quando o idioma detectado do texto é diferente. Ver
`app/services/traducao_conteudo_service.py`.

| Variável                          | Descrição | Padrão | Exemplo |
|------------------------------------|-----------|--------|---------|
| `LIBRETRANSLATE_ENABLED`           | Liga/desliga a tradução automática. | `false` | `true` |
| `LIBRETRANSLATE_URL`               | URL base do serviço LibreTranslate. Em produção/dev via compose, é o nome interno do serviço. | (vazio) | `http://libretranslate:5000` |
| `LIBRETRANSLATE_TIMEOUT_SECONDS`   | Timeout (segundos) de CADA chamada HTTP individual (uma por texto). | `15` | `20` |
| `LIBRETRANSLATE_BATCH_BUDGET_SECONDS` | Orçamento de tempo TOTAL pra tentativas de tradução de um mesmo lote — ao esgotar, para de chamar o serviço e trata o resto como não traduzido nesta passada (fail-open parcial). | `20` | `30` |

Com `LIBRETRANSLATE_ENABLED=false` (ou `LIBRETRANSLATE_URL` vazio), o sistema
sempre mostra o texto original — nunca quebra a página. Suba o container
antes de habilitar: `docker compose -f docker-compose.prod.yml up -d libretranslate`.

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

> **Implementado.** Criptografia Fernet dos campos `nome` e `email` no PostgreSQL. Default `ENCRYPT_PII_AT_REST=false` — zero breaking change até ops ativar.
> ADR: [`docs/adr/001-criptografia-pii-fernet.md`](adr/001-criptografia-pii-fernet.md)

| Variável               | Descrição | Padrão | Exemplo |
|------------------------|-----------|--------|---------|
| `ENCRYPTION_KEY`       | Chave Fernet (base64url, 32 bytes) para criptografia dos campos `nome` e `email` em usuários. Gere com `python scripts/gerar_chave_criptografia.py`. | (vazio) | (string base64url 44 chars) |
| `ENCRYPT_PII_AT_REST`  | Quando `true` e `ENCRYPTION_KEY` válida: criptografa `nome`/`email` ao salvar; descriptografa ao ler; usa `email_lookup_hash` para login. **Em produção com `true`: a app não sobe sem `ENCRYPTION_KEY` válida.** | `false` | `true` |

### Procedimento de ativação

> **Ordem crítica:** migração 100% ANTES de definir `ENCRYPT_PII_AT_REST=true`.
> Usuários sem `email_lookup_hash` não conseguem logar com flag ativo.
> O índice único em `email_lookup_hash` já faz parte do schema Postgres desde a migração
> `alembic/versions/552599f9b52c_usuarios.py` — não precisa criar nada separado.

```bash
# 1. Gerar chave
python scripts/gerar_chave_criptografia.py
# Copiar ENCRYPTION_KEY para o .env (manter ENCRYPT_PII_AT_REST=false por ora)

# 2. Confirmar que a migração Alembic já rodou (índice email_lookup_hash já existe)
alembic current

# 3. Dry-run (sem alterar dados)
ENCRYPTION_KEY=<chave> python scripts/migrations/migrar_pii_criptografia.py

# 4. Aplicar migração (app pode continuar rodando durante a migração)
ENCRYPT_PII_AT_REST=true ENCRYPTION_KEY=<chave> python scripts/migrations/migrar_pii_criptografia.py --apply

# 5. Smoke test: login com usuário migrado

# 6. Somente após 100% migrado: ativar flag e aplicar
#    ENCRYPT_PII_AT_REST=true no .env → ./scripts/watchtower_trigger.sh
```

Ver checklist completo em `docs/DEPLOYMENT_PLAN.md §Criptografia PII`.

### Fail-fast em produção

Com `FLASK_ENV=production` + `ENCRYPT_PII_AT_REST=true`: a aplicação **não sobe** se `ENCRYPTION_KEY` estiver ausente ou inválida (ValueError no boot). Em dev/testing: apenas warning.

---

## Armazenamento de Anexos — Cloudflare R2 (storage legado, sem escrita nova)

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `R2_ACCOUNT_ID` | ID da conta Cloudflare. | (vazio) |
| `R2_ACCESS_KEY_ID` | Access Key ID do R2. | (vazio) |
| `R2_SECRET_ACCESS_KEY` | Secret Access Key do R2. **Mantenha secreta.** | (vazio) |
| `R2_BUCKET_NAME` | Nome do bucket R2. | (vazio) |
| `R2_PUBLIC_URL` | URL pública do bucket (se acesso público habilitado). | (vazio) |

O fallback intermediário via Firebase Storage foi **removido do código** (auditoria 2026-08-05,
confirmado por logs que nunca disparava). Cascata real hoje: disco local (Fase 1, se
`ANEXO_STORAGE_BACKEND=local`) → R2 → disco local (só em dev, fallback final). `FIREBASE_STORAGE_BUCKET`
não é mais lido por nada em `app/`.

---

## Armazenamento de Anexos — Disco Local (Fase 1 on-premise)

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `ANEXO_STORAGE_BACKEND` | `local` faz uploads **novos** irem para disco local primeiro (R2 vira fallback só se o disco falhar). Qualquer outro valor pula direto pro R2 (sem Firebase Storage — removido do código). | `r2` |
| `ANEXO_LOCAL_DIR` | Diretório de disco onde anexos novos são salvos quando o backend `local` está ativo. Em produção deve ser um bind-mount fora do container (ver `docker-compose.prod.yml`, HD dedicado `/var/anexos_chamados`). | mesmo caminho de `UPLOAD_FOLDER` |

Anexos já existentes no R2/Firebase **não são migrados** — continuam lidos normalmente pelos seus
prefixos originais (Opção A do plano de migração, ver `~/.claude/plans/unified-mixing-torvalds.md`).

No startup, `_verificar_anexo_local_dir` (`app/__init__.py`) falha rápido (RuntimeError) se
`ANEXO_LOCAL_DIR` não puder ser criado ou não tiver permissão de escrita — mesmo comportamento de
fail-fast já usado para `UPLOAD_FOLDER`.

### Backup do diretório de anexos

`scripts/backup_anexos.sh` faz `rsync` do `ANEXO_LOCAL_DIR` para um segundo disco (HD `/srv`,
~466GB) mais snapshots diários via hardlink com retenção configurável. Roda no **host físico**, via
cron, fora do container:

```
0 2 * * * /caminho/para/sistema_chamados/scripts/backup_anexos.sh
```

Variáveis opcionais do script (default entre parênteses): `ANEXO_LOCAL_DIR` (origem),
`ANEXO_BACKUP_DIR` (`/srv/backup_anexos_chamados`), `ANEXO_BACKUP_LOG`
(`/var/log/backup_anexos_chamados.log`), `ANEXO_BACKUP_RETENCAO_DIAS` (`7`).

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

## Firebase (LEGADO — rede de segurança de rollback, não o banco ativo)

**Superado desde o Marco 12 (2026-08-04).** O Firestore foi desligado em produção — PostgreSQL é
o banco ativo (ver seção abaixo). `app/database.py` (inicializador Firebase) continua no
repositório só como rede de segurança de rollback, **sem nenhum import ativo em `app/`** hoje.
Prazo pra remover de vez: ~2026-09-03 (30 dias do corte).

- `GOOGLE_CREDENTIALS_JSON`/`credentials.json`: opcionais, só alimentam esse inicializador legado.
- `FIREBASE_STORAGE_BUCKET`: **não é mais lido por nada em `app/`** — o fallback de upload via
  Firebase Storage foi removido do código (auditoria 2026-08-05). Pode ser omitido.
- Azure Container Apps (mencionado em versões antigas deste doc como "produção"): desativado
  desde 2026-07-31 — produção é o servidor físico on-premise hoje.

---

## PostgreSQL — banco ativo

Migração do Firestore concluída no Marco 12 (2026-08-04, corte único). Camada de acesso em
`app/db/` (SQLAlchemy 2.0 + Alembic), inicializada em `create_app()` via `app.db.init_engine(app)`.

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `DATABASE_URL` | String de conexão Postgres (`postgresql://user:senha@host:5432/db`). **Obrigatória** — a app não sobe sem isso (`init_engine()` fica no-op e todo acesso a dado falha). | (obrigatória, sem default) |
| `TEST_DATABASE_URL` | String de conexão do Postgres **de teste** (real, não mock) — usada pela suíte pytest e por `alembic upgrade head`/`downgrade base`. No CI, setada automaticamente pelo serviço `postgres:16-alpine` (`.github/workflows/ci.yml`). Em dev local, aponte pra um banco dedicado do projeto — não reutilize um banco de outro projeto na mesma instância. | (vazio) |

Comandos úteis (rodar na raiz do projeto, com `TEST_DATABASE_URL` no ambiente):
```bash
alembic upgrade head      # aplica todas as migrations
alembic downgrade base    # reverte tudo (schema vazio)
alembic revision --autogenerate -m "descrição"   # gera migration a partir dos models em app/db/models/
```

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
DATABASE_URL=postgresql://user:senha@postgres:5432/sistema_chamados
HEALTH_SECRET=<valor de python -c "import secrets; print(secrets.token_urlsafe(32))">
APP_BASE_URL=http://10.20.0.199:8080
# ^ HTTP, não HTTPS — servidor físico LAN-only sem certificado. Se algum dia ganhar
# domínio/HTTPS, trocar pra https:// e não esquecer REQUIRE_HTTPS (default True).

# Anexos: disco local (Fase 1, destino principal) com R2 como storage legado
ANEXO_STORAGE_BACKEND=local
# ANEXO_LOCAL_DIR=/var/anexos_chamados
# R2_ACCOUNT_ID=...
# R2_ACCESS_KEY_ID=...
# R2_SECRET_ACCESS_KEY=...
# R2_BUCKET_NAME=...
# R2_PUBLIC_URL=...

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
