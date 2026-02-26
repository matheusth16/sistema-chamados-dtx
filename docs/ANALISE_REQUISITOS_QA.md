# Análise de Requisitos – Sistema de Chamados DTX

**Documento:** Análise de Requisitos para QA  
**Projeto:** Sistema de Chamados DTX  
**Stack:** Python/Flask, Firestore, Firebase Auth  

---

## 1. Visão Geral do Sistema

O sistema é uma aplicação web de **gerenciamento de chamados** com:

- Autenticação (Firebase/Flask-Login) e perfis: **solicitante**, **supervisor**, **admin**
- Criação e listagem de chamados com paginação (cursor-based)
- Atualização de status (individual e em lote)
- Edição de chamados (supervisor/admin), anexos, notificações e i18n (PT/EN)

---

## 2. Especificações Técnicas Relevantes para Testes

### 2.1 Stack e Configuração

| Item | Especificação |
|------|----------------|
| Runtime | Python 3.8+ |
| Framework | Flask |
| Banco | Firestore (acesso apenas via backend; regras negam acesso direto do cliente) |
| Autenticação | Flask-Login + usuários em Firestore (`usuarios`), senha com werkzeug hash |
| CSRF | WTF_CSRF_ENABLED = True (em produção); testes usam WTF_CSRF_ENABLED = False |
| Upload | Máx. 16 MB; extensões: png, jpg, jpeg, pdf, xlsx |
| Paginação | Cursor-based; limite configurável (ex.: 10 itens por página, API até 100) |
| Rate limit | Produção: 200/hora, 2000/dia; bulk-status: 20/min; paginar/carregar-mais: 60/min; login: 5/min |

### 2.2 Estrutura de Dados

**Chamado (Firestore `chamados`):**

- `numero_chamado`, `categoria`, `rl_codigo`, `prioridade`, `tipo_solicitacao`, `gate`, `impacto`
- `descricao`, `anexo`, `anexos[]`
- `responsavel`, `responsavel_id`, `motivo_atribuicao`
- `solicitante_id`, `solicitante_nome`, `area`
- `status`: `Aberto` \| `Em Atendimento` \| `Concluído`
- `data_abertura`, `data_conclusao` (timestamp; Concluído preenche `data_conclusao`)

**Usuário (Firestore `usuarios`):**

- `email`, `nome`, `perfil` (`solicitante` \| `supervisor` \| `admin`), `areas` (lista)
- `senha_hash` (werkzeug)

---

## 3. Regras de Negócio (Prioritárias para Testes)

### 3.1 Autenticação e Autorização

- **Login:** POST `/login` com `email` e `senha`; sessão criada com `remember=False`.
- **Logout:** GET `/logout`; requer login.
- **Redirecionamento pós-login:**
  - Solicitante → `/` (formulário novo chamado)
  - Supervisor/Admin → `/admin` (dashboard)
- **Rotas protegidas:** sem login → 302 para `/login` (ou 401 JSON em APIs).
- **Perfis:**
  - **Solicitante:** pode criar chamado, ver “Meus Chamados”, ver apenas chamados onde `solicitante_id == current_user.id`.
  - **Supervisor:** dashboard, filtrar por área; ver/editar apenas chamados cuja **área do chamado** está em `user.areas` (não basta ser responsável).
  - **Admin:** acesso total (ver/editar todos os chamados).

### 3.2 Criação de Chamado (Solicitante)

- **Rota:** POST `/` (index); decorador `@requer_solicitante` e rate limit 10/hora.
- **Campos obrigatórios:** descrição (mín. 3 caracteres), setor/tipo.
- **Categoria Projetos:** `rl_codigo` obrigatório; 1–100 caracteres; caracteres permitidos: letras, números, espaço, `- _ . / ( ) ,` (regex `^[\w\s\-./(),]+$`).
- **Anexo:** opcional; extensões: png, jpg, jpeg, pdf, xlsx; tamanho máx. 16 MB (config).
- **Prioridade:** Projetos = 0; demais = informada ou 1.
- **Atribuição:** se solicitante escolher responsável no formulário (supervisor/admin), usa esse; senão, atribuição automática por área/categoria; se falhar, fica como solicitante e mensagem de aviso.
- **Área do chamado:** setor (tipo) ou área do solicitante ou "Geral".
- **Histórico:** registro de criação no `historico`.

### 3.3 Atualização de Status

- **POST `/api/atualizar-status`:** qualquer usuário logado; JSON: `chamado_id`, `novo_status` ∈ {Aberto, Em Atendimento, Concluído}.
  - Validação: campos obrigatórios, status válido.
  - Se status mudar: histórico + notificação ao solicitante (Em Atendimento / Concluído).
  - Concluído: preenche `data_conclusao` com SERVER_TIMESTAMP.
- **POST `/api/bulk-status`:** apenas **supervisor** ou **admin**; JSON: `chamado_ids` (lista, máx. 50), `novo_status`.
  - Supervisor: só atualiza chamados cuja área está em `current_user.areas` ou onde é o responsável; demais entram em `erros` com “Sem permissão”.
  - Resposta: sempre 200 com `atualizados`, `total_solicitados`, `erros[]`.

### 3.4 Edição de Chamado

- **POST `/api/editar-chamado`:** apenas **supervisor** ou **admin**; FormData.
  - Campos: `chamado_id` (obrigatório), `novo_status`, `nova_descricao`, `novo_responsavel_id`, `anexo`.
  - Supervisor: só pode editar se a **área do chamado** estiver em `current_user.areas` (ou for responsável / área comum conforme implementação).
  - Chamado inexistente → 404; sem permissão → 403.
  - Histórico para alterações de status, responsável, descrição e anexo.

### 3.5 Paginação e Listagem

- **GET `/api/chamados/paginar`:** login obrigatório; query params: `limite` (1–100, padrão 50), `cursor`, `status`, `gate`, `categoria`, `responsavel`, `search`.
- **POST `/api/carregar-mais`:** JSON `cursor`, `limite` (máx. 50); mesmo filtro implícito da listagem.
- Supervisor vê apenas chamados cuja área está em suas áreas (filtro por permissão).

### 3.6 Visualização de Chamado por ID

- **GET `/api/chamado/<chamado_id>`:**
  - Solicitante: só se `chamado.solicitante_id == current_user.id`.
  - Supervisor/Admin: `usuario_pode_ver_chamado(current_user, chamado)` (admin sempre; supervisor só se `chamado.area in user.areas`).

### 3.7 Notificações e Web Push

- **GET `/api/notificacoes`:** lista notificações do usuário; query `nao_lidas=1` opcional.
- **POST `/api/notificacoes/<id>/ler`:** marca uma como lida.
- **POST `/api/notificacoes/ler-todas`:** marca todas como lidas.
- **GET `/api/push-vapid-public`:** retorna chave pública VAPID.
- **POST `/api/push-subscribe`:** body `subscription` com `endpoint`; salva inscrição para o usuário logado.

### 3.8 Outros Endpoints

- **GET `/health`:** sem auth; retorna `{"status": "ok"}` 200.
- **GET `/sw.js`:** service worker; sem auth.
- **GET `/api/supervisores/disponibilidade`:** query `area` (opcional); retorna supervisores da área.

### 3.9 Validações e Erros

- **Exceções customizadas:** `ChamadoNaoEncontradoError`, `ValidacaoChamadoError`, `PermissaoNegadaError`, etc.
- **API:** 400 (validação), 403 (acesso negado), 404 (não encontrado), 500 (mensagem genérica sem expor detalhes).

### 3.10 Segurança e Configuração

- Produção exige `SECRET_KEY` forte (diferente do default de dev).
- Firestore: acesso somente pelo backend; regras `allow read, write: if false` para acesso direto do cliente.
- Headers de segurança: X-Content-Type-Options, X-Frame-Options, HSTS em HTTPS.
- Validação de Origin/Referer em POST sensíveis quando `APP_BASE_URL` definido.

---

## 4. Requisitos Não Funcionais (Para Testes)

- **Performance:** paginação cursor-based; índices Firestore para filtros (categoria+status+data_abertura, etc.).
- **Disponibilidade:** health check em `/health`.
- **Logs:** ações importantes (login, alteração de status, criação de chamado) registradas.
- **i18n:** textos em PT/EN; painel de traduções (admin).

---

## 5. Resumo para Cobertura de Testes

| Área | O que validar |
|------|----------------|
| Auth | Login/logout, redirecionamento por perfil, rotas protegidas (302/401) |
| Chamado (criação) | Validação de campos, regra Projetos+RL, anexos, atribuição, histórico |
| Status | Atualização unitária (qualquer logado), bulk (só supervisor/admin, permissão por área) |
| Edição | Apenas supervisor/admin; supervisor só da sua área; campos e histórico |
| Permissões | Admin vê tudo; supervisor só área; solicitante só próprios chamados |
| API paginação | Params, cursor, estrutura de resposta, filtros |
| Notificações / Push | Listar, marcar lida, VAPID, subscribe |
| Health / SW | Health 200; sw.js servido |
| Validação/Erros | 400/403/404/500 e mensagens conforme especificação |

Este documento serve de base para o **Plano de Testes** e para os **Casos de Teste** detalhados.
