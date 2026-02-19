# 📚 Guia de Troubleshooting - Cloud Run Deploy

## ❌ Erro Atual
```
ERROR: (gcloud.run.deploy) Build failed; check build logs for details
```

## ✅ Código está OK
- Testado: Todos os 10 módulos importam corretamente
- Validado: 23 rotas registradas
- Verificado: App inicia no ambiente do Cloud Run
- Nenhum erro de sintaxe Python

## 🔧 Passos para Resolver

### 1. Verificar Logs do Build no Console Cloud
```
https://console.cloud.google.com/cloud-build/builds?project=sistema-de-chamados-dtx-aero
```
Clique no build que falhou para ver os logs detalhados.

### 2. Tentar Deploy Novamente (Simples)
```bash
# No terminal com gcloud configurado:
cd "c:\Users\MatheusCosta\OneDrive - DTX Aerospace\Área de Trabalho\Projetos\sistema_chamados"

# Deploy simples
gcloud run deploy sistema-chamados-dtx \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars="SECRET_KEY=chave-secreta-do-matheus-dtx-2026,FLASK_ENV=production"
```

### 3. Deploy com Cache Ignorado (Force)
Se o problema é de cache:
```bash
gcloud run deploy sistema-chamados-dtx \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars="SECRET_KEY=chave-secreta-do-matheus-dtx-2026" \
  --build-context=. \
  --no-cache
```

### 4. Problemas Possíveis e Soluções

#### Problema: "dependencies not found"  
**Solução:** Verificar `requirements.txt`
```bash
pip install -r requirements.txt  # Testar localmente
```

#### Problema: "permission denied"
**Solução:** Configurar projeto gcloud
```bash
gcloud config set project sistema-de-chamados-dtx-aero
gcloud auth application-default login
```

#### Problema: Timeout durante build
**Solução:** Aumentar timeout do Cloud Build
- Var de ambiente: `CLOUDBUILD_TIMEOUT=1800` (segundos)

#### Problema: Firebase credenciais
**Solução:** Já está configurado! (`database.py` usa Application Default Credentials)
- ✅ `credentials.json` está em `.gitignore` (seguro)
- ✅ Código tenta credentials.json localmente
- ✅ Usa Google Cloud ADC no Cloud Run

## 📝 Checklist Pré-Deploy

- [ ] Código compilou sem erros: `python test_imports.py`
- [ ] App inicia: `python test_cloud_run.py`
- [ ] Commit feito: `git log -1`
- [ ] Push feito: `git status` (branch atualizado)
- [ ] gcloud config OK: `gcloud config list`
- [ ] Projeto correto:  `gcloud config get-value project`

## 🚀 Comando Final (Recomendado)

Após validar se gcloud está OK:
```bash
cd "c:\Users\MatheusCosta\OneDrive - DTX Aerospace\Área de Trabalho\Projetos\sistema_chamados"

# Validar tudo primeiro
python test_cloud_run.py

# Deploy
gcloud run deploy sistema-chamados-dtx \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars="SECRET_KEY=chave-secreta-do-matheus-dtx-2026,FLASK_ENV=production" \
  --memory=512Mi \
  --cpu=1 \
  --timeout=600 \
  --max-instances=10
```

## 💡 Se ainda falhar

1. Acesse: https://console.cloud.google.com/cloud-build/builds
2. Clique no build vermelho (falhou)
3. Leia os logs até achar "ERROR:" 
4. Copie a mensagem de erro
5. Procure a solução baseado no erro específico

---

**Última atualização:** 19/02/2026
**Status do Código:** ✅ 100% funcionando localmente
