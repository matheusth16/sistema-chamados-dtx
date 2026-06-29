# API — DTX Digital Andon System

Referência completa dos endpoints JSON utilizados pelo frontend.
Atualizado em: 2026-06-10 | Versão: 1.0

---

## Visão Geral

| Propriedade | Valor |
|-------------|-------|
| **Base URL** | Mesma origem do frontend (ex.: `https://seu-dominio.com`) |
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
| GET | `/gestor/dashboard` | Sim | gestor (supervisor + nivel_gestao) ou admin |

---

## Health Check

### `GET /health`

Verifica disponibilidade da aplicação. Não exige autenticação.

**Modo raso (padrão):** resposta imediata sem I/O — usado pelo healthcheck da plataforma de deploy.
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
curl -X POST https://seu-dominio.com/api/atualizar-status \
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

- `acao: "confirmar"` → atualiza `confirmacao_solicitante = "confirmado"` e envia e-mail ao responsável (`notificar_responsavel_chamado_confirmado`) em background
- `acao: "reabrir"` → reverte status para `Aberto`, registra histórico com o motivo e envia e-mail ao responsável (`notificar_supervisor_chamado_reaberto`) em background

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

> O parâmetro `area` passa por resolução interna (`setor_para_area`) antes da busca. O mapa de setores → áreas é lido do Firestore (`config/setor_para_area`) com cache TTL 5 min e fallback estático (F-30 resolvido).

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

## Escalonamento (Fase 3)

### `POST /api/chamado/<chamado_id>/transferir-area`

Transfere o chamado para outra área com novo responsável obrigatório.

**Auth:** Sim — `@requer_supervisor_area`

**Permissão:** Owner (`responsavel_id == current_user.id`) ou admin/admin_global.

**Body JSON:**

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `area` | string | Sim | Área destino (não vazia) |
| `supervisor_id` | string | Sim | ID do supervisor destino (anti-órfão) |
| `motivo` | string | Sim | Razão da transferência (máx 500 chars) |

**Resposta 200:**
```json
{ "sucesso": true, "dados": { "area": "Planejamento", "responsavel_id": "uid_dest" } }
```

**Erros:**

| Status | Motivo |
|--------|--------|
| 400 | `motivo` ou `supervisor_id` ou `area` vazios; supervisor não pertence à área destino |
| 403 | Usuário sem acesso ao chamado (IDOR) ou não é owner |
| 404 | Chamado não encontrado |

**Efeitos colaterais:** recalcula `supervisor_ids_com_acesso`; grava `Historico` (acao=`transferencia_area`); notificação e-mail ao novo responsável (thread background).

---

### `POST /api/chamado/<chamado_id>/escalonar-colega`

Escala o chamado para um colega da mesma área sem alterar a área.

**Auth:** Sim — `@requer_supervisor_area`

**Permissão:** Owner (`responsavel_id == current_user.id`) ou admin/admin_global.

**Body JSON:**

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `supervisor_id` | string | Sim | ID do colega destino (deve ser da mesma área; ≠ atual) |
| `motivo` | string | Sim | Razão do escalonamento (máx 500 chars) |

**Resposta 200:**
```json
{ "sucesso": true, "dados": { "responsavel_id": "uid_colega" } }
```

**Erros:**

| Status | Motivo |
|--------|--------|
| 400 | `motivo` ou `supervisor_id` vazios; destino == atual; colega não pertence à área |
| 403 | Usuário sem acesso ao chamado (IDOR) ou não é owner |
| 404 | Chamado não encontrado |

**Efeitos colaterais:** recalcula `supervisor_ids_com_acesso`; grava `Historico` (acao=`escalonamento_colega`); notificação e-mail ao colega (thread background); área inalterada.

---

## Participantes (Fase 4)

### `POST /api/chamado/<chamado_id>/incluir-participantes`

Adiciona supervisores colaboradores em `participantes[]`.

**Auth:** Sim — `@requer_supervisor_area`

**Permissão:** Owner (`responsavel_id == current_user.id`) ou admin/admin_global.

**Body JSON:**

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `participantes` | array | Sim | Lista de `{ "supervisor_id": str, "area": str }` |

**Resposta 200:**
```json
{
  "sucesso": true,
  "dados": {
    "participantes": [...],
    "adicionados": [{ "supervisor_id": "uid", "area": "Logistica", "nome": "Pedro" }]
  }
}
```

**Invariantes:**
- Owner não pode ser adicionado como participante.
- `supervisor_id` já presente na lista é silenciosamente ignorado (sem duplicar).
- Cada `supervisor_id` deve pertencer à `area` informada.
- Após inclusão: `supervisor_ids_com_acesso` recalculado; histórico gravado (`acao=inclusao_participantes`).

**Efeitos colaterais:** notificação e-mail a cada participante novo (thread background).

**Erros:**

| Status | Motivo |
|--------|--------|
| 400 | `participantes` vazia ou ausente |
| 400 | `supervisor_id` não existe ou não pertence à `area` |
| 400 | `supervisor_id` é o próprio owner |
| 403 | Usuário sem acesso ao chamado (IDOR) ou não é owner/admin |
| 404 | Chamado não encontrado |

---

### `POST /api/chamado/<chamado_id>/concluir-minha-parte`

Participante marca sua parte como concluída.

**Auth:** Sim — `@login_required` (qualquer perfil logado que seja participante)

**Permissão:** `current_user.id` deve estar em `participantes[*].supervisor_id` com `status != "concluido"`.

**Body JSON:** `{}` (pode ser omitido)

**Resposta 200:**
```json
{ "sucesso": true, "dados": { "pode_concluir_global": true } }
```

`pode_concluir_global: true` indica que todos participantes concluíram — owner pode fechar o chamado.

**Efeitos colaterais:**
- Grava `concluido_em` (datetime no fuso `SLA_TIMEZONE`) e `status="concluido"` no item do participante.
- Histórico gravado (`acao=conclusao_parte_participante`).
- Quando `pode_concluir_global=true`: owner recebe notificação in-app + e-mail + Web Push (thread background).

**Erros:**

| Status | Motivo |
|--------|--------|
| 403 | Usuário não é participante do chamado |
| 400 | Participante já concluiu sua parte |
| 404 | Chamado não encontrado |

---

## Dashboard Gerencial (Fase 5)

### `GET /gestor/dashboard`

Dashboard read-only para usuários com `nivel_gestao` definido. Exibe contadores e listagem de
chamados classificados por filtros gerenciais. Sem botões de ação — visualização pura.

**Auth:** Sim — `@requer_gestor_ou_admin`

**Perfis com acesso:**
- `supervisor` com `nivel_gestao != None` → acesso read-only (sem edição)
- `admin` (qualquer) → acesso com capacidade de edição mantida via `/painel`

**Perfis bloqueados:** `solicitante`, supervisor sem `nivel_gestao` → 302 redirect.

**Query params:**

| Parâmetro | Padrão | Valores | Descrição |
|-----------|--------|---------|-----------|
| `filtro` | `todos` | `todos`, `atrasados`, `aberto_sem_resposta`, `aberto`, `multi_setor`, `multi_setor_travado` | Filtra a lista de chamados exibida |

**Resposta:** `200 text/html` — página completa com template `gestor_dashboard.html`.

**Contadores retornados no contexto do template:**

| Chave | Descrição |
|-------|-----------|
| `contadores.total` | Total de chamados carregados (até 500 — limitação v1) |
| `contadores.atrasados` | Chamados com `is_atrasado=True` ou SLA excedido |
| `contadores.aberto_sem_resposta` | Chamados `status="Aberto"` há ≥ 60 min corridos (v1) |
| `contadores.multi_setor_travado` | Chamados com participantes e ao menos um sem `status="concluido"` |

> **Fase 6 (2026-06-25):** `aberto_sem_resposta` agora usa `business_time.minutos_uteis_entre`
> (tempo útil real, não wall-clock). A limitação de 60 min corridos documentada na Fase 5
> foi corrigida em `gestor_dashboard_service._is_aberto_sem_resposta`.

**Erros:**
- **302** — Usuário sem `nivel_gestao` ou sem perfil `supervisor`/`admin`

---

## Jobs em background / SLA Escalonamento (Fases 6–7)

Os jobs APScheduler são internos — não há endpoints HTTP para acionar ou consultar.
Esta seção documenta o comportamento observável e os efeitos colaterais de cada job.

### Job `sla_escalacao` — ordem de execução

A cada **10 minutos**, o job chama as três funções na ordem:
1. `processar_escada_a()` — escalada de resposta (chamados Abertos sem atendimento)
2. `processar_avisos_resolucao()` — avisos preventivos 50%/80% ao responsável
3. `processar_escada_b()` — escalada de resolução (chamados Em Atendimento pós-deadline)

---

### Escada A — resposta gerencial (Fase 6)

| Propriedade | Valor |
|-------------|-------|
| Intervalo | A cada **10 minutos** |
| Lock | Redis via `executar_job_com_lock` (evita execuções paralelas em multi-worker) |
| Serviço | `app/services/sla_escalacao_service.processar_escada_a()` |

**Elegibilidade de chamado:**
- `status == "Aberto"` (não iniciado o atendimento)
- `escalacao_resposta_nivel < 4` (ainda há degraus disponíveis)

**Degraus da Escada A** (tempo útil acumulado desde a abertura):

| Degrau | Threshold | Destinatário | Chave `GESTOR_EMAILS` |
|--------|-----------|-------------|------------------------|
| 1 | +60 min úteis | Gestor do Setor | `gestor_setor` |
| 2 | +120 min úteis | Gerente de Produção | `gerente_producao` |
| 3 | +180 min úteis | Assistente GM | `assistente_gm` |
| 4 | +240 min úteis | General Manager | `gm` |

**Janela de envio:** seg–sex 07:00–11:30 e 13:00–16:30 BRT.
Chamados elegíveis fora dessa janela são contabilizados em `pulados_fora_janela` e reprocessados na próxima execução.

**Comportamento sem e-mail configurado:** se a chave do nível não estiver em `GESTOR_EMAILS`, o nível é incrementado normalmente (sem envio). Evita que um chamado fique preso esperando configuração ausente. Log de `WARNING` emitido.

**Reabertura:** `POST /api/chamado/<id>/confirmar-resolucao` com `acao="reabrir"` reseta `escalacao_resposta_nivel = 0`, reiniciando a Escada A do zero (ADR-004).

**Índice Firestore obrigatório** (deploy em produção):
```json
{ "status": "ASC", "escalacao_resposta_nivel": "ASC" }
```
Ver `docs/INDICES_FIRESTORE.md`.

**Estatísticas retornadas** (logadas via `app.logger.info`):
```json
{ "processados": 5, "escalados": 2, "emails": 2, "erros": 0, "pulados_fora_janela": 1 }
```

---

### Avisos preventivos 50%/80% (Fase 7 — pré-estouro)

**Serviço:** `processar_avisos_resolucao()`

**Elegibilidade:**
- `status == "Em Atendimento"` com `data_em_atendimento` definido
- `responsavel_id` presente
- Flag correspondente ainda não enviada (`alerta_supervisor_50_enviado` / `alerta_supervisor_80_enviado`)

**Marcos via `percentual_prazo_resolucao`:**

| Marco | Threshold | Flag de idempotência |
|-------|-----------|----------------------|
| 50% | `pct >= 0.5` | `alerta_supervisor_50_enviado` |
| 80% | `pct >= 0.8` | `alerta_supervisor_80_enviado` |

**Canais ao responsável:** in-app + e-mail + Web Push.
Se o responsável não tiver e-mail cadastrado, in-app + Web Push disparam normalmente e a flag é gravada mesmo assim (evita loop).

**Janela útil:** seg–sex 07:00–11:30 e 13:00–16:30 BRT.
Threshold atingido fora da janela → `pulados_fora_janela++`, reprocessado na próxima execução dentro da janela.

**Estatísticas retornadas:**
```json
{ "processados": 3, "notificados_50": 1, "notificados_80": 0, "erros": 0, "pulados_fora_janela": 0 }
```

---

### Escada B — resolução gerencial (Fase 7 — pós-estouro deadline)

**Serviço:** `processar_escada_b()`

**Deadline de resolução:**
- `categoria == "Projetos"` → 2 dias úteis a partir de `data_em_atendimento` (até 16:30)
- Demais categorias → 3 dias úteis (até 16:30)
- Calculado via `adicionar_dias_uteis(data_em_atendimento, dias)`

**Elegibilidade:**
- `status == "Em Atendimento"` com `data_em_atendimento` definido
- `agora > deadline` (prazo já vencido)
- `escalacao_resolucao_nivel < 4`

**Degraus pós-deadline** (minutos úteis APÓS o deadline):

| Degrau | Threshold após deadline | Destinatário | Chave `GESTOR_EMAILS` |
|--------|------------------------|-------------|------------------------|
| 1 | +0 min úteis | Gestor do Setor | `gestor_setor` |
| 2 | +240 min úteis (4h) | Gerente de Produção | `gerente_producao` |
| 3 | +480 min úteis (8h) | Assistente GM | `assistente_gm` |
| 4 | +720 min úteis (12h) | General Manager | `gm` |

**Canal gerencial:** e-mail only (`notificar_escalada_resolucao_gerencial`).

**Janela útil:** seg–sex 07:00–11:30 e 13:00–16:30 BRT. Fora da janela → `pulados_fora_janela++`.

**Índice Firestore obrigatório:**
```json
{ "status": "ASC", "escalacao_resolucao_nivel": "ASC" }
```

**Estatísticas retornadas:**
```json
{ "processados": 2, "escalados": 1, "emails": 1, "erros": 0, "pulados_fora_janela": 0 }
```

---

### Reset de flags (claim + reabertura)

Ao fazer claim (Aberto → Em Atendimento) ou reabrir um chamado, todos os campos de escalação são zerados atomicamente:

| Campo | Reset |
|-------|-------|
| `escalacao_resposta_nivel` | `0` |
| `escalacao_resolucao_nivel` | `0` |
| `alerta_supervisor_50_enviado` | `False` |
| `alerta_supervisor_80_enviado` | `False` |

### Job `relatorio_semanal`

Executa toda sexta-feira às 10h00 BRT. Chama `enviar_relatorio_semanal()` via `app/services/report_service.py`. Lock Redis (`executar_job_com_lock`).

### Job `reset_ranking_semanal`

Executa todo domingo às 23h59 BRT. Chama `GamificationService.resetar_ranking_semanal()`.

### Job `limpar_contadores_uso`

Executa todo domingo às 02h00 BRT. Remove entradas de `contadores_uso` com mais de 90 dias.

### Job `alerta_prazo_24h` — **desativado**

Substituído pela Escada A (`sla_escalacao`) na Fase 6. A função `enviar_alertas_prazo_24h` permanece disponível em `report_service.py` para reativação se necessário.

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
| `POST /api/atualizar-status` | 30/min |
| `POST /api/bulk-status` | 10/min |
| `POST /api/push-subscribe` | 5/min |
| `POST /api/csp-report` | 20/min |
| `POST /login` | 10/min |
| `GET /exportar` | 10/hora |
| `GET /exportar-avancado` | 5/hora |
| Demais endpoints | Sem limite explícito (Flask-Limiter sem `default_limits`) |

Ao exceder: `429 Too Many Requests` (resposta do Flask-Limiter).

> Os limites são aplicados por decorador `@limiter.limit(...)` nas rotas. Endpoints
> não listados (ex.: `/api/chamados/paginar`, `/api/carregar-mais`,
> `/api/supervisores/lista`) **não** têm limite explícito — o limitador é
> configurado sem `default_limits` (ver `app/limiter.py`).

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
| 2026-06-24 | — | `POST /api/chamado/<id>/transferir-area` — Fase 3 escalonamento |
| 2026-06-24 | — | `POST /api/chamado/<id>/escalonar-colega` — Fase 3 escalonamento |
| 2026-06-25 | — | `POST /api/chamado/<id>/incluir-participantes` — Fase 4 multi-setor |
| 2026-06-25 | — | `POST /api/chamado/<id>/concluir-minha-parte` — Fase 4 multi-setor |
| 2026-06-25 | — | `GET /gestor/dashboard` — Fase 5 dashboard read-only gestor |
| 2026-06-25 | — | Job `sla_escalacao` — Fase 6 Escada A gerencial a cada 10 min (substitui `alerta_prazo_24h`) |
| 2026-06-25 | — | `gestor/dashboard` — `aberto_sem_resposta` corrigido para tempo útil (Fase 6) |
| 2026-06-29 | — | `POST /api/chamado/<id>/confirmar-resolucao` — `acao=confirmar` agora notifica responsável por e-mail |
| 2026-06-26 | — | Fase 7: avisos 50%/80% + Escada B resolução no job `sla_escalacao` |
