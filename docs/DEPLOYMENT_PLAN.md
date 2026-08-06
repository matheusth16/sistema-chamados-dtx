# Plano de Deployment — Sistema de Chamados DTX

> **Atualizado 2026-08-06.** Produção roda hoje em **servidor físico on-premise da DTX**
> (10.20.0.199:8080, LAN-only), não mais Azure Container Apps (desligado 2026-07-31) — e o banco é
> **PostgreSQL**, não mais Firestore (migrado no Marco 12, 2026-08-04). O fluxo real de deploy é:
> GitHub Actions builda e publica a imagem no GHCR a cada push em `main`; a aplicação da imagem
> nova no servidor é **manual**, via `scripts/watchtower_trigger.sh` rodado no próprio servidor
> (não há deploy automático). Anexos: disco local (Fase 1) com Cloudflare R2 como storage legado.
> E-mail: Microsoft Graph API. A seção "Azure Container Apps" abaixo é histórico preservado — não
> siga esses passos, o recurso está parado.

---

## SUPERADO — Deploy no Azure Container Apps (free tier, histórico)

> **Este caminho não é mais usado.** Preservado como registro do que já foi montado — o Container
> App em si continua existindo no Azure, mas **parado** desde 2026-07-31, não recebe mais deploy.
> Pule pra seção "Deploy real (servidor físico)" abaixo.

Caminho recomendado quando não há servidor próprio disponível. Usa a mesma imagem
Docker já existente no repo (`Dockerfile`), sem precisar de Docker instalado na
máquina de desenvolvimento — o build acontece no GitHub Actions.

**Por que Container Apps:** o plano Consumption tem cota **sempre gratuita mensal**
(180.000 vCPU-segundos, 360.000 GiB-segundos de memória, 2 milhões de requisições/mês,
por assinatura) — não é um trial de 30 dias. Com `min-replicas=0` (escala a zero
quando ocioso), um sistema interno de baixo tráfego tende a ficar dentro da cota o
mês inteiro. HTTPS gerenciado incluso no domínio `*.azurecontainerapps.io`.

**Trade-off:** com `min-replicas=0` a primeira requisição após período ocioso sofre
cold start (alguns segundos para o container subir). Para eliminar isso seria preciso
`min-replicas=1`, o que sai da faixa gratuita (~US$10-15/mês estimado).

**Trade-off #2 (achado F-83, resolvido 2026-07-22):** o mesmo scale-to-zero mata o
APScheduler in-process — jobs agendados só disparam enquanto o container está de pé,
o que raramente dura os 10 minutos contínuos que o job crítico `sla_escalacao`
precisa. Em vez de manter o container sempre ligado (reintroduz o custo de
`min-replicas=1`), esse job específico passou a ser disparado por
`POST /internal/cron/sla-escalacao` (autenticado por `CRON_SECRET`, header
`X-Cron-Token`), chamado a cada 10 min pelo workflow
`.github/workflows/cron-sla-escalacao.yml` — acorda o container só pelo tempo do job
(~4.320 execuções/mês, bem dentro da cota free). Requer `CRON_SECRET` configurado
tanto no GitHub Secrets (o workflow usa pra autenticar) quanto como variável de
ambiente no Container App (a rota usa pra validar).

### B.1 — Build automático da imagem (já configurado)

O workflow `.github/workflows/cd-build-image.yml` builda a imagem a cada push em
`main` e publica em `ghcr.io/matheusth16/sistema-chamados-dtx:latest` (repositório
público — sem necessidade de token/PAT para o Azure puxar a imagem).

### B.2 — Criar os recursos no Azure (via Portal, uma vez)

1. **Criar um Container Apps Environment** (Portal → "Container Apps" → Create →
   aba Environment: criar novo, região `Brazil South` se disponível).
2. **Criar o Container App:**
   - Imagem: `ghcr.io/matheusth16/sistema-chamados-dtx:latest` (registro "Docker Hub or other registries", sem credencial — imagem pública).
   - Ingress: **Enabled**, **HTTPS only**, Traffic: **Accepting traffic from anywhere**, target port `8080`.
   - Scale: **min replicas 0**, **max replicas 1** (subir depois se necessário).
   - Recursos: 0.5 vCPU / 1 GiB costuma bastar para uso interno leve.
3. **Variáveis de ambiente / secrets** (Container App → Settings → Secrets, depois referenciar nas Environment variables) — usar como base o `.env.example`:
   - `FLASK_ENV=production`
   - `SECRET_KEY` (gerar com `openssl rand -hex 32`)
   - `HEALTH_SECRET` (gerar com `python -c "import secrets; print(secrets.token_urlsafe(32))"`)
   - `GOOGLE_CREDENTIALS_JSON` (conteúdo do `credentials.json` em uma linha — usar como **secret**, não env var em texto plano)
   - `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET` (secret), `GRAPH_SENDER_EMAIL`
   - `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` (secret), `R2_BUCKET_NAME`, `R2_PUBLIC_URL` (se usar R2 para anexos)
   - `APP_BASE_URL` — só dá pra preencher **depois** de criar o app (passo B.3), pois depende do FQDN gerado.
4. Criar o Container App. O Azure gera um FQDN do tipo `sistema-chamados.<sufixo>.<região>.azurecontainerapps.io`.

### B.3 — Segunda passada: fechar o APP_BASE_URL

1. Copiar o FQDN gerado.
2. Voltar em Settings → Environment variables e definir `APP_BASE_URL=https://<fqdn>`.
3. Salvar — isso cria uma nova revisão automaticamente.

### B.4 — Validar

```bash
curl -I https://<fqdn>/login        # deve responder 200 (ou 302 se já tiver sessão)
curl https://<fqdn>/health          # {"status": "ok"}
```

Rodar também o checklist funcional do "Passo 3" abaixo (login, dashboard, criar
chamado, upload de anexo, exportação).

### B.5 — Atualizações futuras

Cada push em `main` gera uma nova imagem `:latest` no GHCR automaticamente. Para o
Container App puxar a versão nova:
- Portal → Container App → Revisions and replicas → Create new revision (mesma
  imagem `:latest`, force pull), **ou**
- instalar o Azure CLI localmente e rodar:
  ```bash
  az containerapp update -n sistema-chamados -g <resource-group> \
    --image ghcr.io/matheusth16/sistema-chamados-dtx:latest
  ```

### B.6 — Índices Firestore e demais passos operacionais

Os passos "Passo 4" (anexos), "Passo 5" (índices Firestore), criptografia PII e
job de contadores de uso abaixo se aplicam igualmente a este caminho — são
independentes de onde o container roda.

---

## Deploy real (servidor físico) — o que roda hoje

Produção é `docker-compose.prod.yml` no servidor físico (10.20.0.199), com 3 serviços:
`postgres` (16-alpine, volume LVM dedicado), `web` (imagem do GHCR) e `watchtower`
(fork `nicholas-fedor/watchtower`, API HTTP só em `127.0.0.1:8081`, sem polling).

**Fluxo normal (já configurado, não precisa repetir):**
1. `git push` em `main` → `.github/workflows/cd-build-image.yml` builda, escaneia com Trivy
   (não-bloqueante) e publica em `ghcr.io/matheusth16/sistema-chamados-dtx:latest`.
2. A imagem nova **não é aplicada sozinha**. Alguém precisa rodar no servidor:
   ```bash
   ./scripts/watchtower_trigger.sh
   ```
   Isso chama a API local do Watchtower, que puxa a imagem nova do GHCR e recria só o
   container `web` (Postgres e Watchtower não são afetados).
3. Validar:
   ```bash
   docker compose -f docker-compose.prod.yml ps          # web deve estar "healthy"
   curl http://10.20.0.199:8080/health                    # {"status": "ok"}
   docker logs -f sistema_chamados-web-1                   # conferir ausência de erros
   ```

**Primeiro setup do zero num servidor novo** (raro — só se for provisionar outro servidor):
```bash
git clone <repo> sistema_chamados && cd sistema_chamados
# Preencher .env na raiz (copiar de .env.example, ver docs/ENV.md) — DATABASE_URL,
# SECRET_KEY, HEALTH_SECRET são obrigatórias; credentials.json NÃO é (opcional/legado)
docker compose -f docker-compose.prod.yml up -d
# Depois de subir: alembic upgrade head (dentro do container web ou via exec)
```

Gunicorn: **1 worker, 8 threads (gthread)**, sem Nginx/proxy na frente — a porta do
container é publicada direto (`8080:8080`).

---

## Checklist pré-deploy (obrigatório)

Executar antes de cada `docker compose up`:

### Se upgrading de versão anterior à Onda 3 (fail-fast de configuração)

Execute apenas se fazendo upgrade de uma versão que não tinha estas variáveis:

- [ ] Adicionar `APP_BASE_URL=https://<seu-dominio>` ao `.env` (HTTPS obrigatório)
- [ ] Adicionar `HEALTH_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(32))")` ao `.env`
- [ ] Validar boot: `python -c "import config"` com `FLASK_ENV=production` — deve sair sem erro
- [ ] Reconfigurar monitoramento: usar header `X-Health-Token` em vez de `?token=` na URL:
  ```
  Antes (deprecado): /health?deep=1&token=<valor>
  Agora (primário) : -H "X-Health-Token: <valor>" /health?deep=1
  ```

### Variáveis de ambiente (fail-fast em prod)

- [ ] `FLASK_ENV=production` definida no `.env`
- [ ] `SECRET_KEY` forte e único (gerado com `openssl rand -hex 32`)
- [ ] `APP_BASE_URL` definida, não vazia, começa com `https://` (ex: `https://chamados.dtx.aero`)
- [ ] `HEALTH_SECRET` definida com mínimo 16 chars (gerado com `python -c "import secrets; print(secrets.token_urlsafe(32))"`)
- [ ] Redis: se escalar para múltiplos workers, `REDIS_URL` definida E `GUNICORN_WORKERS=N` correto

> **Verify rápido:** `docker run --rm --env-file .env <image> python -c "import config"` — se sair sem erro, vars OK.

### Qualidade de código

- [ ] `ruff check app/ tests/ --fix && ruff format app/ tests/` — zero erros
- [ ] `bandit -r app/ -ll` — zero HIGH/MEDIUM
- [ ] `pytest --tb=short -q` — 100% passando

### Segurança

- [ ] `.env` **não** está no git (`git status` não lista `.env`)
- [ ] `credentials.json` **não** está no git
- [ ] `SESSION_COOKIE_SECURE=True` no `.env` (ou omitido — padrão True em prod)

---

## Pré-requisitos no servidor

- Docker Engine + plugin `docker compose` instalados
- Arquivo `.env` preenchido (copie de `.env.example` — ver `docs/ENV.md`); `credentials.json`
  é **opcional** (só alimenta a rede de segurança de rollback em `app/database.py`, não é
  necessário pra rodar)
- Porta de publicação livre no host (produção usa `8080`)

---

## Passo 1 — Obter o código no servidor (só no primeiro setup)

```bash
git clone <repo> sistema_chamados
cd sistema_chamados
git checkout main
```

No dia a dia isso não é repetido — a imagem já vem pronta do GHCR (ver "Deploy real" acima).

---

## Passo 2 — Subida do container

```bash
docker compose -f docker-compose.prod.yml up -d
```

A imagem já vem **pré-buildada** do GHCR (`ghcr.io/matheusth16/sistema-chamados-dtx:latest`) —
não builda localmente em produção. O `Dockerfile` multi-stage (`css-builder` Node 20 →
`builder` Python 3.14 → `runtime` Python 3.14-slim, usuário não-root) só roda no GitHub Actions.

O `start.sh` sobe o gunicorn: **1 worker / 8 threads** (`gthread`), bind `0.0.0.0:8080`,
timeout 120s, sem Nginx/proxy na frente. `docker-compose.prod.yml` publica `8080:8080`.

---

## Passo 3 — Validar a subida

```bash
docker compose -f docker-compose.prod.yml ps    # container deve estar "healthy"
curl http://10.20.0.199:8080/health              # deve retornar 200
docker logs --tail=50 sistema_chamados-web-1     # conferir ausência de erros
```

Checklist funcional:
- [ ] Login funciona
- [ ] Dashboard carrega
- [ ] Criar chamado funciona
- [ ] Upload de anexo funciona
- [ ] Exportação (PDF/Excel) funciona
- [ ] Supervisores veem apenas chamados do(s) seu(s) setor(es)

### Ambiente staging/HML (CWI 4.1)

> **Controle primário:** VPN / rede corporativa / firewall. O ambiente HML nunca deve ser acessível da internet pública sem controle de rede. A camada Basic Auth abaixo é **fallback de app**.

**Verificação QA (procedimento manual CWI 4.1):**
- [ ] Acessar URL HML de computador pessoal (fora da rede corporativa / sem VPN): `curl -I http://<hml-host>/dashboard` → deve ser bloqueado pelo firewall de rede **antes de alcançar a app**
- [ ] Se VPN não estiver configurada, ativar fallback Basic Auth: definir `STAGING_AUTH_ENABLED=true`, `STAGING_AUTH_USER` e `STAGING_AUTH_PASSWORD` no `.env` do HML com `FLASK_ENV=staging`
- [ ] Verificar que `/health`, `/login` e `/sw.js` não exigem Basic Auth: `curl -I http://<hml-host>/health` → `200 OK` (sem 401)
- [ ] Verificar que produção NÃO usa Basic Auth: `STAGING_AUTH_ENABLED` não deve estar definida (ou ser `false`) no `.env` de produção

**Configuração Basic Auth (fallback HML — se VPN não disponível):**
```bash
# No .env do ambiente HML (não produção):
FLASK_ENV=staging
STAGING_AUTH_ENABLED=true
STAGING_AUTH_USER=hml_user
STAGING_AUTH_PASSWORD=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
```

**Teste manual:**
```bash
# Sem credencial → 401
curl -I http://hml-host/dashboard
# HTTP/1.1 401 UNAUTHORIZED
# WWW-Authenticate: Basic realm="DTX Staging"

# Com credencial correta → 302 (redirect login da app)
curl -u hml_user:senha http://hml-host/dashboard
# HTTP/1.1 302 FOUND

# Rotas excluídas → 200
curl -I http://hml-host/health
# HTTP/1.1 200 OK
```

Ver: `docs/adr/002-protecao-ambientes-staging.md`, `docs/ENV.md § Proteção de ambiente staging/HML`

---

### Segurança pós-deploy (CWI 2.1)

> Os 3 itens abaixo (redirect HTTPS, cookie Secure, HSTS) **não se aplicam ao servidor físico
> atual** — roda LAN-only, HTTP puro, `REQUIRE_HTTPS=false` por decisão documentada. Não é achado
> novo, é o ambiente real. Só valem de verdade se/quando o servidor ganhar HTTPS.

- [ ] **HTTP redireciona para HTTPS:** `curl -I http://<host>/login` → `HTTP/1.1 301 MOVED PERMANENTLY` + `Location: https://...`
- [ ] **`/health` shallow responde 200 sem expor estado interno:** `curl http://<host>/health` → `{"status": "ok"}` (sem token não expõe deep)
- [ ] **`/health?deep=1` autenticado via header (não query):** `curl -H "X-Health-Token: $HEALTH_SECRET" "https://<host>/health?deep=1"` → `{"status": "ok"}`
- [ ] **Cookies têm flag Secure:** DevTools → Application → Cookies → colunas `Secure` marcadas após login
- [ ] **Boot fail-fast validado:** `docker run --rm --env-file .env <image> python -c "import config; print('ok')"` retorna `ok` sem erro (já feito no pré-deploy)
- [ ] **HSTS presente:** `curl -I https://<host>/login | grep Strict-Transport-Security` → `max-age=31536000`

### Playbook QA pós-deploy — Matriz CWI (11 sub-itens)

> Referência completa em `docs/CHECKLIST_SEGURANCA.md §20`. Use este checklist copy-paste após cada deploy em produção ou HML.
> **Manual ops** = requer acesso de rede externo / inspeção do banco. **HML** = validável no ambiente HML antes de prod.

> **⚠️ CWI 2.1 não se aplica à produção atual como escrito.** O servidor físico roda LAN-only,
> **sem HTTPS** (`REQUIRE_HTTPS=false` no `.env` de produção — decisão documentada, ver
> [[project_migracao_servidor_local]]). Rodar o comando abaixo contra a produção real hoje
> **não** vai retornar `301 https://` — isso é esperado, não é achado de segurança novo. O check
> só se aplica de verdade se/quando o servidor ganhar HTTPS.

| Item | Tipo | Comando / procedimento | Esperado |
|---|---|---|---|
| **CWI 1.1** — Acesso anônimo | Automático | `curl -I https://<host>/meus-chamados` | `302 /login` |
| **CWI 1.2** — Permissão por perfil | Automático | Login como solicitante → `/admin-categorias` | `302` ou `403` |
| **CWI 1.3** — IDOR | Automático | `GET /api/chamado/<id_alheio>` autenticado | `403` |
| **CWI 2.1** — HTTPS | Manual ops | `curl -I http://<prod-host>/login` | `301 https://` (N/A no servidor físico atual — LAN-only sem HTTPS) |
| **CWI 2.2** — Senha hash | Manual ops | Postgres → `SELECT senha_hash FROM usuarios LIMIT 1` | Prefixo `scrypt:` ou `pbkdf2:` |
| **CWI 2.3** — PII | Automático + parcial | `GET /api/chamado/<id>` → sem `senha_hash` na resposta | Sem campos internos |
| **CWI 3.1** — Injection | Automático | `?search=%27+OR+1%3D1--` | Chamados da área; sem 500 |
| **CWI 3.2** — Erros genéricos | Automático | Payload inválido → JSON de erro | Sem traceback / detalhe interno |
| **CWI 4.1** — Staging não público | HML + manual ops | (ver seção abaixo) | Bloqueado fora VPN |
| **CWI 4.2** — Swagger | Automático | `curl -I https://<host>/swagger` | `404` |

**CWI 4.1 detalhado — duas camadas:**

```bash
# Camada 1 (ops — de fora da rede corporativa):
# Acessar http://<hml-host>/dashboard sem VPN → deve ser bloqueado pelo firewall de rede
# (conexão recusada ou timeout — não chega na app)

# Camada 2 (fallback app — configurar STAGING_AUTH_ENABLED=true no HML):
# Sem credencial:
curl -I http://<hml-host>/dashboard
# → 401 WWW-Authenticate: Basic realm="DTX Staging"

# Com credencial correta:
curl -u $STAGING_AUTH_USER:$STAGING_AUTH_PASSWORD http://<hml-host>/dashboard
# → 302 /login (passou pelo Basic Auth)

# Rota excluída (health, login, sw.js) — sem Basic Auth:
curl -I http://<hml-host>/health
# → 200 OK (sem WWW-Authenticate: Basic)

# ATENÇÃO: /health/ (trailing slash) NÃO é excluído → 401.
# Use /health (sem slash) nos monitores de saúde.
```

---

## Passo 4 — Anexos (Cloudflare R2 / Firebase Storage)

O sistema grava anexos novos em **disco local** (Fase 1, volume dedicado no servidor) quando
`ANEXO_STORAGE_BACKEND=local`; sem esse backend explícito, cai em **Cloudflare R2**
(bucket privado, URLs pré-assinadas). O fallback intermediário via Firebase Storage foi
removido do código (confirmado por auditoria de logs: nunca disparava). Configure no `.env`:

- `ANEXO_STORAGE_BACKEND=local` + `ANEXO_LOCAL_DIR` (destino principal em produção)
- `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, `R2_PUBLIC_URL` (storage legado, só leitura de anexos antigos)

Limite de tamanho controlado por `MAX_CONTENT_LENGTH` (~10 MB). Anexos locais precisam de
backup próprio (rsync/cron pro disco secundário) — diferente do R2, que tinha durabilidade
delegada ao provedor.

---

## Passo 5 — Índices PostgreSQL

Índices são definidos via migração Alembic, não deploy separado:

```bash
alembic revision --autogenerate -m "add index X"   # gera a migração
alembic upgrade head                                 # aplica
```

### Acesso direto ao banco

Não existe mais cliente JS/mobile com acesso direto ao Postgres — todo acesso passa pelo
backend Flask/SQLAlchemy por construção (sem exposição de porta externa do Postgres:
`docker-compose.prod.yml` publica `127.0.0.1:5432`, só acessível de dentro do próprio
servidor). Não há regra de segurança "deny-all" separada pra manter (era `firestore.rules`,
já removido do repositório — histórico em `docs/ARQUITETURA.md` ADR-07).

---

## Criptografia PII (Onda 4 — LGPD / CWI 2.3)

> **Padrão:** `ENCRYPT_PII_AT_REST=false`. Zero breaking change enquanto ops não ativar.
> Ativar apenas **após** concluir os passos abaixo na ordem exata.
> ADR: [`docs/adr/001-criptografia-pii-fernet.md`](adr/001-criptografia-pii-fernet.md)

### Checklist de ativação (ordem obrigatória)

- [ ] **1. Gerar chave Fernet** (uma vez por ambiente; guardar em local seguro):
  ```bash
  python scripts/gerar_chave_criptografia.py
  # Saída: ENCRYPTION_KEY=<string base64url 44 chars>
  ```
- [ ] **2. Backup dos dados** — `pg_dump` da tabela `usuarios` antes de qualquer migração:
  ```bash
  docker exec sistema_chamados-postgres-1 pg_dump -U <user> -d <db> -t usuarios > backup_usuarios.sql
  ```
- [ ] **3. Índice em `email_lookup_hash`** — já faz parte do schema desde a migração
  `alembic/versions/552599f9b52c_usuarios.py` (índice único na coluna). Não precisa criar nada
  separado — só confirmar que `alembic upgrade head` já rodou nesse ambiente.
- [ ] **4. Adicionar ao `.env` do servidor** (com `ENCRYPT_PII_AT_REST=false` ainda):
  ```
  ENCRYPTION_KEY=<chave_gerada>
  ENCRYPT_PII_AT_REST=false   # ← mantenha false até após o --apply
  ```
- [ ] **5. Dry-run — confirmar contagem sem alterar dados:**
  ```bash
  ENCRYPTION_KEY=<chave> python scripts/migrations/migrar_pii_criptografia.py
  ```
- [ ] **6. Aplicar migração** (app pode continuar rodando durante a migração; dual-read garante compatibilidade):
  ```bash
  ENCRYPT_PII_AT_REST=true ENCRYPTION_KEY=<chave> python scripts/migrations/migrar_pii_criptografia.py --apply
  ```
- [ ] **7. Smoke test** — tentar login com um usuário migrado. Se falhar, verificar se `ENCRYPTION_KEY` do `--apply` é igual à configurada no servidor.
- [ ] **8. Ativar flag e reiniciar** — somente após 100% das linhas migradas:
  ```bash
  # No .env do servidor:
  ENCRYPT_PII_AT_REST=true
  # Aplicar: ./scripts/watchtower_trigger.sh (recria só o container web)
  ```

### Rollback

Se algo der errado após `--apply` mas antes de ativar `ENCRYPT_PII_AT_REST=true`: a app continua funcionando (dual-read — linhas criptografadas são ignoradas no login enquanto encryption OFF). Para reverter a migração: restaurar o backup da tabela `usuarios` (`psql < backup_usuarios.sql`).

Se o flag já estava `true` e a app não sobe (ENCRYPTION_KEY inválida/ausente): corrigir `ENCRYPTION_KEY` no `.env` e reiniciar.

---

## Passo 6 — Mapeamento setor → área (F-30)

Já feito de uma vez só durante o corte pra Postgres (Marco 12) — não é mais um passo de deploy
recorrente. `utils_areas.setor_para_area()` lê da tabela `config_setor_area` (coluna `mapa`) como
fonte de verdade; sem a linha, a app usa o fallback estático (comportamento legado, sem risco de
indisponibilidade).

> **⚠️ Achado 2026-08-06 — `scripts/migrations/migrar_setor_area.py` está obsoleto/quebrado.**
> Esse script ainda grava em `config/setor_para_area` no **Firestore** (`from app.database import
> db`), mas `app/utils_areas.py` já lê exclusivamente de Postgres (`ConfigSetorAreaRow`) desde o
> Marco 12 — rodar esse script hoje não tem efeito nenhum na app real. **Não precisa rodar este
> passo** em deploys novos: a linha `config_setor_area` já foi semeada de uma vez só durante o
> corte pra Postgres (`scripts/migrate_firestore_to_postgres.py::_load_config_setor_area`). Se
> precisar editar o mapa setor→área hoje, é direto na tabela Postgres — não existe script
> dedicado ainda (candidato a criar um `scripts/migrations/atualizar_setor_area_postgres.py`,
> mas não existe até este achado ser tratado). Script antigo marcado como candidato à remoção.

**Após editar o mapa diretamente no Postgres**: aguardar TTL 5 min ou chamar
`invalidar_cache_setor_area()` por processo para flush imediato.

> Referências: `docs/plans/adr-f30-setor-para-area.md`

---

> **Nota — Job F-31 (contadores_uso):** a query de limpeza (`data < corte`) roda sobre a tabela
> `contadores_uso` no PostgreSQL. Um índice na coluna `data` é definido via migração Alembic — se
> a query ficar lenta em volume alto, adicionar `op.create_index(...)` numa migração nova (ver
> Passo 5 acima), não há mais índice "composto Firestore" a se preocupar.

---

## Atualização / Redeploy

```bash
# No servidor:
./scripts/watchtower_trigger.sh
```

Isso puxa a imagem `:latest` mais recente do GHCR e recria só o container `web`
(`restart: unless-stopped` garante que ele volte sozinho após reinício do host). Não faz
`git pull`/build no servidor — a imagem já vem pronta do GitHub Actions.

---

## Rollback

**Aplicação (voltar pra imagem anterior):** retag manual da imagem anterior no GHCR como
`:latest` (ou `git revert` + push, que gera uma imagem nova revertida) + rodar
`./scripts/watchtower_trigger.sh` de novo.

**Banco (schema):** `alembic downgrade -1` (ou pra uma revisão específica). **Cuidado**: já se
observou em rehearsal que `alembic downgrade base` pode reportar sucesso no log sem de fato
limpar todos os dados — validar com `TRUNCATE` direto ou inspeção manual da tabela, não confiar
só no exit code do Alembic.

---

## Monitoramento

```bash
docker logs -f sistema_chamados-web-1        # logs em tempo real (stdout/stderr do gunicorn)
docker stats --no-stream                      # uso de CPU/memória
curl http://10.20.0.199:8080/health
```

Painéis adicionais no servidor: **Portainer** (`:9443`, gestão de containers) e **Netdata**
(`:19999`, métricas de sistema) — ambos restritos à LAN.

---

## Se o build falhar

| Sintoma | Ação |
|---|---|
| Falha no stage `css-builder` (no GitHub Actions) | Conferir `package.json`/`npm run build:css` localmente |
| Falha no `pip install` (no GitHub Actions) | Conferir `requirements.txt` |
| Container sobe e morre no servidor | `docker logs sistema_chamados-web-1` — geralmente `.env` incompleto (`DATABASE_URL`/`SECRET_KEY`/`HEALTH_SECRET` ausentes) |
| Health check falha | Verificar se a porta 8080 interna responde `/health`; conferir se `sistema_chamados-postgres-1` está `healthy` |
