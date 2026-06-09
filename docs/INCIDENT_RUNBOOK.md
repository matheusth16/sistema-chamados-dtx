# Runbook de Incidentes — Sistema de Chamados

> Ref rápida para quando algo quebra. Diagnose → Ação → Postmortem leve.

---

## Resposta rápida (primeiros 5 minutos)

```
1. Confirmar o sintoma — o que usuário vê? (503? tela branca? login falha?)
2. Verificar logs: gcloud run services logs read sistema-chamados --region=southamerica-east1 --limit=50
3. Verificar health: curl https://SEU_DOMINIO/health
4. Se crítico → rollback imediato (ver seção abaixo)
5. Após estável → postmortem leve (ver template)
```

---

## Cenários de falha comuns

### 1. Serviço Cloud Run retorna 503 / não responde

**Diagnose**
```bash
gcloud run services describe sistema-chamados --region=southamerica-east1
gcloud run services logs read sistema-chamados --region=southamerica-east1 --limit=100
```

**Causas mais prováveis**
| Sintoma nos logs | Causa | Ação |
|---|---|---|
| `WORKER TIMEOUT` | Requisição lenta (Firestore/e-mail) | Aumentar `--timeout` ou otimizar query |
| `Error: credentials.json not found` | Secret não montado no Cloud Run | Verificar Secret Manager / variável de ambiente |
| `OSError: [Errno 28] No space left` | Disco cheio (worker-tmp-dir) | Adicionar `--worker-tmp-dir /dev/shm` (já configurado) |
| `Memory limit exceeded` | App consumindo > 512Mi | Aumentar memória: `gcloud run services update ... --memory 1Gi` |
| Container não inicializa | Build com erro | Ver logs do Cloud Build; fazer rollback |

**Rollback rápido**
```bash
# Ver revisões disponíveis
gcloud run revisions list --service=sistema-chamados --region=southamerica-east1

# Rollback para revisão anterior
gcloud run services update-traffic sistema-chamados \
  --region=southamerica-east1 \
  --to-revisions=NOME-REVISAO-ANTERIOR=100
```

---

### 2. Erro de autenticação Firebase / Firestore

**Sintoma**: `google.auth.exceptions.TransportError` ou `DefaultCredentialsError` nos logs

**Diagnose**
```bash
# Verificar se a conta de serviço tem as permissões corretas
gcloud projects get-iam-policy SEU_PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:*"
```

**Ações**
1. Confirmar que `GOOGLE_APPLICATION_CREDENTIALS` está configurado **ou** que o Cloud Run usa a conta de serviço correta
2. Se usando `credentials.json` via Secret Manager: verificar se o secret está montado
3. Rolar a credencial se comprometida:
   - Firebase Console → Configurações → Contas de serviço → Gerar nova chave privada
   - Atualizar o secret no Secret Manager
   - Fazer novo deploy

---

### 3. Timeout / lentidão no dashboard

**Sintoma**: Dashboard demora >5s, usuários reclamam de tela travada

**Diagnose**: Ver query N+1 em `app/services/dashboard_service.py` — problema conhecido (ALTO, backlog).

**Ação imediata**
- Reduzir `ITENS_POR_PAGINA_DASHBOARD` no `.env` de 500 para 50
- Reiniciar o serviço: `gcloud run services update sistema-chamados --region=... --clear-env-vars` (ou novo deploy)

**Fix definitivo**: Migrar para query agregada + paginação real (backlog crítico).

---

### 4. E-mails não enviados

**Sintoma**: Supervisor não recebe notificações, logs mostram `SMTPAuthenticationError` ou timeout

**Diagnose**
```bash
# Testar SMTP isolado (não afeta produção)
cd scripts/
python teste_email_smtp_m365.py
```

**Ações**
| Erro | Causa | Ação |
|---|---|---|
| `SMTPAuthenticationError` | Senha expirou ou MFA mudou | Gerar nova senha de app no M365 Admin |
| `ConnectionRefusedError` | Porta 587 bloqueada | Tentar porta 465 (SSL) |
| `TimeoutError` | Servidor lento | Aumentar timeout em `app/services/notifications.py` |

**Mitigação**: e-mails não-críticos. O sistema continua funcionando sem eles. Notificações in-app continuam ativas.

---

### 5. Upload de anexos falha

**Sintoma**: Erro ao anexar arquivo; usuário recebe "Falha ao enviar anexo"

**Diagnose**
```bash
gcloud run services logs read sistema-chamados --region=southamerica-east1 \
  --filter="Firebase Storage" --limit=20
```

**Ações**
| Cenário | Ação |
|---|---|
| `Firebase Storage indisponível` | Verificar `FIREBASE_STORAGE_BUCKET` no Cloud Run env vars |
| `403 Forbidden` | Conta de serviço sem permissão `Storage Object Admin` no bucket |
| `File too large` | Limite de 10MB atingido (config `MAX_CONTENT_LENGTH`) |

---

### 6. GCP billing desativado / serviço suspenso

**Contexto**: Cloud Run para automaticamente se o billing for desabilitado.

**Ação**
1. Acessar: https://console.cloud.google.com/billing
2. Vincular método de pagamento
3. Reativar o projeto: `gcloud projects undelete SEU_PROJECT_ID` (se necessário)
4. O serviço Cloud Run volta automaticamente em ~5 minutos após billing ativo

**PRAZO ATUAL: billing desativado — agir antes de 19/06/2026**

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

## Contatos e links úteis

| Recurso | Link |
|---|---|
| Cloud Run console | https://console.cloud.google.com/run |
| Cloud Build history | https://console.cloud.google.com/cloud-build |
| Firestore console | https://console.cloud.google.com/firestore |
| Firebase Storage | https://console.firebase.google.com |
| Billing | https://console.cloud.google.com/billing |
| Logs Explorer | https://console.cloud.google.com/logs |
