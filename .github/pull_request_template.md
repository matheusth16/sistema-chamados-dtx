## Descrição

> Explique o que foi alterado e por quê. Se resolve uma issue, referencie: `Closes #123`.

## Tipo de mudança

- [ ] Bug fix
- [ ] Nova funcionalidade
- [ ] Refatoração (sem mudança de comportamento)
- [ ] Melhoria de performance
- [ ] Documentação
- [ ] Infraestrutura / CI

## Checklist

### Código
- [ ] O código segue os padrões do projeto (`ruff check app/` passa sem erros)
- [ ] Não há secrets ou credenciais no diff
- [ ] Não há `print()` ou `console.log()` de debug esquecidos
- [ ] Imports organizados e sem F401 não intencionais

### Testes
- [ ] Testes unitários adicionados/atualizados para as mudanças
- [ ] `pytest tests/` passa localmente (exceto E2E)
- [ ] Cobertura não caiu significativamente

### Segurança
- [ ] `bandit -r app/ -ll` passou sem novos findings de severidade média ou alta
- [ ] Inputs do usuário são validados/saneados
- [ ] Sem SQL injection, XSS ou outras vulnerabilidades introduzidas

### Templates / Frontend
- [ ] Novos elementos interativos têm `data-testid` para E2E
- [ ] Textos visíveis ao usuário usam `{{ t('chave') }}` (i18n)
- [ ] Layout responsivo verificado (mobile e desktop)

### Firestore
- [ ] Novas queries têm índices criados (se necessário)
- [ ] Regras de segurança do Firestore atualizadas (se aplicável)

## Como testar

> Descreva os passos para o revisor testar as mudanças manualmente.

1. ...
2. ...

## Screenshots (se aplicável)

> Adicione capturas de tela para mudanças visuais.
