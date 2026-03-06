# Scripts de manutenção

Execute sempre **a partir da raiz do projeto** (onde está o `run.py`).

## Índice rápido

| Script | Quando usar |
|--------|-------------|
| **verificar_dependencias.py** | Antes de commit/deploy: audit de vulnerabilidades + testes |
| **criar_usuario.py** | Criar usuário (solicitante, supervisor, admin) no sistema |
| **gerar_vapid_keys.py** | Gerar chaves Web Push (notificações no navegador) para o `.env` |
| **gerar_chave_criptografia.py** | Gerar chave para criptografia de PII (LGPD) para o `.env` |
| **init_categorias.py** | Inicializar categorias padrão no Firestore (setores, gates, impactos) |
| **atualizar_firebase.py** | Sincronizar collections de categorias com os dados do formulário |
| **migrar_campo_senha.py** | Migração: adicionar campos de controle de senha em usuários existentes |
| **migrar_grupos_rl.py** | Migração: criar grupos RL e vincular chamados de Projetos |
| **reset_ranking_semanal.py** | Zerar ranking semanal (gamificação); usar em cron toda segunda-feira |
| **verificar_supervisores.py** | Listar supervisores e áreas (diagnóstico) |
| **resumo_supervisores.py** | Resumo de supervisores por setor (diagnóstico) |
| **apagar_todos_chamados.py** | **Cuidado:** apaga todos os chamados e histórico (dev/reset) |
| **testar_email_smtp.py** | Testar envio de e-mail SMTP (diagnóstico de notificações) |
| **deploy_fresh.ps1** | Deploy no Cloud Run com rebuild sem cache (Windows) |
| **ver_logs_build.ps1** | Ver logs do último build do Cloud Build (Windows) |

---

## Python (executar com `python scripts/<script>`)

### verificar_dependencias.py

Verifica vulnerabilidades (`pip audit`) e roda a suíte de testes (`pytest`). Recomendado antes de commit ou deploy.

```bash
python scripts/verificar_dependencias.py
python scripts/verificar_dependencias.py --cov        # testes com cobertura
python scripts/verificar_dependencias.py --no-audit   # só testes
python scripts/verificar_dependencias.py --no-tests  # só pip audit
```

### criar_usuario.py

Cria usuários no sistema (solicitante, supervisor, admin) de forma interativa ou rápida. Use após configurar o Firebase e o `.env`.

```bash
python scripts/criar_usuario.py
```

### gerar_vapid_keys.py

Gera chaves VAPID para Web Push (notificações no navegador). Copie a saída para o `.env` como `VAPID_PUBLIC_KEY` e `VAPID_PRIVATE_KEY`.

```bash
python scripts/gerar_vapid_keys.py
```

### gerar_chave_criptografia.py

Gera uma chave Fernet para criptografia de dados sensíveis em repouso (LGPD). Copie a linha gerada para o `.env` como `ENCRYPTION_KEY`. Para ativar: `ENCRYPT_PII_AT_REST=true`.

```bash
python scripts/gerar_chave_criptografia.py
```

### init_categorias.py

Inicializa categorias padrão no Firestore (setores, gates, impactos) se o banco estiver vazio. Use na primeira configuração do projeto.

```bash
python scripts/init_categorias.py
```

### atualizar_firebase.py

Atualiza as collections `categorias_setores` e `categorias_impactos` no Firebase com os dados exatos do formulário (limpa as antigas e recria). Use com cuidado em produção.

Requer `credentials.json` na raiz do projeto.

```bash
python scripts/atualizar_firebase.py
```

### migrar_campo_senha.py

Migração one-shot: adiciona os campos `must_change_password` e `password_changed_at` a todos os usuários existentes (para controle de troca de senha obrigatória). Execute uma vez ao habilitar a funcionalidade.

```bash
python scripts/migrar_campo_senha.py
```

### migrar_grupos_rl.py

Migração: cria documentos na coleção `grupos_rl` a partir dos chamados com categoria "Projetos" e `rl_codigo`, e atualiza cada chamado com `grupo_rl_id`. Execute uma vez ao habilitar grupos RL.

```bash
python scripts/migrar_grupos_rl.py
```

### reset_ranking_semanal.py

Zera o campo `exp_semanal` de todos os usuários (gamificação). Deve ser executado via cron/scheduler toda segunda-feira.

```bash
python scripts/reset_ranking_semanal.py
```

### verificar_supervisores.py

Lista todos os supervisores e suas áreas no Firestore. Útil para diagnóstico e conferência de permissões.

```bash
python scripts/verificar_supervisores.py
```

### resumo_supervisores.py

Exibe um resumo de supervisores cadastrados por setor. Útil para diagnóstico.

```bash
python scripts/resumo_supervisores.py
```

### apagar_todos_chamados.py

**Cuidado:** apaga **todos** os chamados e o histórico associado do Firestore. Use apenas em ambiente de desenvolvimento ou para reset completo. Exige confirmação interativa (ou `--confirm` para automação).

Requer `credentials.json` na raiz do projeto.

```bash
python scripts/apagar_todos_chamados.py
python scripts/apagar_todos_chamados.py --confirm   # pula confirmação
```

### testar_email_smtp.py

Testa o envio de e-mail via SMTP usando as variáveis `MAIL_*` do `.env`. Use para diagnosticar erros de autenticação ou conexão (Gmail, Outlook, etc.).

```bash
python scripts/testar_email_smtp.py
python scripts/testar_email_smtp.py destino@exemplo.com   # enviar para e-mail específico
```

---

## PowerShell (Windows)

### deploy_fresh.ps1

Deploy para Cloud Run forçando rebuild sem cache. Execute **na raiz do projeto**:

```powershell
.\scripts\deploy_fresh.ps1
```

### ver_logs_build.ps1

Exibe os logs do último build do Cloud Build (para debugar deploy que falhou). Execute **na raiz do projeto**:

```powershell
.\scripts\ver_logs_build.ps1
.\scripts\ver_logs_build.ps1 -BuildId "c3596f94-9d0d-4452-8ad8-bc9e1b1d89eb"
```
