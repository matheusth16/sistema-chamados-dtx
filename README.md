# Sistema de Chamados DTX

> Sistema web de gerenciamento de chamados integrado com Firebase/Firestore, construído com Python/Flask.

![CI](https://github.com/matheusth16/sistema-chamados-dtx/actions/workflows/ci.yml/badge.svg)

## Características

- **Paginação Otimizada**: Cursor-based pagination para performance com grandes volumes (sem OOM)
- **Índices Firestore**: Índices compostos para máxima velocidade de queries
- **Atualização em Tempo Real**: Status atualiza sem recarregar a página
- **Dashboard Completo**: Visualização, filtros, histórico de alterações e bulk status
- **Autenticação Segura**: Login com Flask-Login e perfis (solicitante, supervisor, admin)
- **Upload de Anexos**: Suporte a PDFs, imagens e outros formatos
- **Internacionalização (i18n)**: Suporte a PT-BR, EN e ES com painel de administração de textos
- **Onboarding Interativo**: Tour guiado por perfil ao primeiro acesso (5–7 passos)
- **Notificações**: E-mail, Web Push e notificações in-app com retry automático
- **Logs Estruturados**: JSON logs com rastreamento completo de ações
- **Rate Limiting**: Proteção contra abuso de requisições (Redis em produção)
- **Gamificação**: Sistema de pontos para técnicos de atendimento

## Requisitos

- Python 3.12+
- Firebase Account com Firestore e Firebase Storage
- pip (gerenciador de pacotes Python)

## Instalação

### 1. Clone o repositório

```bash
git clone https://github.com/matheusth16/sistema-chamados-dtx.git
cd sistema-chamados-dtx
```

### 2. Crie um ambiente virtual

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS/Linux
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Instale as dependências

```bash
# Produção
pip install -r requirements.txt

# Desenvolvimento (inclui pytest, ruff, bandit, playwright, etc.)
pip install -r requirements-dev.txt
```

### 4. Configure credenciais do Firebase

1. Acesse o [Firebase Console](https://console.firebase.google.com)
2. Baixe `credentials.json` da sua conta de serviço
3. Coloque na raiz do projeto (nunca versionar)

### 5. Configure variáveis de ambiente

```bash
cp .env.example .env
# Edite .env e defina ao menos SECRET_KEY e FLASK_ENV
# Em produção: FLASK_ENV=production e SECRET_KEY forte (openssl rand -hex 32)
```

Documentação completa: **[docs/ENV.md](docs/ENV.md)**

### 6. Inicie a aplicação

```bash
python run.py
```

Acesse: `http://localhost:5000`

### 7. Scripts utilitários (opcional)

```bash
python scripts/criar_usuario.py              # Criar usuário no sistema
python scripts/gerar_vapid_keys.py           # Chaves Web Push
python scripts/gerar_chave_criptografia.py   # Chave para criptografia de PII (LGPD)
python scripts/atualizar_traducoes_setores.py # Sincronizar traduções EN/ES no Firestore
```

## Perfis de Usuário

| Perfil | Permissões |
|--------|-----------|
| `solicitante` | Criar e acompanhar os próprios chamados |
| `supervisor` | Gerenciar chamados da sua área + relatórios |
| `admin` | Acesso total: chamados, usuários, categorias, traduções, relatórios |

## API

Referência completa: **[docs/API.md](docs/API.md)**

Endpoints principais:

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/health` | Health check — `{"status": "ok"}` |
| GET | `/api/chamados/paginar` | Paginação com cursor (limite, cursor, status, categoria, gate, search) |
| POST | `/api/carregar-mais` | Carregar mais registros (infinite scroll) |
| POST | `/api/atualizar-status` | Atualizar status de um chamado |
| POST | `/api/bulk-status` | Atualizar status em lote (supervisor/admin) |
| POST | `/api/onboarding/avancar` | Avançar passo do onboarding |
| POST | `/api/onboarding/concluir` | Concluir onboarding |

## Estrutura do Projeto

```
sistema-chamados-dtx/
├── app/
│   ├── routes/                   # Rotas Flask
│   │   ├── api.py                # Endpoints JSON/API
│   │   ├── auth.py               # Login, logout, senha
│   │   ├── chamados.py           # Criação e listagem (solicitante)
│   │   ├── dashboard.py          # Dashboard (supervisor/admin)
│   │   ├── usuarios.py           # Gestão de usuários (admin)
│   │   ├── categorias.py         # Gestão de categorias (admin)
│   │   └── traducoes.py          # Gestão de traduções (admin)
│   ├── services/                 # Lógica de negócio
│   │   ├── chamados_criacao_service.py
│   │   ├── chamados_listagem_service.py
│   │   ├── dashboard_service.py
│   │   ├── status_service.py
│   │   ├── notifications.py      # E-mail e Web Push
│   │   ├── notifications_inapp.py
│   │   ├── notify_retry.py       # Retry com backoff exponencial
│   │   ├── permission_validation.py
│   │   ├── email_templates.py    # Templates HTML de e-mail
│   │   ├── validators.py
│   │   ├── analytics.py
│   │   ├── gamification_service.py
│   │   ├── report_service.py
│   │   └── translation_service.py
│   ├── templates/                # Jinja2 (dashboard, formulario, etc.)
│   │   └── components/           # Partials reutilizáveis
│   ├── static/                   # JS, CSS, uploads
│   ├── models.py                 # Modelo Chamado
│   ├── models_usuario.py         # Classe Usuario (UserMixin)
│   ├── models_categorias.py      # Setores, Gates, Impactos
│   ├── models_grupo_rl.py        # Grupos RL
│   ├── models_historico.py       # Histórico de alterações
│   ├── database.py               # Instância Firestore
│   ├── i18n.py                   # Internacionalização (PT-BR, EN, ES)
│   ├── decoradores.py            # @requer_* decoradores de acesso
│   └── translations.json         # Textos i18n (PT-BR/EN/ES)
├── docs/                         # Documentação técnica
├── scripts/                      # Scripts de manutenção
├── tests/
│   ├── conftest.py               # Fixtures globais
│   ├── test_routes/              # Testes de rotas Flask
│   ├── test_services/            # Testes unitários de serviços
│   ├── test_integration/         # Testes de integração
│   ├── test_regression/          # Suite de regressão
│   └── e2e/                      # Testes E2E com Playwright
│       ├── pages/                # Page Objects (POM)
│       └── test_smoke.py         # 14 smoke tests
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                # CI: lint, testes, cobertura, segurança
│   │   └── e2e.yml               # E2E: Playwright smoke suite (não bloqueante)
│   └── pull_request_template.md  # Checklist QA obrigatório
├── config.py
├── run.py
├── requirements.txt
├── requirements-dev.txt
├── pytest.ini
├── firestore.indexes.json
└── firestore.rules
```

## CI/CD

O projeto usa **GitHub Actions** com dois workflows:

### CI (`ci.yml`) — bloqueante
Roda a cada push/PR na `main`:

```
Ruff lint → Ruff format → Bandit SAST → pip-audit → Pytest (cobertura ≥ 70%)
```

### E2E (`e2e.yml`) — não bloqueante
Roda em paralelo. Requer servidor Flask acessível (configurável via `workflow_dispatch`):

```
Playwright Chromium → 14 smoke tests (login, dashboard, controle de acesso)
```

## Qualidade de Código

### Ciclo obrigatório antes de commit

```bash
# 1. Lint e formatação
ruff check app/ tests/ --fix
ruff format app/ tests/

# 2. Segurança estática
bandit -r app/ -ll

# 3. Testes com cobertura
pytest --tb=short -q \
  --cov=app \
  --cov-report=term-missing:skip-covered \
  --cov-fail-under=70
```

**Gate de cobertura:** mínimo de **70%** — CI rejeita abaixo disso.

### Rodar testes específicos

```bash
# Um arquivo
pytest tests/test_services/test_validators.py -v

# Por palavra-chave
pytest tests/ -k "dashboard" --tb=short

# Apenas smoke tests (requer servidor local)
pytest tests/e2e -m smoke --base-url http://127.0.0.1:5000

# Testes que falharam na última execução
pytest --lf --tb=short
```

### Testes E2E

Configure as credenciais de teste (copie `.env.test.example` para `.env.test`):

```bash
cp .env.test.example .env.test
# Preencha: TEST_SOLICITANTE_EMAIL, TEST_SUPERVISOR_EMAIL, TEST_ADMIN_EMAIL e senhas
```

### Artefatos de teste — não versionar

| Artefato | O que é |
|---|---|
| `.coverage` | Banco de dados de cobertura |
| `coverage.xml` | Relatório XML para CI |
| `htmlcov/` | Relatório HTML |
| `.pytest_cache/` | Cache do pytest |
| `__pycache__/` | Bytecode Python |

## Performance

| Operação | Antes | Depois | Melhoria |
|---|---|---|---|
| Carregar dashboard | 3–5s | 200–400ms | **15x** |
| Mudar status | 2–3s | 100–200ms | **20x** |
| Filtrar (com índice) | 2–5s | 50–100ms | **50x** |
| Busca full-text | 3–4s | 300–500ms | **10x** |

### Índices Firestore necessários

```bash
firebase deploy --only firestore:indexes --project seu-projeto-id
```

Ou crie manualmente no console:
1. `categoria` + `status` + `data_abertura`
2. `status` + `data_abertura`
3. `gate` + `status` + `data_abertura`

## Segurança

- Autenticação em todas as rotas sensíveis com `@requer_*` decoradores
- Rate limiting habilitado (Redis em produção)
- Validação rigorosa de entrada em `validators.py`
- CSRF protection ativado (Flask-WTF)
- Senhas hasheadas com werkzeug
- Logs de auditoria completos
- Credenciais Firebase não versionadas
- `SECRET_KEY` forte obrigatória em produção
- Headers: `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, HSTS em HTTPS
- Validação de Origin/Referer em POST sensíveis
- Criptografia em repouso para PII (opcional via `ENCRYPTION_KEY`)
- Conformidade LGPD: **[docs/POLITICA_SEGURANCA_LGPD.md](docs/POLITICA_SEGURANCA_LGPD.md)**

## Documentação

| Documento | Descrição |
|-----------|-----------|
| [docs/ENV.md](docs/ENV.md) | Variáveis de ambiente (.env) |
| [docs/API.md](docs/API.md) | Referência completa da API |
| [docs/QA_DEBUG_PLAYBOOK.md](docs/QA_DEBUG_PLAYBOOK.md) | Playbook de triagem sistemática de falhas de teste |
| [docs/AB_TEST_PLAN.md](docs/AB_TEST_PLAN.md) | Plano de experimento A/B (AB-001: campo descrição guiado) |
| [docs/POLITICA_SEGURANCA_LGPD.md](docs/POLITICA_SEGURANCA_LGPD.md) | Segurança e conformidade LGPD |
| [docs/DEPLOYMENT_PLAN.md](docs/DEPLOYMENT_PLAN.md) | Deploy (Cloud Run, Firebase) |
| [docs/onboarding.md](docs/onboarding.md) | Onboarding interativo: visão de produto e detalhes técnicos |
| `firestore.rules` | Regras de segurança Firestore |
| `firestore.indexes.json` | Índices Firestore |

## Troubleshooting

### `FAILED_PRECONDITION` em query

**Causa:** Índice composto faltando no Firestore.
**Solução:** Criar o índice no Firebase Console ou via `firebase deploy --only firestore:indexes`.

### Dashboard carregando lento

**Causa:** Firestore ainda indexando em background após criação de índices.
**Solução:** Aguardar até 15 minutos.

### Erro de conexão com Firebase

**Causa:** `credentials.json` não encontrado na raiz do projeto.
**Solução:** Baixar da conta de serviço no Firebase Console e colocar na raiz.

### `SECRET_KEY must be set` ao subir em produção

**Causa:** `FLASK_ENV=production` exige `SECRET_KEY` no ambiente.
**Solução:** `export SECRET_KEY=$(openssl rand -hex 32)` ou definir na plataforma de deploy.

### `PermissionError: [WinError 32]` nos logs (Windows)

**Causa:** O reloader do Flask em modo debug abre dois processos com o arquivo de log. O `RotatingFileHandler` não consegue renomear o arquivo enquanto o processo-pai o mantém aberto.
**Solução:** Já corrigido — `_WindowsSafeRotatingFileHandler` captura o erro silenciosamente e continua logando. Nenhuma ação necessária.

### Setor/área aparece em português na interface EN/ES

**Causa:** Setor cadastrado antes das traduções serem adicionadas ao `SECTOR_KEYS_MAP`.
**Solução:** Rodar `python scripts/atualizar_traducoes_setores.py` para sincronizar `nome_en`/`nome_es` no Firestore.

### Dependências

```bash
# Auditar vulnerabilidades
pip-audit -r requirements.txt

# Atualizar (testar após atualizar)
pip install -r requirements.txt --upgrade
```

## Contribuindo

1. Fork o projeto
2. Crie uma branch (`git checkout -b feature/minha-feature`)
3. Siga o ciclo de qualidade (lint + testes passando)
4. Abra um Pull Request usando o template — preencha o checklist QA

## Licença

Este projeto é propriedade da DTX Aerospace.

## Autor

**Matheus Costa**
- GitHub: [@matheusth16](https://github.com/matheusth16)

## Roadmap

- [x] Paginação com cursor / infinite scroll
- [x] Caching e rate limiting (Redis configurável)
- [x] Export Excel e relatórios por período
- [x] i18n PT-BR / EN / ES e painel de traduções
- [x] PWA / notificações Web Push
- [x] Onboarding interativo por perfil
- [x] Gamificação para técnicos
- [x] Suite de testes com cobertura ≥ 70% + E2E smoke
- [x] CI/CD com GitHub Actions (lint, SAST, cobertura, E2E)
- [x] Retry automático para notificações (backoff exponencial)
- [ ] Cache local com IndexedDB (uso offline)
- [ ] Notificações em tempo real (WebSocket)
- [ ] Mobile app

---

**Feito com dedicação por Matheus Costa — DTX Aerospace**
