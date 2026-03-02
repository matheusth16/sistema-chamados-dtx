# 🚀 PLANO DE DEPLOYMENT - SISTEMA DE CHAMADOS DTX

## Status Atual
- ✅ Código: 100% funcionando
- ✅ Features: Dashboard + Excel export + Visibility fix
- ✅ Git: Commitado e pushado (commit `060a8c2`)
- ✅ Requirements: Versões fixadas
- ⏳ Cloud Build: Deve estar rodando agora (ou logo)

---

## PASSO 1: Verificar Build Status
**Tempo: 3-5 minutos**

1. Acesse: https://console.cloud.google.com/cloud-build/builds?project=sistema-de-chamados-dtx-aero

2. Procure pelo build mais recente (deve ser de agora)

3. Aguarde completar:
   - ✅ **Se PASSOU:** Vai para Passo 2
   - ❌ **Se FALHOU:** Vai para "Se Falhar"

---

## PASSO 2: Cloud Run Deploy (Automático ou Manual)

### Opção A: Deploy Automático (Se tem trigger Cloud Run)
Se você já configurou um trigger de Cloud Run que dispara com push:
- ✅ Deploy inicia automaticamente após build passar
- Tempo: ~5-10 minutos
- Acesse: https://console.cloud.google.com/run?project=sistema-de-chamados-dtx-aero

### Opção B: Deploy Manual (Se precisa fazer manualmente)

**Deploy manual** (a partir da raiz do projeto):

```powershell
.\scripts\deploy_fresh.ps1
```

Ou manualmente:

```bash
cd "c:\Users\MatheusCosta\OneDrive - DTX Aerospace\Área de Trabalho\Projetos\sistema_chamados"

gcloud run deploy sistema-chamados-dtx \
  --source . \
  --platform managed \
  --region us-central1 \
  --project sistema-de-chamados-dtx-aero \
  --allow-unauthenticated \
  --set-env-vars="SECRET_KEY=seu-secret-key-forte-aqui,FLASK_ENV=production,FIREBASE_STORAGE_BUCKET=seu-bucket.firebasestorage.app" \
  --set-build-env-vars="GOOGLE_ENTRYPOINT=gunicorn -b :8080 run:app" \
  --memory=512Mi \
  --timeout=60 \
  --max-instances=10
```

---

## PASSO 3: Testar no Cloud Run

Após deploy completar:

1. **Acesse a URL gerada:**
   ```
   https://sistema-chamados-dtx-xxxxxx.run.app
   ```
   (Copie de: https://console.cloud.google.com/run)

2. **Teste:**
   - ✅ Login funciona?
   - ✅ Dashboard carrega?
   - ✅ Botão "Exportar Avançado" existe?
   - ✅ Criar chamado funciona?
   - ✅ Selecionar responsável funciona?

3. **Se algo der erro:**
   - Acesse: Cloud Run → sistema-chamados-dtx → Logs
   - Procure por mensagem de erro

**Anexos:** Os arquivos vão para o **Firebase Storage** (pasta `chamados/`). Tamanho máximo: **5 MB**. Formatos: imagens, PDF, xlsx. Em produção: 1) No **Firebase Console > Storage**, copie o nome do bucket (ex.: `gs://sistema-de-chamados-dtx-aero.firebasestorage.app` → use `sistema-de-chamados-dtx-aero.firebasestorage.app`). 2) No Cloud Run, defina a variável **`FIREBASE_STORAGE_BUCKET`** com esse valor. 3) No GCP IAM, dê à **conta de serviço do Cloud Run** a permissão **Storage Object Admin** no bucket. Sem isso, uploads em produção falham e o Storage fica vazio.

---

## PASSO 4: Configurar Domínio (Bônus)

Se quiser usar um domínio personalizado:

```bash
# 1. No Cloud Run console:
#    → sistema-chamados-dtx → Configurações
#    → "Mapeamentos de Domínio"
#    → "+ Adicionar Mapeamento"
#    → Escolha seu domínio

# 2. Ou use:
gcloud run services update-traffic sistema-chamados-dtx \
  --to-revisions LATEST=100 \
  --region us-central1
```

---

## PASSO 5: Monitorar em Produção

```bash
# Ver logs em tempo real
gcloud run logs read sistema-chamados-dtx --region us-central1 --limit 50 --follow

# Ver métricas
# Acesse: Cloud Run console → sistema-chamados-dtx → Métricas
```

---

## Acompanhamento de uso (plano Spark)

Para não estourar a cota do Firebase no plano Spark (ex.: 50k reads/dia no Firestore), o sistema já usa:

- **Rate limits** em produção (200/hora, 2000/dia por cliente; exportações limitadas a 3/hora).
- **Cache** do relatório completo (5 min), reduzindo leituras repetidas.
- **Paginação por cursor** em "Meus chamados" e **contagem por agregação (count)** para totais, em vez de carregar todos os documentos.
- **Limite** nas queries de analytics (`MAX_CHAMADOS_ANALYTICS`), capando leituras por relatório.

**Onde acompanhar uso:**

- **Firestore:** [Firebase Console → Firestore → Usage](https://console.firebase.google.com) (ou Google Cloud Console → Firestore → Uso). Verifique leituras/escritas por dia.
- **Storage:** Firebase Console → Storage → Usage. Limites do Spark (ex.: 5 GB armazenado, 1 GB download/dia em buckets legados).

Mantenha rate limits e cache ativos em produção; em desenvolvimento eles podem estar desativados.

---

## Índices Firestore (Meus chamados)

Se a rota "Meus chamados" exigir índices compostos, faça o deploy após alterar `firestore.indexes.json`:

```bash
firebase deploy --only firestore:indexes --project sistema-de-chamados-dtx-aero
```

---

## SE FALHAR NO BUILD

Erro 51 ainda aparecer? Aumente o timeout do build:

```bash
gcloud run deploy sistema-chamados-dtx \
  --source . \
  --region us-central1 \
  --project sistema-de-chamados-dtx-aero \
  --build-timeout=1800
```

Ou verifique logs do build:
https://console.cloud.google.com/cloud-build/builds

---

## CHECKLIST FINAL

- [ ] Build passou ✓
- [ ] Deploy completou
- [ ] URL funciona
- [ ] Login OK
- [ ] Dashboard carrega
- [ ] PDF/Excel exporta
- [ ] Novo chamado funciona
- [ ] Supervisores veem mesmo setor

---

## URLS IMPORTANTES

| O Quê | URL |
|-------|-----|
| Cloud Run | https://console.cloud.google.com/run?project=sistema-de-chamados-dtx-aero |
| Cloud Build | https://console.cloud.google.com/cloud-build/builds?project=sistema-de-chamados-dtx-aero |
| Firestore | https://console.cloud.google.com/firestore?project=sistema-de-chamados-dtx-aero |
| Logs | gcloud run logs read sistema-chamados-dtx --region us-central1 |

---

**Tempo Total:** ~20-30 minutos (build + deploy + testes)
**Próximo:** Deploy completado = Sistema no ar! 🎉
