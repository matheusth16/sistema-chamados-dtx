# Plano de Sprint — Sistema de Chamados DTX Aerospace

| Campo | Valor |
|---|---|
| **Documento** | Plano de Sprint — Pós-Auditoria 2026-06-17 (3ª Rodada + revisão) |
| **Versão** | 3.2 |
| **Data de criação** | 2026-06-16 |
| **Última revisão** | 2026-06-19 |
| **Período** | 2026-06-17 a 2026-07-25 (6 semanas) |
| **Status** | **Sprint + Onda A + Onda B + Onda C wave 1 + Onda C wave 2 + Onda C wave 3 concluídos (2026-06-19)** — **82/82 achados resolvidos**; 0 em backlog |
| **Autor** | DTX Aerospace — Engenharia de Software |

---

## Índice

1. [Objetivo do Sprint](#1-objetivo-do-sprint)
2. [Critérios de conclusão (Definition of Done)](#2-critérios-de-conclusão-definition-of-done)
3. [Semana 0 — Quick Fixes Triviais (1 dia)](#3-semana-0--quick-fixes-triviais-1-dia)
4. [Semana 1 — Segurança e P0 críticos (Rodada 1 + novos)](#4-semana-1--segurança-e-p0-críticos)
5. [Semana 2 — Race conditions e segurança Rodada 2 (P0/P1)](#5-semana-2--race-conditions-e-segurança-rodada-2)
6. [Semana 3 — Cobertura de testes e P1 frontend](#6-semana-3--cobertura-de-testes-e-p1-frontend)
7. [Semana 4 — Confiabilidade, performance e Quick wins](#7-semana-4--confiabilidade-performance-e-quick-wins)
8. [Semana 4.5 — CSS e Design System](#8-semana-45--css-e-design-system)
9. [Semana 5 — Documentação e CI](#9-semana-5--documentação-e-ci)
10. [Tabela mestre de itens](#10-tabela-mestre-de-itens)
11. [Riscos do sprint e mitigações](#11-riscos-do-sprint-e-mitigações)
12. [Fora do escopo](#12-fora-do-escopo)

---

## 1. Objetivo do Sprint

Endereçar todos os 82 achados identificados nas três rodadas de auditoria técnica (F-01 a F-82), priorizando os oito riscos de segurança ativos em produção. **Resultado (2026-06-19):** Grupos 0–7 + F-81 + Onda A + Onda B + Onda C wave 1 + Onda C wave 2 + Onda C wave 3 concluídos — zero achados abertos; **82/82 achados resolvidos**; **1183 testes** passando; documentação operacional sincronizada.

---

## Status do sprint (snapshot 2026-06-18)

| Grupo | Escopo | Status |
|---|---|---|
| **0** | Quick fixes (F-50, F-51, F-52, F-53, F-78, F-70) | ✅ Concluído |
| **1** | Segurança P0/P1 (F-01, F-03, F-04, F-05, F-09, F-71, F-72) | ✅ Concluído |
| **2** | Race conditions + HTML injection (F-13, F-14, F-15, F-16, F-33) | ✅ Concluído |
| **3** | Cobertura upload/notifications + i18n JS + mocks (S3-01 a S3-08) | ✅ Concluído |
| **4** | Confiabilidade APScheduler, ranking, cache, WebPush (S4-01 a S4-10) | ✅ Concluído |
| **4.5** | Design system CSS (F-64 a F-67) | ✅ Concluído |
| **5** | Documentação operacional (S5-01 a S5-11) | ✅ Concluído |
| **7** | Sincronização docs principais + README | ✅ Concluído |
| **Onda A** | F-20, F-23, F-25, F-26, F-29, F-58, F-59, F-61, F-63 | ✅ Concluído 2026-06-18 |
| **Fase 0** | F-69 (em uso), F-76 (dotenv presente), F-82 (já fechado) | ✅ Concluído 2026-06-18 |
| **Onda B** | F-24 (N+1 report), F-22 (cache gates), F-21 (round-robin Redis) | ✅ Concluído 2026-06-18 |
| **Onda C wave 1** | F-75 (scripts dry-run/batch), F-48 (handlers inline CSP), F-60 (tour step invariants) | ✅ Concluído 2026-06-18 |
| **Onda C wave 2** | F-31 (cleanup contadores_uso), F-41 (dedup CSS JS), F-68 (tokens de borda CSS) | ✅ Concluído 2026-06-19 |
| **Onda C wave 3** | ~~F-30~~ (SETOR_PARA_AREA → Firestore) | ✅ Concluído 2026-06-19 |
| **F-81** | A/B test formulário (`ab_service.py`, variante B no `formulario.html`) | ✅ Concluído 2026-06-18 |
| **Onda 1** | 6 módulos baseline → ≥85% | ✅ Concluído 2026-06-19 |
| **Onda 2** | 3 módulos segurança → ≥85% | ✅ Concluído 2026-06-19 |
| **Onda 3** | analytics.py 64%→94%, dashboard.py 69%→93% | ✅ Concluído 2026-06-19 |
| **Onda 4** | database.py 52%→100%, __init__.py 72%→98%; ADR | ✅ Concluído 2026-06-22 |
| **Gate Final** | i18n fix (pt_BR padrão), CI 85%, docs sync | ✅ Concluído 2026-06-22 |

### Melhorias de produto (`melhorias-sprint.md`)

| Feature | Descrição | Status |
|---|---|---|
| 1 | Multi-anexo ao adicionar em chamado existente (`anexos_novos`, loop em `edicao_chamado_service.py`) | ✅ Implementado |
| 2 | Anti-self-ticket — bloqueio de responsável = solicitante (`chamados_criacao_service.py`) | ✅ Implementado |
| 3 | E-mail via Microsoft Graph API (substitui Brevo/SMTP) | ✅ Implementado 2026-06-17 |
| AB-001 | A/B test descrição do chamado (`ab_service.py`, experimento AB-001) | ✅ Implementado 2026-06-18 (F-81) |

---

## 2. Critérios de conclusão (Definition of Done)

Um item é considerado **concluído** quando:

- [x] O código foi escrito e passa nos testes relacionados
- [x] `ruff check app/ tests/ --fix` — zero erros novos introduzidos
- [x] `bandit -r app/ -ll` — zero High, zero Medium novos
- [x] `pytest --tb=short -q` — todos os testes passando (**1435 testes**, 2026-06-22)
- [x] Cobertura geral ≥ 85% (gate do CI) — **94,98%**; `python scripts/check_coverage_per_module.py` — **52/52 OK**
- [ ] Commit com mensagem no formato Conventional Commits *(por item, conforme merge)*
- [x] O achado correspondente (F-XX) foi marcado como "Resolvido" em `docs/CHECKLIST_SEGURANCA.md` *(82/82 — **0 em backlog**)*

---

## 3. Semana 0 — Quick Fixes Triviais (1 dia)

**Período:** 2026-06-17 (1 dia)
**Foco:** Resolver todos os itens triviais em uma sessão única antes de iniciar o trabalho pesado. Esforço total estimado: menos de 1 hora.

**Critério de aceite geral:** `pytest --tb=short -q` passa sem warnings nos arquivos alterados; nenhum arquivo legado permanece ativo no diretório principal; `dist/` consta no `.gitignore`.

---

### Tarefa S0-01 — Corrigir tautologia em `test_i18n.py:29` (F-50)

**Arquivo:** `tests/test_i18n.py:29`
**Esforço:** XS (15 min)

O assert atual é uma tautologia lógica e nunca falha, tornando o teste inútil:

```python
# ANTES — sempre True
assert result != "back" or result == "back"

# DEPOIS — assert com semântica real
assert result == "voltar"
```

**Critério de aceite:** `pytest tests/test_i18n.py` passa e o assert detecta regressão se o valor mudar.

---

### Tarefa S0-02 — Corrigir URLs E2E `/relatorios` → `/admin/relatorios` (F-51/52)

**Arquivos:**
- `tests/e2e/test_fluxo_supervisor.py:34,60`
- `tests/e2e/test_fluxo_admin.py:53`

**Esforço:** XS (10 min)

```python
# ANTES
response = client.get('/relatorios')

# DEPOIS
response = client.get('/admin/relatorios')
```

Aplicar a mesma correção nas três ocorrências indicadas.

**Critério de aceite:** Os testes E2E de relatórios passam sem 404.

---

### Tarefa S0-03 — Marcar `tests/e2e/test_solicitante.py` como legado (F-53)

**Arquivo:** `tests/e2e/test_solicitante.py`
**Esforço:** XS (5 min)

O arquivo é legado e conflita com os testes atuais. Duas opções, em ordem de preferência:

1. Remover o arquivo se o conteúdo estiver completamente coberto pelos demais testes E2E.
2. Caso contenha algum caso único, adicionar `@pytest.mark.skip(reason="legado — substituído por test_fluxo_solicitante.py")` em cada função de teste.

**Critério de aceite:** `pytest tests/e2e/` não executa nenhum teste do arquivo legado.

---

### Tarefa S0-04 — Mover `confirmacao-solicitante.md` para `docs/plans/` (F-78)

**Arquivo atual:** `confirmacao-solicitante.md` (raiz do projeto)
**Destino:** `docs/plans/confirmacao-solicitante.md`
**Esforço:** XS (2 min)

```bash
git mv confirmacao-solicitante.md docs/plans/confirmacao-solicitante.md
```

Verificar se há referências ao caminho antigo em outros documentos e atualizar.

**Critério de aceite:** Nenhum arquivo de plano na raiz do repositório; `docs/plans/` organizado.

---

### Tarefa S0-05 — Adicionar `app/static/dist/` ao `.gitignore` (F-70)

**Arquivo:** `.gitignore`
**Esforço:** XS (2 min)

```
# Build artifacts — Tailwind CSS
app/static/dist/
```

Se `app/static/dist/` já estiver rastreado pelo git, remover do índice sem apagar os arquivos:

```bash
git rm -r --cached app/static/dist/
```

**Critério de aceite:** `git status` não lista arquivos dentro de `app/static/dist/` após build.

---

## 4. Semana 1 — Segurança e P0 críticos

**Período:** 2026-06-18 a 2026-06-21
**Foco:** Corrigir vulnerabilidades urgentes da Rodada 1, verificar billing GCP e proteger scripts de migração destrutivos.

---

### Tarefa S1-01 — Corrigir IP spoofing em `get_client_ip()` (P0)

**Achado relacionado:** F-01
**Arquivo:** `app/utils.py:96–106`
**Esforço:** S (menos de 4 horas)

O problema está na função `get_client_ip()` que confia cegamente no cabeçalho `X-Forwarded-For`. Qualquer cliente pode forjar esse cabeçalho e burlar o lockout de brute-force.

A correção é usar `ProxyFix` do Werkzeug, que só aceita o número correto de proxies confiáveis:

```python
# app/__init__.py — adicionar após criar a instância Flask
from werkzeug.middleware.proxy_fix import ProxyFix

def create_app(config=None):
    app = Flask(__name__)
    # ... configurações ...

    # Configura ProxyFix para proxy reverso (1 hop)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # ... resto da factory ...
```

Depois, simplificar `get_client_ip()` em `app/utils.py`:

```python
# app/utils.py
def get_client_ip() -> str:
    """Retorna o IP real do cliente após ProxyFix processar os headers."""
    return request.remote_addr or '0.0.0.0'
```

**Critério de aceite:** Teste de brute-force simulado com `X-Forwarded-For` forjado não burla o lockout.

---

### Tarefa S1-02 — Substituir `datetime.utcnow()` (P1)

**Achado relacionado:** F-04
**Arquivo:** `app/services/analytics.py:87, 216`
**Esforço:** S (menos de 1 hora)

```python
# ANTES (app/services/analytics.py:87 e 216 — dois locais)
agora = datetime.utcnow()

# DEPOIS
from datetime import datetime, timezone
agora = datetime.now(timezone.utc)
```

---

### Tarefa S1-03 — Remover `print()` de `models_historico.py:86` (P1)

**Achado relacionado:** F-05
**Arquivo:** `app/models_historico.py:85, 143`
**Esforço:** S (menos de 30 minutos)

```python
# ANTES (linhas 85 e 143 — dois locais com print de erro)
print(f"Erro ao salvar histórico: {e}")
# e em 143: print(f"Erro ao buscar histórico: {e}")

# DEPOIS — substituir por logging estruturado
import logging
logger = logging.getLogger(__name__)
logger.debug("Historico salvo: %s", self.id)
```

---

### Tarefa S1-04 — Corrigir supressão bandit incorreta (P2)

**Achado relacionado:** F-03
**Arquivo:** `app/services/translation_service.py:27`
**Esforço:** S (menos de 30 minutos)

```python
# ANTES (translation_service.py:27)
resultado = urllib.request.urlopen(url)  # noqa: S310

# DEPOIS — verificar se a chamada é realmente segura, então:
resultado = urllib.request.urlopen(url)  # nosec B310 — URL validada pelo caller
```

---

### Tarefa S1-05 — Corrigir `run.py` para usar `0.0.0.0` em não-debug (P3)

**Achado relacionado:** F-09
**Arquivo:** `run.py:27`
**Esforço:** S (menos de 30 minutos)

```python
# DEPOIS
if app.debug:
    app.run(host='127.0.0.1', port=5000, debug=True)
else:
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
```

---

### Tarefa S1-06 — Verificar alerta de billing GCP vencido (P0 Imediato)

**Achado relacionado:** F-40
**Arquivo:** `docs/INCIDENT_RUNBOOK.md:138`
**Esforço:** S (investigação — menos de 1 hora)

O INCIDENT_RUNBOOK.md linha 138 contém um aviso de que o billing do GCP seria desativado em 19/06/2026 — prazo já vencido. O projeto Firebase/Firestore pode estar vinculado à conta GCP com billing. Firestore sem billing ativo pode parar de funcionar.

**O que fazer:**
1. Acessar [console.cloud.google.com](https://console.cloud.google.com)
2. Verificar se o projeto Firebase ainda tem billing ativo
3. Verificar se Firestore está respondendo normalmente em produção
4. Resolver qualquer pendência de billing antes de qualquer interrupção de serviço

**Critério de aceite:** Firestore operacional confirmado; billing verificado e documentado.

---

### Tarefa S1-07 — Adicionar dry-run e flag `--apply` em `atualizar_firebase.py` (P1)

**Achado relacionado:** F-71
**Arquivo:** `scripts/atualizar_firebase.py`
**Esforço:** S (menos de 2 horas)

O script atualiza documentos no Firestore sem qualquer confirmação, tornando execuções acidentais destrutivas e irreversíveis. Duas abordagens válidas, em ordem de preferência:

**Opção A — Adicionar prompt e flag `--apply`:**
```python
#!/usr/bin/env python
"""
ATENÇÃO: Este script modifica dados no Firestore em produção.
Por padrão executa em modo DRY-RUN (somente leitura).
Use --apply para efetuar as alterações reais.
"""
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--apply', action='store_true',
                    help='Efetua alterações reais (padrão: dry-run)')
args = parser.parse_args()

if args.apply:
    print("[AVISO] Modo APPLY ativo — alterações serão gravadas no Firestore.")
else:
    print("[INFO] Modo DRY-RUN — nenhuma alteração será gravada.")

# ... lógica do script, checando `args.apply` antes de cada escrita
```

**Opção B — Marcar como obsoleto:**
Se o script foi substituído por `migrar_setores_catalogo.py`, adicionar no topo do arquivo:
```python
"""
OBSOLETO: Este script foi substituído por scripts/migrar_setores_catalogo.py
Não executar em produção sem revisar o código e confirmar a necessidade.
"""
raise SystemExit("Script obsoleto. Use migrar_setores_catalogo.py")
```

**Critério de aceite:** Execução sem `--apply` não modifica nenhum documento no Firestore; ou o script exibe erro imediato indicando obsolescência.

---

### Tarefa S1-08 — Adicionar dry-run e flag `--apply` em `atualizar_setores_from_print.py` (P1)

**Achado relacionado:** F-72
**Arquivo:** `scripts/atualizar_setores_from_print.py`
**Esforço:** S (menos de 1 hora)

Aplicar o mesmo tratamento da S1-07: adicionar prompt de confirmação com flag `--apply` (dry-run como padrão), ou marcar como obsoleto com aviso explícito no header do arquivo.

**Critério de aceite:** Mesmo critério da S1-07.

---

## 5. Semana 2 — Race conditions e segurança Rodada 2 (P0/P1)

**Período:** 2026-06-24 a 2026-06-28
**Foco:** Race conditions (F-13, F-14), HTML injection (F-15), lock de traduções (F-16), modal de cancelamento (F-33).

---

### Tarefa S2-01 — Corrigir race condition em `contadores_uso.py` (P0)

**Achado relacionado:** F-13
**Arquivo:** `contadores_uso.py:43-54`
**Esforço:** S (menos de 4 horas)

O problema é um padrão read-then-write sem transação. Dois requests simultâneos leem o mesmo valor antes de qualquer escrita, e ambos passam no limite.

```python
# ANTES — padrão inseguro (read-then-write)
doc = db.collection('contadores_uso').document(chave).get()
atual = doc.to_dict().get('count', 0) if doc.exists else 0
if atual >= limite:
    return False
db.collection('contadores_uso').document(chave).set({'count': atual + 1}, merge=True)

# DEPOIS — usar transação Firestore
@db.transaction
def incrementar_com_transacao(transaction, ref, limite):
    snapshot = ref.get(transaction=transaction)
    atual = snapshot.to_dict().get('count', 0) if snapshot.exists else 0
    if atual >= limite:
        raise Exception('limite_atingido')
    transaction.set(ref, {'count': atual + 1}, merge=True)
    return True
```

Alternativamente, usar `Increment()` atômico para o incremento (verificando o limite em leitura separada com tempo de janela aceitável).

**Critério de aceite:** Teste de concorrência simulada com 10 requests simultâneos não ultrapassa o limite configurado.

---

### Tarefa S2-02 — Corrigir race condition em `gamification_service.py` (P0)

**Achado relacionado:** F-14
**Arquivo:** `gamification_service.py:79-98`
**Esforço:** S (menos de 4 horas)

```python
# ANTES — read-then-write sem transação
doc = db.collection('usuarios').document(uid).get()
dados = doc.to_dict()
nova_exp = dados.get('exp_total', 0) + quantidade
db.collection('usuarios').document(uid).update({'exp_total': nova_exp})

# DEPOIS — Increment() atômico
from google.cloud.firestore_v1 import Increment

db.collection('usuarios').document(uid).update({
    'exp_total': Increment(quantidade),
    'exp_semanal': Increment(quantidade)
})
```

Se a lógica de nível precisar do valor total, usar uma transação para leitura + escrita.

**Critério de aceite:** Teste com 20 requests simultâneos de +10 EXP resulta em exatamente +200 EXP total (sem perda ou duplicação).

---

### Tarefa S2-03 — ~~Corrigir HTML injection em `report_service.py` (P0)~~ ✅ CONCLUÍDO 2026-06-16

**Achado relacionado:** F-15
**Arquivo:** `report_service.py:165-175`
**Esforço:** XS (realizado como parte da verificação de segurança)

A função `_tabela_html` inseria `categoria`, `tipo`, `solicitante` e `data_abertura_fmt` diretamente
no HTML sem escapar. Corrigido com `from html import escape` e `escape(str(c["campo"]))` em todos
os campos provenientes de entrada do usuário.

**Nota:** `email_templates.py` (notificações individuais) já usava `_html()` com `html.escape()` —
estava seguro. O problema era exclusivamente no relatório semanal agendado (`report_service.py`).

**Critério de aceite:** ✅ Um chamado com categoria `<script>alert('xss')</script>` gera e-mail
com o tag escapado (`&lt;script&gt;...`), sem execução de código.

---

### Tarefa S2-04 — Adicionar threading.Lock em `TRANSLATION_MAP` (P1)

**Achado relacionado:** F-16
**Arquivo:** `translation_service.py:147, 186`
**Esforço:** S (menos de 2 horas)

```python
# translation_service.py — adicionar no topo do módulo
import threading

_translation_map_lock = threading.Lock()
TRANSLATION_MAP: dict = {}

# Nas funções que escrevem no dict:
def atualizar_traducao(chave: str, valor: dict) -> None:
    with _translation_map_lock:
        TRANSLATION_MAP[chave] = valor

# Nas funções que leem (snapshot para evitar segurar lock muito tempo):
def obter_traducao(chave: str) -> dict | None:
    with _translation_map_lock:
        return TRANSLATION_MAP.get(chave)
```

**Critério de aceite:** Teste de estresse com 50 threads simultâneas lendo e escrevendo não gera `RuntimeError: dictionary changed size during iteration`.

---

### Tarefa S2-05 — Substituir `window.prompt()` por modal acessível (P1)

**Achado relacionado:** F-33
**Arquivo:** `dashboard_otimizacoes.js:102`
**Esforço:** M (1 a 2 dias — inclui HTML e JS)

```javascript
// ANTES (dashboard_otimizacoes.js:102)
const motivo = window.prompt('Informe o motivo do cancelamento:');
if (!motivo) return;

// DEPOIS — abrir modal HTML e aguardar confirmação
function abrirModalCancelamento(chamadoId) {
    const modal = document.getElementById('modal-cancelamento');
    modal.dataset.chamadoId = chamadoId;
    modal.showModal();  // usa <dialog> nativo (acessível)
}
```

Template do modal (adicionar em `dashboard.html` ou `base.html`):

```html
<dialog id="modal-cancelamento" aria-labelledby="modal-cancelamento-titulo">
  <h2 id="modal-cancelamento-titulo">{{ t('cancelar_chamado') }}</h2>
  <label for="motivo-cancelamento">{{ t('motivo_cancelamento') }}</label>
  <textarea id="motivo-cancelamento" required></textarea>
  <div>
    <button type="button" id="btn-confirmar-cancelamento">{{ t('confirmar') }}</button>
    <button type="button" onclick="this.closest('dialog').close()">{{ t('voltar') }}</button>
  </div>
</dialog>
```

**Critério de aceite:** Cancelamento funciona sem `window.prompt`; modal abre e fecha corretamente; leitor de tela NVDA/VoiceOver consegue navegar e confirmar o cancelamento.

---

## 6. Semana 3 — Cobertura de testes e P1 frontend

**Período:** 2026-07-01 a 2026-07-05
**Foco:** Elevar cobertura de `upload.py` (47% → 80%) e `notifications.py` (53% → 80%); corrigir strings hardcoded no JS; corrigir mocks inertes e asserts permissivos.

---

### Tarefa S3-01 — Testes de `upload.py` (P1)

**Achado relacionado:** F-06
**Arquivo de produção:** `app/services/upload.py`
**Arquivo de teste:** `tests/test_services/test_upload.py` (criar/expandir)
**Esforço:** M (1 a 2 dias)

Casos de teste a implementar: upload R2 (sucesso, falha, sem credenciais), upload Firebase Storage (sucesso, não inicializado), fallback disco (sucesso, sem permissão, nome especial), função principal `salvar_anexo` com cadeia completa e validação de magic bytes.

**Meta:** Passar de 47% para ≥ 80% de cobertura em `upload.py`.

---

### Tarefa S3-02 — Testes de `notifications.py` (P1)

**Achado relacionado:** F-07
**Arquivo de produção:** `app/services/notifications.py`
**Arquivo de teste:** `tests/test_services/test_notifications.py` (criar/expandir)
**Esforço:** M (1 a 2 dias)

Casos de teste a implementar: envio via Graph API (sucesso, erro 401 credenciais inválidas, erro 429 rate limit, vars não configuradas → log warning sem envio), notificação de setores adicionais (múltiplos, lista vazia, supervisor sem e-mail), retry com backoff (`notify_retry.py`), template HTML de e-mail (`email_templates.py` — geração correta de HTML).

**Meta:** Passar de 53% para ≥ 80% de cobertura em `notifications.py`.

---

### Tarefa S3-03 — Corrigir strings hardcoded em `dashboard_otimizacoes.js` (P1)

**Achados relacionados:** F-34, F-36, F-46
**Arquivo:** `dashboard_otimizacoes.js:13-23, 87, 132`
**Esforço:** S (menos de 4 horas)

```javascript
// ANTES — hardcoded em PT-BR
const MSGS = {
    cancelando: 'Cancelando...',
    erro_status: 'Erro ao atualizar status.',
    // ...
};
const statusValidos = ['Aberto', 'Em Atendimento', 'Concluído', 'Cancelado'];
const URL_STATUS = '/api/atualizar-status';

// DEPOIS — injetado pelo template
const MSGS = window.DTX_MSGS || {};
const statusValidos = window.DTX_STATUS_VALIDOS || [];
const URL_STATUS = window.DTX_URLS?.atualizar_status || '/api/atualizar-status';
```

Adicionar em `base.html` (dentro de `<script>` antes dos scripts):

```html
<script>
window.DTX_MSGS = {
    cancelando: "{{ t('cancelando') }}",
    erro_status: "{{ t('erro_status') }}",
    tente_novamente: "{{ t('tente_novamente') }}"
};
window.DTX_STATUS_VALIDOS = {{ status_validos_json | tojson }};
window.DTX_URLS = {
    atualizar_status: "{{ url_for('main.atualizar_status') }}"
};
</script>
```

**Critério de aceite:** Em modo inglês (`?lang=en`), os textos de erro do dashboard aparecem em inglês.

---

### Tarefa S3-04 — Corrigir strings hardcoded em `table-filters.js` (P2)

**Achados relacionados:** F-37, F-38, F-44
**Arquivo:** `table-filters.js:39, 50, 114, 244, 249`
**Esforço:** S (menos de 2 horas)

- Substituir `'Filtrar'` e `'Todos'` por `window.DTX_MSGS.filtrar` e `window.DTX_MSGS.todos`
- Proteger `console.warn` por `if (window.DTX_DEBUG) console.warn(...)`
- Substituir `localeCompare('pt-BR')` por `localeCompare(window.DTX_LOCALE || 'pt-BR')`

---

### Tarefa S3-05 — Corrigir mock inerte em `test_api.py` e `test_regression_suite.py` (P1)

**Achado relacionado:** F-54
**Arquivos:**
- `tests/test_routes/test_api.py:20`
- `tests/test_regression/test_regression_suite.py:181`

**Esforço:** S (menos de 2 horas)

O patch `patch("app.routes.api.db")` é inerte porque as rotas importam o serviço inline; o `db` real já foi importado pelo módulo de serviço antes do patch ser aplicado.

```python
# ANTES — mock inerte
with patch("app.routes.api.db") as mock_db:
    ...

# DEPOIS — patch no módulo do serviço
with patch("app.services.edicao_chamado_service.db") as mock_db:
    ...
```

Verificar todos os patches em ambos os arquivos e aplicar o mesmo padrão aos demais serviços afetados.

**Critério de aceite:** O mock intercepta as chamadas ao Firestore; alterar o retorno do mock afeta o resultado do teste.

---

### Tarefa S3-06 — Corrigir asserts permissivos em `test_api_contract.py` (P1)

**Achado relacionado:** F-55
**Arquivo:** `tests/test_routes/test_api_contract.py`
**Esforço:** S (menos de 1 hora)

```python
# ANTES — aceita 404 como sucesso
assert response.status_code in (200, 404)

# DEPOIS — exige 200 explicitamente
assert response.status_code == 200
```

Revisar todas as ocorrências do padrão `status_code in (...)` no arquivo e substituir pelo assert exato esperado para cada rota.

**Critério de aceite:** Um teste que falha com 404 é detectado como falha, não como sucesso.

---

### Tarefa S3-07 — Corrigir assert `(404, 403)` em `test_api_status.py:93` (P1)

**Achado relacionado:** F-56
**Arquivo:** `tests/test_routes/test_api_status.py:93`
**Esforço:** XS (menos de 30 minutos)

```python
# ANTES
assert response.status_code in (404, 403)

# DEPOIS — definir qual é o comportamento esperado e testar apenas ele
assert response.status_code == 404
```

**Critério de aceite:** O teste testa exatamente um comportamento.

---

### Tarefa S3-08 — Adicionar `test_supervisor_pode_ver_relatorios` (P1)

**Achado relacionado:** F-57
**Arquivo:** `tests/test_routes/test_dashboard.py`
**Esforço:** S (menos de 2 horas)

O supervisor tem acesso à rota `/admin/relatorios` mas não há teste cobrindo esse cenário. Adicionar:

```python
def test_supervisor_pode_ver_relatorios(client_logado_supervisor):
    response = client_logado_supervisor.get('/admin/relatorios')
    assert response.status_code == 200

def test_solicitante_nao_pode_ver_relatorios(client_logado_solicitante):
    response = client_logado_solicitante.get('/admin/relatorios')
    assert response.status_code in (302, 403)
```

**Critério de aceite:** Teste passa e documenta o comportamento esperado de controle de acesso.

---

### Tarefa S3-09 — Setar campos de onboarding no `_usuario_mock()` de `conftest.py` (P1)

**Achado relacionado:** F-62
**Arquivo:** `tests/conftest.py`
**Esforço:** XS (menos de 30 minutos)

O mock de usuário não define os campos `onboarding_completo` e `onboarding_passo`, fazendo com que templates que acessam esses atributos lancem `AttributeError` em testes.

```python
def _usuario_mock(**kwargs):
    mock = MagicMock()
    mock.onboarding_completo = True   # evita injeção do tour em testes
    mock.onboarding_passo = 0
    # ... demais campos existentes ...
    for k, v in kwargs.items():
        setattr(mock, k, v)
    return mock
```

**Critério de aceite:** Nenhum teste lança `AttributeError` relacionado a `onboarding_completo`.

---

## 7. Semana 4 — Confiabilidade, performance e Quick wins

**Período:** 2026-07-08 a 2026-07-12
**Foco:** APScheduler com lock distribuído, cache, agendamento do reset de ranking, e quick wins de qualidade.

---

### Tarefa S4-01 — Redis distributed lock para APScheduler (P2)

**Achado relacionado:** F-02
**Arquivo:** `app/__init__.py:161–219`
**Esforço:** M (1 a 2 dias)

```python
def job_com_lock(nome_job, fn_job):
    """Wrapper que garante execução em apenas 1 worker via Redis lock."""
    redis_url = app.config.get('REDIS_URL')
    if not redis_url:
        fn_job()
        return
    import redis
    from redis.exceptions import LockError
    r = redis.from_url(redis_url)
    lock_key = f"scheduler_lock:{nome_job}"
    try:
        with r.lock(lock_key, timeout=300, blocking_timeout=0):
            fn_job()
    except LockError:
        app.logger.debug("Job %s já em execução em outro worker, pulando.", nome_job)
```

---

### Tarefa S4-02 — Agendar `reset_ranking_semanal` via APScheduler (P2)

**Achado relacionado:** F-27 (exp_semanal nunca zerado)
**Arquivo:** `app/__init__.py`
**Esforço:** S (menos de 2 horas)

```python
from app.services.gamification_service import resetar_ranking_semanal

scheduler.add_job(
    lambda: job_com_lock('reset_ranking_semanal', resetar_ranking_semanal),
    trigger='cron',
    day_of_week='sun',
    hour=23,
    minute=59,
    id='reset_ranking_semanal'
)
```

---

### Tarefa S4-03 — Usar `get_static_cached` em `dashboard.py:159` (P2)

**Achado relacionado:** F-12
**Arquivo:** `app/routes/dashboard.py:159`
**Esforço:** S (menos de 2 horas)

```python
# ANTES — full-scan a cada requisição
usuarios = Usuario.get_all()

# DEPOIS — cacheia por TTL (5 minutos)
from app.cache import get_static_cached
usuarios = get_static_cached(key='usuarios_todos', fn=Usuario.get_all, ttl=300)
```

---

### Tarefa S4-04 — Adicionar limite em `obter_inscricoes` WebPush (P2)

**Achado relacionado:** F-17
**Arquivo:** `webpush_service.py:69`
**Esforço:** S (menos de 1 hora)

```python
# ANTES — sem limite
inscricoes = db.collection('usuarios').document(uid)\
    .collection('push_subscriptions').stream()

# DEPOIS — limitar e logar se acima do esperado
MAX_INSCRICOES = 20
inscricoes_ref = db.collection('usuarios').document(uid)\
    .collection('push_subscriptions').limit(MAX_INSCRICOES)
```

---

### Tarefa S4-05 — Adicionar `@firebase_retry` em `CategoriaImpacto.save()` (P2 — Quick win)

**Achado relacionado:** F-19
**Arquivo:** `models_categorias.py:319`
**Esforço:** XS (menos de 30 minutos)

```python
# ANTES — sem retry
def save(self):
    db.collection('categorias_impacto').document(self.id).set(self.to_dict())

# DEPOIS — com retry (padrão das outras classes)
@firebase_retry
def save(self):
    db.collection('categorias_impacto').document(self.id).set(self.to_dict())
```

---

### Tarefa S4-06 — Corrigir `cor="#gray"` para valor CSS válido (Quick win)

**Achado relacionado:** F-28
**Arquivo:** `models_categorias.py:272`
**Esforço:** XS (menos de 15 minutos)

```python
# ANTES
cor: str = "#gray"

# DEPOIS
cor: str = "gray"
```

---

### Tarefa S4-07 — Corrigir `catch (e) {}` silencioso no `sw.js` (Quick win)

**Achado relacionado:** F-43
**Arquivo:** `app/static/sw.js:10` (**raiz de `static/`, não em `js/`**)
**Esforço:** XS (menos de 30 minutos)

```javascript
// ANTES (app/static/sw.js:10)
try {
    const payload = JSON.parse(event.data.text());
} catch (e) {}

// DEPOIS
try {
    const payload = JSON.parse(event.data.text());
} catch (e) {
    console.error('[sw.js] Erro ao parsear payload push:', e);
}
```

---

### Tarefa S4-08 — Documentar `area` validation em `assignment.atribuir()` (P2)

**Achado relacionado:** F-18
**Arquivo:** `assignment.py:92`
**Esforço:** S (menos de 2 horas)

O campo `area` passado para `atribuir()` não é validado contra a lista de áreas conhecidas. Adicionar validação:

```python
def atribuir(self, chamado: dict, area: str, ...) -> str | None:
    from app.models_categorias import AREAS_VALIDAS  # ou equivalente
    if area not in AREAS_VALIDAS:
        logger.warning("Área desconhecida em atribuição: %s", area)
        return None
    # ... resto da lógica
```

---

### Tarefa S4-09 — Sincronizar `docs/SLO.md` com configuração de deploy (P2) ✅ Concluído

**Achado relacionado:** F-08
**Esforço:** XS

`railway.toml` foi removido (2026-06-17). `docs/SLO.md` atualizado para remover referências à plataforma e usar healthcheckTimeout = 30s como padrão.

---

### Tarefa S4-10 — Estratégia CI para `tailwind.min.css` (P2)

**Achado relacionado:** F-11
**Esforço:** M (1 dia)

Opção recomendada: adicionar `tailwind.min.css` ao `.gitignore` e garantir que o build do Docker sempre regenera. Em desenvolvimento, documentar o comando de build no README.

---

## 8. Semana 4.5 — CSS e Design System

**Período:** 2026-07-14 (mini-semana — parte da semana 4/5)
**Foco:** Consolidar tokens de design, eliminar valores CSS hardcoded e padronizar focus rings em toda a interface.
**Esforço total:** M (1 a 2 dias)

---

### Tarefa S4.5-01 — Substituir valores hardcoded em `table-filters.css` por tokens (F-64)

**Arquivo:** `app/static/css/table-filters.css`
**Esforço:** S (menos de 2 horas)

Substituir cores e sombras codificadas diretamente por referências aos tokens globais do Design System DTX:

```css
/* ANTES — valores hardcoded */
background-color: #1e40af;
border-color: #3b82f6;

/* DEPOIS — tokens globais */
background-color: var(--color-dtx-700);
border-color: var(--color-dtx-500);
```

Revisar o arquivo completo e substituir todas as ocorrências de cores hardcoded. Usar tokens `var(--color-dtx-*)` para cores da marca e `var(--color-surface-*)` para fundos e bordas de superfície.

**Critério de aceite:** Nenhum valor de cor hexadecimal ou RGB literal no arquivo; alteração de token global reflete automaticamente em `table-filters.css`.

---

### Tarefa S4.5-02 — Padronizar focus ring em `dashboard.css` e `relatorios.css` (F-67)

**Arquivos:**
- `app/static/css/dashboard.css`
- `app/static/css/relatorios.css`

**Esforço:** S (menos de 2 horas)

O projeto usa dois padrões conflitantes de indicação de foco: `box-shadow` em alguns componentes e `outline` em outros. Padronizar para:

```css
/* Padrão único de focus ring */
:focus-visible {
    outline: 2px solid var(--color-dtx-600);
    outline-offset: 2px;
    box-shadow: none; /* remover box-shadow de foco */
}
```

Remover todas as regras `box-shadow` usadas exclusivamente para indicação de foco em `dashboard.css` e `relatorios.css`. Manter `box-shadow` apenas para elevação e sombras decorativas.

**Critério de aceite:** Navegação por teclado exibe o mesmo indicador visual em toda a aplicação; sem duplicidade de `outline` + `box-shadow` de foco simultâneos.

---

### Tarefa S4.5-03 — Substituir `rgba()` por sintaxe moderna em `relatorios.css` (F-66)

**Arquivo:** `app/static/css/relatorios.css`
**Esforço:** XS (menos de 30 minutos)

```css
/* ANTES — sintaxe legada */
background-color: rgba(59, 130, 246, 0.1);
border-color: rgba(59, 130, 246, 0.3);

/* DEPOIS — sintaxe moderna CSS Level 4 */
background-color: rgb(59 130 246 / 0.1);
border-color: rgb(59 130 246 / 0.3);
```

Substituir todas as ocorrências de `rgba(r,g,b,a)` pelo formato `rgb(r g b / a)` no arquivo. Idealmente, migrar para tokens com transparência quando disponíveis.

**Critério de aceite:** Nenhuma ocorrência de `rgba(` em `relatorios.css`.

---

### Tarefa S4.5-04 — Substituir tokens locais `--dash-*`/`--reports-*` por tokens globais (F-65)

**Arquivos:**
- `app/static/css/dashboard.css`
- `app/static/css/relatorios.css`

**Esforço:** S (menos de 2 horas)

Os arquivos definem tokens CSS locais (como `--dash-primary`, `--reports-border`) que duplicam os tokens globais do Design System. Substituir as referências a tokens locais por tokens globais onde há equivalente direto:

```css
/* ANTES — token local */
color: var(--dash-primary);
border: 1px solid var(--reports-border);

/* DEPOIS — token global */
color: var(--color-dtx-600);
border: 1px solid var(--color-surface-border);
```

Onde não há equivalente global direto, promover o token local para o arquivo de tokens globais (`app/static/css/` raiz ou equivalente) antes de remover a definição local.

**Critério de aceite:** Nenhuma definição de token `--dash-*` ou `--reports-*`; componentes visualmente idênticos antes e depois da migração.

---

## 9. Semana 5 — Documentação e CI

**Período:** 2026-07-15 a 2026-07-25 (última semana, estendida para acomodar documentação adicional)
**Foco:** Atualizar toda documentação desatualizada, corrigir INCIDENT_RUNBOOK.md, sincronizar API.md, ENV.md e scripts/README.md.

---

### Tarefa S5-01 — Reescrever `docs/INCIDENT_RUNBOOK.md` para Docker (P1)

**Achados relacionados:** F-39, F-40
**Esforço:** M (1 dia)

O documento inteiro usa comandos `gcloud run` (Cloud Run) desatualizados. O sistema agora roda via Docker — Railway também foi removido (2026-06-17). Reescrever com comandos Docker:

```bash
# ANTES (Cloud Run)
gcloud run deploy sistema-chamados --image gcr.io/...

# DEPOIS (Docker)
docker logs -f <container>
docker compose up -d --force-recreate
```

Também corrigir:
- Cenário 5: Firebase Storage → Cloudflare R2
- Linha 138: Resolver e documentar situação do billing GCP

---

### Tarefa S5-02 — Corrigir `docs/historico/ANALISE_COMPLETA_SISTEMA.md` (P2)

**Achados relacionados:** F-35, F-42
**Esforço:** M (meio dia)

Divergências a corrigir:
1. Python "3.8+" → "3.12+"
2. Deploy "Google Cloud Run" → "Docker (plataforma a definir)"
3. Storage "Cloud Storage (Firebase)" → "Cloudflare R2"
4. Auth "Firebase Authentication" → "Flask-Login + Werkzeug hash armazenado no Firestore"
5. Rota `/dashboard` → `/admin`
6. Status "Em Andamento, Pendente, Fechado" → "Em Atendimento, Concluído, Cancelado"
7. Estrutura `/app/models/` como diretório → arquivos diretos em `app/`
8. `SESSION_LIFETIME = 86400` — documentar que são 24h de sessão máxima, com logout por inatividade de 15 min (não contradiz LGPD doc; são conceitos diferentes)
9. Remover referência a `app.py` como entry point → `run.py`

---

### Tarefa S5-03 — Atualizar `docs/ENV.md` (P2)

**Achados relacionados:** F-45
**Esforço:** S (menos de 2 horas)

- Corrigir Firebase Storage como storage principal → R2 é o primário
- Adicionar `ITENS_POR_PAGINA_DASHBOARD` com descrição e valor padrão
- Adicionar variáveis VAPID (`VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_CLAIM_EMAIL`)
- Substituir variáveis BREVO/SMTP (`BREVO_API_KEY`, `MAIL_SERVER`, `MAIL_PORT`) por variáveis Microsoft Graph API: `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`, `GRAPH_SENDER_EMAIL`

---

### Tarefa S5-04 — Atualizar `docs/DEV_SETUP.md` com Node.js (P2)

**Achado relacionado:** F-49
**Esforço:** XS (menos de 30 minutos)

Adicionar Node.js **20+** na lista de pré-requisitos com instrução de instalação e o passo de `npm install && npm run build:css` no setup. (O Dockerfile usa Node 20 — versão mínima local deve espelhar a de produção.)

---

### Tarefa S5-05 — Corrigir inconsistência em `docs/API.md` (P3)

**Achado relacionado:** F-47
**Arquivo:** `docs/API.md` linhas 761 vs 79
**Esforço:** XS (menos de 15 minutos)

A URL `/api/confirmar-resolucao` na seção de erros deve ser padronizada para `/api/chamado/<id>/confirmar-resolucao` conforme o índice.

---

### Tarefa S5-06 — Remover/corrigir chaves `edit_*_soon` de `translations.json` (P3)

**Achado relacionado:** F-32
**Arquivo:** `translations.json:1467-1481`
**Esforço:** S (menos de 1 hora)

As chaves `edit_*_soon` expõem ao usuário que funcionalidades não estão implementadas. Ou implementar as funcionalidades ou substituir por mensagens neutras como `"em_breve"`.

---

### Tarefa S5-07 — Verificar e documentar `e2e.yml` (P3)

**Achado relacionado:** `README.md` menciona `e2e.yml` não encontrado no disco.

1. Verificar no git: `git log --all -- .github/workflows/e2e.yml`
2. Se deletado: avaliar se os testes E2E existentes em `tests/e2e/` precisam CI
3. Se nunca existiu: remover a referência do README.md

> ✅ **Concluído (2026-06-17):** `.github/workflows/e2e.yml` existe no disco e executa a suíte Playwright (`tests/e2e/`). A referência no README é válida — nenhuma ação adicional necessária.

---

### Tarefa S5-08 — Atualizar `docs/DEPLOYMENT_PLAN.md` para Docker (P2)

**Achado relacionado:** F-77
**Arquivo:** `docs/DEPLOYMENT_PLAN.md`
**Esforço:** S (menos de 2 horas)

O documento descreve deploy para Cloud Run. Railway também foi removido (2026-06-17). Reescrever para Docker genérico:
1. Substituir comandos `gcloud run` e `railway *` por equivalentes Docker/Docker Compose.
2. Corrigir o limite de upload para o valor real: **10 MB por arquivo** (`MAX_ANEXO_BYTES`, config.py).

**Critério de aceite:** Nenhuma menção a Cloud Run ou Railway sem aviso de "histórico"; limite de upload correto em 10 MB/arquivo.

> ✅ **Concluído (2026-06-17):** `DEPLOYMENT_PLAN.md` reescrito para Docker; limite corrigido para 10 MB/arquivo. `cloudbuild.yaml` e `.gcloudignore` removidos.

---

### Tarefa S5-09 — Criar `tests/test_routes/test_api_contract.py` ou atualizar docs (P2)

**Achado relacionado:** F-79
**Esforço:** S (menos de 2 horas)

Se os testes de contrato de API já existem em `tests/test_routes/test_api.py`, atualizar `docs/TESTES_API.md` para apontar para esse arquivo em vez de referenciar `test_api_contract.py` inexistente. Se os testes não existem, criar o arquivo com os casos básicos de cada endpoint da API.

**Critério de aceite:** Sem referências quebradas na documentação de testes; testes de contrato de API existem e passam.

---

### Tarefa S5-10 — Atualizar `docs/PLANO_DE_TESTES.md` (P2)

**Achado relacionado:** F-80
**Arquivo:** `docs/PLANO_DE_TESTES.md`
**Esforço:** S (menos de 1 hora)

- Atualizar versão Python de "3.8+" ou "3.10+" para "3.12+"
- Incluir E2E no escopo do plano (atualmente ausente)
- Verificar e atualizar qualquer referência a ferramentas ou frameworks desatualizados

**Critério de aceite:** Documento reflete a stack e escopo de testes atual do projeto.

---

### Tarefa S5-11 — Documentar scripts novos e obsoletos em `scripts/README.md` (P2)

**Achados relacionados:** F-73, F-74
**Arquivo:** `scripts/README.md`
**Esforço:** S (menos de 1 hora)

Adicionar ao README de scripts:

1. **F-73:** Documentar `gerar_email_visual_snapshots.py` (propósito, pré-requisitos, como executar) e `migrar_gates_subetapas.py` (propósito, quando usar, reversibilidade).

2. **F-74:** Documentar que `atualizar_firebase.py` está **obsoleto** e foi substituído por `migrar_setores_catalogo.py`. Adicionar aviso visual no início da entrada correspondente:

```markdown
### `atualizar_firebase.py` (OBSOLETO)

> **Atenção:** Este script foi substituído por `migrar_setores_catalogo.py`.
> Não executar sem revisar o código e confirmar a necessidade.
```

**Critério de aceite:** Todo script em `scripts/` tem entrada no README; scripts obsoletos claramente sinalizados.

---

## 10. Tabela mestre de itens

| ID | Achado | Prioridade | Esforço | Arquivo afetado | Semana | Status |
|---|---|---|---|---|---|---|
| S0-01 | Corrigir tautologia `assert` em `test_i18n.py:29` (F-50) | P2 | XS | `tests/test_i18n.py:29` | 0 | **Concluído 2026-06-17** |
| S0-02 | Corrigir URLs E2E `/relatorios` → `/admin/relatorios` (F-51/52) | P2 | XS | `tests/e2e/test_fluxo_*.py` | 0 | **Concluído 2026-06-17** |
| S0-03 | Marcar `test_solicitante.py` legado como skip/remover (F-53) | P2 | XS | `tests/e2e/test_solicitante.py` | 0 | **Concluído 2026-06-17** |
| S0-04 | Mover `confirmacao-solicitante.md` para `docs/plans/` (F-78) | P3 | XS | raiz → `docs/plans/` | 0 | **Concluído 2026-06-17** |
| S0-05 | Adicionar `app/static/dist/` ao `.gitignore` (F-70) | P3 | XS | `.gitignore` | 0 | **Concluído 2026-06-17** |
| S1-01 | Corrigir IP spoofing com ProxyFix (F-01) | P0 | S | `app/__init__.py`, `app/utils.py:96` | 1 | **Concluído 2026-06-17** |
| S1-02 | Substituir `datetime.utcnow()` (F-04) | P1 | S | `app/services/analytics.py:87, 216` | 1 | **Concluído 2026-06-17** |
| S1-03 | Remover `print()` de produção (F-05) | P1 | S | `app/models_historico.py:85, 143` | 1 | **Concluído 2026-06-17** |
| S1-04 | Corrigir `# noqa: S310` para `# nosec B310` (F-03) | P2 | S | `translation_service.py:27` | 1 | **Concluído 2026-06-17** |
| S1-05 | Corrigir host em `run.py` (F-09) | P3 | S | `run.py:27` | 1 | **Concluído 2026-06-17** |
| S1-06 | Verificar billing GCP vencido (F-40) | P0 | S | `INCIDENT_RUNBOOK.md:138` | 1 | **N/A 2026-06-17** — GCP descontinuado; deploy migrado para Docker |
| S1-07 | Dry-run e flag `--apply` em `atualizar_firebase.py` (F-71) | P1 | S | `scripts/atualizar_firebase.py` | 1 | **Concluído 2026-06-17** |
| S1-08 | Dry-run e flag `--apply` em `atualizar_setores_from_print.py` (F-72) | P1 | S | `scripts/atualizar_setores_from_print.py` | 1 | **Concluído 2026-06-17** |
| S2-01 | Race condition `contadores_uso.py` → transação (F-13) | P0 | S | `contadores_uso.py:43-54` | 2 | **Concluído 2026-06-17** |
| S2-02 | Race condition `gamification_service.py` → Increment (F-14) | P0 | S | `gamification_service.py:79-98` | 2 | **Concluído 2026-06-17** |
| S2-03 | HTML injection em `report_service.py` (F-15) | P0 | S | `report_service.py:166-176` | 2 | **Concluído 2026-06-16** |
| S2-04 | threading.Lock em TRANSLATION_MAP (F-16) | P1 | S | `translation_service.py` | 2 | **Concluído 2026-06-17** |
| S2-05 | Substituir window.prompt por modal acessível (F-33) | P1 | M | `dashboard_otimizacoes.js`, `dashboard.html` | 2 | **Concluído 2026-06-17** |
| S3-01 | Testes `upload.py`: 47% → 80% (F-06) | P1 | M | `tests/test_services/test_upload.py` | 3 | **Concluído 2026-06-18** — `upload.py` 47% → 100% (+13 testes) |
| S3-02 | Testes `notifications.py`: 53% → 80% (F-07) | P1 | M | `tests/test_services/test_notifications.py` | 3 | **Concluído 2026-06-18** — `notifications.py` 72% → 98% (+19 testes) |
| S3-03 | Strings hardcoded em `dashboard_otimizacoes.js` (F-34, F-36, F-46) | P1 | S | `dashboard_otimizacoes.js` | 3 | **Concluído 2026-06-17** — `DTX_MSGS`/`DTX_URLS`/`DTX_STATUS_VALIDOS` via servidor |
| S3-04 | Strings hardcoded em `table-filters.js` (F-37, F-38, F-44) | P2 | S | `table-filters.js` | 3 | **Concluído 2026-06-17** |
| S3-05 | Corrigir mock inerte em `test_api.py` e `test_regression_suite.py` (F-54) | P1 | S | `tests/test_routes/test_api.py:20`, `tests/test_regression/test_regression_suite.py:181` | 3 | **Concluído 2026-06-18** — 3 mocks inertes removidos |
| S3-06 | Corrigir asserts permissivos `(200, 404)` em `test_api_contract.py` (F-55) | P1 | S | `tests/test_routes/test_api_contract.py` | 3 | **Concluído 2026-06-18** — asserts exatos; rota inexistente → `== 404` |
| S3-07 | Corrigir assert `(404, 403)` em `test_api_status.py:93` (F-56) | P1 | XS | `tests/test_routes/test_api_status.py:93` | 3 | **Concluído 2026-06-18** — `== 404` com mock doc.exists=False |
| S3-08 | Adicionar `test_supervisor_pode_ver_relatorios` (F-57) | P1 | S | `tests/test_routes/test_dashboard.py` | 3 | **Concluído 2026-06-18** — 2 testes adicionados (supervisor 200, solicitante 302/403) |
| S3-09 | Setar `onboarding_completo/passo` no `_usuario_mock()` (F-62) | P1 | XS | `tests/conftest.py` | 3 | **Concluído 2026-06-17** |
| S3-10 | Teste IDOR endpoint `/api/atualizar-status` (CT-STAT-08) | P1 | XS | `tests/test_routes/test_api_status.py` | 3 | **Concluído 2026-06-16** |
| —     | CSV/Formula injection no export Excel (F-59) | P1 | — | `excel_export_service.py:75` | — | **Já implementado** (`_safe_cell()`) |
| S4-01 | Redis distributed lock APScheduler (F-02) | P2 | M | `app/__init__.py:161` | 4 | **Concluído 2026-06-18** — `scheduler_lock.py` + 5 testes; jobs wrapeados com lock |
| S4-02 | Agendar `reset_ranking_semanal` (F-27) | P2 | S | `app/__init__.py` | 4 | **Concluído 2026-06-18** — `GamificationService.resetar_ranking_semanal()` + APScheduler domingo 23h59 + 3 testes |
| S4-03 | `get_static_cached` em dashboard (F-12) | P2 | S | `app/routes/dashboard.py:159` | 4 | **Concluído 2026-06-18** — 2 ocorrências substituídas por `get_static_cached("usuarios_all", ...)` |
| S4-04 | Limite em `obter_inscricoes` WebPush (F-17) | P2 | S | `webpush_service.py:69` | 4 | **Concluído 2026-06-18** — `MAX_INSCRICOES=20`, `.limit()` + warning + 2 testes |
| S4-05 | `@firebase_retry` em `CategoriaImpacto.save()` (F-19) | P2 | XS | `models_categorias.py:319` | 4 | **Concluído 2026-06-18** — decorator adicionado + 2 testes (update + retry 3x) |
| S4-06 | Corrigir `cor="#gray"` (F-28) | P3 | XS | `models_categorias.py:272` | 4 | **Concluído 2026-06-17** |
| S4-07 | Corrigir catch silencioso em `sw.js` (F-43) | P3 | XS | `app/static/sw.js:10` | 4 | **Concluído 2026-06-17** |
| S4-08 | Validar `area` em `assignment.atribuir()` (F-18) | P2 | S | `assignment.py:92` | 4 | **Concluído 2026-06-18** — retorno estruturado `sucesso=False` para área vazia/whitespace + 3 testes |
| S4-09 | Sincronizar `docs/SLO.md` (F-08) | P2 | XS | `docs/SLO.md:87` | 4 | **Concluído 2026-06-17** |
| S4-10 | Estratégia CI para `tailwind.min.css` (F-11) | P2 | M | `Dockerfile`, `.gitignore` | 4 | **Concluído 2026-06-18** — adicionado ao `.gitignore`; `DEV_SETUP.md` documentado como obrigatório no setup |
| S4.5-01 | Tokens `var(--color-dtx-*)` em `table-filters.css` (F-64) | P2 | S | `app/static/css/table-filters.css` | 4.5 | **Concluído 2026-06-17** |
| S4.5-02 | Padronizar focus ring — `outline` único (F-67) | P2 | S | `dashboard.css`, `relatorios.css` | 4.5 | **Concluído 2026-06-17** |
| S4.5-03 | Substituir `rgba()` por `rgb(r g b / a)` em `relatorios.css` (F-66) | P2 | XS | `app/static/css/relatorios.css` | 4.5 | **Concluído 2026-06-17** |
| S4.5-04 | Remover tokens locais `--dash-*`/`--reports-*` (F-65) | P2 | S | `dashboard.css`, `relatorios.css` | 4.5 | **Concluído 2026-06-17** |
| S5-01 | Reescrever INCIDENT_RUNBOOK.md para Docker (F-39, F-40) | P1 | M | `docs/INCIDENT_RUNBOOK.md` | 5 | **Concluído 2026-06-17** |
| S5-02 | Corrigir ANALISE_COMPLETA_SISTEMA.md (F-35, F-42) | P2 | M | `docs/historico/ANALISE_COMPLETA_SISTEMA.md` | 5 | **Concluído 2026-06-17** |
| S5-03 | Atualizar ENV.md (F-45) | P2 | S | `docs/ENV.md` | 5 | **Concluído 2026-06-17** |
| S5-04 | Adicionar Node.js ao DEV_SETUP.md (F-49) | P2 | XS | `docs/DEV_SETUP.md` | 5 | **Concluído 2026-06-17** |
| S5-05 | Corrigir inconsistência API.md (F-47) | P3 | XS | `docs/API.md` | 5 | **Concluído 2026-06-17** |
| S5-06 | Remover chaves `edit_*_soon` de translations.json (F-32) | P3 | S | `translations.json:1467` | 5 | **Concluído 2026-06-17** |
| S5-07 | Verificar e2e.yml (README referência) | P3 | S | `README.md`, `.github/` | 5 | **Concluído 2026-06-17** — `e2e.yml` existe e roda Playwright |
| S5-08 | Atualizar `docs/DEPLOYMENT_PLAN.md` para Docker (F-77) | P2 | S | `docs/DEPLOYMENT_PLAN.md` | 5 | **Concluído 2026-06-17** |
| S5-09 | Criar `test_api_contract.py` ou atualizar docs (F-79) | P2 | S | `tests/test_routes/`, `docs/TESTES_API.md` | 5 | **Concluído 2026-06-17** — `TESTES_API.md` atualizado |
| S5-10 | Atualizar `docs/PLANO_DE_TESTES.md` — Python 3.12+, E2E (F-80, F-82) | P2 | S | `docs/PLANO_DE_TESTES.md`, `firestore.indexes.json` | 5 | **Concluído 2026-06-17** |
| S5-11 | Documentar scripts novos e obsoletos em `scripts/README.md` (F-73, F-74) | P2 | S | `scripts/README.md` | 5 | **Concluído 2026-06-17** |
| — | Resolver `AB_TEST_PLAN.md` descreve `ab_service.py` não implementado (F-81) | P3 | XS | `docs/AB_TEST_PLAN.md` | Backlog | **Concluído 2026-06-18** — `ab_service.py` + template A/B + logging + 7 testes |

### Itens de baixa prioridade — todos resolvidos (Onda C wave 3 concluída)

| Achado | Descrição | Arquivo |
|---|---|---|
| ~~F-20~~ | ~~Corrigir estratégia `aleatorio` que sempre seleciona o primeiro supervisor~~ — **Resolvido 2026-06-18** (Onda A) | `assignment.py:123` |
| ~~F-21~~ | ~~Mover `contador_round_robin` para Redis em vez de memória~~ — **Resolvido 2026-06-18** (Onda B) | `assignment.py` |
| ~~F-22~~ | ~~Adicionar cache em `is_gate_valido` com TTL de 5 minutos~~ — **Resolvido 2026-06-18** (Onda B) | `gates_service.py` |
| ~~F-23~~ | ~~Otimizar `_aplicar_filtros_em_memoria` — chamar `to_dict()` 1x por doc~~ — **Resolvido 2026-06-18** (Onda A) | `filters.py:143-149` |
| ~~F-24~~ | ~~Corrigir N+1 em `_enviar_resumo_admins`~~ — **Resolvido 2026-06-18** (Onda B) | `report_service.py` |
| ~~F-25~~ | ~~Truncar `nova_descricao` antes de salvar no Firestore (max_len=3000)~~ — **Resolvido 2026-06-18** (Onda A) | `edicao_chamado_service.py:126-129` |
| ~~F-26~~ | ~~Corrigir `cursor_prev` em `listar_meus_chamados`~~ — **Resolvido 2026-06-18** (Onda A) | `chamados_listagem_service.py:241` |
| ~~F-29~~ | ~~Tratar ImportError de `Increment` com alerta explícito~~ — **Resolvido 2026-06-18** (Onda A) | `contadores_uso.py:15-17` |
| ~~F-30~~ | ~~Externalizar `SETOR_PARA_AREA` para Firestore~~ — **Resolvido 2026-06-19** (Onda C wave 3) | `utils_areas.py` |
| ~~F-31~~ | ~~Implementar cleanup de documentos `contadores_uso` antigos~~ — **Resolvido 2026-06-19** (Onda C wave 2) | `contadores_uso.py` |
| ~~F-41~~ | ~~Verificar duplicatas antes de injetar CSS dinâmico~~ — **Resolvido 2026-06-19** (Onda C wave 2) | `dashboard_otimizacoes.js` |
| ~~F-48~~ | ~~Remover `onmouseover/onmouseout` inline do onboarding.js~~ — **Resolvido 2026-06-18** (Onda C wave 1) | `onboarding.js` |
| ~~F-81~~ | ~~`docs/AB_TEST_PLAN.md` descreve `ab_service.py` não implementado~~ — **Resolvido 2026-06-18** | — |
| ~~F-82~~ | ~~Divergência de campo em índice Firestore documentado vs. índice real~~ — **Resolvido 2026-06-17** (S5-10) | `firestore.indexes.json`, `docs/` |

---

## 11. Riscos do sprint e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Billing GCP realmente desativado — Firestore para de funcionar | Baixa | Crítico | Verificar em S1-06 com urgência; ter plano de mitigação de acesso |
| ProxyFix quebrar outros testes de autenticação | Média | Alto | Rodar suite completa após S1-01; ter rollback pronto |
| Transações Firestore aumentarem latência em `contadores_uso` | Média | Médio | Medir latência antes/depois; aceitar até 50ms adicional |
| Mocks de boto3/Graph API complexos demais, atrasar S3 | Alta | Médio | Iniciar por casos mais simples (sem credenciais → log warning); aceitar 75% se necessário e iterar |
| Redis não disponível em desenvolvimento | Baixa | Baixo | Implementar fallback sem Redis (conforme S4-01) |
| Modal de cancelamento (S2-05) quebrar fluxo existente | Média | Médio | **Mitigado 2026-06-17** — modal `<dialog>` com validação inline; voltar/Escape restaura status anterior |
| tailwind.min.css no .gitignore quebrar build local | Baixa | Médio | Documentar comando de build no README antes de fazer a mudança |
| Corrigir F-03 revelar que `urlopen` é genuinamente inseguro | Baixa | Alto | Auditar o caller antes de adicionar `# nosec` |
| Scripts F-71/72 terem sido executados sem dry-run antes da correção | Baixa | Alto | Auditar logs do Firestore para confirmar estado dos dados antes de S1-07/08 |
| Migração de tokens CSS (S4.5) alterar aparência visual em produção | Média | Médio | Testar visualmente antes de fazer deploy; usar comparação de screenshots |

---

## 12. Fora do escopo

Os itens abaixo foram identificados mas ficam **fora deste sprint**, com justificativa:

| Item | Motivo de não incluir neste sprint |
|---|---|
| ~~Aumentar cobertura de `analytics.py` (60% → 80%)~~ | **Resolvido 2026-06-19 — Onda 3: 64% → 94%** |
| ~~Aumentar cobertura de `dashboard.py` (67% → 80%)~~ | **Resolvido 2026-06-19 — Onda 3: 69% → 93%** |
| Migração para runtime Python 3.12 no Docker | Requer verificação do runtime atual. Tarefa de investigação antes de agir. |
| Novo sistema de e-mail (Graph API) | ✅ Concluído em 2026-06-17 — Graph API implementado, Brevo/SMTP removidos. |
| Perfil `admin_global` + rotas exclusivas | ✅ Concluído em 2026-06-17 — `app/routes/admin_global.py`, `@requer_admin_global`, `is_admin_or_above` no modelo, proteção de criação de admin por sub-admin. |
| Rotação de `ENCRYPTION_KEY` | Procedimento delicado que requer planejamento de migração de dados. Sprint dedicado. |
| ~~Mover `SETOR_PARA_AREA` para Firestore (F-30)~~ | **Resolvido 2026-06-19** — Onda C wave 3. |
| ~~Cleanup de `contadores_uso` antigos (F-31)~~ | **Resolvido 2026-06-19** — `limpar_contadores_antigos(dias=90)` + job APScheduler domingo 02h00 BRT + CLI `scripts/limpar_contadores_uso.py` (Onda C wave 2) |
| ~~Corrigir round-robin em Redis (F-21)~~ | **Resolvido 2026-06-18 — Redis INCR com fallback em memória (Onda B)** |

---

---

## 13. Ondas de Cobertura 1–4 — Concluídas 2026-06-22

| Onda | Módulos | % antes | % depois | Testes adicionados |
|---|---|---:|---:|---:|
| Onda 1 | exceptions, cache, categorias, chamados_criacao, dashboard_service, webpush | 63–83% | ≥87% | +57 |
| Onda 2 | admin_global, usuarios, api | 49–78% | ≥96% | +69 |
| Onda 3 | analytics, dashboard | 64–69% | 93–94% | +110 |
| Onda 4 | database, __init__ | 52–72% | 98–100% | +53 |
| **Total baseline** | **13/13 módulos** | — | **52/52 OK** | **+289** |

> Gate: 85% por módulo. Script: `python scripts/check_coverage_per_module.py`. Global: **94,98%**, 1435 testes, 0 falhas (2026-06-22).

*Documento atualizado em 2026-06-22 — versão 3.4 — DTX Aerospace, Engenharia de Software*
