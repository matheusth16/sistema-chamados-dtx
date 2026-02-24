# Scripts de manutenção

Execute sempre **a partir da raiz do projeto** (onde está o `run.py`).

## init_categorias.py

Inicializa categorias padrão no Firestore (setores, gates, impactos) se o banco estiver vazio.

```bash
python scripts/init_categorias.py
```

## atualizar_firebase.py

Atualiza as collections `categorias_setores` e `categorias_impactos` no Firebase com os dados exatos do formulário (limpa as antigas e recria). Use com cuidado em produção.

```bash
python scripts/atualizar_firebase.py
```

Requer `credentials.json` na raiz do projeto.

## gerar_vapid_keys.py

Gera chaves VAPID para Web Push (notificações no navegador). Copie a saída para o `.env`.

```bash
python scripts/gerar_vapid_keys.py
```

## criar_usuario.py

Cria usuários no sistema (solicitante, supervisor, admin) de forma interativa ou rápida.

```bash
python scripts/criar_usuario.py
```

## deploy_fresh.ps1 (Windows PowerShell)

Deploy para Cloud Run forçando rebuild sem cache. Execute **na raiz do projeto**:

```powershell
.\scripts\deploy_fresh.ps1
```

## ver_logs_build.ps1 (Windows PowerShell)

Exibe os logs do último build do Cloud Build (para debugar deploy que falhou). Execute **na raiz do projeto**:

```powershell
.\scripts\ver_logs_build.ps1
# Ou com ID específico:
.\scripts\ver_logs_build.ps1 -BuildId "c3596f94-9d0d-4452-8ad8-bc9e1b1d89eb"
```
