# Testes de Usabilidade – Sistema de Chamados DTX

**Documento:** Critérios e testes de usabilidade (facilidade de uso para o usuário final)  
**Projeto:** Sistema de Chamados DTX  

---

## 1. Objetivo

Avaliar a **facilidade de uso** do sistema para os perfis: **solicitante**, **supervisor** e **admin**, garantindo que fluxos principais sejam intuitivos, que feedback seja claro e que erros não deixem o usuário sem orientação.

---

## 2. Critérios de Usabilidade (Checklist)

### 2.1 Autenticação

| Critério | Descrição | Como validar |
|----------|-----------|--------------|
| U-AUTH-01 | Usuário não logado que acessa página protegida é levado ao login (sem tela em branco ou 500). | Acesso a `/` ou `/admin` sem sessão → 302 para `/login`. |
| U-AUTH-02 | Após login bem-sucedido, redirecionamento correto por perfil (solicitante → `/`, supervisor/admin → `/admin`). | POST login válido → 302 para a URL esperada. |
| U-AUTH-03 | Credenciais inválidas exibem mensagem de erro (não tela em branco nem stack trace). | POST login inválido → 200 na página de login com feedback (flash). |
| U-AUTH-04 | Campos vazios no login geram mensagem clara (email/senha obrigatórios). | POST com email ou senha vazio → permanece em login com mensagem. |
| U-AUTH-05 | Logout encerra sessão e redireciona para login; próximo acesso a rota protegida pede login novamente. | GET logout → 302 login; depois GET `/` → 302 login. |

### 2.2 Criação de Chamado (Solicitante)

| Critério | Descrição | Como validar |
|----------|-----------|--------------|
| U-CHAM-01 | Formulário com dados inválidos mostra erros claros (descrição, setor, RL para Projetos). | POST com dados inválidos → 200 com lista de erros (flash). |
| U-CHAM-02 | Após criar chamado com sucesso, usuário é redirecionado (não fica na mesma tela sem feedback). | POST com dados válidos → 302 para destino esperado. |
| U-CHAM-03 | Mensagens de validação são compreensíveis (ex.: "descrição mínima 3 caracteres", "código RL obrigatório para Projetos"). | Conteúdo das mensagens de erro do validador. |

### 2.3 Dashboard e Listagem (Supervisor/Admin)

| Critério | Descrição | Como validar |
|----------|-----------|--------------|
| U-DASH-01 | APIs de listagem retornam estrutura consistente (chamados, paginação) para o frontend montar a tela. | GET/POST paginar e carregar-mais → JSON com `chamados`, `paginacao`/`cursor_proximo`, `tem_proxima`. |
| U-DASH-02 | Sem login, chamadas à API retornam 401 com indicativo de login (não 500 nem HTML de erro). | GET/POST em `/api/*` sem sessão → 401 JSON com `requer_login`. |

### 2.4 Ações sobre Chamados (Status, Edição)

| Critério | Descrição | Como validar |
|----------|-----------|--------------|
| U-STAT-01 | Atualização de status retorna sucesso ou erro explícito (chamado não encontrado, status inválido). | POST atualizar-status → 200 com `sucesso`/`mensagem` ou 400/404 com `erro`. |
| U-STAT-02 | Bulk status retorna resumo (quantos atualizados, quais falharam) para o usuário entender o resultado. | POST bulk-status → 200 com `atualizados`, `total_solicitados`, `erros`. |
| U-EDIT-01 | Edição negada (solicitante ou supervisor de outra área) retorna 403 com mensagem de "Acesso negado" / "sua área". | POST editar-chamado sem permissão → 403 JSON com mensagem clara. |

### 2.5 Notificações e Recursos Auxiliares

| Critério | Descrição | Como validar |
|----------|-----------|--------------|
| U-NOT-01 | Listagem de notificações retorna estrutura fixa (notificacoes, total_nao_lidas) para o frontend. | GET notificacoes → 200 com `notificacoes`, `total_nao_lidas`. |
| U-HEALTH-01 | Health check responde de forma previsível para monitoramento (status ok). | GET /health → 200 `{"status":"ok"}`. |

---

## 3. Testes Automatizados de Usabilidade

Os critérios acima são validados automaticamente onde possível (comportamento HTTP e estrutura de resposta). Os testes estão em:

- **`tests/test_integration/test_usabilidade_fluxos.py`** – fluxos de usuário (redirect após login, logout, formulário inválido, estrutura de API para o frontend).

O que **não** é coberto por automação (recomenda-se teste manual ou E2E):

- Clareza visual e texto na tela (i18n).
- Ordem de tabulação e acessibilidade (teclado, leitores de tela).
- Tempo de resposta percebido e feedback de loading na UI.

---

## 4. Execução

- **Checklist manual:** use a tabela da seção 2 em sessões de teste com usuários reais ou QA.
- **Testes automatizados:** `pytest tests/test_integration/test_usabilidade_fluxos.py -v`

Este documento deve ser revisado quando novos fluxos ou telas forem adicionados ao sistema.
