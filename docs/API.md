# API – Endpoints do Sistema de Chamados

Referência dos endpoints JSON e utilitários utilizados pelo frontend. Todas as rotas que exigem autenticação redirecionam para `/login` (302) quando o usuário não está logado.

**Base URL:** a mesma origem do frontend (ex.: `https://seu-dominio.com`).

**CSRF:** Para requisições POST com JSON, envie o token no header:
- `X-CSRFToken`: valor da meta tag `<meta name="csrf-token" content="...">`.

---

## Health check

| Método | URL | Autenticação | Descrição |
|--------|-----|--------------|-----------|
| GET | `/health` | Não | Verifica se a aplicação está no ar (load balancer / monitoramento). |

**Resposta 200:**
```json
{ "status": "ok" }
```

---

## Atualização de status

### POST `/api/atualizar-status`

Atualiza o status de um chamado (Aberto, Em Atendimento, Concluído). Qualquer usuário logado pode alterar (uso típico: supervisor no dashboard).

**Headers:** `Content-Type: application/json`, `X-CSRFToken: <token>` (obrigatório para CSRF).

**Corpo (JSON):**
| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| chamado_id | string | Sim | ID do documento do chamado no Firestore. |
| novo_status | string | Sim | Um de: `Aberto`, `Em Atendimento`, `Concluído`. |

**Respostas:**
- **200** – Sucesso.
  ```json
  { "sucesso": true, "mensagem": "Status alterado para Em Atendimento", "novo_status": "Em Atendimento" }
  ```
- **400** – JSON inválido, `chamado_id` ou `novo_status` ausente, ou status inválido.
  ```json
  { "sucesso": false, "erro": "chamado_id é obrigatório" }
  ```
- **404** – Chamado não encontrado.
  ```json
  { "sucesso": false, "erro": "Chamado não encontrado" }
  ```
- **500** – Erro interno (mensagem genérica).

---

### POST `/api/bulk-status`

Atualiza o status de vários chamados em lote. Apenas **supervisor** ou **admin**.

**Headers:** `Content-Type: application/json`, `X-CSRFToken: <token>`.

**Corpo (JSON):**
| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| chamado_ids | array de string | Sim | Lista de IDs (máx. 50). |
| novo_status | string | Sim | Um de: `Aberto`, `Em Atendimento`, `Concluído`. |

**Respostas:**
- **200** – Sempre sucesso na operação (detalhes por chamado em `erros`).
  ```json
  { "sucesso": true, "atualizados": 3, "total_solicitados": 5, "erros": [ { "id": "abc", "erro": "Não encontrado" } ] }
  ```
- **403** – Acesso negado (perfil não supervisor/admin).
- **400** – `chamado_ids` não é lista ou `novo_status` inválido.

**Rate limit:** 20 requisições por minuto.

---

## Edição de chamado

### POST `/api/editar-chamado`

Edita chamado (status, descrição, responsável, anexo). Apenas **supervisor** ou **admin**. Supervisor só pode editar chamados da própria área.

**Content-Type:** `multipart/form-data` (FormData).

**Campos (form):**
| Campo | Obrigatório | Descrição |
|-------|-------------|-----------|
| chamado_id | Sim | ID do chamado. |
| novo_status | Não | Um de: Aberto, Em Atendimento, Concluído. |
| nova_descricao | Não | Nova descrição (substitui a anterior). |
| novo_responsavel_id | Não | ID do usuário (supervisor/admin) para reatribuir. |
| anexo | Não | Arquivo (adicionado à lista de anexos). |

**Respostas:**
- **200** – Sucesso (com ou sem alterações).
  ```json
  { "sucesso": true, "mensagem": "Chamado atualizado com sucesso", "dados": { ... } }
  ```
- **400** – `chamado_id` ausente.
- **403** – Acesso negado ou supervisor de outra área.
- **404** – Chamado não encontrado.
- **500** – Erro interno.

---

## Paginação e listagem de chamados

### GET `/api/chamados/paginar`

Lista chamados com filtros e paginação por cursor. Requer login (supervisor/admin no dashboard).

**Query params:** (todos opcionais)
| Parâmetro | Descrição |
|----------|------------|
| limite | Inteiro 1–100 (padrão 50). |
| cursor | ID do último documento da página anterior. |
| status | Filtro: Aberto, Em Atendimento, Concluído. |
| gate | Filtro por gate. |
| categoria | Filtro por categoria. |
| responsavel | Nome do responsável. |
| search | Busca por texto (descrição, rl_codigo, responsável, número). |

**Resposta 200:**
```json
{
  "sucesso": true,
  "chamados": [
    {
      "id": "...",
      "numero": "CHM-0001",
      "categoria": "...",
      "rl_codigo": "...",
      "tipo": "...",
      "responsavel": "...",
      "status": "...",
      "prioridade": 1,
      "descricao_resumida": "...",
      "data_abertura": "dd/mm/yyyy HH:mm",
      "data_conclusao": "..."
    }
  ],
  "paginacao": {
    "cursor_proximo": "doc_id",
    "tem_proxima": true,
    "total_pagina": 50,
    "limite": 50
  }
}
```

**Rate limit:** 60/min.

---

### POST `/api/carregar-mais`

Carrega mais chamados (infinite scroll). Mesmos filtros que a listagem (via query params). Requer login.

**Headers:** `Content-Type: application/json`, `X-CSRFToken: <token>`.

**Corpo (JSON):**
| Campo | Tipo | Descrição |
|-------|------|------------|
| cursor | string | ID do último documento da página anterior. |
| limite | int | Máx. 50 (padrão 20). |

**Resposta 200:**
```json
{
  "sucesso": true,
  "chamados": [ { "id": "...", "numero": "...", "categoria": "...", "status": "...", "responsavel": "...", "data_abertura": "..." } ],
  "cursor_proximo": "doc_id",
  "tem_proxima": true
}
```

**Rate limit:** 60/min.

---

## Notificações in-app

### GET `/api/notificacoes`

Lista notificações do usuário (sino).

**Query params:** `nao_lidas=1` (opcional) – retorna apenas não lidas.

**Resposta 200:**
```json
{
  "notificacoes": [ { "id": "...", "chamado_id": "...", "numero_chamado": "...", "mensagem": "...", "lida": false, "data": "..." } ],
  "total_nao_lidas": 5
}
```

---

### POST `/api/notificacoes/<notificacao_id>/ler`

Marca uma notificação como lida.

**Resposta 200:**
```json
{ "sucesso": true }
```
Em erro: `{ "sucesso": false }` (500).

---

## Web Push

### GET `/api/push-vapid-public`

Retorna a chave pública VAPID para inscrição Web Push. Requer login.

**Resposta 200:**
```json
{ "vapid_public_key": "..." }
```

---

### POST `/api/push-subscribe`

Registra a inscrição Web Push do navegador para o usuário logado.

**Corpo (JSON):**
| Campo | Tipo | Descrição |
|-------|------|------------|
| subscription | object | Objeto retornado por `ServiceWorkerRegistration.pushManager.subscribe()` (deve conter `endpoint`). |

**Respostas:**
- **200** – `{ "sucesso": true }` ou `{ "sucesso": false }`.
- **400** – `subscription` ausente ou inválida.
- **500** – Erro interno.

---

## Supervisores

### GET `/api/supervisores/disponibilidade`

Retorna disponibilidade de supervisores por área (carga, etc.). Requer login.

**Query params:** `area` (opcional, padrão `Geral`).

**Resposta 200:**
```json
{
  "sucesso": true,
  "supervisores": [ ... ],
  "area": "Manutencao"
}
```

**Rate limit:** 30/min.

---

## Service Worker

### GET `/sw.js`

Serve o arquivo do service worker (escopo da aplicação). Não requer autenticação.

**Resposta:** JavaScript (`application/javascript`).
