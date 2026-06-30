# Casos de Teste – Sistema de Chamados DTX

**Documento:** Cenários de teste detalhados (passo a passo)
**Projeto:** Sistema de Chamados DTX
**Referências:** [ANALISE_REQUISITOS_QA.md](ANALISE_REQUISITOS_QA.md), [PLANO_DE_TESTES.md](PLANO_DE_TESTES.md), [API.md](API.md)

---

## Convenções

- **Pré-condição:** estado do sistema antes dos passos.
- **Passos:** ações executadas (requisição HTTP ou chamada de função).
- **Resultado esperado:** resposta ou comportamento a ser validado.
- **Tipo:** Unitário (U) | Integração/Rota (I) | Fluxo (F).

---

## 1. Autenticação

### CT-AUTH-01: Login com credenciais válidas (solicitante)

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-AUTH-01 |
| **Tipo** | I |
| **Objetivo** | Verificar que solicitante loga e é redirecionado para `/`. |
| **Pré-condição** | Usuário solicitante existe no sistema; sessão vazia. |
| **Passos** | 1. GET `/login`<br>2. POST `/login` com `email` e `senha` válidos de um solicitante |
| **Resultado esperado** | 1. 200, página de login.<br>2. 302 para `/`; sessão com usuário logado; flash de boas-vindas. |
| **Prioridade** | Alta |

---

### CT-AUTH-02: Login com credenciais válidas (supervisor/admin)

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-AUTH-02 |
| **Tipo** | I |
| **Objetivo** | Supervisor/admin após login vai para `/admin`. |
| **Pré-condição** | Usuário supervisor ou admin existe. |
| **Passos** | 1. POST `/login` com email/senha de supervisor ou admin |
| **Resultado esperado** | 302 para `/admin`. |
| **Prioridade** | Alta |

---

### CT-AUTH-03: Login com email ou senha vazios

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-AUTH-03 |
| **Tipo** | I |
| **Objetivo** | Formulário exige email e senha. |
| **Passos** | 1. POST `/login` com `email=""` e/ou `senha=""` |
| **Resultado esperado** | 200 (permanece na página de login); mensagem de erro (ex.: email/senha obrigatórios). |
| **Prioridade** | Alta |

---

### CT-AUTH-04: Login com credenciais inválidas

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-AUTH-04 |
| **Tipo** | I |
| **Objetivo** | Email ou senha incorretos não criam sessão. |
| **Passos** | 1. POST `/login` com email existente e senha errada (ou email inexistente) |
| **Resultado esperado** | 200; flash de erro (ex.: email ou senha incorretos); não redireciona. |
| **Prioridade** | Alta |

---

### CT-AUTH-05: Logout

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-AUTH-05 |
| **Tipo** | I |
| **Objetivo** | Logout encerra sessão e redireciona para login. |
| **Pré-condição** | Usuário logado. |
| **Passos** | 1. GET `/logout` |
| **Resultado esperado** | 302 para `/login`; sessão encerrada; próxima requisição a rota protegida redireciona para login. |
| **Prioridade** | Alta |

---

### CT-AUTH-06: Acesso a rota protegida sem login

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-AUTH-06 |
| **Tipo** | I |
| **Objetivo** | Rotas que exigem login redirecionam para `/login`. |
| **Passos** | 1. GET `/` (ou GET `/admin`) sem sessão |
| **Resultado esperado** | 302 para `/login`. |
| **Prioridade** | Alta |

---

### CT-AUTH-07: API protegida sem login retorna 401

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-AUTH-07 |
| **Tipo** | I |
| **Objetivo** | APIs que exigem login retornam 401 JSON (não 302). |
| **Passos** | 1. POST `/api/carregar-mais` sem cookie de sessão |
| **Resultado esperado** | 401; corpo JSON com indicativo de login obrigatório (ex.: `requer_login: true`). |
| **Prioridade** | Média |

---

## 2. Criação de Chamado (Validação)

### CT-CHAM-01: Formulário válido (sem anexo, categoria diferente de Projetos)

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-CHAM-01 |
| **Tipo** | U |
| **Objetivo** | Validar que formulário com descrição (≥3 chars), tipo e categoria válidos retorna sem erros. |
| **Passos** | 1. Chamar `validar_novo_chamado(form, None)` com `form = { descricao: 'Descrição com mais de 3 caracteres', tipo: 'Manutencao', categoria: 'Chamado' }` |
| **Resultado esperado** | Lista de erros vazia. |
| **Prioridade** | Alta |

---

### CT-CHAM-02: Descrição obrigatória

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-CHAM-02 |
| **Tipo** | U |
| **Objetivo** | Descrição vazia gera erro. |
| **Passos** | 1. `validar_novo_chamado({ descricao: '', tipo: 'Manutencao', categoria: 'Chamado' })` |
| **Resultado esperado** | Lista contém mensagem indicando que a descrição é obrigatória. |
| **Prioridade** | Alta |

---

### CT-CHAM-03: Descrição com menos de 3 caracteres

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-CHAM-03 |
| **Tipo** | U |
| **Objetivo** | Descrição com menos de 3 caracteres é rejeitada. |
| **Passos** | 1. `validar_novo_chamado({ descricao: 'ab', tipo: 'Manutencao', categoria: 'Chamado' })` |
| **Resultado esperado** | Erro mencionando mínimo 3 caracteres. |
| **Prioridade** | Alta |

---

### CT-CHAM-04: Setor/Tipo obrigatório

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-CHAM-04 |
| **Tipo** | U |
| **Objetivo** | Tipo (setor) vazio gera erro. |
| **Passos** | 1. `validar_novo_chamado({ descricao: 'Descrição válida', tipo: '', categoria: 'Chamado' })` |
| **Resultado esperado** | Erro indicando necessidade de selecionar Setor/Tipo. |
| **Prioridade** | Alta |

---

### CT-CHAM-05: Categoria Projetos sem código RL

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-CHAM-05 |
| **Tipo** | U |
| **Objetivo** | Para Projetos, RL é obrigatório. |
| **Passos** | 1. `validar_novo_chamado({ descricao: 'Projeto X', tipo: 'Engenharia', categoria: 'Projetos', rl_codigo: '' })` |
| **Resultado esperado** | Erro indicando que para Projetos o código RL é obrigatório. |
| **Prioridade** | Alta |

---

### CT-CHAM-06: Categoria Projetos com código RL válido

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-CHAM-06 |
| **Tipo** | U |
| **Objetivo** | Projetos com RL preenchido (ex.: '045', 'ABC-01', '123/2026 (rev.1)') é aceito. |
| **Passos** | 1. `validar_novo_chamado({ descricao: 'Projeto Y', tipo: 'Engenharia', categoria: 'Projetos', rl_codigo: '045' })` |
| **Resultado esperado** | Lista de erros vazia. |
| **Prioridade** | Alta |

---

### CT-CHAM-07: Código RL com caracteres inválidos

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-CHAM-07 |
| **Tipo** | U |
| **Objetivo** | RL com caracteres não permitidos (ex.: @ # %) gera erro. |
| **Passos** | 1. `validar_novo_chamado({ descricao: 'Projeto', tipo: 'Engenharia', categoria: 'Projetos', rl_codigo: '04@123' })` |
| **Resultado esperado** | Erro relacionado ao código RL / caracteres permitidos. |
| **Prioridade** | Média |

---

### CT-CHAM-08: Código RL com mais de 100 caracteres

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-CHAM-08 |
| **Tipo** | U |
| **Objetivo** | RL com mais de 100 caracteres é rejeitado. |
| **Passos** | 1. `validar_novo_chamado({ descricao: 'Projeto', tipo: 'Engenharia', categoria: 'Projetos', rl_codigo: 'A'*101 })` |
| **Resultado esperado** | Erro mencionando máximo 100 caracteres. |
| **Prioridade** | Média |

---

### CT-CHAM-09: Anexo com extensão não permitida

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-CHAM-09 |
| **Tipo** | U |
| **Objetivo** | Arquivo .exe (ou outra não permitida) gera erro. |
| **Passos** | 1. `validar_novo_chamado(form, arquivo)` com `arquivo.filename = 'documento.exe'` |
| **Resultado esperado** | Erro de formato/extensão inválida; permitidos: png, jpg, jpeg, pdf, xlsx. |
| **Prioridade** | Alta |

---

### CT-CHAM-10: Anexo com extensão permitida

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-CHAM-10 |
| **Tipo** | U |
| **Objetivo** | PDF (ou png, jpg, jpeg, xlsx) não gera erro de arquivo. |
| **Passos** | 1. `validar_novo_chamado({ descricao: 'Ok', tipo: 'Manutencao', categoria: 'Chamado' }, arquivo)` com `arquivo.filename = 'anexo.pdf'` |
| **Resultado esperado** | Nenhum erro relacionado a arquivo (outros campos válidos). |
| **Prioridade** | Média |

---

## 3. Atualização de Status (API)

### CT-STAT-01: Atualizar status com sucesso

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-STAT-01 |
| **Tipo** | I |
| **Objetivo** | POST `/api/atualizar-status` com payload válido e chamado existente retorna 200. |
| **Pré-condição** | Usuário logado; chamado existe no Firestore (mock). |
| **Passos** | 1. POST `/api/atualizar-status`, JSON `{ chamado_id: '<id_valido>', novo_status: 'Em Atendimento' }`, header CSRF se necessário |
| **Resultado esperado** | 200; corpo `{ sucesso: true, mensagem: '...', novo_status: 'Em Atendimento' }`. |
| **Prioridade** | Alta |

---

### CT-STAT-02: Atualizar status sem chamado_id

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-STAT-02 |
| **Tipo** | I |
| **Objetivo** | Ausência de chamado_id retorna 400. |
| **Passos** | 1. POST `/api/atualizar-status` com JSON `{ novo_status: 'Aberto' }` (usuário logado) |
| **Resultado esperado** | 400; `{ sucesso: false, erro: 'chamado_id é obrigatório' }` (ou equivalente). |
| **Prioridade** | Alta |

---

### CT-STAT-03: Atualizar status com status inválido

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-STAT-03 |
| **Tipo** | I |
| **Objetivo** | novo_status diferente de Aberto, Em Atendimento, Concluído retorna 400. |
| **Passos** | 1. POST `/api/atualizar-status` com `novo_status: 'Cancelado'` |
| **Resultado esperado** | 400; mensagem de status inválido. |
| **Prioridade** | Alta |

---

### CT-STAT-04: Atualizar status de chamado inexistente

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-STAT-04 |
| **Tipo** | I |
| **Objetivo** | Chamado não encontrado retorna 404. |
| **Passos** | 1. POST `/api/atualizar-status` com chamado_id que não existe (mock retorna inexistente) |
| **Resultado esperado** | 404; `{ sucesso: false, erro: 'Chamado não encontrado' }`. |
| **Prioridade** | Alta |

---

### CT-STAT-05: Bulk-status como solicitante retorna 403

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-STAT-05 |
| **Tipo** | I |
| **Objetivo** | Apenas supervisor e admin podem usar bulk-status. |
| **Pré-condição** | Cliente logado como solicitante. |
| **Passos** | 1. POST `/api/bulk-status` com JSON `{ chamado_ids: ['id1'], novo_status: 'Concluído' }` |
| **Resultado esperado** | 403; `{ sucesso: false, erro: 'Acesso negado' }`. |
| **Prioridade** | Alta |

---

### CT-STAT-06: Bulk-status com chamado_ids não-lista retorna 400

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-STAT-06 |
| **Tipo** | I |
| **Objetivo** | chamado_ids deve ser array. |
| **Pré-condição** | Cliente logado como supervisor ou admin. |
| **Passos** | 1. POST `/api/bulk-status` com `chamado_ids: "id1"` (string) ou omitido |
| **Resultado esperado** | 400; erro indicando que chamado_ids deve ser lista (ou equivalente). |
| **Prioridade** | Média |

---

### CT-STAT-07: Bulk-status com novo_status inválido retorna 400

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-STAT-07 |
| **Tipo** | I |
| **Objetivo** | novo_status deve ser Aberto, Em Atendimento ou Concluído. |
| **Passos** | 1. POST `/api/bulk-status` com `chamado_ids: ['id1'], novo_status: 'Fechado'` (supervisor logado) |
| **Resultado esperado** | 400; erro de novo_status inválido. |
| **Prioridade** | Média |

---

## 4. Edição de Chamado (API)

### CT-EDIT-01: Editar chamado como solicitante retorna 403

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-EDIT-01 |
| **Tipo** | I |
| **Objetivo** | Apenas supervisor e admin podem editar via API. |
| **Pré-condição** | Cliente logado como solicitante. |
| **Passos** | 1. POST `/api/editar-chamado` com FormData `chamado_id=<id>` |
| **Resultado esperado** | 403; `{ sucesso: false, erro: 'Acesso negado' }`. |
| **Prioridade** | Alta |

---

### CT-EDIT-02: Editar chamado sem chamado_id retorna 400

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-EDIT-02 |
| **Tipo** | I |
| **Objetivo** | chamado_id é obrigatório. |
| **Pré-condição** | Cliente logado como supervisor. |
| **Passos** | 1. POST `/api/editar-chamado` com FormData vazio ou sem campo chamado_id |
| **Resultado esperado** | 400; erro indicando obrigatoriedade do ID do chamado. |
| **Prioridade** | Alta |

---

### CT-EDIT-03: Editar chamado inexistente retorna 404

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-EDIT-03 |
| **Tipo** | I |
| **Objetivo** | Chamado não encontrado retorna 404. |
| **Pré-condição** | Supervisor logado; mock Firestore retorna documento inexistente. |
| **Passos** | 1. POST `/api/editar-chamado` com chamado_id inexistente |
| **Resultado esperado** | 404; `{ sucesso: false, erro: 'Chamado não encontrado' }`. |
| **Prioridade** | Alta |

---

### CT-EDIT-04: Supervisor de outra área não pode editar chamado

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-EDIT-04 |
| **Tipo** | I |
| **Objetivo** | Supervisor só edita chamados da sua área. |
| **Pré-condição** | Supervisor com área 'Manutencao'; chamado com area 'TI'. |
| **Passos** | 1. POST `/api/editar-chamado` com id desse chamado (área TI) |
| **Resultado esperado** | 403; mensagem indicando que só pode editar chamados da sua área. |
| **Prioridade** | Alta |

---

## 5. Paginação e Listagem (API)

### CT-PAG-01: GET paginar sem login retorna 401 ou redireciona

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-PAG-01 |
| **Tipo** | I |
| **Objetivo** | Endpoint exige autenticação. |
| **Passos** | 1. GET `/api/chamados/paginar` sem sessão |
| **Resultado esperado** | 302 para login ou 401 JSON conforme implementação. |
| **Prioridade** | Média |

---

### CT-PAG-02: POST carregar-mais retorna estrutura esperada

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-PAG-02 |
| **Tipo** | I |
| **Objetivo** | Resposta contém sucesso, chamados, cursor_proximo, tem_proxima. |
| **Pré-condição** | Usuário logado (ex.: supervisor); mock de filtros retorna lista e cursor. |
| **Passos** | 1. POST `/api/carregar-mais` com JSON `{ cursor: null, limite: 20 }` |
| **Resultado esperado** | 200; corpo com `sucesso: true`, `chamados` (array), `cursor_proximo`, `tem_proxima`. |
| **Prioridade** | Alta |

---

## 6. Chamado por ID (API)

### CT-ID-01: Solicitante acessando chamado de outro usuário retorna 403

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-ID-01 |
| **Tipo** | I |
| **Objetivo** | Solicitante só vê chamados próprios. |
| **Pré-condição** | Solicitante logado; chamado com solicitante_id diferente. |
| **Passos** | 1. GET `/api/chamado/<chamado_id>` |
| **Resultado esperado** | 403; `{ sucesso: false, erro: 'Acesso negado' }`. |
| **Prioridade** | Alta |

---

### CT-ID-02: Supervisor vê chamado da sua área

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-ID-02 |
| **Tipo** | I |
| **Objetivo** | Supervisor com área X vê chamado com area X. |
| **Pré-condição** | Supervisor com areas = ['Manutencao']; chamado.area = 'Manutencao'. |
| **Passos** | 1. GET `/api/chamado/<chamado_id>` |
| **Resultado esperado** | 200; corpo com dados do chamado. |
| **Prioridade** | Alta |

---

## 7. Permissões (Serviço)

### CT-PERM-01: Admin pode ver qualquer chamado

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-PERM-01 |
| **Tipo** | U |
| **Objetivo** | usuario_pode_ver_chamado(admin, chamado) retorna True. |
| **Passos** | 1. Chamar `usuario_pode_ver_chamado(user_admin, chamado)` para qualquer chamado |
| **Resultado esperado** | True. |
| **Prioridade** | Alta |

---

### CT-PERM-02: Supervisor pode ver apenas chamado da sua área

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-PERM-02 |
| **Tipo** | U |
| **Objetivo** | Supervisor com areas ['Manutencao'] vê chamado.area 'Manutencao'; não vê 'TI'. |
| **Passos** | 1. user.perfil='supervisor', user.areas=['Manutencao']; chamado.area='Manutencao' → True<br>2. chamado.area='TI' → False |
| **Resultado esperado** | True no primeiro caso; False no segundo. |
| **Prioridade** | Alta |

---

### CT-PERM-03: Solicitante não tem perfil supervisor/admin

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-PERM-03 |
| **Tipo** | U |
| **Objetivo** | usuario_pode_ver_chamado(solicitante, chamado) retorna False (regra de “ver como supervisor”). |
| **Passos** | 1. user.perfil='solicitante'; chamado qualquer |
| **Resultado esperado** | False. |
| **Prioridade** | Média |

---

## 8. Notificações e Web Push

### CT-NOT-01: GET notificações sem login retorna 401

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-NOT-01 |
| **Tipo** | I |
| **Passos** | 1. GET `/api/notificacoes` sem sessão |
| **Resultado esperado** | 401; corpo com indicativo de login (ex.: requer_login). |
| **Prioridade** | Média |

---

### CT-NOT-02: GET notificações retorna estrutura

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-NOT-02 |
| **Tipo** | I |
| **Objetivo** | Resposta contém notificacoes e total_nao_lidas. |
| **Pré-condição** | Usuário logado; mock de listar/contar. |
| **Passos** | 1. GET `/api/notificacoes` |
| **Resultado esperado** | 200; `notificacoes` (array), `total_nao_lidas` (número). |
| **Prioridade** | Média |

---

### CT-PUSH-01: POST push-subscribe sem subscription retorna 400

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-PUSH-01 |
| **Tipo** | I |
| **Passos** | 1. POST `/api/push-subscribe` com JSON `{}` ou sem campo subscription |
| **Resultado esperado** | 400; erro indicando subscription inválida/ausente. |
| **Prioridade** | Baixa |

---

## 9. Health e Service Worker

### CT-HEALTH-01: Health check retorna 200

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-HEALTH-01 |
| **Tipo** | I |
| **Objetivo** | Endpoint de health para load balancer. |
| **Passos** | 1. GET `/health` |
| **Resultado esperado** | 200; `{ status: 'ok' }`. |
| **Prioridade** | Alta |

---

### CT-SW-01: Service worker é servido

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-SW-01 |
| **Tipo** | I |
| **Passos** | 1. GET `/sw.js` |
| **Resultado esperado** | 200; Content-Type JavaScript; corpo contendo código do service worker. |
| **Prioridade** | Média |

---

## 10. Exceções e Modelo Chamado

### CT-EXC-01: Chamado.from_dict com dados vazios

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-EXC-01 |
| **Tipo** | U |
| **Objetivo** | from_dict({}) ou None levanta ValidacaoChamadoError. |
| **Passos** | 1. Chamado.from_dict({}) ou from_dict(None) |
| **Resultado esperado** | ValidacaoChamadoError (ou equivalente) com mensagem de dados vazios. |
| **Prioridade** | Média |

---

## 11. Alterar senha obrigatória

### CT-SENHA-01: Troca de senha com dados válidos

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-SENHA-01 |
| **Tipo** | I |
| **Objetivo** | Usuário com must_change_password=True altera senha e é redirecionado conforme perfil. |
| **Pré-condição** | Usuário logado com must_change_password=True; nova senha ≥ 6 caracteres, confirmação igual, diferente de 123456. |
| **Passos** | 1. GET `/alterar-senha-obrigatoria`<br>2. POST `/alterar-senha-obrigatoria` com `nova_senha` e `confirmar_senha` válidos |
| **Resultado esperado** | 2. 302 para `/` (solicitante) ou `/admin` (supervisor/admin); flash de sucesso. |
| **Prioridade** | Média |

---

### CT-SENHA-02: Senha com menos de 6 caracteres

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-SENHA-02 |
| **Tipo** | I |
| **Objetivo** | Nova senha com menos de 6 caracteres é rejeitada. |
| **Passos** | 1. POST `/alterar-senha-obrigatoria` com `nova_senha=12345`, `confirmar_senha=12345` (usuário com must_change_password) |
| **Resultado esperado** | 200 ou 302 para mesma página; flash de erro (mínimo 6 caracteres). |
| **Prioridade** | Média |

---

### CT-SENHA-03: Usuário sem obrigação de troca acessa rota

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-SENHA-03 |
| **Tipo** | I |
| **Objetivo** | Usuário já com senha alterada ou admin é redirecionado para dashboard. |
| **Passos** | 1. GET `/alterar-senha-obrigatoria` com usuário logado onde must_change_password=False (ou admin) |
| **Resultado esperado** | 302 para `/` ou `/admin` (não permanece na tela de troca). |
| **Prioridade** | Baixa |

---

## 12. Dashboard, export e relatórios

### CT-DASH-01: GET /admin com login retorna 200

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-DASH-01 |
| **Tipo** | I |
| **Objetivo** | Supervisor ou admin acessa dashboard e recebe página de listagem. |
| **Pré-condição** | Cliente logado como supervisor ou admin. |
| **Passos** | 1. GET `/admin` |
| **Resultado esperado** | 200; HTML com conteúdo do dashboard (lista/filtros). |
| **Prioridade** | Alta |

---

### CT-EXP-01: Exportar sem permissão retorna 403

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-EXP-01 |
| **Tipo** | I |
| **Objetivo** | Solicitante não acessa export. |
| **Pré-condição** | Cliente logado como solicitante. |
| **Passos** | 1. GET `/exportar` ou GET `/admin/relatorios` |
| **Resultado esperado** | 403 ou 302 para login/dashboard conforme implementação. |
| **Prioridade** | Média |

---

### CT-EXP-02: Exportar com supervisor/admin retorna 200

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-EXP-02 |
| **Tipo** | I |
| **Objetivo** | Supervisor ou admin acessa export ou relatórios. |
| **Pré-condição** | Cliente logado como supervisor ou admin; mock de dados se necessário. |
| **Passos** | 1. GET `/exportar` ou GET `/admin/relatorios` |
| **Resultado esperado** | 200 (planilha ou página de relatórios). |
| **Prioridade** | Média |

---

## 13. Admin: usuários, categorias, traduções

### CT-ADM-01: Rotas admin apenas para admin (usuários/categorias)

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-ADM-01 |
| **Tipo** | I |
| **Objetivo** | Solicitante ou supervisor não acessa CRUD de usuários ou categorias (apenas admin). |
| **Pré-condição** | Cliente logado como solicitante ou supervisor. |
| **Passos** | 1. GET `/admin/usuarios`, GET `/admin/categorias` |
| **Resultado esperado** | 403 ou redirecionamento conforme regra de perfil (apenas admin). |
| **Prioridade** | Alta |

---

### CT-ADM-02: Admin acessa listagem de usuários e categorias

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-ADM-02 |
| **Tipo** | I |
| **Objetivo** | Admin consegue abrir páginas de listagem. |
| **Pré-condição** | Cliente logado como admin. |
| **Passos** | 1. GET `/admin/usuarios`, GET `/admin/categorias` |
| **Resultado esperado** | 200; HTML com lista (ou vazia). |
| **Prioridade** | Média |

---

## 14. Segurança (Origin/Referer) e rate limit

### CT-SEC-01: POST sensível com Origin inválido rejeitado

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-SEC-01 |
| **Tipo** | I |
| **Objetivo** | Quando APP_BASE_URL está definido, requisição POST com Origin diferente é rejeitada. |
| **Pré-condição** | App configurado com APP_BASE_URL; cliente envia header Origin de outro domínio. |
| **Passos** | 1. POST para endpoint sensível (ex.: `/api/atualizar-status`) com header `Origin: https://site-estranho.com` |
| **Resultado esperado** | 403 ou 400 (rejeição por origem). |
| **Prioridade** | Média |

---

### CT-RATE-01: Rate limit em login (quando testável)

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-RATE-01 |
| **Tipo** | I |
| **Objetivo** | Exceder limite de tentativas de login (ex.: 5/min) retorna 429 ou bloqueio. |
| **Passos** | 1. Enviar N+1 requisições POST `/login` no mesmo minuto (N = limite configurado) |
| **Resultado esperado** | Última requisição retorna 429 ou mensagem de limite excedido (se rate limit ativo em testes). |
| **Prioridade** | Baixa |

---

## 15. Escalonamento, Multi-setor e SLA (Onda 6)

### CT-ESC-01: Isolamento supervisor mesma área

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-ESC-01 |
| **Tipo** | U |
| **Objetivo** | Supervisor A não vê chamado atribuído ao Supervisor B, mesmo na mesma área. |
| **Pré-condição** | Chamado com `responsavel_id=sup_b`, `supervisor_ids_com_acesso=["sup_b"]`; sup_a com mesma área. |
| **Passos** | 1. Chamar `usuario_pode_ver_chamado(sup_a, chamado)` |
| **Resultado esperado** | Retorna `False`. |
| **Prioridade** | Alta |

---

### CT-ESC-02: Fila sem owner visível

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-ESC-02 |
| **Tipo** | U |
| **Objetivo** | Chamado Aberto sem `responsavel_id` é visível para supervisor da área (fila). |
| **Pré-condição** | Chamado com `responsavel_id=None`, `supervisor_ids_com_acesso=["sup_a"]`; sup_a com área correspondente. |
| **Passos** | 1. Chamar `usuario_pode_ver_chamado(sup_a, chamado)` |
| **Resultado esperado** | Retorna `True`. |
| **Prioridade** | Alta |

---

### CT-ESC-03: Claim Aberto → Em Atendimento

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-ESC-03 |
| **Tipo** | I |
| **Objetivo** | POST status `Em Atendimento` em chamado `Aberto` sem owner atribui `responsavel_id = current_user.id`. |
| **Pré-condição** | Chamado com `status=Aberto`, `responsavel_id=None`; usuário supervisor autenticado. |
| **Passos** | 1. Chamar `atualizar_status_chamado(chamado_id, "Em Atendimento", user_id, user_nome)` |
| **Resultado esperado** | `sucesso=True`; `responsavel_id = user_id`; `data_em_atendimento` gravado. |
| **Prioridade** | Alta |

---

### CT-ESC-04: Transferir área (motivo + supervisor obrigatório)

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-ESC-04 |
| **Tipo** | I |
| **Objetivo** | `transferir_area` troca área e owner; ex-owner perde visão; novo owner ganha. |
| **Pré-condição** | Owner sup_orig ativo; sup_dest em área destino. |
| **Passos** | 1. `transferir_area(chamado_id, "Manutencao", "sup_dest", "motivo", sup_orig)` |
| **Resultado esperado** | `sucesso=True`; `supervisor_ids_com_acesso` não contém sup_orig; contém sup_dest. |
| **Prioridade** | Alta |

---

### CT-ESC-05: Escalonar colega mesma área

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-ESC-05 |
| **Tipo** | I |
| **Objetivo** | `escalonar_colega` troca `responsavel_id` na mesma área; motivo vazio lança ValueError. |
| **Pré-condição** | Owner sup_a; colega sup_b na mesma área. |
| **Passos** | 1. `escalonar_colega(id, "sup_b", "   ", sup_a)` → ValueError.<br>2. `escalonar_colega(id, "sup_b", "Motivo", sup_a)` → sucesso |
| **Resultado esperado** | Passo 1: `ValueError`. Passo 2: `sucesso=True`; `responsavel_id="sup_b"`. |
| **Prioridade** | Alta |

---

### CT-ESC-06: Incluir participantes

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-ESC-06 |
| **Tipo** | I |
| **Objetivo** | Owner inclui supervisor de outra área como participante; `supervisor_ids_com_acesso` atualizado. |
| **Pré-condição** | Chamado com owner; sup_b em área diferente. |
| **Passos** | 1. `incluir_participantes(id, [{"supervisor_id":"sup_b","area":"TI"}], owner)` |
| **Resultado esperado** | `sucesso=True`; `adicionados=[{...}]`; `supervisor_ids_com_acesso` inclui sup_b. |
| **Prioridade** | Alta |

---

### CT-ESC-07: Concluí minha parte + bloqueio fechamento global

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-ESC-07 |
| **Tipo** | U |
| **Objetivo** | `pode_concluir_global` retorna False com participante pendente; True quando todos concluídos. |
| **Pré-condição** | Chamado com participante `status=pendente`. |
| **Passos** | 1. `pode_concluir_global(chamado_com_pendente)` → False.<br>2. Marcar participante como `concluido`.<br>3. `pode_concluir_global(chamado_concluido)` → True |
| **Resultado esperado** | Passo 1: `False`. Passo 3: `True`. |
| **Prioridade** | Alta |

---

### CT-ESC-08: Gestor dashboard read-only + 403 write

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-ESC-08 |
| **Tipo** | I |
| **Objetivo** | Gestor acessa `/gestor/dashboard` (200) mas não pode alterar status. |
| **Pré-condição** | Usuário com `is_gestor_only=True`. |
| **Passos** | 1. GET `/gestor/dashboard` autenticado como gestor.<br>2. `verificar_permissao_mudanca_status(gestor, chamado, "Concluído")` |
| **Resultado esperado** | 1. HTTP 200. 2. `(False, "Acesso negado: gestores têm visão read-only")`. |
| **Prioridade** | Alta |

---

### CT-SLA-01: Escada A — degrau +1h útil após abertura 11:00 → notificação 13:30

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-SLA-01 |
| **Tipo** | U |
| **Objetivo** | Threshold de 60 min úteis atingido às 13:30 (não 12:30), pois almoço 11:30–13:00 não conta. |
| **Pré-condição** | `SLA_HORARIO_INICIO=07:00`, `SLA_ALMOCO_INICIO=11:30`, `SLA_ALMOCO_FIM=13:00`. |
| **Passos** | 1. `minutos_uteis_entre(11:00, 12:30)` → deve ser < 60.<br>2. `minutos_uteis_entre(11:00, 13:30)` → deve ser ≥ 60 |
| **Resultado esperado** | `min_12h30 < 60` e `min_13h30 ≥ 60`. |
| **Prioridade** | Alta |

---

### CT-SLA-02: Escada A/B — nenhum envio fora janela (almoço, após 16:30, fim de semana)

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-SLA-02 |
| **Tipo** | U |
| **Objetivo** | `pode_enviar_notificacao_agora()` retorna False fora da janela útil DTX. |
| **Pré-condição** | Timezone `America/Sao_Paulo`. |
| **Passos** | 1. Sexta 16:45 BRT.<br>2. Sexta 14:00 BRT (dentro).<br>3. Sábado 10:00 BRT |
| **Resultado esperado** | 1. `False`. 2. `True`. 3. `False`. |
| **Prioridade** | Alta |

---

### CT-SLA-03: Escada B — deadline Projetos 2d / demais 3d úteis; data_em_atendimento imutável

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-SLA-03 |
| **Tipo** | U/I |
| **Objetivo** | Editar descrição de chamado em atendimento não altera `data_em_atendimento`. |
| **Pré-condição** | Chamado `Em Atendimento` com `data_em_atendimento` gravado. |
| **Passos** | 1. `processar_edicao_chamado(..., nova_descricao="X", ...)` |
| **Resultado esperado** | Payload de update enviado ao Firestore não contém `data_em_atendimento`. |
| **Prioridade** | Alta |

---

### CT-SLA-04: Avisos 50%/80% + badge em_risco ≥50%

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-SLA-04 |
| **Tipo** | I |
| **Objetivo** | `processar_avisos_resolucao()` grava flag `alerta_supervisor_50_enviado` ao atingir 50% do prazo; flag é idempotente. |
| **Pré-condição** | Chamado `Em Atendimento` com `data_em_atendimento` e percentual ≥ 50%. |
| **Passos** | 1. Executar `processar_avisos_resolucao()` com mock de chamado elegível.<br>2. Executar novamente → não deve reenviar |
| **Resultado esperado** | 1. `notificados_50=1`, flag gravada. 2. `notificados_50=0` (idempotente). |
| **Prioridade** | Alta |

---

---

## 16. Nível 1 — Requester (Lacunas fechadas)

### CT-REQ-01: Criação com observadores → e-mail enviado a cada um

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-REQ-01 |
| **Tipo** | U |
| **Objetivo** | `notificar_observadores_criacao` envia e-mail a cada observador na lista. |
| **Pré-condição** | Lista de observadores com 2 entradas, cada uma com `email` válido. |
| **Passos** | 1. Chamar `notificar_observadores_criacao(chamado_id, "CH-001", "TI", "João", obs_list)` |
| **Resultado esperado** | `enviar_email` chamado 2 vezes; endereços corretos. |
| **Arquivo de teste** | `tests/test_services/test_chamado_notificacao_service.py::TestNotificarObservadoresCriacao` |
| **Prioridade** | Alta |

---

### CT-REQ-02: Observador sem e-mail não recebe notificação

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-REQ-02 |
| **Tipo** | U |
| **Objetivo** | Observador com `email=""` é ignorado silenciosamente por `notificar_observadores_criacao`. |
| **Pré-condição** | Lista com 2 observadores: 1 sem e-mail, 1 com e-mail. |
| **Passos** | 1. Chamar `notificar_observadores_criacao(...)` |
| **Resultado esperado** | `enviar_email` chamado apenas 1 vez (para o que tem e-mail). |
| **Arquivo de teste** | `tests/test_services/test_chamado_notificacao_service.py::TestNotificarObservadoresCriacao::test_observador_sem_email_ignorado` |
| **Prioridade** | Alta |

---

### CT-REQ-03: Histórico gravado na criação com observadores

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-REQ-03 |
| **Tipo** | U/I |
| **Objetivo** | `criar_chamado` grava `Historico(acao="inclusao_observadores")` quando há observadores. |
| **Pré-condição** | FormData com `observadores_json` contendo ao menos 1 observador válido. |
| **Passos** | 1. `criar_chamado(form, solicitante)` com observadores na lista |
| **Resultado esperado** | `Historico.save()` chamado 2×: 1 para "criacao" e 1 para "inclusao_observadores". |
| **Arquivo de teste** | `app/services/chamados_criacao_service.py` (lógica testada via integração) |
| **Prioridade** | Média |

---

### CT-REQ-04: Edição de descrição pelo solicitante (janela 30 min)

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-REQ-04 |
| **Tipo** | I |
| **Objetivo** | `POST /api/chamado/<id>/editar-solicitante` permite edição dentro da janela; bloqueia após. |
| **Pré-condição** | Chamado `Aberto` aberto há < 30 min; solicitante é o dono. |
| **Passos** | 1. POST com `{"descricao":"abc"}` (3 chars — mínimo atual) dentro da janela.<br>2. POST com o mesmo payload após 30 min. |
| **Resultado esperado** | 1. 200 `{"sucesso": true}`.<br>2. 403 com mensagem de janela encerrada. |
| **Arquivo de teste** | `tests/test_services/test_solicitante_edicao_service.py::TestEditarDescricaoSolicitante` |
| **Prioridade** | Alta |

---

### CT-REQ-05: Notificação enviada após edição de descrição

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-REQ-05 |
| **Tipo** | U |
| **Objetivo** | `editar_descricao_solicitante` dispara `_notificar_edicao_descricao` em background após sucesso. |
| **Pré-condição** | Chamado `Aberto` com dono como solicitante, dentro da janela. |
| **Passos** | 1. `editar_descricao_solicitante(chamado_id, "Novo texto", usuario)` com `_notificar_edicao_descricao` mockado |
| **Resultado esperado** | `_notificar_edicao_descricao.assert_called_once()`. |
| **Arquivo de teste** | `tests/test_services/test_solicitante_edicao_service.py::TestNotificacaoEdicaoDescricao::test_edicao_sucedida_dispara_notificacao_em_thread` |
| **Prioridade** | Alta |

---

### CT-REQ-06: Anexo tardio — sucesso e notificação

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-REQ-06 |
| **Tipo** | U/I |
| **Objetivo** | `adicionar_anexo_tardio` salva anexo no Firestore e dispara `_notificar_anexo_tardio`. |
| **Pré-condição** | Chamado `Em Atendimento` com o solicitante como dono. |
| **Passos** | 1. `adicionar_anexo_tardio(chamado_id, "path/f.pdf", "Motivo suficiente", usuario)` com `_notificar_anexo_tardio` mockado |
| **Resultado esperado** | `{"sucesso": true}`; `_notificar_anexo_tardio.assert_called_once()`. |
| **Arquivo de teste** | `tests/test_services/test_solicitante_edicao_service.py::TestNotificacaoAnexoTardio` |
| **Prioridade** | Alta |

---

### CT-REQ-07: Rota POST /api/chamado/<id>/anexo-solicitante — 403 para não-solicitante

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-REQ-07 |
| **Tipo** | I |
| **Objetivo** | Supervisor e admin recebem 403 ao tentar enviar anexo tardio. |
| **Pré-condição** | Usuário autenticado com perfil `supervisor`. |
| **Passos** | 1. POST `/api/chamado/ch1/anexo-solicitante` como supervisor (multipart). |
| **Resultado esperado** | HTTP 403 `{"sucesso": false, "erro": "Acesso restrito ao solicitante."}`. |
| **Arquivo de teste** | `tests/test_routes/test_api_anexo_solicitante.py::TestAnexoSolicitanteRota::test_supervisor_recebe_403` |
| **Prioridade** | Alta |

---

### CT-REQ-08: Rota POST /api/chamado/<id>/anexo-solicitante — 400 sem motivo

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-REQ-08 |
| **Tipo** | I |
| **Objetivo** | Motivo com menos de 10 caracteres retorna 400 sem chamar o service. |
| **Pré-condição** | Usuário `solicitante` autenticado. |
| **Passos** | 1. POST com `motivo="curto"` (< 10 chars). |
| **Resultado esperado** | HTTP 400; `adicionar_anexo_tardio` NÃO é chamado. |
| **Arquivo de teste** | `tests/test_routes/test_api_anexo_solicitante.py::TestAnexoSolicitanteRota::test_motivo_vazio_retorna_400` |
| **Prioridade** | Alta |

---

### CT-REQ-09: Cancelamento grava data_cancelamento

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-REQ-09 |
| **Tipo** | U |
| **Objetivo** | `cancelar_chamado_solicitante` inclui `data_cancelamento: SERVER_TIMESTAMP` no payload Firestore. |
| **Pré-condição** | Chamado `Aberto`, dono como solicitante. |
| **Passos** | 1. `cancelar_chamado_solicitante(chamado_id, "Motivo suficiente", usuario)` |
| **Resultado esperado** | `db.collection.update` chamado com `"data_cancelamento"` no payload. |
| **Arquivo de teste** | `tests/test_services/test_cancelamento_solicitante.py::TestCancelarDataCancelamento` |
| **Prioridade** | Alta |

---

### CT-REQ-10: Fan-out de status para observadores (Em Atendimento / Concluído)

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-REQ-10 |
| **Tipo** | U |
| **Objetivo** | `notificar_observadores_mudanca_status` envia e-mail e in-app a cada destinatário. |
| **Pré-condição** | Chamado com responsável + 1 observador; `destinatarios_do_chamado` retorna 2 usuários. |
| **Passos** | 1. `notificar_observadores_mudanca_status(chamado_id, "CH-001", "TI", "Em Atendimento", dados_chamado)` |
| **Resultado esperado** | `enviar_email` chamado 2×; `criar_notificacao` chamado 2×. |
| **Arquivo de teste** | `tests/test_services/test_chamado_notificacao_service.py::TestNotificarObservadoresMudancaStatus` |
| **Prioridade** | Alta |

---

### CT-REQ-11: status_service dispara fan-out de observadores em background

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-REQ-11 |
| **Tipo** | I |
| **Objetivo** | `atualizar_status_chamado` inclui `_notificar_observadores_status` na closure do thread ao ir para `Em Atendimento`. |
| **Pré-condição** | Chamado `Aberto`; app context disponível. |
| **Passos** | 1. `atualizar_status_chamado(chamado_id, "Em Atendimento", ...)` com `threading.Thread` mockado.<br>2. Executar closure manualmente com `_notificar_observadores_status` mockado. |
| **Resultado esperado** | `_notificar_observadores_status.assert_called_once()`. |
| **Arquivo de teste** | `tests/test_services/test_status_service.py::test_notificacao_observers_disparada_em_background` |
| **Prioridade** | Alta |

---

### CT-REQ-12: Deduplicação em destinatarios_do_chamado

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-REQ-12 |
| **Tipo** | U |
| **Objetivo** | Quando responsável também consta em `observadores`, aparece apenas 1× na lista de destinatários. |
| **Pré-condição** | `dados_chamado` com `responsavel_id="sup_1"` e observadores incluindo `{"usuario_id": "sup_1"}`. |
| **Passos** | 1. `destinatarios_do_chamado(dados_chamado)` |
| **Resultado esperado** | Lista de tamanho 2 (responsável + 1 observador único); `ids.count("sup_1") == 1`. |
| **Arquivo de teste** | `tests/test_services/test_chamado_notificacao_service.py::TestNotificarObservadoresCriacao::test_responsavel_tambem_observador_aparece_uma_vez` |
| **Prioridade** | Alta |

---

### CT-REQ-13: Notificação in-app e web push ao editar descrição

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-REQ-13 |
| **Tipo** | U |
| **Objetivo** | `notificar_edicao_descricao_solicitante` cria notificação in-app (`tipo=observador_edicao_descricao`) e web push para cada destinatário. |
| **Pré-condição** | `destinatarios_do_chamado` mockado retornando 1 usuário. |
| **Passos** | 1. Chamar `notificar_edicao_descricao_solicitante(...)` com `criar_notificacao` e `enviar_webpush_usuario` mockados. |
| **Resultado esperado** | `criar_notificacao` chamado 1× com `tipo="observador_edicao_descricao"`; `enviar_webpush_usuario` chamado 1×. |
| **Arquivo de teste** | `tests/test_services/test_chamado_notificacao_service.py::TestInAppEWebPushNotificacoes` |
| **Prioridade** | Alta |

---

### CT-REQ-14: Notificação in-app e web push ao adicionar anexo tardio

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-REQ-14 |
| **Tipo** | U |
| **Objetivo** | `notificar_anexo_tardio_chamado` cria notificação in-app (`tipo=observador_anexo_tardio`) e web push para cada destinatário. |
| **Pré-condição** | `destinatarios_do_chamado` mockado retornando 1 usuário. |
| **Passos** | 1. Chamar `notificar_anexo_tardio_chamado(...)` com `criar_notificacao` e `enviar_webpush_usuario` mockados. |
| **Resultado esperado** | `criar_notificacao` chamado 1× com `tipo="observador_anexo_tardio"`; `enviar_webpush_usuario` chamado 1×. |
| **Arquivo de teste** | `tests/test_services/test_chamado_notificacao_service.py::TestInAppEWebPushNotificacoes` |
| **Prioridade** | Alta |

---

### CT-REQ-15: Notificação in-app ao cancelar chamado

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-REQ-15 |
| **Tipo** | U |
| **Objetivo** | `notificar_cancelamento_chamado` cria notificação in-app (`tipo=observador_cancelamento`) para cada destinatário. |
| **Pré-condição** | `destinatarios_do_chamado` mockado retornando 1 usuário. |
| **Passos** | 1. Chamar `notificar_cancelamento_chamado(...)` com `criar_notificacao` e `enviar_email` mockados. |
| **Resultado esperado** | `criar_notificacao` chamado 1× com `tipo="observador_cancelamento"`. |
| **Arquivo de teste** | `tests/test_services/test_chamado_notificacao_service.py::TestInAppEWebPushNotificacoes` |
| **Prioridade** | Alta |

---

### CT-REQ-16: Web Push em mudança de status para destinatários

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-REQ-16 |
| **Tipo** | U |
| **Objetivo** | `notificar_observadores_mudanca_status` envia web push para cada destinatário além de e-mail e in-app. |
| **Pré-condição** | `destinatarios_do_chamado` mockado retornando 1 usuário; `enviar_webpush_usuario` mockado. |
| **Passos** | 1. Chamar `notificar_observadores_mudanca_status(...)` dentro de app context. |
| **Resultado esperado** | `enviar_webpush_usuario` chamado 1× por destinatário. |
| **Arquivo de teste** | `tests/test_services/test_chamado_notificacao_service.py::TestNotificarObservadoresMudancaStatusLacunas::test_webpush_enviado_por_destinatario` |
| **Prioridade** | Alta |

---

### CT-REQ-17: Tipo in-app correto para fan-out de status (observador vs. solicitante)

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-REQ-17 |
| **Tipo** | U |
| **Objetivo** | `notificar_observadores_mudanca_status` usa `observador_status_concluido` / `observador_status_em_atendimento` — não `status_concluido_confirmar` (que é exclusivo do fluxo de confirmação do solicitante). |
| **Pré-condição** | `destinatarios_do_chamado` mockado retornando 1 usuário. |
| **Passos** | 1. Chamar com `novo_status="Concluído"` → checar tipo. 2. Chamar com `novo_status="Em Atendimento"` → checar tipo. |
| **Resultado esperado** | `tipo="observador_status_concluido"` e `tipo="observador_status_em_atendimento"` respectivamente. |
| **Arquivo de teste** | `tests/test_services/test_chamado_notificacao_service.py::TestNotificarObservadoresMudancaStatusLacunas` |
| **Prioridade** | Alta |

---

### CT-REQ-18: In-app e web push na inclusão de observador (criação)

| Campo | Descrição |
|-------|-----------|
| **ID** | CT-REQ-18 |
| **Tipo** | U |
| **Objetivo** | `notificar_observadores_criacao` cria notificação in-app (`tipo=observador_incluido`) e web push para obs com `usuario_id`. Obs sem `usuario_id` não geram in-app. |
| **Pré-condição** | Lista de observadores com/sem `usuario_id`; `criar_notificacao` e `enviar_webpush_usuario` mockados. |
| **Passos** | 1. Chamar com obs contendo `usuario_id`. 2. Chamar com obs sem `usuario_id`. |
| **Resultado esperado** | Cenário 1: `criar_notificacao` chamado 1× com `tipo="observador_incluido"`. Cenário 2: `criar_notificacao` não chamado. |
| **Arquivo de teste** | `tests/test_services/test_chamado_notificacao_service.py::TestNotificarObservadoresCriacaoInApp` |
| **Prioridade** | Alta |

---

## Resumo por prioridade

- **Alta:** CT-AUTH-01 a 07, CT-CHAM-01 a 06 e 09, CT-STAT-01 a 05, CT-EDIT-01 a 04, CT-PAG-02, CT-ID-01 e 02, CT-PERM-01 e 02, CT-HEALTH-01, CT-DASH-01, CT-ADM-01, CT-ESC-01 a 08, CT-SLA-01 a 04, CT-REQ-01, 02, 04 a 18.
- **Média:** CT-AUTH-07, CT-CHAM-07, 08, 10, CT-STAT-06 e 07, CT-PAG-01, CT-PERM-03, CT-NOT-01 e 02, CT-SW-01, CT-EXC-01, CT-SENHA-01 e 02, CT-EXP-01 e 02, CT-ADM-02, CT-SEC-01, CT-REQ-03.
- **Baixa:** CT-PUSH-01, CT-SENHA-03, CT-RATE-01.

Estes casos podem ser implementados como testes automatizados (pytest) conforme o [PLANO_DE_TESTES.md](PLANO_DE_TESTES.md). Muitos já possuem equivalentes em `tests/`; este documento serve como especificação funcional e checklist de cobertura.

---

## Mapeamento para testes automatizados (pytest)

| Caso | Arquivo de teste | Nome do teste (ou equivalente) |
|------|------------------|----------------------------------|
| CT-AUTH-01, 02 | test_integration/test_login_flow.py | test_login_post_sucesso_redireciona_conforme_perfil |
| CT-AUTH-03 | test_routes/test_auth.py | test_login_post_email_senha_vazios_permanece_em_login |
| CT-AUTH-04 | test_routes/test_auth.py | test_login_post_credenciais_invalidas_nao_redireciona_para_index |
| CT-AUTH-05 | test_routes/test_auth.py | test_logout_com_usuario_logado_redireciona_para_login |
| CT-AUTH-06 | test_routes/test_auth.py | test_index_sem_login_redireciona_para_login |
| CT-AUTH-07 | test_routes/test_api.py | test_carregar_mais_sem_login_redireciona |
| CT-HEALTH-01 | test_routes/test_health_sw.py | test_health_check_retorna_200_e_ok |
| CT-SW-01 | test_routes/test_health_sw.py | test_service_worker_retorna_200_e_javascript |
| CT-STAT-01 a 07 | test_routes/test_api_status.py | test_atualizar_status_* e test_bulk_status_* |
| CT-EDIT-01 a 04 | test_routes/test_api.py | test_api_editar_chamado_* |
| CT-PAG-01, 02 | test_routes/test_api.py | test_api_chamados_paginar_sem_login_retorna_401, test_carregar_mais_retorna_estrutura_esperada |
| CT-ID-01, 02 | test_routes/test_api.py | test_api_chamado_por_id_solicitante_*, test_api_chamado_por_id_supervisor_* |
| CT-NOT-01, 02 | test_routes/test_api.py | test_api_notificacoes_* |
| CT-PUSH-01 | test_routes/test_api.py | test_api_push_subscribe_sem_subscription_* |
| CT-PERM-01 a 03 | test_services/test_permissions.py | TestUsuarioPodeVerChamado.* |
| CT-CHAM-* (validação) | test_services/test_validators.py | test_validar_novo_chamado_* |
| CT-EXC-01 | test_exceptions.py | TestChamadoFromDictLevantaValidacaoChamadoError.* |
| CT-SENHA-01 a 03 | test_routes/test_auth.py | test_alterar_senha_* (a implementar conforme cenários) |
| CT-DASH-01, CT-EXP-* | test_routes/test_dashboard.py | test_admin_*, test_exportar_* (a implementar) |
| CT-ADM-01, CT-ADM-02 | test_routes/test_usuarios.py, test_routes/test_categorias.py | test_*_requer_admin (a implementar) |
| CT-SEC-01 | test_routes/test_security_origin.py | test_*_origin_invalida |
| CT-RATE-01 | test_routes/test_auth.py | test_rate_limit_login (a implementar se configurável em test) |
| CT-ESC-01, 02 | test_services/test_permissions.py | TestUsuarioPodeVerChamado.test_supervisor_nao_ve_chamado_de_outro, test_supervisor_ve_fila_sem_owner |
| CT-ESC-03 | test_routes/test_api_escalonamento.py | test_claim_atribui_responsavel_id |
| CT-ESC-04 | test_services/test_escalonamento_service.py | test_transferir_area_atualiza_supervisor_ids_com_acesso |
| CT-ESC-05 | test_services/test_escalonamento_service.py | test_escalonar_colega_motivo_vazio_rejeita, test_escalonar_colega_sucesso |
| CT-ESC-06 | test_services/test_escalonamento_service.py | test_incluir_participantes_* |
| CT-ESC-07 | test_services/test_escalonamento_service.py | test_pode_concluir_global_falso_com_participante_pendente, test_pode_concluir_global_verdadeiro |
| CT-ESC-08 | test_routes/test_api_escalonamento.py | test_gestor_dashboard_retorna_200, test_gestor_nao_pode_mudar_status |
| CT-SLA-01 | test_services/test_business_time.py | test_minutos_uteis_pula_almoco |
| CT-SLA-02 | test_services/test_business_time.py | test_pode_enviar_notificacao_fora_janela, test_pode_enviar_notificacao_sabado |
| CT-SLA-03 | test_services/test_edicao_chamado_service.py, test_services/test_escalonamento_service.py | test_edicao_descricao_nao_altera_data_em_atendimento, test_concluir_minha_parte_nao_altera_data_em_atendimento |
| CT-SLA-04 | test_services/test_sla_escalacao_service.py | test_processar_avisos_resolucao_*, test_idempotencia_aviso_50 |
| CT-ESC-* (script QA) | tests/test_scripts/test_executar_qa_escalonamento.py | 5 testes de estrutura e exit code |
