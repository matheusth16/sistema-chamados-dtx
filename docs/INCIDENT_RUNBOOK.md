# Runbook de Incidentes — Sistema de Chamados

> Ref rápida para quando algo quebra. Diagnose → Ação → Postmortem leve.
>
> **Ambiente de execução:** container Docker (gunicorn, 1 worker / 8 threads,
> porta interna 8080) rodando no **Azure Container Apps** (`sistema-chamados` /
> `rg-sistema-chamados`; imagem publicada no GHCR via CI/CD — ver
> `docs/DEPLOYMENT_PLAN.md`). Banco: Firestore. Anexos: Cloudflare R2 (com
> fallback Firebase Storage). E-mail: Microsoft Graph API.
>
> Os comandos abaixo assumem Azure CLI autenticado (`az login`). Alternativa
> sem CLI: Portal → Container Apps → `sistema-chamados` (Log stream, Console,
> Revisions and replicas).

---

## Resposta rápida (primeiros 5 minutos)

```
1. Confirmar o sintoma — o que usuário vê? (503? tela branca? login falha?)
2. Verificar status/revisões: az containerapp revision list -n sistema-chamados -g rg-sistema-chamados -o table
3. Verificar logs:              az containerapp logs show -n sistema-chamados -g rg-sistema-chamados --tail 100
4. Verificar health:            curl https://<fqdn>/health
5. Se crítico → rollback imediato (ver seção abaixo)
6. Após estável → postmortem leve (ver template)
```

> Substitua `<fqdn>` pelo FQDN real do Container App (Portal → Overview, ou `az containerapp show -n sistema-chamados -g rg-sistema-chamados --query properties.configuration.ingress.fqdn`).

---

## Cenários de falha comuns

### 1. Container retorna 503 / não responde

**Diagnose**
```bash
az containerapp revision list -n sistema-chamados -g rg-sistema-chamados -o table
az containerapp logs show -n sistema-chamados -g rg-sistema-chamados --tail 200
```

**Causas mais prováveis**
| Sintoma nos logs | Causa | Ação |
|---|---|---|
| `WORKER TIMEOUT` | Requisição lenta (Firestore/e-mail) | Aumentar `--timeout` em `start.sh` ou otimizar query |
| `GOOGLE_CREDENTIALS_JSON` ausente/erro de parse | Secret não configurado ou JSON inválido | Conferir Container App → Secrets/Environment variables |
| `MemoryError` / réplica reiniciando (OOM) | App consumindo mais que o limite de recursos | Aumentar vCPU/memória do Container App (Scale) |
| Revisão travada em "Provisioning" ou "Failed" | Erro de inicialização na imagem nova | Ver logs da revisão; fazer rollback (abaixo) |

**Rollback rápido** — Container Apps mantém revisões anteriores; não é preciso rebuildar:
```bash
# Listar revisões e achar a última estável antes do problema
az containerapp revision list -n sistema-chamados -g rg-sistema-chamados -o table

# Redirecionar 100% do tráfego para a revisão anterior estável
az containerapp ingress traffic set -n sistema-chamados -g rg-sistema-chamados \
  --revision-weight <nome-revisao-anterior>=100

# Alternativa via Portal: Container App → Revisions and replicas → ative a
# revisão anterior e ajuste o tráfego para 100% nela.
```
Se o problema exigir reverter o código-fonte (não só a revisão), fazer o commit
de correção e deixar o `cd-build-image.yml` publicar uma imagem nova — não há
"voltar servidor" local para isso.

---

### 2. Erro de autenticação Firebase / Firestore

**Sintoma**: `google.auth.exceptions.TransportError` ou `DefaultCredentialsError` nos logs

**Diagnose**
```bash
# Confirmar que o secret GOOGLE_CREDENTIALS_JSON está definido (mostra só o nome, não o valor)
az containerapp secret list -n sistema-chamados -g rg-sistema-chamados -o table
```

**Ações**
1. Confirmar que o secret `GOOGLE_CREDENTIALS_JSON` está definido no Container App (Portal → Secrets) e referenciado na variável de ambiente correspondente
2. Confirmar que a conta de serviço tem as permissões corretas no Firebase/Firestore
3. Rolar a credencial se comprometida:
   - Firebase Console → Configurações → Contas de serviço → Gerar nova chave privada
   - Atualizar o secret `GOOGLE_CREDENTIALS_JSON` no Container App (Portal → Secrets, ou `az containerapp secret set`) com o novo JSON
   - Salvar cria uma nova revisão automaticamente (não precisa de "reiniciar" manual)

---

### 3. Timeout / lentidão no dashboard

**Sintoma**: Dashboard demora >5s, usuários reclamam de tela travada

**Diagnose**: Lentidão pode ser causada por volume alto de chamados na query inicial do dashboard. Verificar `app/services/dashboard_service.py` — usa paginação por cursor; reduzir janela se necessário.

**Ação imediata**
- Reduzir `ITENS_POR_PAGINA_DASHBOARD` para 50 (Container App → Environment variables) — salvar cria revisão nova automaticamente

**Contexto**: N+1 em relatório semanal (`report_service.py`) foi resolvido via batch `Usuario.get_by_ids` (F-24, Onda B 2026-06-18). Lentidão residual no dashboard é de volume, não de padrão N+1.

---

### 4. E-mails não enviados

**Sintoma**: Supervisor não recebe notificações; logs mostram erro de autenticação
do Microsoft Graph (`401`/`403`) ou throttling (`429`).

**Diagnose**
```bash
# Conferir se as variáveis Graph estão definidas (Portal → Environment variables
# lista os nomes; secrets como GRAPH_CLIENT_SECRET não mostram o valor)
az containerapp show -n sistema-chamados -g rg-sistema-chamados \
  --query "properties.template.containers[0].env[?starts_with(name, 'GRAPH_')]"

# Gerar/inspecionar snapshots visuais dos e-mails (roda localmente, não envia para produção)
python scripts/qa/gerar_email_visual_snapshots.py
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
az containerapp logs show -n sistema-chamados -g rg-sistema-chamados --tail 200 \
  | grep -iE "R2|Storage|upload"
```

**Ações**
| Cenário | Ação |
|---|---|
| `R2 indisponível` | Verificar `R2_*` nas variáveis do Container App; sistema cai no fallback Firebase Storage |
| `403 Forbidden` (R2) | Conferir credenciais/permissões do bucket R2 |
| `Firebase Storage indisponível` | Verificar `FIREBASE_STORAGE_BUCKET` nas variáveis do Container App |
| `File too large` | Limite atingido (config `MAX_CONTENT_LENGTH`, ~10MB) |

---

### 6. Cold start / réplica demorando pra subir

**Contexto**: o Container App roda com `min-replicas=0` (economia de cota gratuita —
ver `docs/DEPLOYMENT_PLAN.md`). Após período ocioso, a primeira requisição sofre
cold start (alguns segundos até a réplica subir). Isso é esperado, não é incidente —
mas se demorar muito mais que o normal ou nunca estabilizar, investigar:

**Ação**
1. Conferir o status da réplica: `az containerapp replica list -n sistema-chamados -g rg-sistema-chamados -o table`
2. Ver logs da revisão ativa: `az containerapp logs show -n sistema-chamados -g rg-sistema-chamados --tail 100`
3. Validar health: `curl https://<fqdn>/health`
4. Se a revisão estiver presa em "Failed"/"Provisioning" indefinidamente, ativar a revisão anterior estável (ver rollback no cenário 1)

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
| Status/revisões | `az containerapp revision list -n sistema-chamados -g rg-sistema-chamados -o table` |
| Logs em tempo real | `az containerapp logs show -n sistema-chamados -g rg-sistema-chamados --follow` |
| Ativar revisão (rollback) | `az containerapp ingress traffic set -n sistema-chamados -g rg-sistema-chamados --revision-weight <revisao>=100` |
| Forçar nova imagem | `az containerapp update -n sistema-chamados -g rg-sistema-chamados --image ghcr.io/matheusth16/sistema-chamados-dtx:latest` |
| Shell no container | `az containerapp exec -n sistema-chamados -g rg-sistema-chamados --command sh` |
| Health check | `curl https://<fqdn>/health` |
| Portal (visão geral, secrets, revisões) | https://portal.azure.com → Container Apps → sistema-chamados |
| Firestore console | https://console.firebase.google.com |
| Firebase Storage | https://console.firebase.google.com |
| Cloudflare R2 | https://dash.cloudflare.com |
| Azure AD (Graph / e-mail) | https://portal.azure.com |
| Desenvolvimento local (não produção) | `docker compose up -d --build` (ver `docs/DEPLOYMENT_PLAN.md`) |
