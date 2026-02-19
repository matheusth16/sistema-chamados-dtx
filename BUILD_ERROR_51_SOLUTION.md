# 🔧 Como Resolver o Erro do Cloud Build 51

## ✅ Confirmado: Código está OK
```
✓ Python 3.14.3
✓ 16 dependências instaladas
✓ Importações críticas funcionam  
✓ Aplicação Flask com 23 rotas
✓ WSGI entry point para gunicorn
✓ Firebase configurado
```

---

## 📋 Erro do Cloud Build
```
ERROR: failed to build: exit status 1
step exited with non-zero status: 51
```

Este erro é genérico do Buildpack. Precisa ver os **logs completos**.

---

## 🔍 Passo 1: Ver Logs Detalhados do Build

### No Google Cloud Console:
1. **Acesse:** https://console.cloud.google.com/cloud-build/builds?project=sistema-de-chamados-dtx-aero

2. **Clique no build que falhou** (com ❌ vermelho):
   - `31e209e6` (14:05) ← TENTE ESTE PRIMEIRO
   - ou `c0ec9637` (15:50)

3. **Procure pela aba "Logs"** e veja a mensagem de erro completa

4. **Procure por:**
   - `ERROR:`
   - `Failed to`
   - `ImportError:`
   - `ModuleNotFoundError:`
   - `permission denied`

### Copie a mensagem de erro

---

## 🛠️ Passo 2: Possíveis Soluções

### Erro A: "ModuleNotFoundError" ou "ImportError"
**Solução:** Falta dependência no `requirements.txt`

```bash
# Adicione a dependência faltante:
pip install nome-da-dependencia >> requirements.txt

# Commit e push
git add requirements.txt
git commit -m "fix: adicionar dependência faltante"
git push
```

### Erro B: "permission denied" ou "access denied"
**Solução:** Falta permissão do Cloud Build

```bash
# Adicione permissão ao serviço de build:
# 1. Acesse: https://console.cloud.google.com/iam-admin/iam
# 2. Encontre "Cloud Build Service Account"
# 3. Dê permissão: Editor ou Cloud Run Developer
```

### Erro C: "pip install failed"
**Solução:** Versão incompatível de dependência

```bash
# Atualize requirements.txt com versões específicas:
# Mude:
Flask
firebase-admin

# Para:
Flask==3.0.0
firebase-admin==6.1.0
# (use versões testadas localmente)

git add requirements.txt
git commit -m "fix: especificar versões das dependências"
git push
```

### Erro D: "Timeout"
**Solução:** Build levou muito tempo

```bash
# No Cloud Run console, aumente o timeout:
# gcloud run deploy sistema-chamados-dtx \
#   --source . \
#   ... (outros args)
#   --build-timeout=1800  # 30 minutos
```

### Erro E: "ResourceExhausted" ou memória insuficiente
**Solução:** Aumentar memória do builder

Isso é limitação do projeto Google Cloud. Contate suporte ou:
- Use `--memory=2Gi` no deploy

---

## 💡 Passo 3: Deploy Mais Simples

Se os logs não mostram o erro específico, tente um deploy simplificado:

```bash
# 1. Crie um arquivo simples de teste
# cat > requirements-minimal.txt << EOF
# Flask==3.0.0
# firebase-admin==6.1.0
# gunicorn==21.2.0
# python-dotenv
# pandas
# openpyxl
# EOF

# 2. Tente deploy com versões fixas
gcloud run deploy sistema-chamados-dtx \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars="SECRET_KEY=chave-secreta" \
  --build-timeout=1800 \
  --memory=512Mi
```

---

## 🔄 Passo 4: Se Ainda Falhar

### Opção A: Limpar cache do build

```bash
# Forçar rebuild sem cache
gcloud run deploy sistema-chamados-dtx \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --no-cache  # ← ADICIONE ISTO
```

### Opção B: Criar novo Push Trigger

Às vezes o problema é no trigger de build. Recrie:

1. Acesse: https://console.cloud.google.com/cloud-build/triggers
2. Delete o trigger antigo
3. Recrie: `Cloud Build` → `Create Trigger` → GitHub → `Sistema-chamados-dtx` → Crie novo

### Opção C: Usar Cloud Build manualmente

```bash
gcloud builds submit --region=us-central1 \
  --config=cloudbuild.yaml \
  --timeout=1800
```

Crie arquivo `cloudbuild.yaml`:
```yaml
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', 'us-central1-docker.pkg.dev/$PROJECT_ID/cloud-run-repo/sistema-chamados-dtx', '.']
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'us-central1-docker.pkg.dev/$PROJECT_ID/cloud-run-repo/sistema-chamados-dtx']
  - name: 'gcr.io/cloud-builders/gke-deploy'
    args:
      - run
      - --filename=k8s/
      - --image=us-central1-docker.pkg.dev/$PROJECT_ID/cloud-run-repo/sistema-chamados-dtx
      - --location=us-central1
      - --namespace=production
options:
  machineType: 'N1_HIGHCPU_8'
timeout: 1800s
```

---

## 📋 Checklist Rápido

- [ ] Via os logs completos do build no Cloud Console?
- [ ] Encontrou a mensagem `ERROR:`?
- [ ] Tentou fazer git push de novo?
- [ ] Espera um pouco antes de fazer novo deploy
- [ ] Cloud Build é gerado automaticamente a cada push?

---

## 🚀 Comando Final Recomendado

```bash
cd "c:\Users\MatheusCosta\OneDrive - DTX Aerospace\Área de Trabalho\Projetos\sistema_chamados"

# Teste localmente
python diagnose_build.py

# Se tudo OK:
git status  # Veja se há mudanças
git add .
git commit -m "fix: Cloud Build diagnostics"
git push

# Espere 2-3 minutos o Cloud Build criar automaticamente
# Acesse: https://console.cloud.google.com/cloud-build/builds
```

---

## 📞 Próximos Passos

1. **Clique num build que falhou** no Cloud Console
2. **Vá para "Logs Build"** (abaixo da tabela)
3. **Procure por "ERROR"** 
4. **Copie a mensagem completa**
5. **Tente a solução correspondente** acima

---

**Seu código está OK - o problema é no Google Cloud Build!**
