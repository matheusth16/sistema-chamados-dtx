# Guia de Onboarding Técnico — Sistema de Chamados DTX Aerospace

| Campo | Valor |
|---|---|
| **Versão** | 3.2 |
| **Data** | 2026-06-18 |
| **Autor** | DTX Aerospace — Engenharia de Software |
| **Tempo estimado de leitura** | 55–70 minutos |

---

## Índice

1. [Visão geral em 5 minutos](#1-visão-geral-em-5-minutos)
2. [Pré-requisitos](#2-pré-requisitos)
3. [Setup local passo a passo](#3-setup-local-passo-a-passo)
4. [Mapa do repositório](#4-mapa-do-repositório)
5. [Tabela de módulos](#5-tabela-de-módulos)
6. [Os 4 perfis de usuário](#6-os-4-perfis-de-usuário)
7. [Fluxo de uma requisição de ponta a ponta](#7-fluxo-de-uma-requisição-de-ponta-a-ponta)
8. [Como rodar os testes](#8-como-rodar-os-testes)
9. [Arquitetura de Testes](#9-arquitetura-de-testes)
10. [CSS e Design System DTX Light](#10-css-e-design-system-dtx-light)
11. [Como fazer lint e auditoria de segurança](#11-como-fazer-lint-e-auditoria-de-segurança)
12. [Padrões de código obrigatórios](#12-padrões-de-código-obrigatórios)
13. [Onde NÃO colocar lógica de negócio](#13-onde-não-colocar-lógica-de-negócio)
14. [Como adicionar uma nova rota](#14-como-adicionar-uma-nova-rota)
15. [Como adicionar uma nova tradução](#15-como-adicionar-uma-nova-tradução)
16. [Sistema de Gamificação](#16-sistema-de-gamificação)
17. [Web Push e Service Worker](#17-web-push-e-service-worker)
18. [Armadilhas conhecidas para novos devs](#18-armadilhas-conhecidas-para-novos-devs)
19. [Strings hardcoded e internacionalização no frontend](#19-strings-hardcoded-e-internacionalização-no-frontend)
20. [Melhorias de produto recentes](#20-melhorias-de-produto-recentes-melhorias-sprintmd)
21. [Ciclo de qualidade antes de commit](#21-ciclo-de-qualidade-antes-de-commit)
22. [Conventional commits](#22-conventional-commits)
23. [FAQ — Perguntas frequentes de novos devs](#23-faq--perguntas-frequentes-de-novos-devs)

---

## 1. Visão geral em 5 minutos

### O que é o sistema

O Sistema de Chamados DTX Aerospace é uma aplicação web interna que gerencia solicitações entre colaboradores da empresa. Um **solicitante** abre um chamado descrevendo uma demanda, um **supervisor** da área responsável assume e processa o chamado, e um **administrador** tem visão completa de tudo, incluindo relatórios e gestão de usuários.

> **Baseline de qualidade (2026-06-22 — Onda 4 concluída):** 1435 testes passando, cobertura global 94,98% (gate: 85%), zero achados de Alta severidade abertos, 82/82 achados resolvidos. Gate por módulo: `python scripts/check_coverage_per_module.py` — 52/52 módulos OK, 0 pendentes. Ver `docs/PLANO_SPRINT.md` e `docs/RELATORIO_EXECUTIVO.md`.

### Quem usa

| Perfil | Quantidade | O que faz |
|---|---|---|
| Solicitante | Maioria dos colaboradores | Cria chamados, acompanha status, adiciona comentários |
| Supervisor | Líderes de área | Gerencia chamados da sua área, aprova, encerra, exporta relatórios |
| Admin | TI / Gestão | Tudo: usuários, categorias, relatórios globais, configurações |

### Onde roda

- **Produção:** Docker (cloud) — `https://seu-dominio.com` (a definir)
- **Banco de dados:** Google Firestore (Firebase)
- **Arquivos:** Cloudflare R2 (bucket privado, URLs pré-assinadas com validade de 1h)
- **E-mails:** Microsoft Graph API (client credentials)
- **Cache / Rate limit:** Redis (em produção), dicionário em memória (local)

### Stack técnica resumida

```
Flask 3.0  +  Firestore  +  Flask-Login  +  Flask-WTF (CSRF)
Tailwind CSS (build via Node.js/Tailwind CLI no Docker)  +  GSAP 3 (animações)
Python 3.12+  (local: 3.14)
pytest + unittest.mock
```

---

## 2. Pré-requisitos

### Software obrigatório

| Ferramenta | Versão mínima | Como instalar | Observação |
|---|---|---|---|
| Python | 3.12+ | [python.org](https://python.org) | Obrigatório |
| pip | Junto com Python | — | Obrigatório |
| Git | qualquer | [git-scm.com](https://git-scm.com) | Obrigatório |
| Node.js | 18+ | [nodejs.org](https://nodejs.org) | **Obrigatório para build Tailwind CSS** |

> **Atenção:** Node.js é necessário para compilar o `tailwind.min.css` localmente. Sem ele, o CSS de produção não será gerado e a interface ficará sem estilos. Em produção, o Dockerfile já executa o build automaticamente.

### Credenciais necessárias

Você vai precisar de acesso a:

1. **Firebase Service Account** — arquivo JSON com credenciais do Firestore. Solicite ao responsável pelo projeto.
2. **Variáveis de ambiente** — arquivo `.env` com todas as configurações. Ver seção [3.4 — Configurar variáveis de ambiente](#34-configurar-variáveis-de-ambiente).
3. **Acesso ao repositório Git** — clone via SSH ou HTTPS.

> **Atenção:** Nunca commite o arquivo `.env` ou o JSON do Firebase. Ambos já estão no `.gitignore`. Se você acidentalmente adicioná-los, siga o procedimento de resposta a incidente em `docs/CHECKLIST_SEGURANCA.md`.

---

## 3. Setup local passo a passo

### 3.1 Clonar o repositório

```bash
git clone https://github.com/dtx-aerospace/sistema_chamados.git
cd sistema_chamados
```

### 3.2 Criar e ativar ambiente virtual

```bash
# Criar ambiente virtual
python -m venv venv

# Ativar (Linux/Mac)
source venv/bin/activate

# Ativar (Windows PowerShell)
venv\Scripts\Activate.ps1

# Ativar (Windows CMD)
venv\Scripts\activate.bat
```

### 3.3 Instalar dependências

```bash
# Dependências de produção
pip install -r requirements.txt

# Dependências de desenvolvimento (lint, testes, segurança)
pip install -r requirements-dev.txt
```

### 3.4 Configurar variáveis de ambiente

Crie um arquivo `.env` na raiz do projeto. Solicite o `.env` de exemplo ao responsável ou consulte `docs/ENV.md` para a lista completa. Variáveis mínimas para rodar localmente:

```dotenv
# Flask
SECRET_KEY=sua-chave-secreta-aqui-minimo-32-chars
FLASK_ENV=development
FLASK_DEBUG=True

# Firebase
FIREBASE_CREDENTIALS_PATH=/caminho/para/serviceAccountKey.json
# OU em produção:
# FIREBASE_CREDENTIALS_JSON={"type":"service_account",...}

# Cloudflare R2 (pode deixar vazio para rodar sem upload real)
R2_ENDPOINT_URL=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=

# E-mail via Microsoft Graph API (opcional para desenvolvimento local)
GRAPH_TENANT_ID=
GRAPH_CLIENT_ID=
GRAPH_CLIENT_SECRET=
GRAPH_SENDER_EMAIL=

# Criptografia PII
ENCRYPT_PII_AT_REST=false
ENCRYPTION_KEY=

# Web Push VAPID (opcional para desenvolvimento local)
VAPID_PUBLIC_KEY=
VAPID_PRIVATE_KEY=
VAPID_CLAIM_EMAIL=
```

> **Dica:** Para desenvolvimento local, você pode deixar as variáveis de R2, e-mail e VAPID em branco. O sistema tem fallbacks: arquivos vão para o disco local, e-mails são logados como warning no console (sem envio real) e as notificações push são ignoradas.
>
> **Atenção:** O sistema usa **exclusivamente Microsoft Graph API** para envio de e-mail. Não há mais suporte a BREVO, SMTP ou Power Automate.

### 3.5 Configurar credenciais do Firebase

Coloque o arquivo `serviceAccountKey.json` (obtido com o responsável) em um local seguro fora do repositório e configure `FIREBASE_CREDENTIALS_PATH` apontando para ele.

Alternativamente, exporte o conteúdo do JSON como variável de ambiente:

```bash
export FIREBASE_CREDENTIALS_JSON=$(cat /caminho/para/serviceAccountKey.json)
```

### 3.6 Build do Tailwind CSS (obrigatório para desenvolvimento)

```bash
# Instalar dependências Node.js
npm install

# Build do CSS (geração do tailwind.min.css)
npm run build:css
```

> **Dica:** Em produção, o Dockerfile já executa esse passo automaticamente. Localmente, você precisa rodar manualmente. Se a interface aparecer sem estilo, é sinal de que o build Tailwind não foi executado.

### 3.7 Rodar a aplicação

```bash
python run.py
```

A aplicação estará disponível em `http://localhost:5000`.

### 3.8 Primeiro acesso

Use o script para criar o primeiro usuário admin:

```bash
python scripts/criar_usuario.py
```

Siga as instruções interativas para definir e-mail, senha e perfil `admin`.

### 3.9 Inicializar categorias (se banco vazio)

```bash
python scripts/init_categorias.py
```

Isso popula as categorias, setores, gates e impactos padrão no Firestore.

---

## 4. Mapa do repositório

```
sistema_chamados/
│
├── app/                          # Código da aplicação Flask
│   ├── __init__.py               # Factory da app, middlewares, scheduler, warmup
│   ├── database.py               # Instância Firestore (db)
│   ├── decoradores.py            # @requer_perfil, @requer_solicitante, @requer_supervisor_area
│   ├── exceptions.py             # Exceções customizadas do domínio
│   ├── i18n.py                   # Internacionalização PT-BR / EN / ES
│   ├── cache.py                  # Cache Redis/memória com TTL
│   ├── limiter.py                # Instância compartilhada Flask-Limiter (Redis)
│   ├── firebase_retry.py         # Decorator @firebase_retry com backoff exponencial
│   ├── gates_config.py           # Catálogo canônico de gates (GATE_PAI_OPCOES, GATE_SUBETAPAS)
│   ├── utils.py                  # Utilitários: get_client_ip, paginação, etc.
│   │
│   ├── models.py                 # Modelo Chamado
│   ├── models_usuario.py         # Classe Usuario (UserMixin); perfis: solicitante/supervisor/admin/admin_global
│   ├── models_categorias.py      # CategoriaSetor, CategoriaGate (gate_pai, etapa, ordem), CategoriaImpacto
│   ├── models_historico.py       # Histórico de alterações de status
│   ├── models_grupo_rl.py        # GrupoRL — chamados ligados por código RL
│   │
│   ├── routes/                   # Blueprints de rotas (todos registram no blueprint 'main')
│   │   ├── __init__.py           # Registro de todos os blueprints
│   │   ├── api.py                # Endpoints JSON/API (/api/*)
│   │   ├── auth.py               # Login, logout, troca de senha obrigatória
│   │   ├── chamados.py           # Criação e listagem de chamados (solicitante)
│   │   ├── dashboard.py          # Dashboard, visualização, histórico, export (supervisor/admin)
│   │   ├── usuarios.py           # CRUD de usuários (admin)
│   │   ├── categorias.py         # CRUD de setores, gates, impactos + tradução automática (admin)
│   │   └── admin_global.py       # Governança de admins/supervisores (apenas admin_global)
│   │
│   ├── services/                 # Lógica de negócio (NUNCA misture com rotas)
│   │   ├── chamados_criacao_service.py   # Criação de chamado completo
│   │   ├── chamados_listagem_service.py  # Consultas e filtros de chamados com paginação
│   │   ├── edicao_chamado_service.py     # Edição de chamado existente
│   │   ├── status_service.py             # Atualização de status + histórico + gamificação
│   │   ├── upload.py                     # Upload R2 → Firebase Storage → disco local
│   │   ├── permissions.py                # RBAC: quem pode ver/editar chamado
│   │   ├── permission_validation.py      # supervisor_pode_alterar_chamado(), verificar_permissao_mudanca_status()
│   │   ├── analytics.py                  # Métricas, SLA, relatório completo
│   │   ├── report_service.py             # Relatório semanal por e-mail (HTML)
│   │   ├── notifications.py              # E-mail via Microsoft Graph API (client credentials)
│   │   ├── notifications_inapp.py        # Notificações in-app (Web Push)
│   │   ├── webpush_service.py            # Gerenciamento de inscrições VAPID/Web Push
│   │   ├── email_templates.py            # Builders HTML reutilizáveis para e-mails
│   │   ├── notify_retry.py               # executar_com_retry() com backoff exponencial
│   │   ├── dashboard_service.py          # Lógica do painel administrativo
│   │   ├── login_attempts.py             # Lockout e contador de tentativas
│   │   ├── validators.py                 # Validação de dados (campos, extensões, magic bytes, gates)
│   │   ├── assignment.py                 # Atribuição automática de responsável
│   │   ├── translation_service.py        # Tradução PT→EN/ES: mapa estático + MyMemory API
│   │   ├── gamification_service.py       # Sistema de pontuação e conquistas
│   │   ├── gates_service.py              # build_gate_subetapas() / is_gate_valido() — Firestore+fallback
│   │   ├── filters.py                    # Filtros em memória para chamados
│   │   ├── metrics.py                    # Coleta e agregação de métricas
│   │   ├── pagination.py                 # Utilitários de paginação Firestore
│   │   ├── excel_export_service.py       # Exportação de relatórios para Excel
│   │   ├── contadores_uso.py             # Limite de uso diário por usuário
│   │   └── onboarding_service.py         # Tour de boas-vindas por perfil
│   │
│   ├── templates/                # Templates Jinja2
│   │   ├── base.html             # Template base (Tailwind, GSAP, flash, navbar)
│   │   ├── components/           # Partials reutilizáveis (navbar, filtros, badge, rows)
│   │   ├── admin_global.html     # Dashboard do perfil admin_global
│   │   ├── dashboard.html        # Painel principal
│   │   ├── formulario.html       # Criação de chamado
│   │   ├── visualizar_chamado.html  # Detalhe do chamado
│   │   └── ...
│   │
│   └── static/                   # Arquivos estáticos
│       ├── sw.js                 # Service Worker para Web Push (raiz de static/, NÃO em js/)
│       ├── css/
│       │   ├── input.css         # Fonte de edição do CSS (EDITAR AQUI)
│       │   ├── tailwind.min.css  # CSS compilado — NÃO editar diretamente (artefato de build)
│       │   ├── dashboard.css     # Estilos customizados do painel
│       │   ├── relatorios.css    # Estilos customizados de relatórios
│       │   └── table-filters.css # Estilos de filtros e ordenação de tabelas
│       └── js/
│           ├── gsap-motion.js            # Animações GSAP (API global window.DTXgsap)
│           ├── onboarding.js             # Tour de onboarding
│           ├── table-filters.js          # Filtros de tabela (client-side)
│           └── dashboard_otimizacoes.js  # Otimizações do dashboard (status, cancelamento)
│
├── tests/                        # Suite de testes
│   ├── conftest.py               # Fixtures globais
│   ├── test_routes/              # Testes de rotas HTTP
│   ├── test_services/            # Testes de serviços
│   ├── test_integration/         # Testes de integração de fluxos completos
│   ├── test_regression/          # Suite de regressão
│   └── e2e/                      # Testes end-to-end
│
├── scripts/                      # Scripts operacionais
│   ├── criar_usuario.py          # Criação de usuário inicial
│   ├── init_categorias.py        # Inicialização de categorias
│   └── ...
│
├── docs/                         # Documentação do projeto
├── k6/                           # Scripts de teste de carga (dev-only)
├── config.py                     # Configurações da aplicação (carrega .env)
├── run.py                        # Entry point da aplicação
├── Dockerfile                    # Imagem Docker da aplicação
├── package.json                  # Dependências Node.js (Tailwind CLI)
├── tailwind.config.js            # Configuração do Tailwind CSS e tokens DTX Light
├── firestore.indexes.json        # 20 índices compostos do Firestore
├── ruff.toml                     # Configuração do linter
├── .pre-commit-config.yaml       # Hooks de pré-commit
├── requirements.txt              # Dependências de produção
└── requirements-dev.txt          # Dependências de desenvolvimento
```

---

## 5. Tabela de módulos

### Módulos de rota e infraestrutura

| Módulo | Responsabilidade | Dependências principais | Perfis |
|---|---|---|---|
| `app/__init__.py` | Factory Flask, middlewares, APScheduler, warmup de cache | config, limiter, i18n, routes | Todos |
| `app/routes/auth.py` | Login, logout, troca de senha obrigatória | LoginAttemptTracker, models_usuario | Todos |
| `app/routes/chamados.py` | Criação e listagem de chamados | chamados_criacao_service, validators | Todos |
| `app/routes/dashboard.py` | Dashboard, visualização, histórico, export | dashboard_service, status_service | supervisor, admin |
| `app/routes/api.py` | Endpoints JSON (status, notificações, push) | permissions, status_service | Todos |
| `app/routes/usuarios.py` | CRUD de usuários | models_usuario, notifications | admin |
| `app/routes/categorias.py` | CRUD de setores, gates, impactos + tradução automática | models_categorias, translation_service | admin |
| `app/routes/admin_global.py` | Governança de admins/supervisores (promover, revogar, listar) | models_usuario | admin_global |
| `app/i18n.py` | Internacionalização PT-BR/EN/ES com cache de mtime | translations.json | Todos |
| `app/cache.py` | Cache Redis/memória com TTL | redis-py | Todos |
| `app/limiter.py` | Instância Flask-Limiter compartilhada (Redis em prod, memória local) | flask_limiter, redis | Todos |
| `app/firebase_retry.py` | Decorator `@firebase_retry` com backoff exponencial para operações Firestore | — | Todos |
| `app/gates_config.py` | Catálogo canônico de gates: `GATE_PAI_OPCOES` e `GATE_SUBETAPAS` (fallback estático) | — | admin |
| `app/decoradores.py` | `@requer_perfil`, `@requer_supervisor_area`, `@requer_admin_global` | flask_login, i18n | Todos |

### Módulos de serviço (lógica de negócio)

| Módulo | Responsabilidade | Dependências principais | Perfis |
|---|---|---|---|
| `app/services/chamados_criacao_service.py` | Criação de chamado, upload, atribuição, notificações | upload, assignment, GrupoRL | Todos |
| `app/services/chamados_listagem_service.py` | Queries e filtros de chamados com paginação Firestore | database, permissions, pagination | Todos |
| `app/services/edicao_chamado_service.py` | Edição de campos de chamado existente com histórico | database, validators (max_len=3000) | supervisor, admin |
| `app/services/status_service.py` | Atualização de status, histórico, gamificação | Historico, notifications, GamificationService | supervisor, admin |
| `app/services/upload.py` | Upload R2 → Firebase Storage → disco local | boto3, firebase_admin.storage | Todos |
| `app/services/permissions.py` | RBAC: quem pode ver/editar chamado | models_usuario | supervisor, admin |
| `app/services/analytics.py` | Métricas, SLA, relatório completo (max 2000 docs) | Firestore, cache | supervisor, admin |
| `app/services/report_service.py` | Relatório semanal HTML por e-mail para admins/supervisores | Firestore, Usuario, notif | supervisor, admin |
| `app/services/notifications.py` | E-mail via Microsoft Graph API (client credentials) | email_templates, GRAPH_TENANT_ID/CLIENT_ID/CLIENT_SECRET/SENDER_EMAIL | Todos |
| `app/services/notifications_inapp.py` | Notificações in-app via Web Push VAPID | pywebpush, webpush_service | Todos |
| `app/services/webpush_service.py` | Gerenciamento de inscrições push (criar, obter, deletar) | Firestore | Todos |
| `app/services/dashboard_service.py` | Lógica do painel administrativo, filtros, agregações | chamados_listagem_service | supervisor, admin |
| `app/services/login_attempts.py` | Lockout de IP e e-mail, contador de tentativas | cache | Todos |
| `app/services/validators.py` | Validação de entrada: campos, extensões, magic bytes, gates | models_categorias | Todos |
| `app/services/assignment.py` | Atribuição automática de supervisor ao chamado (3 estratégias) | models_usuario, models_categorias | Todos |
| `app/services/translation_service.py` | Tradução PT→EN/ES via mapa estático + MyMemory API (Firestore como fallback secundário) | TRANSLATION_MAP (dict global), MyMemory API | admin |
| `app/services/gamification_service.py` | EXP, níveis, conquistas, exp_semanal (acumulado) | Firestore, status_service | Todos |
| `app/services/gates_service.py` | `build_gate_subetapas()` e `is_gate_valido()` — consulta Firestore + fallback em `gates_config.py` | database, app/gates_config.py (full-scan sem cache — F-22) | Todos |
| `app/services/filters.py` | Filtragem em memória de chamados já carregados | — | supervisor, admin |
| `app/services/metrics.py` | Coleta e agregação de métricas de uso e SLA | Firestore | supervisor, admin |
| `app/services/pagination.py` | Utilitários de paginação cursor-based para Firestore | database | Todos |
| `app/services/excel_export_service.py` | Exportação de chamados e relatórios para .xlsx | openpyxl | supervisor, admin |
| `app/services/contadores_uso.py` | Controle de limite diário de uso por usuário | Firestore, Increment | Todos |
| `app/services/onboarding_service.py` | Tour de boas-vindas: avancar_passo, concluir_onboarding | models_usuario | Todos |
| `app/services/permission_validation.py` | `supervisor_pode_alterar_chamado()`, `verificar_permissao_mudanca_status()` | models_usuario, models | supervisor, admin |
| `app/services/email_templates.py` | Builders HTML reutilizáveis para e-mails transacionais | — | Todos |
| `app/services/notify_retry.py` | `executar_com_retry()` com backoff exponencial para envio de e-mail | — | Todos |

### Modelos de dados

| Módulo | Responsabilidade |
|---|---|
| `app/models.py` | Modelo Chamado |
| `app/models_usuario.py` | Classe Usuario (UserMixin), to_dict/from_dict, update(), get_by_email() |
| `app/models_categorias.py` | 3 classes: `CategoriaSetor`, `CategoriaGate` (campos: `gate_pai`, `etapa`, `ordem`), `CategoriaImpacto`. **Nota:** `CategoriaImpacto.save()` tem `@firebase_retry(max_retries=3)` — F-19 resolvido 2026-06-18 |
| `app/models_historico.py` | Histórico de alterações de status por chamado |
| `app/models_grupo_rl.py` | GrupoRL — chamados ligados por código RL |

### Utilitários de área e mapeamento

| Módulo | Responsabilidade |
|---|---|
| `app/utils_areas.py` | `setor_para_area()` — Firestore `config/setor_para_area` + cache TTL 5 min + fallback estático `SETOR_PARA_AREA`; `invalidar_cache_setor_area()` para flush manual (F-30 resolvido) |

### Scripts operacionais

| Script | Tipo | Uso |
|---|---|---|
| `scripts/criar_usuario.py` | Setup | Criação interativa de usuário inicial |
| `scripts/init_categorias.py` | Setup | Inicialização de categorias, setores, gates e impactos padrão |
| `scripts/atualizar_traducoes_setores.py` | Migração | Atualiza traduções de setores no Firestore |
| `scripts/gerar_vapid_keys.py` | Setup | Gera par de chaves VAPID para Web Push |
| `scripts/atualizar_firebase.py` | Migração — **OBSOLETO/PERIGOSO** | Sobreescrito por `migrar_setores_catalogo.py`; apaga sem dry-run |
| `scripts/verificar_dependencias.py` | Dev | pip audit + pytest; seguro |
| `scripts/atualizar_setores_from_print.py` | Migração — **PERIGOSO** | 15 setores; sem dry-run |
| `scripts/gerar_email_visual_snapshots.py` | QA/Dev | Snapshots HTML de e-mails; não envia e-mail real |
| `scripts/testar_email_smtp.py` | Diagnóstico | Envia e-mail SMTP real de teste |
| `scripts/migrar_setores_catalogo.py` | Migração | 3 coleções; tem dry-run — **preferir este** |
| `scripts/migrar_gates_subetapas.py` | Migração | Idempotente; não apaga dados |

---

## 6. Os 4 perfis de usuário

| Perfil | Quantidade | O que faz |
|---|---|---|
| Solicitante | Maioria dos colaboradores | Cria chamados, acompanha status, adiciona comentários |
| Supervisor | Líderes de área | Gerencia chamados da sua área, aprova, encerra, exporta relatórios |
| Admin | TI / Gestão | Tudo: usuários, categorias, relatórios globais, configurações |
| Admin Global | Governança TI | Tudo do admin + promove/revoga admins e supervisores de qualquer área |

### Solicitante

- Cria novos chamados com formulário, anexos e descrição
- Acompanha apenas seus próprios chamados
- Adiciona comentários/atualizações ao chamado
- Pode cancelar chamados que ainda não foram aceitos
- Recebe e-mail de notificação quando o status muda
- Recebe notificações Web Push em tempo real (se habilitado)
- Participa do sistema de gamificação (pontuação por interações)

### Supervisor

- Vê todos os chamados da sua área/setor
- Atualiza status de chamados (aceitar, em andamento, concluído, etc.)
- Atribui chamados a outros membros da equipe
- Executa ações em lote (bulk status update — até 50 chamados)
- Exporta relatórios em Excel (.xlsx)
- Não vê chamados de outras áreas
- Recebe relatório semanal por e-mail

### Admin

- Acesso completo a todos os chamados de todas as áreas
- Gerencia usuários (criar, editar, desativar, redefinir senha)
- Gerencia categorias, setores, gates e impactos
- Acessa relatórios globais e métricas de SLA
- Configura setores e estruturas de aprovação (GrupoRL)
- Vê logs de auditoria
- Recebe relatório semanal consolidado por e-mail
- **Não** pode promover/revogar outros admins (exclusivo do Admin Global)

### Admin Global

- Herda todas as permissões do Admin
- Promove usuários a `admin` ou `supervisor` em qualquer área
- Revoga e downgrade de perfis de admin/supervisor
- Acessa painel exclusivo em `/admin-global`
- **Isento** da troca de senha obrigatória no primeiro login

### Decoradores de acesso

```python
# Use estes decoradores para proteger suas rotas:

@requer_solicitante        # Qualquer usuário autenticado (solicitante, supervisor, admin, admin_global)
@requer_supervisor_area    # Supervisor (da área correta), admin ou admin_global
@requer_admin              # Apenas admin ou admin_global
@requer_admin_global       # Exclusivamente admin_global
```

> **Atenção:** `@requer_perfil('admin')` internamente expande para incluir `admin_global`. Nunca compare `current_user.perfil == 'admin'` diretamente — use `current_user.is_admin_or_above` para cobrir os dois perfis.

---

## 7. Fluxo de uma requisição de ponta a ponta

### Exemplo: solicitante cria um chamado

```
1. Usuário preenche formulário em GET /
   └── Template: app/templates/formulario.html

2. Usuário submete POST /
   └── Rota: app/routes/chamados.py → criar_chamado()
   └── Verificação CSRF automática (Flask-WTF)
   └── Verificação de autenticação: @requer_solicitante

3. Rota chama o serviço de validação
   └── app/services/validators.py → validar_novo_chamado()
   └── Verifica: campos obrigatórios, extensão do arquivo, magic bytes

4. Rota chama o serviço de criação
   └── app/services/chamados_criacao_service.py → criar_chamado()

5. Serviço faz upload do anexo
   └── app/services/upload.py → salvar_anexo()
   └── Tenta: Cloudflare R2 → Firebase Storage → disco local

6. Serviço salva o chamado no Firestore
   └── app/database.py → db.collection('chamados').add(dados)
   └── Gera número único em transação atômica

7. Serviço salva entrada no histórico
   └── app/models_historico.py → Historico.save()

8. Serviço dispara notificações em thread separada
   └── app/services/notifications.py → notificar_novo_chamado()
   └── Envia e-mail para supervisor responsável via Microsoft Graph API
   └── app/services/notifications_inapp.py → Web Push para supervisor

9. Rota retorna redirect para /meus-chamados
   └── Flash message: "Chamado #DTX-2026-001 criado com sucesso"
```

---

## 8. Como rodar os testes

### Rodar toda a suite

```bash
pytest --tb=short -q
```

### Rodar com relatório de cobertura

```bash
pytest --cov=app --cov-report=term-missing --tb=short -q
```

Gate de cobertura: **85% global** (`pytest.ini --cov-fail-under=85`) e **85% por módulo**.
Para verificar o gate por módulo (após rodar pytest uma vez):

```powershell
python -m pytest --cov=app --cov-report=term-missing -q
python scripts/check_coverage_per_module.py --json-only
```

> **Nota (2026-06-22 — Onda 4):** Global 94,98%, 52/52 módulos OK. Baseline 13/13 concluído. O script lista exatamente quais módulos estão abaixo do gate.

### Rodar um módulo específico

```bash
# Testes de um arquivo
pytest tests/test_services/test_chamados_criacao_service.py -v

# Testes de uma pasta
pytest tests/test_routes/ --tb=short

# Um teste específico pelo nome
pytest tests/test_routes/test_chamados.py::test_criar_chamado_sucesso -v
```

### Rodar com marcadores

```bash
# Apenas testes de integração
pytest -m integration --tb=short

# Excluir testes lentos
pytest -m "not slow" --tb=short
```

### Padrão de mocks (obrigatório para Firestore)

```python
# Sempre mocke o Firestore assim:
from unittest.mock import patch, MagicMock

def test_criar_chamado(client_logado_solicitante):
    with patch('app.services.chamados_criacao_service.db') as mock_db:
        mock_doc = MagicMock()
        mock_doc.id = 'chamado-123'
        mock_db.collection.return_value.add.return_value = (None, mock_doc)

        response = client_logado_solicitante.post('/criar-chamado', data={...})
        assert response.status_code == 302
```

> **Atenção:** Sempre faça o patch no módulo do serviço, não em `app.database`. Por exemplo: `patch('app.services.chamados_criacao_service.db')`, não `patch('app.database.db')`.

### Fixtures disponíveis (conftest.py)

| Fixture | Descrição |
|---|---|
| `app` | Instância Flask configurada para testes |
| `client` | Cliente HTTP sem autenticação |
| `client_logado_solicitante` | Cliente autenticado como solicitante |
| `client_logado_supervisor` | Cliente autenticado como supervisor |
| `client_logado_admin` | Cliente autenticado como admin |
| `client_logado_admin_global` | Cliente autenticado como admin_global |

---

## 9. Arquitetura de Testes

### Suites disponíveis

| Suite | Localização | Proposito | Markers |
|---|---|---|---|
| Unitario | tests/test_services/, tests/test_routes/ | Isola servico ou rota com mocks | `@smoke` |
| Integracao | tests/test_integration/ | Fluxos multi-modulo sem rede | `@regression` |
| Contrato | tests/test_routes/test_api_contract.py | Garante contrato da API JSON | `@api` |
| Regressao DTX | tests/test_regression/test_dtx_* | Invariantes do design system, i18n, matriz de rotas | `@regression` |
| E2E | tests/e2e/ | Fluxos completos via cliente HTTP real | `@e2e` |

**Executar por marker:**

```bash
pytest -m smoke -q
pytest -m regression -q
pytest -m e2e -q
```

### Padrao de mock (CRITICO)

**Correto — patch no modulo do servico:**

```python
with patch("app.services.edicao_chamado_service.db") as mock_db:
    ...
```

**Errado — patch na rota (mock inerte, teste passa mesmo com bug):**

```python
with patch("app.routes.api.db") as mock_db:  # NAO FAZER
    ...
```

Motivo: as rotas usam imports inline (`from app.services.X import func`). O patch deve ser feito no modulo onde o simbolo e *usado*, nao onde e definido.

### Fixtures do conftest.py

- `app` — instancia Flask de teste (CSRF desabilitado, banco mockado)
- `client` — cliente HTTP nao autenticado
- `client_logado_solicitante` — sessao ativa com perfil solicitante
- `client_logado_supervisor` — sessao ativa com perfil supervisor
- `client_logado_admin` — sessao ativa com perfil admin
- `client_logado_admin_global` — sessao ativa com perfil admin_global

### Suite DTX — diferencial de qualidade

`tests/test_regression/test_dtx_light_invariants.py` le os arquivos de producao reais (`tailwind.config.js`, `app/static/css/input.css`) e verifica que os tokens do design system estao presentes. Nao usa mocks — valida o artefato de producao diretamente.

`tests/test_regression/test_dtx_i18n_smoke.py` renderiza cada template em 9 combinacoes (3 perfis x 3 idiomas) e verifica que nao ha chaves de traducao faltando.

`tests/test_regression/test_dtx_route_matrix.py` cobre 12 rotas x 3 perfis testando codigo de resposta HTTP esperado.

### Armadilha FP-01: Tautologias

```python
# ERRADO — sempre True, nunca falha
assert result != "back" or result == "back"

# CORRETO
assert result == "voltar"
```

Se um teste sempre passa independente do resultado, o teste nao testa nada. Use `assert valor == esperado` direto.

---

## 10. CSS e Design System DTX Light

### Pipeline de build

```
app/static/css/input.css  +  tailwind.config.js
         |  npm run build:css
         v
app/static/css/tailwind.min.css   <- NAO editar diretamente
```

Edite sempre `input.css`. O `tailwind.min.css` é artefato de build — **não está versionado** (`.gitignore`); gere com `npm run build:css` ou use o Dockerfile.

### Tokens disponiveis

| Token | Uso |
|---|---|
| `var(--color-dtx-600)` | Cor primaria DTX (azul) |
| `var(--color-dtx-700)` | Hover, estados ativos |
| `var(--color-surface-base)` | Fundo da pagina |
| `var(--color-surface-raised)` | Cards, paineis |
| `var(--color-surface-border)` | Bordas de componentes |
| `var(--color-status-active-bg)` | Badge "Em andamento" |
| `var(--color-status-closed-bg)` | Badge "Fechado" |
| `var(--color-status-pending-bg)` | Badge "Aguardando" |

**Nunca usar valores hardcoded** (`#1e4a8c`, `#E5E7EB`, `rgba(...)`) — sempre tokens.

### Z-index nomeada

| Camada | Valor | Uso |
|---|---|---|
| nav | 200 | Barra de navegacao |
| dropdown | 210 | Menus dropdown |
| overlay | 220 | Overlays genericos |
| onboarding-backdrop | 8999 | Backdrop do tour |
| onboarding-card | 9001 | Card do tour |

### CSS por pagina

- `dashboard.css` — painel principal (supervisor/admin)
- `relatorios.css` — tela de relatorios
- `table-filters.css` — filtros e ordenacao de tabelas

### Restricoes do design system

- Sem variantes `dark:` (modo escuro nao suportado)
- Sem emojis em templates HTML
- Sombra maxima: `shadow-dtx` (nao usar `shadow-xl` ou maiores)
- Focus ring padrao: `outline: 2px solid var(--color-dtx-600)`

### Referencia

Especificacao completa em `docs/plans/2026-06-12-dtx-light-design-system.md`.

---

## 11. Como fazer lint e auditoria de segurança

### Lint com ruff

```bash
# Verificar erros (sem corrigir)
ruff check app/ tests/

# Verificar e corrigir automaticamente
ruff check app/ tests/ --fix

# Formatar código
ruff format app/ tests/

# Verificar formatação sem alterar (para CI)
ruff format app/ tests/ --check
```

### Auditoria de segurança com bandit

```bash
# Auditoria completa (nível médio e acima)
bandit -r app/ -ll

# Auditoria com relatório detalhado
bandit -r app/ -ll -v

# Verificar apenas um arquivo
bandit app/services/upload.py -ll
```

### Resultado esperado (estado atual)

```
ruff check: All checks passed
bandit: 1 Medium (B310 em translation_service.py:27), 12 Low, 0 High
```

> **Dica:** Se o bandit reportar um falso positivo que você verificou ser seguro, use o comentário `# nosec B310` (não `# noqa: S310` — esse último é para o ruff, não o bandit).

---

## 12. Padrões de código obrigatórios

### Imports inline nas rotas

```python
# CORRETO — import dentro da função de rota
@main.route('/chamados')
@requer_solicitante
def listar_chamados():
    from app.services.chamados_listagem_service import listar_chamados_usuario
    chamados = listar_chamados_usuario(current_user.id)
    return render_template('meus_chamados.html', chamados=chamados)

# ERRADO — import no topo do arquivo de rota
from app.services.chamados_listagem_service import listar_chamados_usuario  # NÃO faça isso
```

> **Atenção:** Este padrão existe por razões de compatibilidade com os mocks nos testes. Imports no topo das rotas quebram os patches de `unittest.mock`.

### Responses JSON

Sempre use este formato para endpoints da API:

```python
# Sucesso
return jsonify({"sucesso": True, "dados": resultado}), 200

# Erro conhecido
return jsonify({"sucesso": False, "erro": "Mensagem amigável"}), 400

# Erro interno (nunca exponha o erro real ao cliente)
import logging
logging.error("Erro interno: %s", str(e))
return jsonify({"sucesso": False, "erro": "Erro interno. Tente novamente."}), 500
```

### Decoradores de acesso (sempre obrigatório)

```python
from app.decoradores import requer_admin, requer_supervisor_area, requer_solicitante

@main.route('/admin/usuarios')
@requer_admin                    # Protege a rota — retorna 403 se não for admin
def listar_usuarios():
    ...
```

### Nomenclatura

| Elemento | Estilo | Exemplo |
|---|---|---|
| Arquivos Python | snake_case | `chamados_criacao_service.py` |
| Classes | PascalCase | `class ChamadoService:` |
| Funções e variáveis | snake_case | `def criar_chamado():` |
| URLs | kebab-case | `/meus-chamados`, `/admin-categorias` |
| Templates HTML | snake_case | `visualizar_chamado.html` |

### Serviços vs. Rotas

```
app/routes/    → Recebe requisição, valida input, chama serviço, retorna resposta
app/services/  → Contém TODA a lógica de negócio
```

---

## 13. Onde NÃO colocar lógica de negócio

> **Atenção:** Violações deste princípio dificultam testes, aumentam o acoplamento e criam bugs difíceis de rastrear.

**Não coloque lógica de negócio em:**

- `app/routes/*.py` — Rotas devem ser finas: receber, delegar, responder
- `app/templates/*.html` — Jinja2 é para apresentação, não regras de negócio
- `app/models*.py` — Modelos devem representar dados, não implementar fluxos complexos
- `config.py` — Configuração apenas

**Coloque lógica de negócio em:**

- `app/services/*.py` — Sempre. Um serviço por domínio.

**Exemplo correto:**

```python
# app/routes/chamados.py — FINO (correto)
@main.route('/criar', methods=['POST'])
@requer_solicitante
def criar():
    from app.services.chamados_criacao_service import criar_chamado
    from app.services.validators import validar_novo_chamado

    erros = validar_novo_chamado(request.form, request.files)
    if erros:
        return jsonify({"sucesso": False, "erro": erros[0]}), 400

    resultado = criar_chamado(request.form, request.files, current_user)
    return jsonify({"sucesso": True, "dados": resultado}), 201


# app/services/chamados_criacao_service.py — GORDO (correto)
def criar_chamado(form_data, files, usuario):
    # Toda a lógica aqui: upload, numeração, histórico, notificações
    ...
```

---

## 14. Como adicionar uma nova rota

### Passo 1 — Escreva o teste primeiro (TDD)

```python
# tests/test_routes/test_minha_feature.py
def test_nova_rota_retorna_200(client_logado_admin):
    response = client_logado_admin.get('/admin/nova-feature')
    assert response.status_code == 200
```

### Passo 2 — Escolha ou crie o arquivo de rota correto

```
Chamados/solicitante       → app/routes/chamados.py
Dashboard/supervisor       → app/routes/dashboard.py
API JSON                   → app/routes/api.py
Usuários (admin)           → app/routes/usuarios.py
Categorias (admin)         → app/routes/categorias.py
Governança (admin_global)  → app/routes/admin_global.py
```

### Passo 3 — Adicione a rota

```python
# app/routes/dashboard.py
@main.route('/admin/nova-feature')
@requer_admin
def nova_feature():
    from app.services.nova_feature_service import obter_dados_feature
    dados = obter_dados_feature()
    return render_template('nova_feature.html', dados=dados)
```

### Passo 4 — Crie o serviço

```python
# app/services/nova_feature_service.py
def obter_dados_feature():
    from app.database import db
    # lógica aqui
    docs = db.collection('colecao').stream()
    return [d.to_dict() for d in docs]
```

### Passo 5 — Adicione o template (se necessário)

```html
<!-- app/templates/nova_feature.html -->
{% extends "base.html" %}
{% block content %}
  <!-- conteúdo aqui -->
{% endblock %}
```

### Passo 6 — Rode o ciclo de qualidade

```bash
ruff check app/ tests/ --fix && ruff format app/ tests/ && bandit -r app/ -ll && pytest --tb=short -q
```

---

## 15. Como adicionar uma nova tradução

O sistema suporta PT-BR, EN e ES. Toda string visível ao usuário deve estar traduzida.

### Passo 1 — Adicionar ao translations.json

```json
// app/translations.json
{
  "pt": {
    "minha_chave": "Meu texto em português",
    "minha_chave_com_variavel": "Olá, {nome}!"
  },
  "en": {
    "minha_chave": "My text in English",
    "minha_chave_com_variavel": "Hello, {name}!"
  },
  "es": {
    "minha_chave": "Mi texto en español",
    "minha_chave_com_variavel": "¡Hola, {nombre}!"
  }
}
```

> **Atenção:** Sempre adicione as 3 versões simultaneamente. Uma chave faltando em qualquer idioma retorna o texto em PT-BR (fallback padrão), mas isso deve ser corrigido antes do commit.

### Passo 2 — Usar nos templates

```html
<!-- Em templates Jinja2 -->
<h1>{{ t('minha_chave') }}</h1>
<p>{{ t('minha_chave_com_variavel', nome=current_user.nome) }}</p>
```

### Passo 3 — Usar no Python (flash messages e e-mails)

```python
from app.i18n import t

mensagem = t('minha_chave')
flash(mensagem, 'sucesso')
```

### Passo 4 — Usar no JavaScript

```javascript
// Strings de UI em JS devem usar window.DTX_MSGS injetado no template, não hardcoded
const msg = window.DTX_MSGS?.minha_chave || 'Texto fallback';
```

> **Atenção:** Nunca coloque strings de UI diretamente no JavaScript. Veja a seção 19 para o padrão completo.

### Passo 5 — Traduzir setores no Firestore (se aplicável)

Se a tradução for de categorias ou setores armazenados no Firestore, use o script:

```bash
python scripts/atualizar_traducoes_setores.py
```

---

## 16. Sistema de Gamificação

O sistema possui um mecanismo de gamificação para engajar usuários. Ele é gerenciado em `app/services/gamification_service.py`.

### Estrutura de dados (no Firestore, documento do usuário)

```
usuarios/{uid}:
  ├── exp_total: int           # EXP acumulada de todos os tempos
  ├── exp_semanal: int         # EXP da semana atual — zerado todo domingo 23h59 BRT via APScheduler
  ├── nivel: int               # Nível atual (calculado a partir do exp_total)
  ├── conquistas: list[str]    # Lista de IDs de conquistas desbloqueadas
  └── ultima_atividade: datetime
```

### Como a EXP é adicionada

O fluxo de adição de pontos começa sempre em `status_service.py`, que chama `GamificationService._adicionar_exp()` ao processar uma mudança de status:

```
status_service.py → atualizar_status()
  └── GamificationService._adicionar_exp(usuario_id, quantidade)
      └── Firestore: lê EXP atual + escreve novo valor
          ATENCAO: operação read-then-write sem transação (F-14)
          →  Risco de race condition em requisições simultâneas
```

### Pontuação por ação (referência)

| Ação | EXP |
|---|---|
| Abrir chamado | +10 |
| Concluir chamado (supervisor) | +25 |
| Confirmar resolução (solicitante) | +15 |
| Cancelar chamado | -5 |

### Limitações conhecidas

- `exp_semanal` é zerado semanalmente por `GamificationService.resetar_ranking_semanal()`, agendado no APScheduler (domingo 23h59 BRT) — F-27 resolvido 2026-06-18. O campo é atualizado em batch Firestore (máx 500 ops/batch).
- A operação de incremento de EXP não usa transação atômica — em ambiente de alta concorrência pode haver perda ou duplicação de pontos (F-14).

### Armadilha: `exp_semanal` usa campo top-level, não mapa aninhado

`GamificationService._adicionar_exp` escreve em `exp_semanal` (campo raiz do documento), **não** em `gamification.exp_semanal`. O método `resetar_ranking_semanal()` lê `data.get("exp_semanal")` — use o mesmo campo ao acessar dados de gamificação diretamente.

### Próximo passo

Quando for corrigir F-14, use `Increment()` atômico do Firestore ou uma transação:

```python
# Forma correta — atômica
from google.cloud.firestore_v1 import Increment
db.collection('usuarios').document(uid).update({
    'exp_total': Increment(quantidade),
    'exp_semanal': Increment(quantidade)
})
```

---

## 17. Web Push e Service Worker

O sistema suporta notificações push via Web Push API (VAPID), gerenciado por três componentes:

### Componentes

| Arquivo | Responsabilidade |
|---|---|
| `app/static/sw.js` | Service Worker — recebe e exibe notificações push no navegador (**raiz de `static/`, não em `js/`**) |
| `app/services/webpush_service.py` | Gerencia inscrições: criar, obter, deletar no Firestore |
| `app/services/notifications_inapp.py` | Envia pushes usando `pywebpush` e as inscrições armazenadas |

### Fluxo de inscrição

```
1. Usuário acessa /api/webpush/subscribe (POST)
2. navegador registra sw.js e gera PushSubscription
3. Frontend envia subscription JSON para /api/webpush/subscribe
4. webpush_service.py → salva no Firestore em usuarios/{uid}/push_subscriptions
5. Ao ocorrer evento (novo chamado, mudança de status):
   notifications_inapp.py → obtém inscrições → pywebpush.webpush() → sw.js exibe
```

### Variáveis de ambiente necessárias

```dotenv
VAPID_PUBLIC_KEY=...      # Chave pública VAPID (injetada no frontend)
VAPID_PRIVATE_KEY=...     # Chave privada VAPID (apenas no servidor)
VAPID_CLAIM_EMAIL=...     # E-mail de contato para o serviço push
```

Para gerar novas chaves VAPID:

```bash
python scripts/gerar_vapid_keys.py
```

### Limitações conhecidas

- `obter_inscricoes` em `webpush_service.py` limita a `MAX_INSCRICOES=20` via `.limit()` — F-17 resolvido 2026-06-18. Se o limite for atingido, um `logger.warning` é emitido.
- O `app/static/sw.js` tem um `catch (e) {}` silencioso no parse do payload — falhas de parsing são perdidas sem log (F-43).

---

## 18. Armadilhas conhecidas para novos devs

Esta seção documenta comportamentos não óbvios que causam bugs difíceis de rastrear.

### Armadilha 1 — Round-robin não funciona em produção (F-21)

O `AtribuidorAutomatico` em `assignment.py` tem uma estratégia de atribuição chamada `round_robin` que usa um `contador_round_robin` para distribuir chamados entre supervisores.

**Problema:** Esse contador vive em memória (`assignment.py:49`). Em produção com Gunicorn multi-worker (ex: 4 workers), cada processo tem seu próprio contador — todos começando em 0. O resultado real é que cada worker faz seu próprio round-robin isolado, sem coordenação entre eles.

**Impacto:** A distribuição de chamados não é uniforme em produção.

**Solução futura:** Usar Redis como armazenamento compartilhado do contador entre workers.

### Armadilha 2 — Estratégia "aleatório" seleciona sempre o primeiro (F-20) ✅ Resolvido 2026-06-18

A estratégia `aleatorio` em `AtribuidorAutomatico._selecionar_supervisor()` (`assignment.py:123`) tinha um bug: em vez de selecionar aleatoriamente entre os supervisores disponíveis, sempre retornava o primeiro da lista. Corrigido com `random.choice(supervisores_com_carga)`.

**Impacto anterior:** Chamados com estratégia "aleatório" eram sempre atribuídos ao mesmo supervisor.

### Armadilha 3 — Gates sem cache causam full-scan a cada validação (F-22)

`is_gate_valido()` em `gates_service.py:43` consulta o Firestore a cada chamada para verificar se um gate de categoria é válido. Não há cache dessa consulta.

**Impacto:** Em fluxos que validam múltiplos gates (ex: criação de chamado com categoria complexa), o Firestore recebe N consultas desnecessárias.

**Workaround atual:** Aceitar o overhead em volumes baixos. Solução futura: cache com TTL de 5 minutos.

### Armadilha 4 — `_aplicar_filtros_em_memoria` chama to_dict() 5x por documento (F-23) ✅ Resolvido 2026-06-18

O método `_aplicar_filtros_em_memoria` em `filters.py:143-149` chamava `doc.to_dict()` 5 vezes por documento. Corrigido: `d = doc.to_dict()` uma vez por iteração; lookups subsequentes via `d.get(...)`.

**Impacto anterior:** Performance degradada em listas longas de chamados.

### Armadilha 5 — `cursor_prev` retorna o parâmetro de entrada, não o cursor real (F-26) ✅ Resolvido 2026-06-18

`listar_meus_chamados()` em `chamados_listagem_service.py:241` agora retorna `cursor_prev = docs[0].id if docs and cursor else None`, corrigindo o retorno incorreto do parâmetro de entrada.

### Armadilha 6 — `Increment` importado com fallback None (F-29) ✅ Resolvido 2026-06-18

Em `contadores_uso.py:15-17`, o import do `Increment` do Firestore agora é direto (`from google.cloud.firestore_v1 import Increment`) e a lógica usa `@firestore.transactional` para garantir atomicidade. O fallback `None` foi removido.

### Armadilha 7 — `TRANSLATION_MAP` sem lock (F-16) ✅ Resolvido 2026-06-17

O dicionário `TRANSLATION_MAP` em `translation_service.py` é protegido por `_translation_map_lock` (`threading.RLock`) em todas as leituras e escritas. Chamadas à API MyMemory ocorrem fora do lock.

### Armadilha 8 — `window.prompt()` bloqueado em produção (F-33) ✅ Resolvido 2026-06-17

O cancelamento de chamados no dashboard usa o modal `<dialog id="modal-cancelamento">` em `dashboard.html`, acionado por `solicitarMotivoCancelamento()` em `dashboard_otimizacoes.js`. Não há mais `window.prompt()` no fluxo de cancelamento.

### Armadilha 9 — `app/static/dist/` é bundle experimental (F-70) ✅ Resolvido 2026-06-17

O diretório `app/static/dist/` contém um bundle SPA experimental que não é utilizado pelos templates Flask. Não editar esse diretório. **`app/static/dist/` está no `.gitignore`** — artefatos de build não devem ser commitados.

### Armadilha 10 — Scripts destrutivos sem proteção (F-71/72) ✅ Resolvido 2026-06-17

`scripts/atualizar_firebase.py` e `scripts/atualizar_setores_from_print.py` agora exigem `--apply` para executar alterações destrutivas; o padrão é `--dry-run`. O primeiro script é **obsoleto** — preferir `scripts/migrar_setores_catalogo.py`. Consulte `scripts/README.md` para a matriz completa de scripts.

### Armadilha 11 — APScheduler em multi-worker: patch por job, não por scheduler

Todos os jobs APScheduler são envolvidos por `executar_job_com_lock(app, nome_job, fn)` de `app/services/scheduler_lock.py`. Isso garante que, com múltiplos workers Gunicorn, apenas **um** worker execute cada job por vez via Redis lock (timeout=300s, `blocking_timeout=0` → não bloqueia, pula silenciosamente).

**Armadilha em testes:** `import redis` é feito inline dentro da função — não é um atributo do módulo `scheduler_lock`. Para mockar em testes, use `patch("redis.from_url", ...)` (patcha no módulo real `redis`) ou `patch.dict("sys.modules", {"redis": None})` para simular ImportError. Não use `patch("app.services.scheduler_lock.redis", ...)` — isso não funciona com imports inline.

### Armadilha 12 — `exp_semanal` é zerado automaticamente ✅ Resolvido 2026-06-18

`GamificationService.resetar_ranking_semanal()` zera `exp_semanal` de todos os usuários. Job agendado no APScheduler **domingo 23h59 BRT**. Campo é top-level em `usuarios/{uid}` — não confundir com mapa aninhado `gamification.exp_semanal`.

### Armadilha 13 — `contadores_uso` cresce indefinidamente sem cleanup ✅ Resolvido 2026-06-19 (F-31)

Documentos da coleção `contadores_uso` (formato `{user_id}_{YYYY-MM-DD}`) acumulavam para sempre. A política de retenção é **90 dias**: documentos mais antigos são filtrados pelo campo `data` e removidos em batch (≤500 ops/commit).

**Execução automática:** job `limpar_contadores_uso` no APScheduler, todo **domingo às 02h00 BRT**, protegido por distributed lock Redis.

**CLI manual:**
```bash
python scripts/limpar_contadores_uso.py              # dry-run (padrão seguro)
python scripts/limpar_contadores_uso.py --apply      # deleta de verdade
```

**Armadilha em testes:** `db.batch()` só é chamado se houver ao menos 1 doc no stream — o mock de `mock_db.batch.assert_not_called()` funciona quando o stream retorna `iter([])`. Se mockar com uma lista não vazia, `batch.delete` e `batch.commit` serão chamados.

### Armadilha 14 — Arquivo de teste legado ativo (F-53) ✅ Resolvido 2026-06-17

`tests/e2e/test_solicitante.py` está marcado com `@pytest.mark.skip` (legado). Usar **`tests/e2e/test_fluxo_solicitante.py`** para fluxos E2E de solicitante.

### Armadilha 15 — `confirmacao-solicitante.md` fora de lugar (F-78) ✅ Resolvido 2026-06-17

O plano de confirmação de resolução pelo solicitante está em **`docs/plans/confirmacao-solicitante.md`** — feature planejada, ainda não implementada.

### Armadilha 16 — `setor_para_area()` tem cache de 5 min ✅ Resolvido 2026-06-19 (F-30)

`setor_para_area()` em `app/utils_areas.py` usa `get_static_cached("setor_para_area_map", _carregar_mapa_firestore, 300)`. Isso significa que mudanças no documento Firestore `config/setor_para_area` levam **até 5 minutos** para propagar.

**Flush imediato:** `from app.utils_areas import invalidar_cache_setor_area; invalidar_cache_setor_area()` (por processo — em multi-worker, cada worker tem seu próprio cache).

**Armadilha em testes:** Sempre chame `static_cache_delete("setor_para_area_map")` antes e depois de testes que mockem `_carregar_mapa_firestore` ou `db` em `utils_areas`. O cache é por processo (`_static_cache` global) e contamina outros testes se não limpo.

---

## 19. Strings hardcoded e internacionalização no frontend

> **Status (2026-06-17):** os achados F-34, F-36, F-37, F-38, F-44 e F-46 foram resolvidos — `dashboard_otimizacoes.js` e `table-filters.js` consomem `DTX_MSGS`, `DTX_URLS` e `DTX_STATUS_VALIDOS` injetados pelo servidor. Permanecem strings hardcoded em templates pontuais (`base.html` WebPush, `navbar.html`) — backlog menor.

Um dos problemas identificados na auditoria era que vários arquivos JavaScript tinham strings de interface diretamente no código em PT-BR. O padrão abaixo é o **estado atual** do projeto após o sprint Grupo 3/5.

### Padrão correto: window.DTX_MSGS

O padrão do projeto para expor strings traduzidas ao JavaScript é injetar um objeto global a partir do template base:

```html
<!-- app/templates/base.html — dentro do <head> ou antes do </body> -->
<script>
  window.DTX_MSGS = {
    erro_generico: "{{ t('erro_generico') }}",
    cancelando: "{{ t('cancelando') }}",
    tente_novamente: "{{ t('tente_novamente') }}"
  };
  window.DTX_URLS = {
    atualizar_status: "{{ url_for('main.atualizar_status') }}"
  };
</script>
```

```javascript
// dashboard_otimizacoes.js — usar o objeto injetado
const MSGS = window.DTX_MSGS || {
    // fallback mínimo apenas para desenvolvimento sem template
    erro_generico: 'Erro. Tente novamente.'
};
```

### Estado após sprint (resolvido vs. pendente)

| Local | Status | Achado |
|---|---|---|
| `dashboard_otimizacoes.js` — `MSGS`, URLs, `statusValidos` | ✅ Via `DTX_MSGS`/`DTX_URLS`/`DTX_STATUS_VALIDOS` | F-34, F-36, F-46 |
| `table-filters.js` — labels e locale | ✅ Via `DTX_MSGS` + `DTX_DEBUG` guard | F-37, F-38, F-44 |
| `base.html` (WebPush JS) | ⏳ `"Ativando..."` ainda hardcoded | — |
| `navbar.html:51` | ⏳ `aria-label="Abrir menu"` | — |
| `indices_firestore.html` | ⏳ Template sem `t()` | — |

### Regra

- Qualquer string visível ao usuário no JS deve vir de `window.DTX_MSGS`
- Qualquer URL de API no JS deve vir de `window.DTX_URLS` (não hardcoded)
- `console.warn/log` em JS de produção deve ser protegido por `window.DTX_DEBUG`

---

## 20. Melhorias de produto recentes (`melhorias-sprint.md`)

Três melhorias de produto + A/B test implementados além do sprint de auditoria:

| # | Feature | Onde olhar |
|---|---|---|
| 1 | **Multi-anexo** ao adicionar arquivos em chamado existente | `visualizar_chamado.html` (`multiple`, `name="anexos_novos"`), `dashboard.py`, `api.py`, loop em `edicao_chamado_service.py` |
| 2 | **Anti-self-ticket** — solicitante não pode ser responsável na criação | `chamados_criacao_service.py` (`_resolver_responsavel`), testes em `test_chamados_criacao_service.py` e `test_api_supervisores.py` |
| 3 | **Microsoft Graph API** — e-mail exclusivamente via Graph (sem Brevo/SMTP) | `notifications.py` (`_enviar_via_graph`), variáveis `GRAPH_*` em `.env.example` |
| 4 | **A/B test AB-001** — variante B no formulário (placeholder contextual + contador) | `ab_service.py`, `chamados.py`, `formulario.html`, logging em `validators.py` |

---

## 21. Ciclo de qualidade antes de commit

Execute **todos** os passos abaixo antes de qualquer commit. Nenhuma exceção.

```bash
# Passo 1 — Lint e formatação
ruff check app/ tests/ --fix
ruff format app/ tests/

# Passo 2 — Auditoria de segurança
bandit -r app/ -ll

# Passo 3 — Testes completos
pytest --tb=short -q

# Passo 4 — Push (via script da skill)
bash skills/Essencial/git-pushing/scripts/smart_commit.sh "tipo: descrição"
```

> **Atenção:** O gate de cobertura é **85%** global e **85% por módulo** (`python scripts/check_coverage_per_module.py`). Se sua mudança reduzir a cobertura abaixo desse valor, adicione testes antes de abrir PR.

### Checklist rápido

- [ ] `ruff check` — zero erros
- [ ] `ruff format` — código formatado
- [ ] `bandit -r app/ -ll` — zero High, nenhum Medium novo
- [ ] `pytest --tb=short -q` — 1309+ testes passando
- [ ] Cobertura >= 85% global; `python scripts/check_coverage_per_module.py` — todos os módulos >= 85%
- [ ] Nenhuma variável de ambiente ou credencial no commit
- [ ] Strings novas adicionadas ao `translations.json` nos 3 idiomas
- [ ] Strings de UI em JS usam `window.DTX_MSGS`, não hardcoded

---

## 22. Conventional commits

### Formato

```
tipo(escopo): Assunto em imperativo, máx 70 chars

Corpo opcional: explica O QUE e POR QUÊ, não o como.

Co-Authored-By: Claude <noreply@anthropic.com>
```

### Tipos disponíveis

| Tipo | Quando usar | Exemplo |
|---|---|---|
| `feat` | Nova funcionalidade | `feat(chamados): Adicionar campo de urgência` |
| `fix` | Correção de bug | `fix(auth): Corrigir lockout por IP` |
| `security` | Hardening / correção de segurança | `security(utils): Corrigir IP spoofing em get_client_ip` |
| `test` | Adição ou correção de testes | `test(upload): Aumentar cobertura para 80%` |
| `refactor` | Refatoração sem mudança de comportamento | `refactor(services): Extrair validação para validators.py` |
| `perf` | Melhoria de performance | `perf(dashboard): Usar get_static_cached em usuario lookup` |
| `chore` | Manutenção (deps, config, CI) | `chore(deps): Atualizar ruff para 0.9.10` |
| `docs` | Documentação | `docs: Atualizar GUIA_ONBOARDING_TECNICO.md` |
| `style` | Formatação sem mudança de lógica | `style: Aplicar ruff format em services/` |

### Regras do assunto

- Imperativo presente: "Adicionar" não "Adicionado"
- Primeira letra maiúscula, sem ponto final
- Máximo 70 caracteres

---

## 23. FAQ — Perguntas frequentes de novos devs

**P: Por que os imports ficam dentro das funções de rota?**
R: Para compatibilidade com `unittest.mock`. Se você importar no topo do arquivo, o `patch()` nos testes não consegue interceptar as chamadas. Ver seção 12.

**P: Como adiciono um novo campo ao modelo Chamado?**
R: Edite `app/models.py`. Adicione o campo ao `to_dict()` e ao `from_dict()`. Se o campo precisa de índice no Firestore, adicione em `firestore.indexes.json` e faça deploy com `firebase deploy --only firestore:indexes`. Consulte `docs/INDICES_FIRESTORE.md`.

**P: Por que o pytest falha com "FirebaseApp not initialized"?**
R: O `conftest.py` usa uma instância mock do Firestore. Se você importou `db` no topo de um módulo novo (em vez de dentro da função), o import acontece antes do mock ser aplicado. Mova o import para dentro da função ou use `patch()` corretamente.

**P: Como faço para ver os logs de e-mail em desenvolvimento?**
R: Deixe `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET` e `GRAPH_SENDER_EMAIL` em branco no `.env`. O serviço de notificações detecta a ausência das credenciais e emite um `logging.warning` no console em vez de tentar enviar o e-mail real. Nunca use `MAIL_SERVER`/`BREVO_API_KEY` — essas variáveis não são mais suportadas.

**P: Posso usar `db.collection().get()` para listar todos os chamados?**
R: Não para coleções grandes. Sempre use paginação com `.limit()` e `.start_after()`. Ver `app/services/chamados_listagem_service.py` como exemplo.

**P: Como reseto a senha de um usuário?**
R: Via painel de admin em `/admin/usuarios`, ou via script: `python scripts/criar_usuario.py --reset-senha`.

**P: Qual é a diferença entre `@requer_solicitante` e `login_required`?**
R: `@requer_solicitante` inclui `login_required` mais verifica se o usuário está ativo e se não precisa trocar a senha. Sempre use os decoradores do projeto, não o do Flask-Login diretamente.

**P: Como adiciono um novo idioma?**
R: Adicione a chave de idioma em `app/translations.json`, registre o idioma em `app/i18n.py` na lista `IDIOMAS_SUPORTADOS`, e adicione a opção de seleção no template de configurações.

**P: O que é o GrupoRL?**
R: Grupo de Revisão e Liberação — estrutura hierárquica de aprovação para determinadas categorias de chamado. Configurado via painel admin em `/admin-categorias`.

**P: Como crio um superusuário para o ambiente de desenvolvimento?**
R: Use `python scripts/criar_usuario.py` e defina o perfil como `admin`. Para testar funcionalidades exclusivas de governança, defina o perfil como `admin_global`. Em desenvolvimento, você pode criar quantos usuários precisar. Só existe um `admin_global` por instância (restrição por design).

**P: O que é `ENCRYPT_PII_AT_REST`?**
R: Flag que ativa a criptografia de campos sensíveis (nome, e-mail, telefone) no Firestore usando a chave `ENCRYPTION_KEY`. Em desenvolvimento, deixe `false`. Em produção, consulte `docs/ENV.md` para o procedimento correto de ativação.

**P: Por que `run.py` e não `app.py`?**
R: Convenção do projeto. O `run.py` é o entry point da aplicação. Em produção (Docker), o Gunicorn usa `run:app` ou equivalente.

**P: Como vejo as métricas de cobertura por arquivo?**
R: `pytest --cov=app --cov-report=term-missing -q` — a coluna `Missing` mostra exatamente quais linhas não são cobertas. Para ver quais módulos estão abaixo do gate de 85%: `python scripts/check_coverage_per_module.py --json-only`.

**P: O round-robin de atribuição funciona em produção?**
R: Não completamente. O contador de round-robin é por processo — em ambiente multi-worker do Gunicorn, cada worker tem seu próprio contador. Ver seção 18 (Armadilha 1 — F-21) para detalhes e a solução planejada.

**P: Como vejo as notificações push localmente?**
R: Configure as variáveis `VAPID_*` no `.env`. Acesse via HTTPS (mesmo localhost — alguns browsers exigem HTTPS para Service Workers). Em desenvolvimento você pode usar `ngrok` para criar um túnel HTTPS temporário.

**P: O que é `cor="#gray"` que aparece no banco de dados?**
R: É um valor padrão inválido em `models_categorias.py:272` — foi escrito `"#gray"` em vez de `"gray"` ou `"#808080"`. CSS ignora valores inválidos, então a cor não aparece. Ver achado F-28 no plano de sprint para a correção.

**P: Por que `exp_semanal` do ranking não muda entre semanas?**
R: Resolvido em 2026-06-18 (S4-02). `GamificationService.resetar_ranking_semanal()` é executado todo domingo 23h59 BRT via APScheduler com distributed lock Redis. Se você está em desenvolvimento local sem Redis, pode rodar manualmente: `python scripts/reset_ranking_semanal.py --force`.

**P: Como faço deploy dos índices do Firestore?**
R: Execute `firebase deploy --only firestore:indexes`. O arquivo `firestore.indexes.json` define os índices compostos. Sobre F-82 (resolvido): o filtro do dashboard por responsável usa o campo **`responsavel`** (nome), conforme `app/services/filters.py` (`FieldFilter("responsavel", "==", ...)`), portanto os índices sobre `responsavel` estão corretos. O campo `responsavel_id` (UID) também existe, mas é usado para agrupamento/atribuição e notificações, não para esse filtro.

**P: Quais scripts de migração posso rodar com segurança?**
R: `scripts/migrar_setores_catalogo.py` (tem `--dry-run`), `scripts/migrar_gates_subetapas.py` (idempotente) e `scripts/verificar_dependencias.py` (apenas leitura). Evite `scripts/atualizar_firebase.py` (obsoleto, apaga sem dry-run) e `scripts/atualizar_setores_from_print.py` (sem dry-run). Ver tabela de scripts na seção 5.

---

*Documento atualizado em 2026-06-18 — DTX Aerospace, Engenharia de Software*
