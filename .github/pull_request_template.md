## Descrição

> Explique o que foi alterado e por quê. Se resolve uma issue, referencie: `Closes #123`.

## Tipo de mudança

- [ ] Bug fix
- [ ] Nova funcionalidade
- [ ] Refatoração (sem mudança de comportamento)
- [ ] Melhoria de performance
- [ ] Documentação
- [ ] Infraestrutura / CI

---

## QA — O que foi testado

> Descreva os cenários cobertos. Marque todos que se aplicam.

### Nível de teste
- [ ] **Unitário** — serviços/funções isolados com mocks
- [ ] **Integração** — fluxo completo com client Flask (sem servidor externo)
- [ ] **E2E** — navegador real contra servidor local

### Evidência de cobertura
```
# Cole o resultado de: pytest --cov=app --cov-report=term-missing -q
# Exemplo esperado: TOTAL  xxx  yyy  70%+
```

### Rotas críticas impactadas
> Marque as rotas que foram alteradas **ou** que podem ser afetadas por efeito colateral.

- [ ] `auth` — login, logout, troca de senha, onboarding
- [ ] `usuarios` — criação, edição, permissões por perfil
- [ ] `dashboard` — filtros, agregações, relatórios
- [ ] `api` — contratos JSON (sucesso/erro), paginação
- [ ] `categorias` / `traducoes` — admin

---

## Checklist de Qualidade

### Regressão
- [ ] Nenhum teste existente foi quebrado (`pytest --tb=short -q` passa)
- [ ] Comportamento anterior preservado onde não houve mudança intencional
- [ ] Casos de borda cobertos (entrada vazia, null, tamanho máximo)

### Cenários negativos
- [ ] Fluxo de erro testado (ex.: dado inválido, usuário sem permissão)
- [ ] Respostas de erro retornam `{"sucesso": false, "erro": "..."}` sem expor stack trace
- [ ] Erros do Firestore tratados (timeout, documento inexistente)

### Autorização e permissões
- [ ] Rota protegida pelos decoradores corretos (`@requer_solicitante`, `@requer_supervisor_area`, `@requer_admin`)
- [ ] Testado o acesso negado para perfil inferior ao exigido
- [ ] Supervisor não acessa dados de área diferente da sua

### i18n e fallback
- [ ] Novos textos visíveis ao usuário usam `{{ t('chave') }}` (nunca string literal no template)
- [ ] Chave adicionada em PT-BR, EN e ES (ou marcada com `# TODO i18n`)
- [ ] Fallback para PT-BR quando tradução ausente não quebra a página

### Código
- [ ] `ruff check app/ tests/` passa sem erros
- [ ] `bandit -r app/ -ll` sem novos findings de severidade média ou alta
- [ ] Sem `print()` / `console.log()` de debug
- [ ] Sem secrets ou credenciais no diff
- [ ] Lógica de negócio em `app/services/`, não nas rotas

### Firestore
- [ ] Novas queries com índices criados (se necessário)
- [ ] Sem `db.collection().get()` sem paginação em coleções grandes
- [ ] Regras de segurança do Firestore atualizadas (se aplicável)

### Templates / Frontend
- [ ] Novos elementos interativos têm `data-testid` para E2E
- [ ] Layout responsivo verificado (mobile e desktop)

---

## Como testar manualmente

> Passos para o revisor reproduzir e validar as mudanças.

1. ...
2. ...

## Screenshots (se aplicável)

> Capturas de tela para mudanças visuais (antes / depois).
