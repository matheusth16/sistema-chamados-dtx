# Plano: 3 Melhorias Sprint

## Goal
Três mudanças pontuais no sistema de chamados:
1. Múltiplos anexos ao adicionar em chamado existente
2. Bloquear responsável = solicitante na criação de chamado
3. Trocar Brevo/SMTP por Microsoft Graph API para envio de e-mail

---

## Mapa de impacto por feature

| Feature | Arquivos alterados |
|---|---|
| 1 - Multi-anexo (add) | `visualizar_chamado.html`, `dashboard.py:227`, `api.py:200`, `edicao_chamado_service.py` |
| 2 - Anti-self-ticket | `chamados_criacao_service.py`, `validators.py` (ou inline) |
| 3 - Graph API | `notifications.py`, `config.py`, `.env.example` |

---

## Feature 1 — Múltiplos anexos ao adicionar (chamado existente)

**Diagnóstico:** O input em `visualizar_chamado.html:164` não tem `multiple`. A rota `dashboard.py:227` usa `.get("anexo")` (um arquivo). O serviço `edicao_chamado_service.py:182` recebe um único `arquivo_anexo`.

### Tarefas

- [ ] **1.1 HTML** — `app/templates/visualizar_chamado.html:164`
  - Adicionar `multiple` ao `<input type="file" id="modal-input-anexo">`
  - Mudar `name="anexo"` → `name="anexos_novos"` (evita conflito semântico)
  - Verificar: input aceita múltiplos arquivos

- [ ] **1.2 JS** — `visualizar_chamado.html:409-425` (script no final do template)
  - Atualizar listener: quando `files.length > 1`, mostrar `"{N} arquivo(s) selecionado(s)"`; quando `files.length == 1`, mostrar o nome do único arquivo
  - Verificar: selecionar 2 arquivos → texto correto aparece

- [ ] **1.3 Rota dashboard** — `app/routes/dashboard.py:227`
  - Mudar: `arquivo_anexo=request.files.get("anexo")`
  - Para: `arquivos_novos=request.files.getlist("anexos_novos")`
  - Verificar: parâmetro correto chega ao serviço

- [ ] **1.4 Rota API** — `app/routes/api.py:200`
  - Mesmo ajuste: `.get("anexo")` → `.getlist("anexos_novos")`
  - Verificar: rota API aceita lista

- [ ] **1.5 Serviço** — `app/services/edicao_chamado_service.py`
  - Mudar assinatura: `arquivo_anexo` → `arquivos_novos: list`
  - Substituir o bloco `# 5. Anexo` (linhas 181-214) por loop sobre a lista `arquivos_novos`
    - Para cada arquivo com `filename` válido: `salvar_anexo(arq)` e acumular em `anexos_existentes`
    - Um `Historico` por arquivo adicionado
  - Verificar: 2 arquivos enviados → ambos aparecem no chamado

- [ ] **1.6 Testes** — Atualizar / criar testes que passam `arquivo_anexo=` para `arquivos_novos=`

---

## Feature 2 — Bloquear responsável = solicitante

**Diagnóstico:** Em `_resolver_responsavel()` (`chamados_criacao_service.py:35-73`), a opção 1 (manual) não checa se `responsavel_id_form == solicitante_id`. O fallback (opção 3, linha 69) já atribui o próprio solicitante — isso é comportamento de espera, não proibição, mas deixa o chamado sem responsável real.

**Regra de negócio:** Ninguém pode selecionar a si mesmo como responsável no formulário de criação. Se o único supervisor da área for o próprio solicitante, o sistema registra como "aguardando atribuição manual" (já ocorre no fallback).

### Tarefas

- [ ] **2.1 Backend** — `app/services/chamados_criacao_service.py:47-54`
  - Na opção 1 (responsável escolhido via form), adicionar guard:
    ```python
    if responsavel_id_form == solicitante_id:
        # Pula para auto-atribuição — não permite self-assign
        pass  # (vai cair no bloco de auto-atribuição abaixo)
    elif responsavel_id_form and responsavel_nome_form:
        ...  # lógica atual
    ```
  - Verificar: se solicitante_id == responsavel_id_form → ignora e vai para auto-atribuição

- [ ] **2.2 Frontend** — `app/templates/formulario.html`
  - No JS que popula o dropdown de supervisores (`/api/supervisores/lista`): filtrar o `current_user.id` da lista antes de renderizar as opções
  - Ou: no endpoint `/api/supervisores/lista` (`app/routes/api.py`) → excluir da resposta o usuário logado
  - Preferir filtro no endpoint (mais seguro): adicionar `if u.id != current_user.id` ao montar a lista
  - Verificar: supervisor logado não aparece como opção para si mesmo

- [ ] **2.3 Testes** — Caso: `responsavel_id_form == solicitante_id` → sistema ignora e auto-atribui

---

## Feature 3 — Trocar Brevo/SMTP por Microsoft Graph API

**Diagnóstico:** `notifications.py` tem `_enviar_via_brevo()` (linhas 63-113) e SMTP inline em `enviar_email()` (linhas 137-193). A função `enviar_email()` é o único ponto de envio — todos os outros `notificar_*` a chamam.

**Graph API (client credentials):**
1. POST `https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token`
   - body: `client_id`, `client_secret`, `scope=https://graph.microsoft.com/.default`, `grant_type=client_credentials`
   - → obtém `access_token`
2. POST `https://graph.microsoft.com/v1.0/users/{SENDER_EMAIL}/sendMail`
   - header: `Authorization: Bearer {access_token}`
   - body JSON: `{ "message": { "subject": "...", "body": { "contentType": "HTML", "content": "..." }, "toRecipients": [{ "emailAddress": { "address": "..." } }] } }`

**Vars de ambiente necessárias:**
- `GRAPH_TENANT_ID` — Directory (tenant) ID
- `GRAPH_CLIENT_ID` — Application (client) ID
- `GRAPH_CLIENT_SECRET` — Secret value (o "value" fornecido pelo TI)
- `GRAPH_SENDER_EMAIL` — caixa de envio (ex: `dtxls.support@dtx.aero`)

### Tarefas

- [ ] **3.1 Config** — `config.py`
  - Remover: `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_TLS`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_DEFAULT_SENDER`
  - Adicionar: `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`, `GRAPH_SENDER_EMAIL`
  - Manter: `NOTIFY_RELAY_EMAIL`, `NOTIFY_SOLICITANTE_EMAIL`, `POWER_AUTOMATE_TEST_DEST_EMAIL`

- [ ] **3.2 notifications.py** — Remover Brevo + SMTP, adicionar Graph
  - Remover: `import smtplib`, `import time`, `from email.mime.*`
  - Remover: função `_enviar_via_brevo()` inteira (linhas 63-113)
  - Remover: `_SMTP_MAX_TENTATIVAS` e `_SMTP_BACKOFF_BASE`
  - Remover: `_mail_setting()` (não mais necessária)
  - Adicionar: função `_enviar_via_graph(destinatario, assunto, corpo_html, corpo_texto, from_addr)` usando `urllib.request` (sem lib extra):
    - Passo 1: obter token OAuth2 via POST (sem timeout excessivo, 10s)
    - Passo 2: enviar via Graph sendMail (timeout 15s)
    - Retorna `(True, None)` ou `(False, erro_str)`
  - Reescrever `enviar_email()`: remover lógica de Brevo/SMTP, chamar `_enviar_via_graph()`
  - Manter: `_config()`, `_base_url()`, `_link_chamado()`, `_link_dashboard()`, `_relay_email()`, `_disparar_evento_power_automate()`, todos os `notificar_*`

- [ ] **3.3 `.env.example`**
  - Remover linhas de MAIL_SERVER, MAIL_PORT, MAIL_USE_TLS, MAIL_USERNAME, MAIL_PASSWORD, MAIL_DEFAULT_SENDER, BREVO_API_KEY
  - Adicionar seção Graph API com as 4 vars (valores de placeholder)

- [ ] **3.4 Testes** — Atualizar mocks: `patch('app.services.notifications._enviar_via_graph')` em vez de Brevo/SMTP
  - Verificar: testes de notificação passam sem BREVO_API_KEY e sem MAIL_*

---

## Ordem de execução recomendada

1. **Feature 2** (mais simples, só backend + 1 endpoint) — risco baixo
2. **Feature 1** (HTML + 2 rotas + 1 serviço) — risco médio, sem quebra de API
3. **Feature 3** (substituição de provedor) — risco médio, testar com Railway env vars

## Done When

- [ ] Multiple files: selecionar 3 arquivos no "Novo Anexo" → todos aparecem na lista de anexos do chamado
- [ ] Self-block: supervisor logado → não aparece na lista de responsáveis do próprio formulário
- [ ] Graph API: novo chamado criado → responsável recebe e-mail via M365 (Graph), sem BREVO_API_KEY nem MAIL_* configurados
- [ ] `pytest --tb=short -q` passa sem erros
- [ ] `bandit -r app/ -ll` passa sem falhas críticas
