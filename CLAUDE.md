# CLAUDE.md — Convenções do Projeto sistema_chamados

## Stack
- **Backend:** Flask 3.0 + Firestore (firebase-admin), Flask-Login, Flask-WTF (CSRF)
- **Frontend:** Tailwind CSS (CDN), GSAP 3 (ScrollTrigger, ScrollToPlugin)
- **Python:** 3.12+, pytest + unittest.mock
- **Blueprint:** único `main` — todos os módulos de rota registram nele

## Perfis de usuário
- `solicitante` — cria e acompanha os próprios chamados
- `supervisor` — gerencia chamados da sua área + relatórios
- `admin` — acesso total: chamados, usuários, categorias, traduções, relatórios

## Padrões de código

### Python / Flask
- Imports inline nas rotas (`from app.services.X import func`) — padrão do projeto
- Responses JSON: sempre `{"sucesso": bool, "erro"?: str, "dados"?: obj}`
- Decoradores de acesso: `@requer_solicitante`, `@requer_supervisor_area`, `@requer_admin`
- Serviços em `app/services/` — lógica de negócio separada das rotas
- Exceções customizadas em `app/exceptions.py`

### Testes
- Mock de Firestore: `patch('app.database.db')` ou `patch('app.services.X.db')`
- Imports inline nas rotas — patch **no módulo do serviço**, não em `api`
- CSRF desabilitado em testes: `app.config['WTF_CSRF_ENABLED'] = False`
- Fixtures em `tests/conftest.py`: `client_logado_{solicitante,supervisor,admin}`
- **Regra TDD:** nenhum código de produção sem teste falhando primeiro

### Nomenclatura
- Arquivos: `snake_case.py`
- Classes: `PascalCase`
- Funções e variáveis: `snake_case`
- Rotas URL: `kebab-case` (`/meus-chamados`, `/admin-categorias`)
- Templates: `snake_case.html`

## Ciclo de qualidade (obrigatório antes de commit)

```bash
# 1. Lint + format
ruff check app/ tests/ --fix
ruff format app/ tests/

# 2. Segurança
bandit -r app/ -ll

# 3. Testes
pytest --tb=short -q

# 4. Push (usa o script da skill)
bash skills/Essencial/git-pushing/scripts/smart_commit.sh "tipo: descrição"
```

## Conventional commits
- `feat:` nova funcionalidade
- `fix:` correção de bug
- `test:` adição/correção de testes
- `refactor:` refatoração sem mudança de comportamento
- `chore:` tarefas de manutenção (deps, config, CI)
- `docs:` documentação

## Estrutura de arquivos-chave
```
app/
├── __init__.py              # Criação da app Flask, segurança, i18n, scheduler
├── models.py                # Modelo Chamado
├── models_usuario.py        # Classe Usuario (UserMixin), to_dict/from_dict
├── models_categorias.py     # Modelo de categorias
├── database.py              # Instância Firestore
├── decoradores.py           # @requer_* decoradores
├── i18n.py                  # Internacionalização (PT-BR, EN, ES)
├── routes/
│   ├── api.py               # Rotas JSON/API
│   ├── auth.py              # Login, logout, senha
│   ├── chamados.py          # Criação e listagem (solicitante)
│   ├── dashboard.py         # Dashboard (supervisor/admin)
│   ├── usuarios.py          # Gestão de usuários (admin)
│   ├── categorias.py        # Gestão de categorias (admin)
│   └── traducoes.py         # Gestão de traduções (admin)
└── services/
    ├── chamados_criacao_service.py
    ├── chamados_listagem_service.py
    ├── status_service.py
    ├── notifications.py
    ├── notifications_inapp.py
    ├── analytics.py
    ├── dashboard_service.py
    ├── permissions.py
    ├── validators.py
    └── ...

tests/
├── conftest.py
├── test_routes/
├── test_services/
├── test_integration/
├── test_e2e/
└── test_regression/
```

## O que NÃO fazer
- Não usar `db.collection().get()` sem paginação em coleções grandes
- Não expor erros internos nas responses JSON (logar, mas retornar mensagem genérica)
- Não adicionar lógica de negócio diretamente nas rotas — usar services
- Não commitar sem passar o ciclo de qualidade acima
- Não usar `git add .` sozinho — revisar o que está sendo commitado
