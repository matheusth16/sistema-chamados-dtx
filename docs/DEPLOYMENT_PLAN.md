# Plano de Deployment — Sistema de Chamados DTX

> **Dois caminhos documentados:** (A) container Docker em servidor próprio/on-premise
> (seção "Passo 1" em diante) ou (B) **Azure Container Apps** — hospedagem gerenciada
> gratuita (seção abaixo), sem precisar de servidor nem Docker instalado localmente.
> Banco: Firestore. Anexos: Cloudflare R2 (fallback Firebase Storage). E-mail: Microsoft Graph API.

---

## Deploy no Azure Container Apps (free tier)

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
- Arquivo `credentials.json` (conta de serviço Firebase) na raiz do projeto
- Arquivo `.env` preenchido (copie de `.env.example` — ver `docs/ENV.md`)
- Porta de publicação livre no host (por padrão `5000`)

---

## Passo 1 — Obter o código no servidor

```bash
git clone <repo> sistema_chamados
cd sistema_chamados
git checkout main   # ou a tag/release desejada
```

Coloque `credentials.json` e `.env` na raiz (não são versionados).

---

## Passo 2 — Build e subida do container

```bash
docker compose up -d --build
```

O `Dockerfile` é multi-stage:
1. **css-builder** (Node 20) — gera o Tailwind purgado (`tailwind.min.css`)
2. **builder** (Python 3.14) — instala dependências
3. **runtime** (Python 3.14-slim) — imagem final, usuário não-root, gunicorn

O `start.sh` sobe o gunicorn: **1 worker / 8 threads** (`gthread`), bind `0.0.0.0:8080`,
timeout 120s. O compose mapeia `5000:8080` por padrão.

---

## Passo 3 — Validar a subida

```bash
docker compose ps                       # container deve estar "healthy"
curl http://localhost:5000/health       # deve retornar 200
docker compose logs --tail=50 web       # conferir ausência de erros
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

- [ ] **HTTP redireciona para HTTPS:** `curl -I http://<host>/login` → `HTTP/1.1 301 MOVED PERMANENTLY` + `Location: https://...`
- [ ] **`/health` shallow responde 200 sem expor estado interno:** `curl http://<host>/health` → `{"status": "ok"}` (sem token não expõe deep)
- [ ] **`/health?deep=1` autenticado via header (não query):** `curl -H "X-Health-Token: $HEALTH_SECRET" "https://<host>/health?deep=1"` → `{"status": "ok"}`
- [ ] **Cookies têm flag Secure:** DevTools → Application → Cookies → colunas `Secure` marcadas após login
- [ ] **Boot fail-fast validado:** `docker run --rm --env-file .env <image> python -c "import config; print('ok')"` retorna `ok` sem erro (já feito no pré-deploy)
- [ ] **HSTS presente:** `curl -I https://<host>/login | grep Strict-Transport-Security` → `max-age=31536000`

### Playbook QA pós-deploy — Matriz CWI (11 sub-itens)

> Referência completa em `docs/CHECKLIST_SEGURANCA.md §20`. Use este checklist copy-paste após cada deploy em produção ou HML.
> **Manual ops** = requer acesso de rede externo / inspeção de Firestore. **HML** = validável no ambiente HML antes de prod.

| Item | Tipo | Comando / procedimento | Esperado |
|---|---|---|---|
| **CWI 1.1** — Acesso anônimo | Automático | `curl -I https://<host>/meus-chamados` | `302 /login` |
| **CWI 1.2** — Permissão por perfil | Automático | Login como solicitante → `/admin-categorias` | `302` ou `403` |
| **CWI 1.3** — IDOR | Automático | `GET /api/chamado/<id_alheio>` autenticado | `403` |
| **CWI 2.1** — HTTPS | Manual ops | `curl -I http://<prod-host>/login` | `301 https://` |
| **CWI 2.2** — Senha hash | Manual ops | Firestore → `usuarios` → `senha_hash` | Prefixo `scrypt:` ou `pbkdf2:` |
| **CWI 2.3** — PII | Automático + parcial | `GET /api/chamado/<id>` → sem `senha_hash` na resposta | Sem campos internos |
| **CWI 3.1** — Injection | Automático | `?search=%27+OR+1%3D1--` | Chamados da área; sem 500 |
| **CWI 3.2** — Erros genéricos | Automático | Payload inválido → JSON de erro | Sem traceback / "Firestore" |
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

O sistema grava anexos no **Cloudflare R2** (bucket privado, URLs pré-assinadas) e,
em caso de indisponibilidade, cai no **Firebase Storage**. Configure no `.env`:

- `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, `R2_PUBLIC_URL`
- `FIREBASE_STORAGE_BUCKET` (fallback)

Limite de tamanho controlado por `MAX_CONTENT_LENGTH` (~10 MB). Sem credenciais
válidas, uploads em produção falham — valide com um anexo de teste após o deploy.

---

## Passo 5 — Índices Firestore

Se alterar `firestore.indexes.json`, aplique os índices compostos e single-field:

```bash
firebase deploy --only firestore:indexes
```

(Requer Firebase CLI autenticado no projeto Firebase usado como banco.)

### Regras de segurança (Firestore + Storage)

`firestore.rules` e `storage.rules` só valem no projeto Firebase real depois de
deployadas — editar o arquivo local não muda nada em produção até rodar:

```bash
firebase deploy --only firestore:rules,storage
```

Ambas as regras são deny-all por padrão (`allow read, write: if false`) — o
acesso real é sempre via Firebase Admin SDK no backend, que ignora essas
regras. Elas existem só como defesa em profundidade contra acesso direto
indevido (cliente/browser) caso algo seja mal configurado no futuro.

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
- [ ] **2. Backup dos dados** — exportar coleção `usuarios` no Firebase Console antes de qualquer migração.
- [ ] **3. Criar índice Firestore** — obrigatório antes do `--apply`:
  ```bash
  firebase deploy --only firestore:indexes
  # Cria o fieldOverride: usuarios / email_lookup_hash (ASC)
  # Ou manualmente: Firebase Console > Firestore > Indexes > Single field
  ```
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
- [ ] **8. Ativar flag e reiniciar** — somente após 100% dos docs migrados:
  ```bash
  # No .env do servidor:
  ENCRYPT_PII_AT_REST=true
  # Reiniciar: docker compose up -d --build
  ```

### Rollback

Se algo der errado após `--apply` mas antes de ativar `ENCRYPT_PII_AT_REST=true`: a app continua funcionando (dual-read — docs criptografados são ignorados no login enquanto encryption OFF). Para reverter a migração: restaurar backup da coleção `usuarios`.

Se o flag já estava `true` e a app não sobe (ENCRYPTION_KEY inválida/ausente): corrigir `ENCRYPTION_KEY` no `.env` e reiniciar.

---

## Passo 6 — Mapeamento setor → área (F-30)

Necessário apenas no **primeiro deploy após a Onda C wave 3**. Semeia o documento
`config/setor_para_area` no Firestore para que `utils_areas.setor_para_area()` use o
Firestore como fonte de verdade. Sem o documento, a app usa o fallback estático (comportamento legado) — sem risco de indisponibilidade.

```bash
# Dry-run (seguro — só exibe o payload, não grava nada)
python scripts/migrations/migrar_setor_area.py

# Gravar config/setor_para_area no Firestore (executar uma vez após o deploy)
python scripts/migrations/migrar_setor_area.py --apply
```

**Ordem recomendada:** pode rodar antes ou depois do `docker compose up`; o fallback estático cobre os primeiros requests se o documento ainda não existir.

**Após editar o mapa diretamente no Firestore** (via console ou script): aguardar TTL 5 min ou chamar `invalidar_cache_setor_area()` por processo para flush imediato.

> Referências: `docs/plans/adr-f30-setor-para-area.md`, `scripts/README.md → migrar_setor_area.py`

---

> **Nota — Job F-31 (contadores_uso):** na primeira execução do job de domingo 02h00 BRT, a
> query `where("data", "<", corte_str)` pode exigir um índice composto Firestore no campo `data`.
> Se aparecer erro `FAILED_PRECONDITION` nos logs, crie o índice via console Firebase ou adicione
> em `firestore.indexes.json` e execute `firebase deploy --only firestore:indexes`.

---

## Atualização / Redeploy

```bash
git pull
docker compose up -d --build
```

O `restart: unless-stopped` garante que o container volte após reinício do host.

---

## Rollback

```bash
docker compose down
git checkout <tag-ou-commit-estável>
docker compose up -d --build
```

---

## Monitoramento

```bash
docker compose logs -f web      # logs em tempo real (stdout/stderr do gunicorn)
docker stats --no-stream        # uso de CPU/memória
curl http://localhost:5000/health
```

---

## Acompanhamento de cota Firebase

Para não estourar a cota do Firebase, o sistema já usa:

- **Rate limits** em produção (200/hora, 2000/dia por cliente; exportações 3/hora).
- **Cache** do relatório completo (5 min).
- **Paginação por cursor** + **contagem por agregação (count)** para totais.
- **Limite** nas queries de analytics (`MAX_CHAMADOS_ANALYTICS`).

Acompanhe o uso em **Firebase Console → Firestore/Storage → Usage**. Mantenha rate
limits e cache ativos em produção.

---

## Se o build falhar

| Sintoma | Ação |
|---|---|
| Falha no stage `css-builder` | Conferir `package.json`/`npm run build:css` localmente |
| Falha no `pip install` | Conferir `requirements.txt` e conectividade do host |
| Container sobe e morre | `docker compose logs web` — geralmente `.env`/`credentials.json` ausentes |
| Health check falha | Verificar se a porta 8080 interna responde `/health` |
