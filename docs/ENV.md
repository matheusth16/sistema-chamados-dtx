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

| Variável              | Descrição | Padrão | Exemplo |
|-----------------------|-----------|--------|---------|
| `MAIL_SERVER`         | Host SMTP para envio de e-mails. | (vazio) | `smtp.gmail.com` |
| `MAIL_PORT`           | Porta SMTP. | `587` | `587` |
| `MAIL_USE_TLS`        | Usar TLS. Valores considerados verdadeiros: `true`, `1`, `yes`. | (como true) | `true` |
| `MAIL_USERNAME`       | Usuário SMTP. | (vazio) | `noreply@empresa.com` |
| `MAIL_PASSWORD`       | Senha ou app password SMTP. | (vazio) | (senha segura) |
| `MAIL_DEFAULT_SENDER` | Remetente padrão dos e-mails. | (vazio) | `Chamados DTX <noreply@empresa.com>` |

Se `MAIL_SERVER` estiver vazio, o envio por e-mail fica desabilitado.

---

## Microsoft Teams

| Variável            | Descrição | Padrão | Exemplo |
|---------------------|-----------|--------|---------|
| `TEAMS_WEBHOOK_URL` | URL do webhook do canal do Teams para notificações (ex.: novo chamado). | (vazio) | `https://outlook.office.com/webhook/...` |

Se vazia, notificações para Teams não são enviadas.

---

## Web Push (notificações no navegador)

| Variável            | Descrição | Padrão | Exemplo |
|---------------------|-----------|--------|---------|
| `VAPID_PUBLIC_KEY`  | Chave pública VAPID para Web Push. Gere com: `python scripts/gerar_vapid_keys.py`. | (vazio) | (string longa base64) |
| `VAPID_PRIVATE_KEY` | Chave privada VAPID. **Não exponha em repositórios.** | (vazio) | (string longa base64) |

Se ambas estiverem vazias, a inscrição/Web Push fica desabilitada.

---

## Logging

| Variável         | Descrição | Padrão | Exemplo |
|------------------|-----------|--------|---------|
| `LOG_LEVEL`      | Nível do log: `DEBUG`, `INFO`, `WARNING`, `ERROR`. Em produção use `INFO` ou `WARNING`. | `INFO` | `INFO` |
| `LOG_MAX_BYTES`  | Tamanho máximo por arquivo de log antes de rotação (bytes). | `2097152` (2 MB) | `5242880` |
| `LOG_BACKUP_COUNT` | Quantidade de arquivos de log rotacionados mantidos. | `5` | `10` |

Logs são gravados em `logs/sistema_chamados.log` (formato JSON com rotação).

---

## Firebase

O Firebase é inicializado em `app/database.py`:

- **Desenvolvimento:** arquivo `credentials.json` na raiz do projeto (conta de serviço do Firebase).
- **Produção (ex.: Cloud Run):** pode usar Application Default Credentials (não é obrigatório ter `credentials.json`).

Nenhuma variável de ambiente é obrigatória para o Firebase; o caminho do certificado é fixo em relação à raiz do projeto quando o arquivo existe.

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

# Recomendado com múltiplos workers
REDIS_URL=redis://:senha@redis-host:6379/0

# Opcionais: e-mail, Teams, Web Push, logging
# MAIL_SERVER=...
# TEAMS_WEBHOOK_URL=...
# VAPID_PUBLIC_KEY=...
# VAPID_PRIVATE_KEY=...
# LOG_LEVEL=INFO
```
