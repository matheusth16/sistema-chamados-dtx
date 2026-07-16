# Scripts de manutenção

Execute sempre **a partir da raiz do projeto** (onde está o `run.py`).
A maioria dos scripts que tocam o banco requer `credentials.json` na raiz.

## Índice rápido

| Script | Quando usar |
|--------|-------------|
| **executar_qa_manual_cwi.py** | Playbook QA manual CWI (11 sub-itens): validação local via test client; gera JSON em `docs/evidencias/` |
| **executar_qa_escalonamento.py** | Playbook QA Onda 6 — Escalonamento + SLA Gerencial (10 cenários ESC-01..ESC-10): isolamento, claim, transferência, multi-setor, gestor, tempo útil, deadline imutável; `--json` gera JSON em `docs/evidencias/` |
| **check_coverage_per_module.py** | Gate de cobertura >= 85% por módulo em `app/` (lê `coverage.json`) |
| **verificar_dependencias.py** | Antes de commit/deploy: audit de vulnerabilidades + testes |
| **criar_usuario.py** | Criar usuário (solicitante, supervisor, admin) no sistema |
| **promover_admin_global.py** | Promover um usuário existente ao perfil `admin_global` |
| **gerar_vapid_keys.py** | Gerar chaves Web Push (notificações no navegador) para o `.env` |
| **gerar_chave_criptografia.py** | Gerar chave Fernet para criptografia de PII (LGPD) para o `.env` |
| **init_categorias.py** | Inicializar categorias padrão no Firestore (setores, gates, impactos) |
| **migrar_setores_catalogo.py** | Sincronizar catálogo de setores (idempotente, com `--dry-run`) |
| **migrar_setor_area.py** | Semear `config/setor_para_area` no Firestore (mapa setor → área); default dry-run, `--apply` para gravar (F-30) |
| **migrar_gates_subetapas.py** | Migração: estrutura de gates com subetapas |
| **migrar_grupos_rl.py** | Migração: criar grupos RL e vincular chamados de Projetos |
| **migrar_campo_senha.py** | Migração: adicionar campos de controle de senha em usuários |
| **migrar_supervisor_ids_com_acesso.py** | Backfill campo `supervisor_ids_com_acesso` em chamados legados (Fase 2 — isolamento supervisor); **obrigatório após deploy da Fase 2**; idempotente, dry-run por padrão |
| **migrar_participantes.py** | Backfill `participantes[]` a partir de `setores_adicionais` legado (Fase 4 — multi-setor); idempotente, dry-run por padrão |
| **migrar_usuarios_ativo.py** | Backfill campo `ativo` em usuários legados (Onda 2 — desativação); idempotente, dry-run por padrão |
| **migrar_pii_criptografia.py** | Criptografa `nome` e `email` com Fernet + grava `email_lookup_hash` (Onda 4 — LGPD); idempotente, dry-run por padrão |
| **atualizar_traducoes_setores.py** | Atualizar traduções (pt/en/es) dos setores existentes |
| **reset_ranking_semanal.py** | Zerar ranking semanal (gamificação) manualmente; **automatizado via APScheduler** (domingo 23h59 BRT) |
| **limpar_contadores_uso.py** | Remover documentos antigos de `contadores_uso` (retenção 90 dias); **automatizado via APScheduler** (domingo 02h00 BRT); default dry-run |
| **verificar_supervisores.py** | Listar supervisores e áreas (diagnóstico) |
| **resumo_supervisores.py** | Resumo de supervisores por setor (diagnóstico) |
| **gerar_email_visual_snapshots.py** | Gerar snapshots HTML dos templates de e-mail (não envia) |
| **disparar_testes_emails_visual_uat.py** | Disparar e-mails reais de UAT via Microsoft Graph (cuidado) |
| **testar_email_smtp.py** | Diagnóstico legado de envio SMTP (produção usa Microsoft Graph API) |
| **apagar_todos_chamados.py** | **Cuidado:** apaga todos os chamados e histórico (dev/reset) |
| **atualizar_firebase.py** | **Obsoleto/destrutivo:** use `migrar_setores_catalogo.py`. Tem `--apply` (padrão dry-run) |
| **atualizar_setores_from_print.py** | **Destrutivo one-shot:** reset de setores. Tem `--apply` (padrão dry-run) |
| **fix_logger_fstrings.py** | Ferramenta de refactor: converter f-strings de logging |
| **verificar_dependencias.py** | Audit de dependências + suíte de testes |

> **Nota sobre deploy:** o projeto roda em container Docker (ver `Dockerfile` e
> `docker-compose.yml`). Não há mais scripts de deploy para GCP/Cloud Run.
> Para subir: `docker compose up -d --build`.

---

## Jobs APScheduler (background — sem script manual)

Os seguintes jobs são executados automaticamente pelo APScheduler embutido na app.
Não há scripts manuais para acioná-los; esta tabela documenta configuração e dependências.

| Job ID | Trigger | Serviço | Dependências em produção |
|--------|---------|---------|--------------------------|
| **`sla_escalacao`** (Fases 6–7) | Interval — a cada 10 min | `processar_escada_a()` + `processar_avisos_resolucao()` + `processar_escada_b()` | Usuários com Nível de Gestão cadastrados em `/admin/usuarios` (destinatários resolvidos via `gestor_escalonamento_service.py`, sem env var); índices Firestore `status ASC + escalacao_resposta_nivel ASC` e `status ASC + escalacao_resolucao_nivel ASC` (ver `docs/INDICES_FIRESTORE.md`) |
| **`relatorio_semanal`** | Cron — sex 10h00 BRT | `report_service.enviar_relatorio_semanal()` | `GRAPH_*` configurado para envio de e-mail |
| **`reset_ranking_semanal`** | Cron — dom 23h59 BRT | `GamificationService.resetar_ranking_semanal()` | — |
| **`limpar_contadores_uso`** | Cron — dom 02h00 BRT | `contadores_uso.limpar_contadores_antigos()` | — |

Todos os jobs usam `executar_job_com_lock` (`scheduler_lock.py`) para evitar execuções paralelas em ambiente multi-worker. O job `alerta_prazo_24h` (cron 08h) foi **desativado** na Fase 6 — substituído por `sla_escalacao`.

**Stats logados pelo `sla_escalacao` a cada execução** (via `app.logger.info`):
```json
{
  "escada_a":          { "processados": 0, "escalados": 0, "emails": 0, "erros": 0, "pulados_fora_janela": 0 },
  "avisos_resolucao":  { "processados": 0, "notificados_50": 0, "notificados_80": 0, "erros": 0, "pulados_fora_janela": 0 },
  "escada_b":          { "processados": 0, "escalados": 0, "emails": 0, "erros": 0, "pulados_fora_janela": 0 }
}
```

> **Índice Firestore obrigatório antes do primeiro deploy com Fase 6:**
> `chamados` — `status ASC, escalacao_resposta_nivel ASC`.
> Sem ele, `processar_escada_a()` falha com `FAILED_PRECONDITION` no Firestore.
> Ver `docs/INDICES_FIRESTORE.md`.

---

## Python (executar com `python scripts/<script>`)

### executar_qa_manual_cwi.py

Executa o playbook QA manual CWI (11 sub-itens) contra a app local via Flask test client.
Itens que exigem infra externa (VPN HML, inspeção Firestore prod) são marcados SKIP.

```bash
python scripts/executar_qa_manual_cwi.py
python scripts/executar_qa_manual_cwi.py --json > docs/evidencias/qa_manual_cwi_resultado.json
```

Exit 0 — todos os checks locais PASS. Evidência: `docs/evidencias/QA_MANUAL_CWI_EVIDENCIA.md`.

### check_coverage_per_module.py

Gate de cobertura por módulo: verifica que cada arquivo `.py` em `app/` com statements > 0 atinge o threshold (padrão 85%). Lê `coverage.json` gerado pelo pytest; se o arquivo não existir, executa pytest automaticamente.

```bash
python scripts/check_coverage_per_module.py                  # roda pytest + verifica módulos (threshold 85%)
python scripts/check_coverage_per_module.py --json-only      # lê coverage.json existente, sem re-executar pytest
python scripts/check_coverage_per_module.py --threshold 90   # threshold customizado
```

Exit 0 — todos os módulos elegíveis >= threshold.
Exit 1 — um ou mais módulos abaixo (ou pytest falhou).
Exit 2 — `coverage.json` não encontrado e `--json-only` ativo.

**Integração CI:** o workflow `.github/workflows/ci.yml` executa pytest com `--cov-fail-under=85`, gera `coverage.json` e roda `python scripts/check_coverage_per_module.py --json-only` como gate por módulo. Falha em qualquer módulo abaixo de 85% quebra o CI.

### verificar_dependencias.py

Verifica vulnerabilidades (`pip audit`) e roda a suíte de testes (`pytest`). Recomendado antes de commit ou deploy.

```bash
python scripts/verificar_dependencias.py
python scripts/verificar_dependencias.py --cov        # testes com cobertura
python scripts/verificar_dependencias.py --no-audit   # só testes
python scripts/verificar_dependencias.py --no-tests   # só pip audit
```

### criar_usuario.py

Cria usuários no sistema (solicitante, supervisor, admin) de forma interativa. Use após configurar o Firebase e o `.env`.

```bash
python scripts/criar_usuario.py
```

### promover_admin_global.py

Promove um usuário existente ao perfil `admin_global` (acesso total + rotas exclusivas).

```bash
python scripts/promover_admin_global.py
```

### gerar_vapid_keys.py

Gera chaves VAPID para Web Push (notificações no navegador). Copie a saída para o `.env` como `VAPID_PUBLIC_KEY` e `VAPID_PRIVATE_KEY`.

```bash
python scripts/gerar_vapid_keys.py
```

### gerar_chave_criptografia.py

Gera uma chave Fernet para criptografia dos campos PII `nome` e `email` em repouso (LGPD / CWI 2.3). Copie a linha gerada para o `.env` como `ENCRYPTION_KEY`. Para ativar: `ENCRYPT_PII_AT_REST=true`.

```bash
python scripts/gerar_chave_criptografia.py
```

Ver [ADR-001](../docs/adr/001-criptografia-pii-fernet.md) e `docs/ENV.md` para o procedimento completo de ativação.

### migrar_pii_criptografia.py

Criptografa `nome` e `email` dos usuários existentes com Fernet e grava `email_lookup_hash` (sha256). Idempotente: pula docs já migrados.

**Pré-requisito (antes de `--apply` em produção):** criar índice single-field em `email_lookup_hash` no Firestore.

```bash
python scripts/migrar_pii_criptografia.py              # dry-run: lista o que seria migrado
ENCRYPT_PII_AT_REST=true ENCRYPTION_KEY=<chave> \
  python scripts/migrar_pii_criptografia.py --apply    # criptografa e persiste
```

Flags:
- `--dry-run` (padrão): lista documentos sem alterar
- `--apply`: executa migração (exige `ENCRYPT_PII_AT_REST=true` + `ENCRYPTION_KEY` válida)

### init_categorias.py

Inicializa categorias padrão no Firestore (setores, gates, impactos) se o banco estiver vazio. Use na primeira configuração do projeto.

```bash
python scripts/init_categorias.py
```

### migrar_setores_catalogo.py

Sincroniza o catálogo de setores no Firestore de forma **idempotente**. Substitui o antigo `atualizar_firebase.py`.
Padrão: **dry-run** — não grava nada sem `--apply`.

```bash
python scripts/migrar_setores_catalogo.py             # dry-run (seguro, apenas lista)
python scripts/migrar_setores_catalogo.py --apply     # grava de verdade
```

Após `--apply`, um checkpoint JSON é gravado em `scripts/.checkpoints/migrar_setores_<ts>_<fase>.json`
com as stats de cada fase (catálogo / chamados / usuários). Em caso de falha parcial, verifique
os checkpoints para saber quais fases foram concluídas e execute novamente — as operações são
idempotentes (re-executar é seguro). **Não há rollback automático**; para desfazer manualmente,
use o console do Firestore ou restaure um backup do projeto.

### migrar_gates_subetapas.py / migrar_grupos_rl.py / migrar_campo_senha.py

Migrações one-shot com dry-run obrigatório. Execute primeiro sem flag para revisar, depois com `--apply`.

```bash
python scripts/migrar_gates_subetapas.py              # dry-run (seguro, apenas lista)
python scripts/migrar_gates_subetapas.py --apply      # grava de verdade

python scripts/migrar_grupos_rl.py                    # dry-run (seguro, apenas lista)
python scripts/migrar_grupos_rl.py --apply            # grava de verdade

python scripts/migrar_campo_senha.py
```

**Detalhes de `--apply`:**
- `migrar_gates_subetapas.py`: usa `batch.set()` em chunks ≤500 ops (sem `gate.save()` individual). Checkpoint gravado em `scripts/.checkpoints/migrar_gates_<ts>_gates.json`.
- `migrar_grupos_rl.py`: usa `batch.update()` em chunks ≤500 ops (sem `document().update()` individual); itera chamados com cursor `limit/start_after` (sem carregar tudo em memória). Checkpoint gravado em `scripts/.checkpoints/migrar_grupos_rl_<ts>_grupos_rl.json`.
- `migrar_setores_catalogo.py`: todos os campos (`catalogo`, `chamados`, `usuarios`) usam batch. Checkpoints em `scripts/.checkpoints/migrar_setores_<ts>_<fase>.json`.

Os arquivos de checkpoint são **artefatos locais de execução** (não versionados — `scripts/.checkpoints/` está no `.gitignore`). Em caso de falha parcial, verifique quais fases têm checkpoint para saber o que já foi concluído; re-executar é seguro (operações idempotentes). **Não há rollback automático**; para desfazer, use o console do Firestore ou restaure um backup.

### atualizar_traducoes_setores.py

Atualiza as traduções (pt/en/es) dos setores já cadastrados no Firestore.

```bash
python scripts/atualizar_traducoes_setores.py
```

### reset_ranking_semanal.py

Zera o campo `exp_semanal` de todos os usuários via `GamificationService.resetar_ranking_semanal()`.

**Execução automática:** o APScheduler dispara o reset todo domingo às 23h59 BRT (job `reset_ranking_semanal` em `app/__init__.py`), protegido por distributed lock Redis (`scheduler_lock.py`). Este script é útil para execução manual (manutenção, desenvolvimento, testes).

```bash
python scripts/reset_ranking_semanal.py           # pede confirmação interativa
python scripts/reset_ranking_semanal.py --force   # pula confirmação (CI/cron manual)
```

### limpar_contadores_uso.py

Remove documentos da coleção `contadores_uso` (Firestore) com mais de N dias de acordo com a política de retenção de 90 dias.

**Execução automática:** o APScheduler dispara a limpeza todo domingo às 02h00 BRT (job `limpar_contadores_uso` em `app/__init__.py`), protegido por distributed lock Redis (`scheduler_lock.py`).

```bash
python scripts/limpar_contadores_uso.py              # dry-run: lista docs que seriam removidos
python scripts/limpar_contadores_uso.py --apply      # deleta documentos > 90 dias
python scripts/limpar_contadores_uso.py --dias 30    # retenção customizada (30 dias)
python scripts/limpar_contadores_uso.py --apply --dias 30
```

**Armadilha:** sem `--apply`, o script nunca deleta nada. O batch Firestore opera em lotes de ≤500 ops; coleções grandes são processadas em múltiplos commits.

### migrar_setor_area.py

Semeia o documento `config/setor_para_area` no Firestore com o campo `mapa` (setor → área). Necessário para que `utils_areas.setor_para_area()` use o Firestore como fonte de verdade em vez do dicionário hardcoded (F-30).

Padrão: **dry-run** — exibe o payload sem escrever nada.

```bash
python scripts/migrar_setor_area.py          # dry-run: mostra o que seria gravado
python scripts/migrar_setor_area.py --apply  # grava config/setor_para_area no Firestore
```

**Ordem de deploy recomendada:**
1. Fazer deploy do código (app já usa fallback estático se o doc não existir)
2. Executar `--apply` para semear o Firestore
3. O cache se aquece automaticamente no próximo request (`TTL 5 min`)

**Após editar o mapa no Firestore** (via console ou script), o cache expira em até 5 minutos. Para flush imediato (por processo):
```python
from app.utils_areas import invalidar_cache_setor_area
invalidar_cache_setor_area()
```

Após `--apply`, um checkpoint JSON é gravado em `scripts/.checkpoints/migrar_setor_area_<ts>_gravar_mapa.json`.

> **Referência:** `docs/plans/adr-f30-setor-para-area.md`

### migrar_usuarios_ativo.py

Backfill do campo `ativo` em documentos de usuários criados antes da Onda 2 (desativação de contas).
Documentos sem o campo são interpretados como `ativo=true` pelo código (retrocompatibilidade via `data.get("ativo", True)`),
mas a migração garante que o campo exista explicitamente no Firestore.

Padrão: **dry-run** — não grava nada sem `--apply`.

```bash
python scripts/migrar_usuarios_ativo.py           # dry-run: lista o que seria atualizado
python scripts/migrar_usuarios_ativo.py --apply   # grava ativo=true nos docs sem o campo
```

**Evidência dry-run (2026-06-22):** 7 documentos identificados sem campo `ativo` — todos usuários legados.
Operação idempotente: docs que já têm o campo (true ou false) são pulados (`[SKIP]`).

> **Referência:** `app/models_usuario.py` — campo `ativo`; `app/routes/auth.py:79–83` — bloqueio de login; `app/__init__.py:87–90` — invalidação de sessão ativa via `user_loader`.

### migrar_supervisor_ids_com_acesso.py

Backfill do campo `supervisor_ids_com_acesso` em chamados criados antes da Fase 2 (isolamento por supervisor).
Chamados sem esse campo **não aparecem no dashboard** do supervisor após o deploy da Fase 2 — a migração é **obrigatória**.

Padrão: **dry-run** — não grava nada sem `--apply`. Idempotente: chamados já com o campo calculado corretamente são pulados (`[OK]`).

```bash
# Staging/Produção — verificar o que seria atualizado antes de gravar
python scripts/migrar_supervisor_ids_com_acesso.py --dry-run

# Aplicar — executa em batches de 500 (seguro para coleções grandes)
python scripts/migrar_supervisor_ids_com_acesso.py --apply
```

**Ordem de deploy recomendada (Fase 2):**
1. Fazer deploy do código com as alterações da Fase 2
2. Executar `--dry-run` no ambiente alvo para estimar volume
3. Executar `--apply` para backfill dos chamados legados
4. Confirmar no console Firestore que chamados legados têm o campo preenchido

> **Referência:** `app/services/permissions.py` — `calcular_supervisor_ids_com_acesso()`; `app/routes/api.py` — `_aplicar_filtro_perfil()` query `array_contains`; `docs/adr/004-escalonamento-sla-gerencial.md` — ADR-004 Fase 2.

### migrar_participantes.py

Backfill do campo `participantes[]` em chamados que usavam o modelo legado `setores_adicionais` (lista de strings).
A migração converte cada entrada de `setores_adicionais` num objeto `{supervisor_id, area, status: "pendente", concluido_em: null}`, buscando o supervisor responsável da área no Firestore.

Padrão: **dry-run** — não grava nada sem `--apply`. Idempotente: chamados já com `participantes[]` preenchido são pulados.

```bash
# Verificar o que seria migrado (seguro, somente leitura)
python scripts/migrar_participantes.py

# Aplicar — gravar participantes[] nos chamados sem o campo
python scripts/migrar_participantes.py --apply
```

**Ordem de deploy recomendada (Fase 4):**
1. Fazer deploy do código com as alterações da Fase 4
2. Executar sem `--apply` para estimar volume e revisar o mapeamento
3. Executar `--apply` para backfill
4. Confirmar no console Firestore que chamados legados têm `participantes[]` preenchido

> **Referência:** `docs/adr/004-escalonamento-sla-gerencial.md` (decisão dual-path `setores_adicionais` vs `participantes[]`); `docs/evidencias/FASE4_DOD_EVIDENCIA.md`.

### verificar_supervisores.py / resumo_supervisores.py

Diagnóstico: listam supervisores e suas áreas no Firestore.

```bash
python scripts/verificar_supervisores.py
python scripts/resumo_supervisores.py
```

### gerar_email_visual_snapshots.py / disparar_testes_emails_visual_uat.py

`gerar_email_visual_snapshots.py` renderiza os templates de e-mail em HTML local
(não envia nada). `disparar_testes_emails_visual_uat.py` envia e-mails reais de UAT
via Microsoft Graph API — **use com cuidado** e com destinatários de teste.

```bash
python scripts/gerar_email_visual_snapshots.py
python scripts/disparar_testes_emails_visual_uat.py
```

### testar_email_smtp.py

Diagnóstico **legado** de envio via SMTP. A produção usa exclusivamente a
Microsoft Graph API; mantido apenas para testes pontuais de conectividade SMTP.

```bash
python scripts/testar_email_smtp.py
python scripts/testar_email_smtp.py destino@exemplo.com
```

### apagar_todos_chamados.py

**Cuidado:** apaga **todos** os chamados e o histórico associado do Firestore. Use apenas em desenvolvimento ou para reset completo. Exige confirmação interativa (ou `--confirm`).

```bash
python scripts/apagar_todos_chamados.py
python scripts/apagar_todos_chamados.py --confirm
```

### atualizar_firebase.py / atualizar_setores_from_print.py (destrutivos)

Scripts **destrutivos e legados** que apagam e recriam coleções de categorias.
Por padrão rodam em **dry-run** (nenhuma alteração). Use `--apply` para gravar.
Prefira `migrar_setores_catalogo.py` para sincronização de setores.

```bash
python scripts/atualizar_firebase.py            # dry-run (seguro)
python scripts/atualizar_firebase.py --apply    # grava de verdade
python scripts/atualizar_setores_from_print.py            # dry-run
python scripts/atualizar_setores_from_print.py --apply    # grava
```
