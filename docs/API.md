# API — DTX Digital Andon System

Referência completa dos endpoints JSON utilizados pelo frontend.
Atualizado em: 2026-06-10 | Versão: 1.0

---

## Visão Geral

| Propriedade | Valor |
|-------------|-------|
| **Base URL** | Mesma origem do frontend (ex.: `https://seu-dominio.up.railway.app`) |
| **Formato** | JSON em todos os endpoints (exceto `/api/download-anexo` e `/sw.js`) |
| **Autenticação** | Sessão Flask-Login (cookie de sessão) |
| **CSRF** | Header `X-CSRFToken` obrigatório em todos os POST com JSON |

### Padrão de resposta

**Sucesso:**
```json
{ "sucesso": true, "dados": { ... } }
```

**Erro:**
```json
{ "sucesso": false, "erro": "mensagem descritiva" }
```

### CSRF

Para POSTs com JSON, inclua o token no header HTTP:
```
X-CSRFToken: <valor da meta tag <meta name="csrf-token">>
```

Para POSTs com `FormData` (multipart), o token é lido automaticamente do cookie.

### Códigos de status comuns

| Código | Significado |
|--------|-------------|
| `200` | Sucesso |
| `302` | Redirecionamento (download de anexo) |
| `400` | Requisição inválida (parâmetro ausente ou formato incorreto) |
| `403` | Sem permissão (perfil inadequado ou recurso de outro usuário) |
| `404` | Recurso não encontrado |
| `500` | Erro interno (mensagem genérica; detalhes nos logs) |
| `503` | Serviço temporariamente indisponível |

---

## Autenticação

Todas as rotas (exceto `/health` e `/sw.js`) exigem que o usuário esteja autenticado.
Requisições não autenticadas recebem **302 → `/login`** (não JSON).

**Perfis:**
- `solicitante` — acesso ao próprio chamado
- `supervisor` — acesso a chamados da(s) área(s) + relatórios
- `admin` — acesso total

---

## Índice de Endpoints

| Método | URL | Auth | Perfil mínimo |
|--------|-----|------|---------------|
| GET | `/health` | Não | — |
| GET | `/api/download-anexo` | Sim | solicitante |
| POST | `/api/atualizar-status` | Sim | supervisor |
| POST | `/api/editar-chamado` | Sim | supervisor |
| POST | `/api/bulk-status` | Sim | supervisor |
| GET | `/api/chamado/<id>` | Sim | solicitante |
| GET | `/api/chamados/paginar` | Sim | supervisor |
| POST | `/api/carregar-mais` | Sim | supervisor |
| POST | `/api/chamado/<id>/confirmar-resolucao` | Sim | solicitante |
| GET | `/api/notificacoes` | Sim | solicitante |
| GET | `/api/notificacoes/contar` | Sim | solicitante |
| POST | `/api/notificacoes/<id>/ler` | Sim | solicitante |
| POST | `/api/notificacoes/ler-todas` | Sim | solicitante |
| GET | `/api/push-vapid-public` | Sim | solicitante |
| POST | `/api/push-subscribe` | Sim | solicitante |
| POST | `/api/onboarding/avancar` | Sim | solicitante |
| POST | `/api/onboarding/concluir` | Sim | solicitante |
| POST | `/api/onboarding/pular` | Sim | solicitante |
| GET | `/api/supervisores/lista` | Sim | solicitante |
| GET | `/sw.js` | Não | — |

---

## Health Check

### `GET /health`

Verifica disponibilidade da aplicação. Não exige autenticação.

**Modo raso (padrão):** resposta imediata sem I/O — usado pelo Railway healthcheck.
**Modo deep (`?deep=1`):** verifica Firestore e cache — usado por UptimeRobot/BetterUptime.

**Query params:**

| Parâmetro | Valores | Descrição |
|-----------|---------|-----------|
| `deep` | `1` ou `true` | Ativa verificação de dependências |

**Resposta 200 — modo raso:**
```json
{ "status": "ok" }
```

**Resposta 200 — modo deep (tudo saudável):**
```json
{
  "status": "ok",
  "checks": {
    "firestore": "ok",
    "cache": "ok"
  },
  "duration_ms": 42.3,
  "version": "a1b2c3d"
}
```

**Resposta 503 — modo deep (Firestore indisponível):**
```json
{
  "status": "degraded",
  "checks": {
    "firestore": "error:ConnectionError",
    "cache": "ok"
  },
  "duration_ms": 2041.0,
  "version": "a1b2c3d"
}
```

> `cache: "degraded:..."` é informacional — não altera o `status` geral nem o código HTTP.

---

## Chamados

### `GET /api/download-anexo`

Gera URL pré-assinada (1 hora) para download de anexo privado no Cloudflare R2.

**Auth:** Sim — solicitante só pode baixar anexos dos próprios chamados.

**Query params:**

| Parâmetro | Obrigatório | Descrição |
|-----------|-------------|-----------|
| `chamado_id` | Sim | ID do chamado no Firestore |
| `chave` | Sim | Chave R2 do anexo (formato `r2:<caminho>`) |

**Resposta:**
- `302` — redireciona para a URL pré-assinada do R2
- `400` — parâmetros ausentes ou `chave` sem prefixo `r2:`
- `403` — chamado pertence a outro usuário
- `404` — chamado não encontrado
- `503` — falha ao gerar URL (problema no R2)

**Exemplo:**
```
GET /api/download-anexo?chamado_id=abc123&chave=r2:uploads/chamados/abc123/doc.pdf
```

---

### `POST /api/atualizar-status`

Atualiza o status de um chamado. Supervisor/admin operam normalmente; solicitante só pode usar ações específicas (ex.: reabrir via `confirmar-resolucao`).

**Auth:** Sim | **CSRF:** Obrigatório

**Headers:**
```
Content-Type: application/json
X-CSRFToken: <token>
X-Requested-With: XMLHttpRequest
```

**Corpo:**
```json
{
  "chamado_id": "abc123",
  "novo_status": "Concluído",
  "motivo_cancelamento": "Problema resolvido externamente"
}
```

| Campo | Tipo | Obrigatório | Valores |
|-------|------|-------------|---------|
| `chamado_id` | string | Sim | ID Firestore |
| `novo_status` | string | Sim | `Aberto`, `Em Atendimento`, `Concluído`, `Cancelado` |
| `motivo_cancelamento` | string | Sim se `Cancelado` | Texto livre |

**Respostas:**

- **200** — Status atualizado:
```json
{
  "sucesso": true,
  "mensagem": "Status alterado para Concluído",
  "novo_status": "Concluído"
}
```

- **400** — Parâmetro ausente ou status inválido:
```json
{ "sucesso": false, "erro": "Status inválido \"Encerrado\"" }
```

- **403** — Sem permissão para alterar este chamado/status:
```json
{ "sucesso": false, "erro": "Apenas o responsável ou admin pode concluir este chamado" }
```

- **404** — Chamado não encontrado
- **500** — Erro interno

**Exemplo cURL:**
```bash
curl -X POST https://dominio.up.railway.app/api/atualizar-status \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: SEU_TOKEN_CSRF" \
  -b "session=COOKIE_DE_SESSAO" \
  -d '{"chamado_id":"abc123","novo_status":"Em Atendimento"}'
```

**Exemplo JavaScript (fetch):**
```javascript
const csrfToken = document.querySelector('meta[name="csrf-token"]').content;

const resp = await fetch('/api/atualizar-status', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-CSRFToken': csrfToken,
    'X-Requested-With': 'XMLHttpRequest',
  },
  body: JSON.stringify({ chamado_id: 'abc123', novo_status: 'Em Atendimento' }),
});
const { sucesso, mensagem, erro } = await resp.json();
```

---

### `POST /api/editar-chamado`

Edita campos do chamado (status, descrição, responsável, SLA, setores adicionais, anexo).
Apenas **supervisor** ou **admin**. Supervisor só pode editar chamados da própria área.

**Auth:** Sim | **Content-Type:** `multipart/form-data`

**Campos (FormData):**

| Campo | Obrigatório | Descrição |
|-------|-------------|-----------|
| `chamado_id` | Sim | ID Firestore do chamado |
| `novo_status` | Não | `Aberto`, `Em Atendimento`, `Concluído`, `Cancelado` |
| `motivo_cancelamento` | Não | Obrigatório quando `novo_status=Cancelado` |
| `nova_descricao` | Não | Substitui a descrição atual |
| `novo_responsavel_id` | Não | UID do novo responsável (supervisor/admin) |
| `sla_dias` | Não | Número de dias para o prazo SLA |
| `setores_adicionais` | Não | Lista de setores (campo repetível no form) |
| `anexo` | Não | Arquivo a ser adicionado à lista de anexos |

**Resposta 200:**
```json
{
  "sucesso": true,
  "mensagem": "Chamado atualizado com sucesso",
  "dados": {
    "novo_status": "Concluído",
    "nova_descricao": "...",
    "responsavel": "Nome do Responsável"
  }
}
```

- **400** — `chamado_id` ausente ou validação falhou
- **403** — Perfil solicitante ou supervisor de outra área
- **404** — Chamado não encontrado
- **500** — Erro interno

---

### `POST /api/bulk-status`

Atualiza o status de múltiplos chamados em lote. Apenas **supervisor** ou **admin**.
Supervisor só atualiza chamados da própria área ou que é responsável.
Limite: 50 chamados por requisição.

**Auth:** Sim | **CSRF:** Obrigatório

**Corpo:**
```json
{
  "chamado_ids": ["id1", "id2", "id3"],
  "novo_status": "Concluído"
}
```

| Campo | Tipo | Obrigatório | Valores |
|-------|------|-------------|---------|
| `chamado_ids` | array de strings | Sim | Máx. 50 IDs |
| `novo_status` | string | Sim | `Aberto`, `Em Atendimento`, `Concluído` |

> Nota: `Cancelado` não é aceito no bulk (exige motivo individual).

**Resposta 200** (sempre retorna 200 mesmo com erros parciais):
```json
{
  "sucesso": true,
  "atualizados": 3,
  "total_solicitados": 5,
  "erros": [
    { "id": "id4", "erro": "Não encontrado" },
    { "id": "id5", "erro": "Sem permissão para este chamado" }
  ]
}
```

- **400** — `chamado_ids` não é lista ou `novo_status` inválido
- **403** — Perfil não é supervisor/admin

---

### `GET /api/chamado/<chamado_id>`

Retorna dados completos de um chamado por ID.
Controle de acesso: solicitante vê apenas o próprio chamado; supervisor vê da área; admin vê todos.

**Auth:** Sim

**URL params:** `chamado_id` — ID Firestore do chamado.

**Resposta 200:**
```json
{
  "sucesso": true,
  "chamado": {
    "id": "abc123",
    "numero_chamado": "CHM-0042",
    "rl_codigo": "RL-2024-001",
    "categoria": "Manutenção",
    "tipo_solicitacao": "Planejamento",
    "gate": "G1",
    "responsavel": "João Silva",
    "descricao": "Texto completo da solicitação...",
    "data_abertura": "10/06/2026 14:30",
    "status": "Em Atendimento",
    "sla_info": {
      "prazo_dias": 3,
      "status_sla": "no_prazo",
      "percentual": 45
    }
  }
}
```

- **403** — Chamado de outro usuário/área
- **404** — Chamado não encontrado

---

### `GET /api/chamados/paginar`

Lista chamados com filtros e paginação por cursor. Para uso no dashboard (supervisor/admin).

**Auth:** Sim

**Query params:**

| Parâmetro | Padrão | Descrição |
|-----------|--------|-----------|
| `limite` | `50` | Registros por página (1–100) |
| `cursor` | — | ID do último documento da página anterior |
| `status` | — | Filtro: `Aberto`, `Em Atendimento`, `Concluído`, `Cancelado` |
| `gate` | — | Filtro por gate |
| `categoria` | — | Filtro por categoria |
| `responsavel` | — | Filtro por nome do responsável |
| `search` | — | Busca em descrição, número, RL, responsável |

**Resposta 200:**
```json
{
  "sucesso": true,
  "chamados": [
    {
      "id": "abc123",
      "numero": "CHM-0042",
      "categoria": "Manutenção",
      "rl_codigo": "RL-001",
      "tipo": "Planejamento",
      "responsavel": "João Silva",
      "status": "Aberto",
      "prioridade": 2,
      "descricao_resumida": "Texto resumido até 100 caracteres...",
      "data_abertura": "10/06/2026 14:30",
      "data_conclusao": null
    }
  ],
  "paginacao": {
    "cursor_proximo": "abc456",
    "tem_proxima": true,
    "total_pagina": 50,
    "limite": 50
  }
}
```

---

### `POST /api/carregar-mais`

Carrega próxima página de chamados (infinite scroll). Filtros via query params da URL atual.

**Auth:** Sim | **CSRF:** Obrigatório

**Corpo:**
```json
{
  "cursor": "id_ultimo_doc",
  "limite": 20
}
```

| Campo | Padrão | Máximo |
|-------|--------|--------|
| `cursor` | — | — |
| `limite` | `20` | `50` |

**Resposta 200:**
```json
{
  "sucesso": true,
  "chamados": [
    {
      "id": "...",
      "numero": "CHM-0043",
      "categoria": "TI",
      "status": "Aberto",
      "responsavel": "Maria Santos",
      "data_abertura": "10/06/2026 15:00"
    }
  ],
  "cursor_proximo": "abc789",
  "tem_proxima": false
}
```

---

### `POST /api/chamado/<chamado_id>/confirmar-resolucao`

Solicitante confirma ou rejeita a resolução de um chamado com status `Concluído`.
Apenas o **solicitante dono** do chamado, quando `confirmacao_solicitante == "pendente"`.

**Auth:** Sim | **CSRF:** Obrigatório

**URL params:** `chamado_id`

**Corpo:**
```json
{
  "acao": "reabrir",
  "motivo": "O problema não foi resolvido corretamente."
}
```

| Campo | Obrigatório | Valores | Notas |
|-------|-------------|---------|-------|
| `acao` | Sim | `confirmar`, `reabrir` | |
| `motivo` | Sim se `reabrir` | Texto livre | |

**Resposta 200:**
```json
{ "sucesso": true }
```

- `acao: "confirmar"` → atualiza `confirmacao_solicitante = "confirmado"`
- `acao: "reabrir"` → reverte status para `Aberto`, registra histórico com o motivo

**Erros:**
- **400** — `acao` inválida, `motivo` ausente para `reabrir`, ou chamado não aguarda confirmação
- **403** — Usuário não é o solicitante ou não tem perfil `solicitante`
- **404** — Chamado não encontrado

---

## Notificações in-app

### `GET /api/notificacoes`

Lista notificações do usuário logado (para o sino de notificações).

**Query params:**

| Parâmetro | Descrição |
|-----------|-----------|
| `nao_lidas=1` | Retorna apenas notificações não lidas |

**Resposta 200:**
```json
{
  "sucesso": true,
  "notificacoes": [
    {
      "id": "notif_123",
      "chamado_id": "abc123",
      "numero_chamado": "CHM-0042",
      "mensagem": "Status do CHM-0042 alterado para Em Atendimento",
      "lida": false,
      "data": "10/06/2026 14:30"
    }
  ],
  "total_nao_lidas": 3
}
```

Limite: 30 notificações por chamada.

---

### `GET /api/notificacoes/contar`

Retorna apenas o contador de notificações não lidas. Mais leve que `/api/notificacoes` — use para polling periódico.

**Resposta 200:**
```json
{ "total_nao_lidas": 3 }
```

> Sempre retorna `200` mesmo em caso de erro interno (retorna `0` para não quebrar a UI).

---

### `POST /api/notificacoes/<notificacao_id>/ler`

Marca uma notificação específica como lida. Apenas a notificação do próprio usuário.

**Auth:** Sim | **CSRF:** Obrigatório

**URL params:** `notificacao_id`

**Resposta 200:**
```json
{ "sucesso": true }
```

Em erro: `{ "sucesso": false }` com status `500`.

---

### `POST /api/notificacoes/ler-todas`

Marca todas as notificações do usuário logado como lidas.

**Auth:** Sim | **CSRF:** Obrigatório

**Corpo:** vazio (`{}`)

**Resposta 200:**
```json
{ "sucesso": true, "atualizadas": 5 }
```

- `atualizadas`: quantidade de notificações marcadas como lidas nesta operação.

---

## Web Push

### `GET /api/push-vapid-public`

Retorna a chave pública VAPID para configuração do Web Push no navegador.

**Auth:** Sim

**Resposta 200:**
```json
{ "vapid_public_key": "BG8dou6GR4q..." }
```

---

### `POST /api/push-subscribe`

Registra ou atualiza a inscrição Web Push do navegador para o usuário logado.

**Auth:** Sim | **CSRF:** Obrigatório

**Corpo:**
```json
{
  "subscription": {
    "endpoint": "https://fcm.googleapis.com/fcm/send/...",
    "keys": {
      "p256dh": "BNcRdreA...",
      "auth": "tBHItJI..."
    }
  }
}
```

> `subscription` é o objeto retornado por `ServiceWorkerRegistration.pushManager.subscribe()`.

**Respostas:**
- **200** — `{ "sucesso": true }` ou `{ "sucesso": false }` (se falha ao salvar)
- **400** — `subscription` ausente ou sem `endpoint`
- **500** — Erro interno

**Exemplo JavaScript:**
```javascript
const reg = await navigator.serviceWorker.ready;
const vapidKey = await fetch('/api/push-vapid-public').then(r => r.json());

const subscription = await reg.pushManager.subscribe({
  userVisibleOnly: true,
  applicationServerKey: vapidKey.vapid_public_key,
});

await fetch('/api/push-subscribe', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content,
  },
  body: JSON.stringify({ subscription }),
});
```

---

## Onboarding

As três rotas abaixo controlam o tour de boas-vindas exibido a novos usuários.
O estado é persistido por usuário no Firestore (`onboarding_passo`, `onboarding_completo`).

### `POST /api/onboarding/avancar`

Salva o passo atual do tour para retomá-lo se o usuário fechar sem concluir.

**Auth:** Sim | **CSRF:** Obrigatório

**Corpo:**
```json
{ "passo": 2 }
```

| Campo | Tipo | Obrigatório | Restrição |
|-------|------|-------------|-----------|
| `passo` | int | Sim | ≥ 0 |

**Resposta 200:**
```json
{ "sucesso": true }
```

- **400** — `passo` ausente, não inteiro ou < 0

---

### `POST /api/onboarding/concluir`

Marca o onboarding como concluído ao finalizar todos os passos do tour.

**Auth:** Sim | **CSRF:** Obrigatório

**Corpo:** vazio (`{}`)

**Resposta 200:**
```json
{ "sucesso": true }
```

---

### `POST /api/onboarding/pular`

Pula o tour e marca onboarding como concluído (equivalente a `/concluir`).

**Auth:** Sim | **CSRF:** Obrigatório

**Corpo:** vazio (`{}`)

**Resposta 200:**
```json
{ "sucesso": true }
```

---

## Supervisores

### `GET /api/supervisores/lista`

Lista supervisores disponíveis para uma área. Usado no formulário de abertura de chamado para seleção de responsável.

**Auth:** Sim

**Query params:**

| Parâmetro | Padrão | Descrição |
|-----------|--------|-----------|
| `area` | `Geral` | Nome do setor (ex.: `Planejamento`, `TI`) |

> O parâmetro `area` passa por resolução interna (`setor_para_area`) antes da busca.

**Resposta 200:**
```json
{
  "sucesso": true,
  "area": "Planejamento",
  "supervisores": [
    { "id": "uid123", "nome": "João Silva", "email": "joao@dtx.com" },
    { "id": "uid456", "nome": "Maria Santos", "email": "maria@dtx.com" }
  ]
}
```

> Sempre retorna `200` mesmo em erro interno (lista vazia + campo `erro`).

---

## Service Worker

### `GET /sw.js`

Serve o arquivo do service worker na raiz do domínio (necessário para o escopo correto do Push).
Não exige autenticação.

**Resposta:** `application/javascript`, status `200`.

---

## Referência de Erros

### Formato de erro padrão

```json
{ "sucesso": false, "erro": "Descrição do erro" }
```

### Tabela de erros por endpoint

| Endpoint | Código | Mensagem de erro |
|----------|--------|-----------------|
| `POST /api/atualizar-status` | 400 | `"chamado_id é obrigatório"` |
| `POST /api/atualizar-status` | 400 | `"novo_status é obrigatório"` |
| `POST /api/atualizar-status` | 400 | `"Status inválido \"<valor>\""` |
| `POST /api/atualizar-status` | 400 | `"Motivo do cancelamento é obrigatório"` |
| `POST /api/bulk-status` | 400 | `"chamado_ids deve ser uma lista"` |
| `POST /api/bulk-status` | 400 | `"novo_status inválido"` |
| `POST /api/bulk-status` | 400 | `"Nenhum chamado informado"` |
| `POST /api/push-subscribe` | 400 | `"subscription inválida"` |
| `POST /api/onboarding/avancar` | 400 | `"passo inválido"` |
| `POST /api/confirmar-resolucao` | 400 | `"Ação inválida"` |
| `POST /api/confirmar-resolucao` | 400 | `"Informe o motivo para reabrir o chamado"` |
| `POST /api/confirmar-resolucao` | 400 | `"Chamado não aguarda confirmação"` |
| Qualquer | 500 | `"Erro interno. Tente novamente."` |

### Erros de autenticação

Rotas sem sessão retornam `302 → /login` (não JSON).
Rotas com perfil insuficiente retornam `403 { "sucesso": false, "erro": "Acesso negado" }`.

---

## Rate Limiting

| Endpoint | Limite |
|----------|--------|
| `POST /api/atualizar-status` | 60/min |
| `POST /api/bulk-status` | 20/min |
| `GET /api/chamados/paginar` | 60/min |
| `POST /api/carregar-mais` | 60/min |
| `GET /api/supervisores/lista` | 30/min |
| Outros endpoints | 100/min (global) |

Ao exceder: `429 Too Many Requests` (resposta do Flask-Limiter).

---

## Changelog

| Data | Versão | Mudança |
|------|--------|---------|
| 2026-06-10 | 1.0 | Documentação completa — todos os 20 endpoints |
| 2026-06-10 | — | `GET /health?deep=1` — deep health check com Firestore |
| 2026-06-10 | — | `POST /api/chamado/<id>/confirmar-resolucao` — confirmação de resolução |
| 2026-06-10 | — | Endpoints de onboarding (`/avancar`, `/concluir`, `/pular`) |
| 2026-06-10 | — | `GET /api/notificacoes/contar` — contador sem transferência de docs |
| 2026-06-10 | — | `GET /api/download-anexo` — download via R2 pré-assinado |
