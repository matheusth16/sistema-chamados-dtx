# Configuração do Ambiente de Desenvolvimento

Guia para subir o projeto localmente do zero.

---

## Pré-requisitos

| Ferramenta | Versão mínima | Download |
|---|---|---|
| Python | 3.12 | python.org/downloads |
| Git | qualquer | git-scm.com |
| Docker Desktop (opcional) | qualquer | docker.com |

Verifique o que já está instalado:

```powershell
python --version   # Python 3.12.x
git --version
docker --version   # só se quiser usar o Compose
```

---

## 1. Clonar e criar o ambiente virtual

```powershell
git clone https://github.com/matheusth16/sistema-chamados-dtx.git
cd sistema-chamados-dtx

python -m venv .venv
.venv\Scripts\Activate.ps1
```

> Se o PowerShell bloquear o script: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

---

## 2. Instalar dependências

```powershell
# Produção
pip install -r requirements.txt

# Ferramentas de dev (ruff, bandit, pytest, playwright…)
pip install -r requirements-dev.txt
```

---

## 3. Credenciais do Firebase

1. Firebase Console → Configurações do projeto → Contas de serviço → **Gerar nova chave privada**
2. Renomeie o arquivo baixado para `credentials.json`
3. Coloque na raiz do projeto (nunca versionar — já está no `.gitignore`)

---

## 4. Variáveis de ambiente

```powershell
Copy-Item .env.example .env
```

Edite `.env`. Mínimo para rodar localmente:

```env
FLASK_ENV=development
SECRET_KEY=qualquer-string-aleatoria-para-dev
```

Para referência completa de todas as variáveis: **[docs/ENV.md](ENV.md)**

---

## 5. Rodar a aplicação

```powershell
python run.py
```

Acesse: `http://localhost:5000`

### Alternativa: Docker Compose (hot-reload)

```powershell
docker compose up --build
```

Acesse: `http://localhost:5000`
O código em `app/` é montado como volume — alterações recarregam sem rebuild.

---

## 6. Rodar os testes

```powershell
pytest --tb=short -q
```

Para ver o relatório de cobertura:

```powershell
pytest --cov=app --cov-report=term-missing -q
```

Os testes usam mocks do Firestore — nenhuma conexão com Firebase é necessária.

---

## 7. Instalar os hooks de pré-commit (recomendado)

```powershell
pre-commit install
```

A partir daí, cada `git commit` roda automaticamente: ruff (lint + format) e bandit (segurança).

Para rodar manualmente antes de commitar:

```powershell
ruff check app/ tests/ --fix
ruff format app/ tests/
bandit -r app/ -ll
```

---

## Estrutura de diretórios-chave

```
sistema_chamados/
├── app/                  # Código Flask
│   ├── routes/           # Blueprints de rotas
│   ├── services/         # Lógica de negócio
│   └── templates/        # Jinja2 templates
├── tests/                # Suíte de testes (pytest)
├── scripts/              # Utilitários (diagnóstico, deploy)
├── docs/                 # Documentação
├── credentials.json      # Credencial Firebase (NÃO versionar)
├── .env                  # Variáveis de ambiente (NÃO versionar)
├── run.py                # Entrypoint Flask
├── Dockerfile            # Imagem multi-stage (build + runtime)
└── docker-compose.yml    # Dev local com hot-reload
```

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'firebase_admin'`**
O venv não está ativo. Execute `.venv\Scripts\Activate.ps1` e tente novamente.

**`FileNotFoundError: credentials.json`**
Coloque o arquivo na raiz do projeto (passo 3).

**`ValueError: SECRET_KEY must be set`**
`.env` não foi criado ou `SECRET_KEY` está em branco (passo 4).

**Porta 5000 já em uso**
Defina outra porta no `.env`: `PORT=5001`

**Testes falham com `PermissionError` no Windows**
Certifique-se de que o venv está ativo e os pacotes de dev instalados.

---

## Próximos passos

- Para deploy em produção: [docs/DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md)
- Para incidentes em produção: [docs/INCIDENT_RUNBOOK.md](INCIDENT_RUNBOOK.md)
- Ciclo de qualidade antes de commitar: ver `CLAUDE.md`
