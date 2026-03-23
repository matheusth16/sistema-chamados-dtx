# Sistema de Chamados DTX

> Sistema web de gerenciamento de chamados integrado com Firebase/Firestore, construído com Python/Flask.

## 🚀 Características

- **Paginação Otimizada**: Cursor-based pagination para performance com grandes volumes (sem OOM)
- **Índices Firestore**: Índices compostos para máxima velocidade de queries
- **Atualização em Tempo Real**: Status atualiza sem recarregar a página
- **Dashboard Completo**: Visualização, filtros, histórico de alterações e bulk status
- **Autenticação Segura**: Login com Firebase Authentication e perfis (solicitante, supervisor, admin)
- **Upload de Anexos**: Suporte a arquivos (PDFs, imagens, etc.)
- **Internacionalização (i18n)**: Traduções PT/EN e painel de administração de textos (idioma padrão: **EN**, com suporte a `?lang=pt_BR`)
- **Logs Estruturados**: Rastreamento completo de ações
- **Rate Limiting**: Proteção contra abuso de requisições (Redis em produção)

## 📋 Requisitos

- Python 3.12+
- Firebase Account com Firestore
- pip (gerenciador de pacotes Python)

## 🔧 Instalação

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

# Desenvolvimento (inclui pytest, ruff, bandit, etc.)
pip install -r requirements-dev.txt
```

### 4. Configure credenciais do Firebase

1. Vá para [Firebase Console](https://console.firebase.google.com)
2. Baixe `credentials.json` da sua conta de serviço
3. Coloque na raiz do projeto

### 5. Configure variáveis de ambiente

Copie o exemplo e preencha (veja **docs/ENV.md** para a lista completa):

```bash
cp .env.example .env
# Edite .env e defina ao menos SECRET_KEY e FLASK_ENV
# Em produção: defina FLASK_ENV=production e use SECRET_KEY forte (ex: openssl rand -hex 32)
```

Documentação das variáveis: **[docs/ENV.md](docs/ENV.md)**

### 6. Inicie a aplicação

```bash
python run.py
```

Acesse: `http://localhost:5000`

### 7. Scripts úteis (opcional)

Na raiz do projeto você pode rodar scripts de manutenção (criação de usuário, chaves VAPID, deploy, etc.). Documentação: **[scripts/README.md](scripts/README.md)**.

```bash
python scripts/verificar_dependencias.py  # Audit + testes (recomendado antes de commit)
python scripts/gerar_vapid_keys.py        # Chaves Web Push
python scripts/gerar_chave_criptografia.py # Chave para criptografia de PII (LGPD)
python scripts/criar_usuario.py            # Criar usuário no sistema
```

## 📚 API

Referência completa dos endpoints: **[docs/API.md](docs/API.md)**.

Resumo rápido:
- **GET** `/health` — Health check (retorna `{"status": "ok"}`).
- **GET** `/api/chamados/paginar` — Paginação com cursor; query params: `limite`, `cursor`, `status`, `categoria`, `gate`, `search`.
- **POST** `/api/carregar-mais` — Carregar mais registros (infinite scroll).
- **POST** `/api/atualizar-status` — Atualizar status de um chamado.
- **POST** `/api/bulk-status` — Atualizar status em lote (supervisor/admin).

## 🏗️ Estrutura do Projeto

```
sistema-chamados-dtx/
├── app/
│   ├── routes/                  # Rotas (chamados, auth, api, dashboard, usuários, categorias, traduções)
│   ├── services/                # Lógica de negócio (filters, pagination, validators, analytics, permissions, etc.)
│   ├── templates/               # Jinja2 (dashboard, formulario, historico, usuarios, admin_traducoes, etc.)
│   ├── static/                  # JS, CSS, uploads
│   ├── models.py, models_categorias.py, models_usuario.py
│   ├── database.py, i18n.py, limiter.py, cache.py
│   └── translations.json        # Textos i18n (PT/EN)
├── docs/                        # Documentação (ENV.md, API.md, DEPLOYMENT_PLAN.md, etc.)
├── scripts/                     # Scripts de manutenção (criar_usuario, gerar_vapid_keys, deploy, etc.)
├── tests/                       # Testes (routes, services, utils)
├── config.py                    # Configurações
├── run.py                       # Ponto de entrada
├── requirements.txt
├── firestore.indexes.json
├── firestore.rules
└── README.md
```

### Caminhos de arquivos (Windows)

No repositório **não há arquivos duplicados**. O Git sempre usa barras normais (`/`) nos caminhos. No Windows, `app\routes\api.py` e `app/routes/api.py` referem-se ao **mesmo arquivo**; o `.gitattributes` garante normalização. Em imports e referências no código, use sempre `app/routes/api.py` e `app/services/notifications_inapp.py`.

## ⚡ Performance

### Impacto das Otimizações

| Operação | Antes | Depois | Melhoria |
|---|---|---|---|
| Carregar dashboard | 3-5s | 200-400ms | **15x** |
| Mudar status | 2-3s | 100-200ms | **20x** |
| Filtrar (com índice) | 2-5s | 50-100ms | **50x** |
| Busca full-text | 3-4s | 300-500ms | **10x** |

### Índices Firestore Recomendados

Para máxima performance, crie os seguintes índices no Firestore Console:

1. `categoria` + `status` + `data_abertura`
2. `status` + `data_abertura`
3. `categoria` + `prioridade` + `data_abertura`
4. `gate` + `status` + `data_abertura`

Ou via CLI:
```bash
firebase deploy --only firestore:indexes --project seu-projeto-id
```

## 🔒 Segurança

- ✅ Autenticação realizada em todas as rotas sensíveis
- ✅ Rate limiting habilitado
- ✅ Validação rigorosa de entrada
- ✅ CSRF protection ativado
- ✅ Passwords hasheados com werkzeug
- ✅ Logs de auditoria completos
- ✅ Credenciais Firebase não são versionadas
- ✅ Em produção, `SECRET_KEY` é obrigatória (valor forte e único)
- ✅ Headers de segurança: `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, HSTS em HTTPS
- ✅ Validação de Origin/Referer em POST sensíveis quando `APP_BASE_URL` está definido
- ✅ **Criptografia em repouso**: opcional para PII (ex.: nome de usuário) via `ENCRYPTION_KEY` e `ENCRYPT_PII_AT_REST`; gere a chave com `python scripts/gerar_chave_criptografia.py`
- ✅ **Dados em trânsito**: sessão e cookies em HTTPS; SMTP com TLS; APIs externas em HTTPS
- ✅ **Conformidade LGPD**: política de segurança e boas práticas em **[docs/POLITICA_SEGURANCA_LGPD.md](docs/POLITICA_SEGURANCA_LGPD.md)**

## 📖 Documentação

| Documento | Descrição |
|-----------|-----------|
| [docs/ENV.md](docs/ENV.md) | Variáveis de ambiente (.env) |
| [docs/API.md](docs/API.md) | Referência completa da API |
| [docs/POLITICA_SEGURANCA_LGPD.md](docs/POLITICA_SEGURANCA_LGPD.md) | Segurança, criptografia e conformidade LGPD |
| [docs/DEPLOYMENT_PLAN.md](docs/DEPLOYMENT_PLAN.md) | Deploy (Cloud Run, Firebase) |
| [docs/onboarding.md](docs/onboarding.md) | Onboarding interativo: visão de produto e detalhes técnicos |
| [scripts/README.md](scripts/README.md) | Scripts de manutenção |
| `firestore.rules` | Regras de segurança Firestore |
| `firestore.indexes.json` | Índices Firestore |
| `config.py` | Configurações da aplicação |

## 🐛 Troubleshooting

### Erro: "FAILED_PRECONDITION" em query

**Causa:** Índice composto faltando
**Solução:** Criar índice no Firebase Console ou via CLI

### Dashboard carrega lento

**Causa:** Firestore indexando em background
**Solução:** Esperar 15 minutos após criar índices

### Erro de conexão com Firebase

**Causa:** `credentials.json` não encontrado
**Solução:** Adicionar arquivo de credenciais na raiz do projeto

### Erro ao subir em produção: "SECRET_KEY must be set"

**Causa:** Em `FLASK_ENV=production` a aplicação exige `SECRET_KEY` no ambiente.
**Solução:** Defina `SECRET_KEY` com um valor forte (ex: `openssl rand -hex 32`) nas variáveis de ambiente.

### Dependências

O `requirements.txt` usa **versões fixas** (ex.: Flask 3.1.2, firebase-admin 7.1.0) para reprodutibilidade entre ambientes.

É importante manter dependências seguras e atualizadas:

1. **Auditar vulnerabilidades** (recomendado de forma periódica):
   ```bash
   pip install -U pip
   pip audit
   ```

2. **Atualizar pacotes** quando necessário (testar a aplicação após atualizar):
   ```bash
   pip install -r requirements.txt --upgrade
   ```

Após alterar versões, atualize o `requirements.txt` com `pip freeze` ou ajuste manualmente as versões pinadas.

### Ciclo de qualidade (obrigatório antes de commit)

Execute os passos abaixo na ordem. O CI fará o mesmo — falhar localmente é mais rápido que falhar no pipeline.

```bash
# 1. Lint e formatação automática
ruff check app/ tests/ --fix
ruff format app/ tests/

# 2. Análise de segurança estática
bandit -r app/ -ll

# 3. Testes com relatório de cobertura
pytest --tb=short -q \
  --cov=app \
  --cov-report=term-missing:skip-covered \
  --cov-fail-under=70
```

**Gate de cobertura:** mínimo de **70%** (CI rejeita abaixo disso).

Para rodar apenas um módulo ou um arquivo específico:
```bash
pytest tests/test_services/test_validators.py -v
pytest tests/ -k "dashboard" --tb=short
```

### Artefatos de teste — não versionar

Os arquivos abaixo são gerados automaticamente e já estão no `.gitignore`. **Nunca os adicione ao git:**

| Artefato | O que é |
|---|---|
| `.coverage` | Banco de dados de cobertura do pytest-cov |
| `coverage.xml` | Relatório XML para CI/upload |
| `htmlcov/` | Relatório HTML de cobertura |
| `.pytest_cache/` | Cache interno do pytest |
| `__pycache__/` | Bytecode compilado Python |

Se um desses aparecer em `git status`, rode:
```bash
git rm --cached <arquivo>   # remove do rastreamento sem deletar localmente
```

## 🤝 Contribuindo

1. Faça um Fork do projeto
2. Crie uma branch para sua feature (`git checkout -b feature/AmazingFeature`)
3. Commit suas mudanças (`git commit -m 'Add some AmazingFeature'`)
4. Push para a branch (`git push origin feature/AmazingFeature`)
5. Abra um Pull Request

## 📄 Licença

Este projeto é propriedade da DTX Aerospace.

## 👤 Autor

**Matheus Costa**
- GitHub: [@matheusth16](https://github.com/matheusth16)
- Email: matheus@dtx-aerospace.com

## 🎯 Roadmap

- [x] Paginação com "Carregar Mais" / infinite scroll
- [x] Caching e rate limit com Redis (configurável)
- [x] Export (Excel) e relatórios
- [x] i18n (PT/EN) e painel de traduções
- [x] **PWA / notificações**: Service Worker e Web Push (notificações push no navegador) — base para uso offline e alertas
- [ ] Cache local com IndexedDB (opcional; melhora uso offline)
- [ ] Notificações em tempo real (WebSocket; complementa Web Push)
- [ ] Mobile app

---

**Feito com ❤️ por Matheus Costa**
