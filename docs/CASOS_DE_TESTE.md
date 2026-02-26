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

## Resumo por prioridade

- **Alta:** CT-AUTH-01 a 07, CT-CHAM-01 a 06 e 09, CT-STAT-01 a 05, CT-EDIT-01 a 04, CT-PAG-02, CT-ID-01 e 02, CT-PERM-01 e 02, CT-HEALTH-01.
- **Média:** CT-AUTH-07, CT-CHAM-07, 08, 10, CT-STAT-06 e 07, CT-PAG-01, CT-PERM-03, CT-NOT-01 e 02, CT-SW-01, CT-EXC-01.
- **Baixa:** CT-PUSH-01.

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
