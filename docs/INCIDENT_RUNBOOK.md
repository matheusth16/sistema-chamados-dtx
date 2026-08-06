# Runbook de Incidentes — Sistema de Chamados

> Ref rápida para quando algo quebra. Diagnose → Ação → Postmortem leve.
>
> **Atualizado 2026-08-06.** Ambiente de execução: container Docker (gunicorn, 1 worker / 8
> threads, porta 8080) rodando no **servidor físico on-premise da DTX** (10.20.0.199, LAN-only),
> não mais Azure Container Apps (desligado 2026-07-31). Banco: **PostgreSQL** (não mais
> Firestore, migrado no Marco 12, 2026-08-04). Anexos: disco local (Fase 1, destino principal)
> com Cloudflare R2 como storage legado. E-mail: Microsoft Graph API.
>
> Os comandos abaixo assumem acesso SSH ao servidor (`ssh <usuário>@10.20.0.199`) com permissão
> pra rodar `docker`. Não há mais Azure CLI/Portal envolvido — o servidor roda
> `docker-compose.prod.yml` com 3 serviços: `postgres`, `web` e `watchtower`.

---

## Resposta rápida (primeiros 5 minutos)

```
1. Confirmar o sintoma — o que usuário vê? (503? tela branca? login falha?)
2. Verificar status:  ssh <usuário>@10.20.0.199 "docker ps --format 'table {{.Names}}\t{{.Status}}'"
3. Verificar logs:    ssh <usuário>@10.20.0.199 "docker logs --tail 100 sistema_chamados-web-1"
4. Verificar health:  curl http://10.20.0.199:8080/health
5. Se crítico → rollback imediato (ver seção abaixo)
6. Após estável → postmortem leve (ver template)
```

---

## Cenários de falha comuns

### 1. Container retorna 503 / não responde

**Diagnose**
```bash
ssh <usuário>@10.20.0.199 "docker ps --format 'table {{.Names}}\t{{.Status}}'"
ssh <usuário>@10.20.0.199 "docker logs --tail 200 sistema_chamados-web-1"
```

**Causas mais prováveis**
| Sintoma nos logs | Causa | Ação |
|---|---|---|
| `WORKER TIMEOUT` | Requisição lenta (query Postgres/e-mail) | Aumentar `--timeout` em `start.sh` ou otimizar query |
| `DATABASE_URL` ausente/erro de conexão | `.env` incompleto ou Postgres fora do ar | Conferir `docker ps` mostra `sistema_chamados-postgres-1` healthy; conferir `.env` no servidor |
| Container reiniciando em loop (OOM) | App consumindo mais memória que o limite | `docker stats --no-stream` pra confirmar; considerar ajustar limites no compose |
| Container não sobe após `watchtower_trigger.sh` | Erro de inicialização na imagem nova | Ver `docker logs sistema_chamados-web-1`; fazer rollback (abaixo) |

**Rollback rápido**:
```bash
# No servidor — retag a imagem anterior conhecida-boa como :latest no GHCR
# (fora do servidor, via gh/docker CLI com push access), depois:
ssh <usuário>@10.20.0.199 "./scripts/watchtower_trigger.sh"
```
Alternativa mais direta se souber a tag/digest anterior: editar `docker-compose.prod.yml` no
servidor pra apontar pra uma tag/digest específica (não `:latest`) e rodar
`docker compose -f docker-compose.prod.yml up -d` manualmente.

---

### 2. Erro de conexão com PostgreSQL

**Sintoma**: `sqlalchemy.exc.OperationalError`, `psycopg.OperationalError`, ou app não sobe
citando `DATABASE_URL` nos logs.

**Diagnose**
```bash
ssh <usuário>@10.20.0.199 "docker ps --filter name=postgres --format '{{.Names}} {{.Status}}'"
ssh <usuário>@10.20.0.199 "docker logs --tail 100 sistema_chamados-postgres-1"
```

**Ações**
1. Confirmar que `sistema_chamados-postgres-1` está `healthy` (`docker ps`).
2. Confirmar `DATABASE_URL` no `.env` do servidor bate com usuário/senha/db do serviço `postgres`.
3. Se o container Postgres não sobe: checar espaço em disco do volume LVM dedicado
   (`/mnt/data/sistema_chamados/postgres`) — `df -h`.
4. `app/database.py` (Firestore, legado) não é mais usado — se aparecer erro citando
   `firebase_admin`, é porque o import morto acidentalmente voltou a ser referenciado em algum
   lugar; verificar `grep -rn "app.database" app/` (deveria dar zero hits).

---

### 3. Timeout / lentidão no dashboard

**Sintoma**: Dashboard demora >5s, usuários reclamam de tela travada

**Diagnose**: Lentidão pode ser causada por volume alto de chamados na query inicial do dashboard. Verificar `app/services/dashboard_service.py` — usa paginação por cursor; reduzir janela se necessário.

**Ação imediata**
- Reduzir `ITENS_POR_PAGINA_DASHBOARD` para 50 no `.env` do servidor, depois `./scripts/watchtower_trigger.sh` (ou `docker compose -f docker-compose.prod.yml up -d` se editou localmente)

**Contexto**: N+1 em relatório semanal (`report_service.py`) foi resolvido via batch `Usuario.get_by_ids` (F-24, Onda B 2026-06-18). Lentidão residual no dashboard é de volume, não de padrão N+1.

---

### 4. E-mails não enviados

**Sintoma**: Supervisor não recebe notificações; logs mostram erro de autenticação
do Microsoft Graph (`401`/`403`) ou throttling (`429`).

**Diagnose**
```bash
# Conferir se as variáveis Graph estão no .env do servidor (não mostrar o secret em log/tela compartilhada)
ssh <usuário>@10.20.0.199 "grep '^GRAPH_' .env | cut -d= -f1"

# Gerar/inspecionar snapshots visuais dos e-mails (roda localmente, não envia para produção)
python scripts/qa/gerar_email_visual_snapshots.py
```

**Ações**
| Erro | Causa | Ação |
|---|---|---|
| `401 Unauthorized` | Client secret expirado | Gerar novo secret no Azure AD (App Registration) e atualizar `GRAPH_CLIENT_SECRET` no `.env` do servidor + `watchtower_trigger.sh` |
| `403 Forbidden` | App sem permissão `Mail.Send` | Conceder/consentir `Mail.Send` (Application) no Azure AD |
| `429 Too Many Requests` | Throttling do Graph | Retentativa com backoff (ver `app/services/notify_retry.py`) |
| Timeout | Rede/Graph lento | Verificar conectividade de saída do servidor |

**Mitigação**: e-mails não são críticos. O sistema continua funcionando sem eles.
As notificações in-app e Web Push continuam ativas.

---

### 5. Upload de anexos falha

**Sintoma**: Erro ao anexar arquivo; usuário recebe "Falha ao enviar anexo"

**Diagnose**
```bash
ssh <usuário>@10.20.0.199 "docker logs --tail 200 sistema_chamados-web-1" | grep -iE "R2|disco|local|upload"
```

**Ações**
| Cenário | Ação |
|---|---|
| `ANEXO_STORAGE_BACKEND=local` falhando | Verificar espaço/permissão em `ANEXO_LOCAL_DIR` (`/var/anexos_chamados` no servidor) |
| `R2 indisponível` | Verificar `R2_*` no `.env` do servidor — sem R2 configurado em produção, upload falha (não há mais fallback Firebase Storage, removido do código) |
| `403 Forbidden` (R2) | Conferir credenciais/permissões do bucket R2 |
| `File too large` | Limite atingido (config `MAX_CONTENT_LENGTH`, ~10MB) |

---

### 6. Container reiniciando ou demorando pra subir

> **Superado**: cold start por `min-replicas=0` era específico do Azure Container Apps
> (desativado). O servidor físico é **sempre-ligado** — não há scale-to-zero nem cold start
> esperado. Se o container está demorando ou reiniciando, é sintoma real, não comportamento
> normal — tratar como o cenário 1 (503/não responde).

**Ação**
1. Conferir o status: `ssh <usuário>@10.20.0.199 "docker ps --format 'table {{.Names}}\t{{.Status}}'"`
2. Ver logs: `ssh <usuário>@10.20.0.199 "docker logs --tail 100 sistema_chamados-web-1"`
3. Validar health: `curl http://10.20.0.199:8080/health`
4. Se preso reiniciando, seguir o rollback do cenário 1.

---

## Template de postmortem leve (preencher após incidente)

```markdown
## Incidente: [título curto] — [data]

**Duração**: X minutos | **Severidade**: baixa/média/alta
**Impacto**: [quem foi afetado e como]

### O que aconteceu (timeline resumida)
- HH:MM — [evento 1]
- HH:MM — [evento 2]
- HH:MM — resolvido

### Causa raiz
[Uma frase clara: "X aconteceu porque Y"]

### O que funcionou bem
- [ex.: alertas dispararam rápido]

### O que não funcionou
- [ex.: logs insuficientes para diagnose]

### Ações preventivas
| Ação | Prazo |
|------|-------|
| [ação concreta] | [data] |
```

---

## Comandos e links úteis

| Recurso | Comando / Link |
|---|---|
| Status dos containers | `ssh <usuário>@10.20.0.199 "docker ps --format 'table {{.Names}}\t{{.Status}}'"` |
| Logs em tempo real | `ssh <usuário>@10.20.0.199 "docker logs -f sistema_chamados-web-1"` |
| Aplicar imagem nova / rollback | `ssh <usuário>@10.20.0.199 "./scripts/watchtower_trigger.sh"` |
| Shell no container | `ssh <usuário>@10.20.0.199 "docker exec -it sistema_chamados-web-1 sh"` |
| Health check | `curl http://10.20.0.199:8080/health` |
| Portainer (gestão visual de containers) | https://10.20.0.199:9443 (LAN only) |
| Netdata (métricas de sistema) | http://10.20.0.199:19999 (LAN only) |
| Cloudflare R2 (anexos legados) | https://dash.cloudflare.com |
| Azure AD (Graph API / e-mail) | https://portal.azure.com |
| GHCR (imagens publicadas) | https://github.com/matheusth16/sistema-chamados-dtx/pkgs/container/sistema-chamados-dtx |
| Desenvolvimento local (não produção) | `docker compose up -d --build` (ver `docs/DEPLOYMENT_PLAN.md`) |
