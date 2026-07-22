# CLAUDE.md — Convenções do Projeto sistema_chamados

## Stack
- **Backend:** Flask 3.1 + Firestore (firebase-admin), Flask-Login, Flask-WTF (CSRF), Flask-Limiter (rate limiting em auth/API/dashboard, ver `app/limiter.py`), gunicorn (WSGI em produção)
- **Frontend:** Tailwind CSS (compilado via CLI, `npm run build:css` — não é CDN), GSAP 3 (ScrollTrigger, ScrollToPlugin)
- **Python:** 3.14, pytest + unittest.mock
- **Blueprint:** único `main` — todos os módulos de rota registram nele
- **Autenticação/Segurança:** MFA via TOTP + QR code (`pyotp`, `segno`, ver `app/routes/mfa.py`), SSO Microsoft/Entra ID (`msal`, ver `app/services/sso_microsoft_service.py`), criptografia de PII em repouso — LGPD (`cryptography`, ver `app/services/pii_encryption.py`)
- **Serviços externos:** Firebase/Firestore (banco), Cloudflare R2 via boto3 (anexos — bucket privado, URLs pré-assinadas), Microsoft Graph API (e-mail), Web Push (`pywebpush`, ver `app/services/webpush_service.py`)
- **Infra:** Redis (cache/backend do rate limiter, ver `app/cache.py`), APScheduler (jobs agendados, ver `app/__init__.py`)
- **Exportação:** Excel via `openpyxl` (ver `app/services/excel_export_service.py`)

## Perfis de usuário
- `solicitante` — cria e acompanha os próprios chamados
- `supervisor` — gerencia chamados da sua área + relatórios
- `admin` — acesso total: chamados, usuários, categorias, relatórios
- `admin_global` — herda tudo de `admin`; usado para supervisores com acesso expandido entre áreas

## Padrões de código

### Python / Flask
- Imports inline nas rotas (`from app.services.X import func`) — padrão do projeto
- Responses JSON: sempre `{"sucesso": bool, "erro"?: str, "dados"?: obj}`
- Decoradores de acesso: `@requer_solicitante`, `@requer_supervisor_area`, `@requer_perfil("admin")` (não existe um `@requer_admin` dedicado)
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

# 4. Gate de cobertura por módulo (>= 85%)
python scripts/check_coverage_per_module.py --json-only

# 5. Push (usa o script da skill global)
bash ~/.claude/skills/git-pushing/scripts/smart_commit.sh "tipo: descrição"
```

## Conventional commits

Formato: `tipo(escopo): assunto` — escopo é opcional.

```
tipo(escopo): Assunto em imperativo, máx 70 chars

Corpo opcional: explica O QUE e POR QUÊ, não o como.

Co-Authored-By: Claude <noreply@anthropic.com>
```

Tipos:
- `feat:` nova funcionalidade
- `fix:` correção de bug
- `security:` hardening / correção de segurança
- `test:` adição/correção de testes
- `refactor:` refatoração sem mudança de comportamento
- `perf:` melhoria de performance
- `chore:` tarefas de manutenção (deps, config, CI)
- `docs:` documentação
- `style:` formatação sem mudança de lógica

Regras do assunto:
- Imperativo presente: "Add feature" não "Added feature"
- Primeira letra maiúscula, sem ponto final
- Máximo 70 caracteres

## Estrutura de arquivos-chave
```
app/
├── __init__.py              # Criação da app Flask, segurança, i18n, scheduler
├── models.py                # Modelo Chamado
├── models_usuario.py        # Classe Usuario (UserMixin), to_dict/from_dict
├── models_categorias.py     # Modelo de categorias
├── models_historico.py      # Histórico de alterações dos chamados
├── database.py              # Instância Firestore
├── decoradores.py           # @requer_* decoradores
├── i18n.py                  # Internacionalização (PT-BR, EN, ES)
├── routes/
│   ├── api_chamados.py      # Rotas JSON/API — status, edição, bulk, paginação, onboarding
│   ├── api_colaboracao.py   # Rotas JSON/API — escalonamento, participantes
│   ├── api_notificacoes.py  # Rotas JSON/API — notificações in-app, web push
│   ├── api_solicitante.py   # Rotas JSON/API — self-service do solicitante (anexos, editar, cancelar)
│   ├── auth.py              # Login, logout, senha
│   ├── chamados.py          # Criação e listagem (solicitante)
│   ├── dashboard.py         # Dashboard (supervisor/admin)
│   ├── usuarios.py          # Gestão de usuários (admin)
│   ├── categorias.py        # Gestão de categorias (admin)
│   ├── admin_global.py      # Governança de admins/supervisores (perfil admin_global)
│   └── mfa.py               # Configuração de MFA (TOTP + QR code)
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
├── e2e/
└── test_regression/
```

## O que NÃO fazer
- Não usar `db.collection().get()` sem paginação em coleções grandes
- Não expor erros internos nas responses JSON (logar, mas retornar mensagem genérica)
- Não adicionar lógica de negócio diretamente nas rotas — usar services
- Não commitar sem passar o ciclo de qualidade acima
- Não usar `git add .` sozinho — revisar o que está sendo commitado

## Skills padrão deste projeto
Base gerada por `/aas` (bootstrap) em 2026-07-21, revisada em 2026-07-22 — ponto de partida pra qualquer `/aas <tema>` futuro.

- **Segurança** (obrigatória): `backend-security-coder`, `auth-implementation-patterns`, `secrets-management`, `privacy-by-design`, `sast-configuration` — auth combina Flask-Login + MFA (pyotp) + SSO Microsoft (msal); PII criptografado em repouso (LGPD); múltiplos segredos (Firebase, R2, MSAL, chave Fernet)
- **Dados/storage**: `nosql-expert` — Firestore é NoSQL, não relacional
- **Testes/qualidade**: `pytest-skill`, `test-driven-development`, `playwright-skill`, `k6-load-testing` — TDD é regra explícita deste arquivo; `pytest-playwright` real em `requirements-dev.txt` com suíte em `tests/e2e/` (CI `e2e.yml` bloqueia merge); `scripts/qa/k6/{smoke,load,stress}.js` + workflow semanal `k6-smoke.yml` contra produção
- **UX/Acessibilidade**: `tailwind-patterns`, `ui-a11y` — design system real é Tailwind; acessibilidade já auditada (WCAG 2.1 AA, 2026-07-21)
- **Internacionalização**: `i18n-localization` — app já suporta PT-BR/EN/ES de verdade (`app/i18n.py`, `translations.json`); convenção do projeto exige traduzir todo texto novo nos 3 idiomas ao implementar qualquer feature
- **Deploy/operações**: `docker-expert`, `github-actions-templates` — produção roda em Azure Container Apps, mas o deploy real é via GitHub Actions (`cd-build-image.yml`: build→push GHCR→`az containerapp update` com digest), não a CLI `azd`; `azd-deployment` removido por não corresponder ao fluxo real
- **Manutenção**: `git-pushing`, `lint-and-validate` — já é o fluxo real (`smart_commit.sh` no ciclo de qualidade acima)
