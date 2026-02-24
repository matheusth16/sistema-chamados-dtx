# Plano de aplicação das sugestões rápidas

Este documento descreve o plano para aplicar as melhorias sugeridas na análise do projeto.

---

## 1. CSRF na API (atualizar docstring e alinhar com o frontend)

**Objetivo:** Deixar claro que a rota `/api/atualizar-status` exige CSRF e que o frontend deve enviar o token no header `X-CSRFToken`.

**Situação atual:**
- Em `app/__init__.py` está documentado: *"API de status exige CSRF; o frontend envia o token no header X-CSRFToken (meta csrf-token)"*.
- Em `app/routes/api.py` a docstring da rota diz: *"Isento de CSRF para fetch"*, o que contradiz o comentário do `__init__.py` e pode confundir manutenção futura.

**Ações:**
1. Em `app/routes/api.py`, alterar a docstring de `atualizar_status_ajax()` para algo como:  
   *"Atualiza status do chamado via JSON. Requer CSRF; o frontend deve enviar o token no header X-CSRFToken (ex.: valor da meta tag csrf-token)."*
2. Verificar no frontend (ex.: `dashboard.html` ou JS que chama essa rota) se o `fetch` já envia o header `X-CSRFToken`. Se não enviar, adicionar o header usando o valor da meta tag `csrf-token` (ou equivalente).
3. Garantir que não haja `csrf.exempt` aplicado a essa view em nenhum lugar (já confirmado: não há exempt no código).

**Arquivos:** `app/routes/api.py`, possivelmente `app/templates/base.html` (meta tag) e o template/JS que faz o fetch de atualização de status.

---

## 2. Import fora de ordem em `api.py`

**Objetivo:** Manter todos os imports no topo do arquivo, seguindo PEP 8.

**Situação atual:**  
Em `app/routes/api.py`, a linha `from app.services.upload import salvar_anexo` está entre a função `atualizar_status_ajax` e a rota `api_editar_chamado` (por volta da linha 88).

**Ações:**
1. Remover a linha `from app.services.upload import salvar_anexo` do meio do arquivo.
2. Adicionar `from app.services.upload import salvar_anexo` no bloco de imports do topo (junto aos outros `from app.services.*`).

**Arquivo:** `app/routes/api.py`.

---

## 3. Expandir testes para serviços e rotas críticas

**Objetivo:** Aumentar a cobertura e a confiabilidade em refatorações e deploys.

**Situação atual:**  
Existem `conftest.py`, testes de integração (login, criar chamado, bulk status), testes de rotas (auth, chamados, api_status) e de serviços (notifications, analytics, assignment).

**Ações (prioridade sugerida):**
1. **Serviço de filtros (`app/services/filters.py`)**  
   - Criar `tests/test_services/test_filters.py`.  
   - Testar `aplicar_filtros_dashboard_com_paginacao` e `aplicar_filtros_dashboard` com mocks do Firestore (query_ref mockado, args variados: status, gate, categoria, search, cursor).  
   - Cobrir: filtro por status, por gate, por categoria, busca por texto, paginação por cursor (retorno com `proxima_pagina`, lista de docs).

2. **Validadores (`app/services/validators.py`)**  
   - Criar `tests/test_services/test_validators.py`.  
   - Testar `validar_novo_chamado` com casos: formulário válido, campos obrigatórios faltando, descrição curta/longa, arquivo com extensão não permitida, arquivo grande (se houver validação).

3. **Rotas de API adicionais**  
   - Em `tests/test_routes/test_api_status.py` (ou em um `test_api.py` mais amplo): além do status, incluir testes para `api_editar_chamado` (403 para solicitante, 400 para dados inválidos), `carregar_mais` (estrutura da resposta), `api_notificacoes_listar` (autenticado), `api_push_subscribe` (POST com subscription), se fizer sentido com mocks.  
   - Manter foco em contratos (status code, estrutura JSON) e permissões (quem pode chamar o quê).

4. **Opcional:** testes para `app/services/date_validators.py` e para `app/utils.py` (ex.: `gerar_numero_chamado`, `extrair_numero_chamado`) em `tests/test_services/test_date_validators.py` e `tests/test_utils.py`.

**Arquivos novos/alterados:**  
`tests/test_services/test_filters.py`, `tests/test_services/test_validators.py`, expansão em `tests/test_routes/test_api_status.py` ou `test_api.py`; opcionalmente `tests/test_services/test_date_validators.py` e `tests/test_utils.py`.

---

## 4. Documentação da API (endpoints `/api/*`)

**Objetivo:** Ter uma referência rápida dos endpoints, método, URL, corpo e respostas para integração e manutenção.

**Ações:**
1. Criar o arquivo `docs/API.md` (ou `app/API.md` na raiz do projeto, conforme convenção do repositório).
2. Listar cada rota sob `/api/` (e `/health` se desejado), no formato:
   - **Método e URL**
   - **Autenticação:** login obrigatório (e perfil, quando aplicável)
   - **Corpo da requisição** (JSON ou FormData) com campos principais
   - **Respostas:** 200 (exemplo de JSON de sucesso), 400/403/404/500 (quando aplicável)
3. Incluir:
   - `POST /api/atualizar-status` (JSON: chamado_id, novo_status; header X-CSRFToken)
   - `POST /api/editar-chamado` (FormData: chamado_id, novo_status, etc.)
   - `POST /api/bulk-status` (JSON: lista de {chamado_id, novo_status})
   - `GET/POST` de notificações (listar, marcar lida)
   - `POST /api/push-subscribe` (inscrição Web Push)
   - `GET /api/carregar-mais` (paginação)
   - `GET /api/disponibilidade-supervisores` (ou nome exato da rota)
   - Outras rotas em `app/routes/api.py` que forem consideradas parte da API pública interna.

**Arquivo:** `docs/API.md` (ou caminho escolhido pelo time).

---

## 5. Observação sobre `models_usuario.py`

Na análise inicial foi mencionada a possível remoção do import `FieldFilter` por parecer não usado. Após verificação, **`FieldFilter` é utilizado** em `get_supervisores_por_area` (filtros compostos). Nenhuma alteração necessária; import deve permanecer.

---

## Ordem sugerida de execução

| Ordem | Item                    | Esforço | Impacto |
|-------|-------------------------|--------|--------|
| 1     | Import em `api.py`      | Baixo   | Consistência de código |
| 2     | Docstring CSRF + checagem frontend | Baixo | Clareza e segurança |
| 3     | Documentação API (`docs/API.md`) | Médio | Manutenção e onboarding |
| 4     | Testes (filters, validators, api) | Médio/Alto | Confiabilidade e refatoração |

Assim que você aprovar este plano, as alterações dos itens 1 e 2 podem ser feitas primeiro (rápidas); em seguida a documentação da API; por último a expansão dos testes de forma incremental.

---

## Status de aplicação (concluído)

- **Item 1 (CSRF + import):** Aplicado. Docstring de `atualizar_status_ajax` atualizada; `salvar_anexo` movido para o topo de `api.py`. Frontend já envia `X-CSRFToken` (dashboard e base).
- **Item 2 (docs/API.md):** Criado `docs/API.md` com todos os endpoints `/api/*`, health e `/sw.js`.
- **Item 3 (test_filters):** Criado `tests/test_services/test_filters.py` (filtros e paginação).
- **Item 4 (test_validators):** Criado `tests/test_services/test_validators.py` (validar_novo_chamado).
- **Item 5 (testes API):** Criado `tests/test_routes/test_api.py` (editar chamado 403/400/404, carregar-mais, notificações, push).
- **Item 6 (opcionais):** Criados `tests/test_services/test_date_validators.py` e `tests/test_utils.py`.

**Nota:** Os testes de rotas (`test_api.py`, `test_api_status.py`) dependem do ambiente ter todas as dependências instaladas (ex.: `pytz`). Execute `pip install -r requirements.txt` no ambiente de testes. Os testes de serviços (filters, validators, date_validators, utils) não precisam do app Flask completo e passaram localmente.
