# Plano de Testes – Sistema de Chamados DTX

**Documento:** Plano e Estratégia de Testes  
**Projeto:** Sistema de Chamados DTX  
**Referência:** [ANALISE_REQUISITOS_QA.md](ANALISE_REQUISITOS_QA.md)  

---

## 1. Objetivos dos Testes

- Garantir que as **regras de negócio** (autenticação, perfis, criação/edição de chamados, status, permissões) sejam atendidas.
- Validar **APIs** (contratos, códigos HTTP, mensagens de erro) conforme documentação em [API.md](API.md).
- Cobrir **validações** (formulários, payloads) e **comportamento em erro** (400, 403, 404, 500).
- Evitar regressões em **fluxos críticos**: login, criação de chamado, atualização de status (individual e bulk), edição por supervisor/admin.

---

## 2. Escopo

### 2.1 Dentro do Escopo

| Módulo | Escopo |
|--------|--------|
| Autenticação | Login, logout, redirecionamento por perfil, rotas protegidas |
| Chamados (criação) | Validação de formulário, regra Projetos+RL, anexos, atribuição |
| API Status | Atualizar status (unitário), bulk-status (permissão + área) |
| API Edição | Editar chamado (supervisor/admin, área, campos) |
| API Paginação | GET paginar, POST carregar-mais (estrutura e filtros) |
| API Chamado por ID | GET por ID (permissão solicitante/supervisor/admin) |
| Notificações | Listar, marcar lida, ler-todas |
| Web Push | VAPID público, subscribe (validação de payload) |
| Permissões | Serviço de permissões (admin/supervisor/área) |
| Validadores | Descrição, tipo, categoria Projetos, RL, anexo |
| Utilitários e exceções | Número de chamado, exceções customizadas |
| Health / Service Worker | Health 200, sw.js servido |

### 2.2 Fora do Escopo (Nesta Fase)

- Testes de carga e performance (Firestore/Redis).
- Testes E2E em navegador (Selenium/Playwright) — podem ser adicionados depois.
- Testes de integração com Firebase real (credenciais); preferir mocks.
- Validação visual de UI (layout, i18n).

---

## 3. Estratégia e Níveis de Teste

### 3.1 Testes Unitários

- **Serviços:** `validators`, `permissions`, `status_service`, `pagination`, `filters`, `assignment`, `date_validators`, `analytics`, `notifications_inapp`.
- **Modelos:** `Chamado.from_dict` / `to_dict`, `Usuario` (onde não dependa de Firestore real).
- **Utilitários:** `gerar_numero_chamado`, `utils` diversos.
- **Exceções:** tipos e mensagens.

**Ferramenta:** pytest.  
**Dependências:** Mock de Firestore e de funções externas (email, push, etc.).

### 3.2 Testes de Integração (Rotas)

- **Rotas HTTP:** cliente Flask `app.test_client()`, sessão simulada (login mockado).
- **Cenários:** usuário não logado (302 ou 401), solicitante, supervisor, admin.
- **APIs:** POST/GET com JSON ou FormData; assert em status code e corpo JSON.

**Ferramenta:** pytest + fixtures do `conftest.py` (`client`, `client_logado_solicitante`, `client_logado_supervisor`, `client_logado_admin`, `mock_firestore`).

### 3.3 Testes de Fluxo (Integração)

- Fluxo de login (POST login → redirecionamento).
- Fluxo de criação de chamado (formulário válido/inválido).
- Fluxo de bulk-status (supervisor com/sem permissão por área).

**Ferramenta:** pytest; mocks para Firestore e serviços externos.

### 3.4 Testes de Contrato (API)

- Verificar que a resposta JSON segue o formato documentado em [API.md](API.md) (campos obrigatórios, tipos).
- Códigos HTTP: 200, 400, 403, 404, 401, 500 conforme especificação.

---

## 4. Cenários Prioritários (Resumo)

1. **Auth:** login com/sem credenciais; logout; acesso a rota protegida sem login; redirecionamento por perfil.
2. **Criação de chamado:** campos obrigatórios; descrição mínima; Projetos + RL (obrigatório, válido/inválido); anexo (extensão permitida/não permitida).
3. **Atualizar status:** sucesso; chamado inexistente (404); payload inválido (400).
4. **Bulk-status:** apenas supervisor/admin (403 para solicitante); supervisor só atualiza chamados da sua área; lista vazia/inválida (400).
5. **Editar chamado:** 403 solicitante; 400 sem `chamado_id`; 404 inexistente; 403 supervisor de outra área; sucesso com campos opcionais.
6. **Paginação:** GET paginar e POST carregar-mais com/sem cursor; estrutura de resposta com `paginacao` / `cursor_proximo`, `tem_proxima`.
7. **Chamado por ID:** 403 solicitante vendo chamado de outro; 403 supervisor de outra área; 200 com dados corretos.
8. **Notificações:** listar, marcar lida, ler-todas (estrutura e 401 sem login).
9. **Permissões:** `usuario_pode_ver_chamado` para admin, supervisor (área própria/outra), solicitante.
10. **Health / SW:** GET `/health` 200; GET `/sw.js` 200 e content-type JavaScript.

---

## 5. Ambiente e Dados de Teste

- **Config:** `FLASK_ENV=testing` (já definido em `conftest.py`); `WTF_CSRF_ENABLED=False` nos testes.
- **Fixtures:** usuários mockados com `_usuario_mock(uid, email, nome, perfil, area, areas)`.
- **Firestore:** não usar banco real nos testes automatizados; usar `patch('app.database.db', MagicMock())` ou equivalente.
- **Cobertura:** executar com `pytest --cov=app` para acompanhar cobertura; focar em rotas e serviços de negócio.

---

## 6. Critérios de Saída

- Todos os testes planejados implementados e passando.
- Testes de regressão executados antes de merge/deploy (ex.: `python scripts/verificar_dependencias.py` ou `pytest`).
- Nenhum teste que dependa de credenciais Firebase ou Redis em CI (apenas mocks).

---

## 7. Riscos e Mitigações

| Risco | Mitigação |
|-------|------------|
| Testes flaky por dependência de rede/ Firestore | Usar mocks para `app.database.db` e serviços externos |
| Cobertura baixa em rotas não documentadas | Incluir rotas críticas no plano (dashboard, usuários, categorias) conforme prioridade |
| Mudança de contrato da API | Manter casos de teste alinhados a [API.md](API.md) e atualizar ambos |

---

## 8. Documentos Relacionados

| Documento | Conteúdo |
|-----------|----------|
| [CASOS_DE_TESTE.md](CASOS_DE_TESTE.md) | Casos de teste detalhados (passo a passo) |
| [TESTES_USABILIDADE.md](TESTES_USABILIDADE.md) | Critérios de usabilidade e testes de facilidade de uso |
| [TESTES_REGRESSAO.md](TESTES_REGRESSAO.md) | Suite de regressão e como executar |
| [TESTES_API.md](TESTES_API.md) | Testes de contrato e validação da API |

## 9. Próximos Passos

- Manter [CASOS_DE_TESTE.md](CASOS_DE_TESTE.md) atualizado com os cenários passo a passo.
- Adicionar testes de integração para dashboard e relatórios quando estável.
- Considerar testes E2E para fluxos principais (login → criar chamado → ver lista) em fase posterior.

Este plano deve ser revisado quando houver mudança relevante de escopo ou de requisitos.
