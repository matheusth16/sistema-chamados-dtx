# Plano: 3 Melhorias Sprint

> **Status:** Todas as features verificadas e concluídas em 2026-06-18.
> Feature 3 (Graph API) concluída em sprint anterior. Features 1 e 2 verificadas em 2026-06-18 — todos os testes passando.

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

- [x] **1.1 HTML** — `app/templates/visualizar_chamado.html:164`
  - Adicionar `multiple` ao `<input type="file" id="modal-input-anexo">`
  - Mudar `name="anexo"` → `name="anexos_novos"` (evita conflito semântico)
  - Verificar: input aceita múltiplos arquivos

- [x] **1.2 JS** — `visualizar_chamado.html:409-425` (script no final do template)
  - Atualizar listener: quando `files.length > 1`, mostrar `"{N} arquivo(s) selecionado(s)"`; quando `files.length == 1`, mostrar o nome do único arquivo
  - Verificar: selecionar 2 arquivos → texto correto aparece

- [x] **1.3 Rota dashboard** — `app/routes/dashboard.py:227`
  - Mudar: `arquivo_anexo=request.files.get("anexo")`
  - Para: `arquivos_novos=request.files.getlist("anexos_novos")`
  - Verificar: parâmetro correto chega ao serviço

- [x] **1.4 Rota API** — `app/routes/api.py:200`
  - Mesmo ajuste: `.get("anexo")` → `.getlist("anexos_novos")`
  - Verificar: rota API aceita lista

- [x] **1.5 Serviço** — `app/services/edicao_chamado_service.py`
  - Mudar assinatura: `arquivo_anexo` → `arquivos_novos: list`
  - Substituir o bloco `# 5. Anexo` (linhas 181-214) por loop sobre a lista `arquivos_novos`
    - Para cada arquivo com `filename` válido: `salvar_anexo(arq)` e acumular em `anexos_existentes`
    - Um `Historico` por arquivo adicionado
  - Verificar: 2 arquivos enviados → ambos aparecem no chamado

- [x] **1.6 Testes** — Atualizar / criar testes que passam `arquivo_anexo=` para `arquivos_novos=`

---

## Feature 2 — Bloquear responsável = solicitante

**Diagnóstico:** Em `_resolver_responsavel()` (`chamados_criacao_service.py:35-73`), a opção 1 (manual) não checa se `responsavel_id_form == solicitante_id`. O fallback (opção 3, linha 69) já atribui o próprio solicitante — isso é comportamento de espera, não proibição, mas deixa o chamado sem responsável real.

**Regra de negócio:** Ninguém pode selecionar a si mesmo como responsável no formulário de criação. Se o único supervisor da área for o próprio solicitante, o sistema registra como "aguardando atribuição manual" (já ocorre no fallback).

### Tarefas

- [x] **2.1 Backend** — `app/services/chamados_criacao_service.py:47-54`
  - Na opção 1 (responsável escolhido via form), guard adicionado: `if responsavel_id_form and responsavel_nome_form and responsavel_id_form != solicitante_id:`
  - Verificar: se solicitante_id == responsavel_id_form → ignora e vai para auto-atribuição ✓

- [x] **2.2 Frontend** — `app/routes/api.py` endpoint `/api/supervisores/lista`
  - Filtro no endpoint (mais seguro): `if u.id != current_user.id` ao montar a lista
  - Verificar: supervisor logado não aparece como opção para si mesmo ✓

- [x] **2.3 Testes** — Caso: `responsavel_id_form == solicitante_id` → sistema ignora e auto-atribui

---

## Feature 3 — Trocar Brevo/SMTP por Microsoft Graph API

**Status: concluída em sprint anterior.**

`notifications.py` usa exclusivamente `_enviar_via_graph()` com as vars `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`, `GRAPH_SENDER_EMAIL`. Sem BREVO_API_KEY nem MAIL_*.

### Tarefas

- [x] **3.1 Config** — `config.py` sem variáveis MAIL_*; vars GRAPH_* presentes
- [x] **3.2 notifications.py** — `_enviar_via_graph()` implementada; Brevo/SMTP removidos
- [x] **3.3 `.env.example`** — seção Graph API com as 4 vars; sem MAIL_* ou BREVO_*
- [x] **3.4 Testes** — mocks via `patch('app.services.notifications._enviar_via_graph')`; testes passando

---

## Ordem de execução recomendada

1. **Feature 2** (mais simples, só backend + 1 endpoint) — risco baixo
2. **Feature 1** (HTML + 2 rotas + 1 serviço) — risco médio, sem quebra de API
3. **Feature 3** (substituição de provedor) — risco médio, testar com GRAPH_* env vars

## Done When

- [x] Multiple files: `edicao_chamado_service.py` aceita `arquivos_novos: list`; rotas usam `getlist("anexos_novos")`
- [x] Self-block: supervisor logado → não aparece em `/api/supervisores/lista`; guard em `chamados_criacao_service.py`
- [x] Graph API: `_enviar_via_graph()` em `notifications.py`; sem BREVO_API_KEY nem MAIL_*
- [x] `pytest --tb=short -q` passa sem erros (1435 testes, 94,98% cobertura, gate 52/52)
- [x] `bandit -r app/ -ll` — 0 High, 0 Medium
