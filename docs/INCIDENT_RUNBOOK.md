# Runbook de Incidentes — Sistema de Chamados

> Ref rápida para quando algo quebra. Diagnose → Ação → Postmortem leve.
>
> **Ambiente de execução:** container Docker (gunicorn, 1 worker / 8 threads,
> porta interna 8080) rodando em servidor local/on-premise. Banco: Firestore.
> Anexos: Cloudflare R2 (com fallback Firebase Storage). E-mail: Microsoft Graph API.

---

## Resposta rápida (primeiros 5 minutos)

```
1. Confirmar o sintoma — o que usuário vê? (503? tela branca? login falha?)
2. Verificar status do container: docker compose ps
3. Verificar logs:               docker compose logs --tail=100 web
4. Verificar health:             curl http://localhost:5000/health
5. Se crítico → rollback imediato (ver seção abaixo)
6. Após estável → postmortem leve (ver template)
```

> Substitua `localhost:5000` pelo host/porta reais do servidor se acessado remotamente.

---

## Cenários de falha comuns

### 1. Container retorna 503 / não responde

**Diagnose**
```bash
docker compose ps
docker compose logs --tail=200 web
docker stats --no-stream
```

**Causas mais prováveis**
| Sintoma nos logs | Causa | Ação |
|---|---|---|
| `WORKER TIMEOUT` | Requisição lenta (Firestore/e-mail) | Aumentar `--timeout` em `start.sh` ou otimizar query |
| `Error: credentials.json not found` | Volume de credenciais não montado | Verificar volume `./credentials.json:/app/credentials.json:ro` no compose |
| `OSError: [Errno 28] No space left` | Disco do host cheio | Liberar espaço; `--worker-tmp-dir /dev/shm` já configurado |
| `MemoryError` / container morto (OOM) | App consumindo mais que o limite | Aumentar limite de memória no host/compose |
| Container reinicia em loop | Erro de inicialização | Ver logs do build/start; fazer rollback |

**Rollback rápido**
```bash
# Voltar para a imagem/tag anterior conhecida como estável
docker compose down
git checkout <tag-ou-commit-estável>
docker compose up -d --build

# Ou, se houver imagem anterior taggeada:
docker tag sistema-chamados:previous sistema-chamados:latest
docker compose up -d
```

---

### 2. Erro de autenticação Firebase / Firestore

**Sintoma**: `google.auth.exceptions.TransportError` ou `DefaultCredentialsError` nos logs

**Diagnose**
```bash
# Confirmar que o credentials.json está montado dentro do container
docker compose exec web ls -l /app/credentials.json
```

**Ações**
1. Confirmar que o volume `./credentials.json:/app/credentials.json:ro` está montado e o arquivo existe na raiz do host
2. Confirmar que a conta de serviço tem as permissões corretas no Firebase/Firestore
3. Rolar a credencial se comprometida:
   - Firebase Console → Configurações → Contas de serviço → Gerar nova chave privada
   - Substituir `credentials.json` no servidor
   - Reiniciar: `docker compose restart web`

---

### 3. Timeout / lentidão no dashboard

**Sintoma**: Dashboard demora >5s, usuários reclamam de tela travada

**Diagnose**: Lentidão pode ser causada por volume alto de chamados na query inicial do dashboard. Verificar `app/services/dashboard_service.py` — usa paginação por cursor; reduzir janela se necessário.

**Ação imediata**
- Reduzir `ITENS_POR_PAGINA_DASHBOARD` no `.env` de 500 para 50
- Reiniciar o serviço: `docker compose restart web`

**Contexto**: N+1 em relatório semanal (`report_service.py`) foi resolvido via batch `Usuario.get_by_ids` (F-24, Onda B 2026-06-18). Lentidão residual no dashboard é de volume, não de padrão N+1.

---

### 4. E-mails não enviados

**Sintoma**: Supervisor não recebe notificações; logs mostram erro de autenticação
do Microsoft Graph (`401`/`403`) ou throttling (`429`).

**Diagnose**
```bash
# Conferir as variáveis Graph dentro do container
docker compose exec web env | grep GRAPH_

# Gerar/inspecionar snapshots visuais dos e-mails (não envia para produção)
python scripts/gerar_email_visual_snapshots.py
```

**Ações**
| Erro | Causa | Ação |
|---|---|---|
| `401 Unauthorized` | Client secret expirado | Gerar novo secret no Azure AD e atualizar `GRAPH_CLIENT_SECRET` |
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
docker compose logs web | grep -iE "R2|Storage|upload"
```

**Ações**
| Cenário | Ação |
|---|---|
| `R2 indisponível` | Verificar `R2_*` no `.env`; sistema cai no fallback Firebase Storage |
| `403 Forbidden` (R2) | Conferir credenciais/permissões do bucket R2 |
| `Firebase Storage indisponível` | Verificar `FIREBASE_STORAGE_BUCKET` no `.env` |
| `File too large` | Limite atingido (config `MAX_CONTENT_LENGTH`, ~10MB) |

---

### 6. Servidor local indisponível / reinício

**Contexto**: O container é reiniciado automaticamente (`restart: unless-stopped`),
mas o host pode reiniciar (queda de energia, manutenção).

**Ação**
1. Confirmar que o Docker está ativo no host: `docker info`
2. Subir o stack: `docker compose up -d`
3. Validar health: `curl http://localhost:5000/health`
4. Conferir que o `restart: unless-stopped` está no `docker-compose.yml` para auto-recuperação

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
| Status dos containers | `docker compose ps` |
| Logs em tempo real | `docker compose logs -f web` |
| Reiniciar serviço | `docker compose restart web` |
| Rebuild + subir | `docker compose up -d --build` |
| Shell no container | `docker compose exec web sh` |
| Health check | `curl http://localhost:5000/health` |
| Firestore console | https://console.firebase.google.com |
| Firebase Storage | https://console.firebase.google.com |
| Cloudflare R2 | https://dash.cloudflare.com |
| Azure AD (Graph / e-mail) | https://portal.azure.com |
