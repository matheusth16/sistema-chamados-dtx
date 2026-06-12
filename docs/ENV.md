# Variáveis de ambiente

Referência das variáveis de ambiente usadas pelo Sistema de Chamados DTX.
Copie `.env.example` para `.env` e preencha conforme o ambiente (desenvolvimento ou produção).

---

## Obrigatórias em produção

| Variável      | Descrição | Exemplo |
|---------------|-----------|---------|
| `SECRET_KEY`  | Chave secreta do Flask (sessões, CSRF, cookies). Em produção **deve** ser forte e único. | `openssl rand -hex 32` → ex.: `a1b2c3d4e5...` |
| `FLASK_ENV`   | Ambiente da aplicação. Em produção a aplicação exige `SECRET_KEY` definida. | `development` ou `production` |

**Produção:** Defina `FLASK_ENV=production` e `SECRET_KEY` com valor gerado (ex.: `openssl rand -hex 32`). Não use o valor padrão de desenvolvimento.

---

## Servidor (run.py)

| Variável      | Descrição | Padrão | Exemplo |
|---------------|-----------|--------|---------|
| `PORT`        | Porta HTTP em que o servidor sobe. | `5000` | `8080` |
| `FLASK_HOST`  | Host de bind. Em desenvolvimento costuma ser `127.0.0.1`. | `127.0.0.1` (dev) / `localhost` (prod) | `0.0.0.0` |
| `ENV`         | Alternativa a `FLASK_ENV` (usa-se se `FLASK_ENV` não estiver definida). | — | `production` |

---

## Redis (rate limit e cache)

| Variável   | Descrição | Padrão | Exemplo |
|------------|-----------|--------|---------|
| `REDIS_URL` | URL do Redis para rate limiting (Flask-Limiter) e cache (relatórios/listas). Se vazia, usa memória local por processo (limites não compartilhados entre workers). **Recomendado em produção** com Gunicorn/Cloud Run para compartilhar limite e cache entre processos. | `memory://` | `redis://localhost:6379/0` ou `redis://:senha@host:6379/0` |

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

O envio de e-mail usa **SMTP**. Configure as variáveis abaixo.

| Variável              | Descrição | Padrão | Exemplo |
|-----------------------|-----------|--------|---------|
| `MAIL_SERVER`         | Host SMTP para envio de e-mails. | (vazio) | `smtp.gmail.com` |
| `MAIL_PORT`           | Porta SMTP. | `587` | `587` |
| `MAIL_USE_TLS`        | Usar TLS. Valores considerados verdadeiros: `true`, `1`, `yes`. | (como true) | `true` |
| `MAIL_USERNAME`       | Usuário SMTP. | (vazio) | `noreply@empresa.com` |
| `MAIL_PASSWORD`       | Senha ou app password SMTP. | (vazio) | (senha segura) |
| `MAIL_DEFAULT_SENDER` | Remetente padrão dos e-mails. | (vazio) | `Chamados DTX <noreply@empresa.com>` |

Se `MAIL_SERVER` estiver vazio, o envio por e-mail fica desabilitado.

| `NOTIFY_SOLICITANTE_EMAIL` | Ativa e-mail ao solicitante em mudança de status para *Em Atendimento* ou *Concluído*. Requer `MAIL_SERVER` configurado. | `false` | `true` |
| `POWER_AUTOMATE_TEST_DEST_EMAIL` | Sobrescreve destinatário do evento `USUARIO_CADASTRADO` — para testar fluxo Power Automate sem enviar ao usuário real. | (vazio) | `dev@empresa.com` |

**Office 365 / Outlook:** use `MAIL_SERVER=smtp.office365.com`, `MAIL_PORT=587`, `MAIL_USE_TLS=true`. O administrador do tenant pode precisar habilitar "Authenticated SMTP" na caixa de correio (Manage email apps). Com MFA, use senha de app.

---

## Web Push (notificações no navegador)

| Variável            | Descrição | Padrão | Exemplo |
|---------------------|-----------|--------|---------|
| `VAPID_PUBLIC_KEY`  | Chave pública VAPID para Web Push. Gere com: `python scripts/gerar_vapid_keys.py`. | (vazio) | (string longa base64) |
| `VAPID_PRIVATE_KEY` | Chave privada VAPID. **Não exponha em repositórios.** | (vazio) | (string longa base64) |

Se ambas estiverem vazias, a inscrição/Web Push fica desabilitada.

---

## Criptografia de PII em repouso (LGPD — roadmap)

> **Atenção:** as variáveis abaixo estão reservadas, mas a funcionalidade **não está implementada** ainda. Defini-las não tem efeito no comportamento atual da aplicação.

| Variável               | Descrição | Padrão | Exemplo |
|------------------------|-----------|--------|---------|
| `ENCRYPTION_KEY`       | Chave Fernet (base64, 32 bytes) para criptografia futura do campo `nome` em Firestore. Quando implementada, exigirá migração dos dados existentes. | (vazio) | (string base64) |
| `ENCRYPT_PII_AT_REST`  | Quando `true` e `ENCRYPTION_KEY` definida, ativará a criptografia. Sem efeito até implementação. | `false` | `true` |

---

## Armazenamento de Anexos — Cloudflare R2 (alternativo ao Firebase Storage)

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `R2_ACCOUNT_ID` | ID da conta Cloudflare. | (vazio) |
| `R2_ACCESS_KEY_ID` | Access Key ID do R2. | (vazio) |
| `R2_SECRET_ACCESS_KEY` | Secret Access Key do R2. **Mantenha secreta.** | (vazio) |
| `R2_BUCKET_NAME` | Nome do bucket R2. | (vazio) |
| `R2_PUBLIC_URL` | URL pública do bucket (se acesso público habilitado). | (vazio) |

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

## Auditoria de dependências

Execute periodicamente para verificar vulnerabilidades conhecidas nas dependências Python:

```bash
pip audit
```

Recomenda-se integrar `pip audit` no pipeline de CI e corrigir vulnerabilidades reportadas. Ver também `requirements.txt` na raiz do projeto.

---

## Firebase

O Firebase é inicializado em `app/database.py`:

- **Desenvolvimento:** arquivo `credentials.json` na raiz do projeto (conta de serviço do Firebase).
- **Produção (ex.: Cloud Run):** usa Application Default Credentials (ADC).

| Variável | Descrição | Obrigatório em produção |
|----------|-----------|-------------------------|
| `FIREBASE_STORAGE_BUCKET` | Nome **exato** do bucket do Firebase Storage (Firebase Console > Storage: use o valor do bucket, ex. `projeto.firebasestorage.app` ou `projeto.appspot.com`). Sem isso, em produção os uploads falham. A conta de serviço do Cloud Run precisa da permissão **Storage Object Admin** no bucket. Se não definir, o app tenta `GOOGLE_CLOUD_PROJECT.firebasestorage.app` no Cloud Run. | **Recomendado** (senão usa projeto.firebasestorage.app se GOOGLE_CLOUD_PROJECT estiver definido) |

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
APP_BASE_URL=https://seu-dominio.com

# Para anexos no Cloud Run (use o bucket do Firebase Console > Storage, ex.: projeto.firebasestorage.app)
# FIREBASE_STORAGE_BUCKET=seu-projeto.firebasestorage.app

# Recomendado com múltiplos workers
REDIS_URL=redis://:senha@redis-host:6379/0

# Opcionais: e-mail, Web Push, logging
# MAIL_SERVER=...
# VAPID_PUBLIC_KEY=...
# VAPID_PRIVATE_KEY=...
# LOG_LEVEL=INFO
```
