# Relatório Executivo — Sistema de Chamados DTX Aerospace

| Campo | Valor |
|---|---|
| **Documento** | Relatório Executivo de Auditoria |
| **Versão** | 3.4 |
| **Data** | 2026-06-22 |
| **Responsável** | DTX Aerospace — Engenharia de Software |
| **Próxima revisão** | 2026-09-18 |

---

## Índice

1. [Resumo Executivo](#1-resumo-executivo)
2. [O que está funcionando bem](#2-o-que-está-funcionando-bem)
3. [Pontos fortes identificados — 3ª rodada](#3-pontos-fortes-identificados--3ª-rodada)
4. [Riscos identificados](#4-riscos-identificados)
5. [Ações prioritárias](#5-ações-prioritárias)
6. [Métricas de saúde do sistema](#6-métricas-de-saúde-do-sistema)
7. [Próximos passos recomendados](#7-próximos-passos-recomendados)
8. [Nota sobre documentação desatualizada](#8-nota-sobre-documentação-desatualizada)
9. [Glossário](#9-glossário)

---

## 1. Resumo Executivo

O Sistema de Chamados DTX Aerospace é uma aplicação web interna desenvolvida para gerenciar solicitações e demandas entre os colaboradores da empresa. Ele permite que **solicitantes** registrem pedidos de suporte ou serviço, que **supervisores** acompanhem e gerenciem as demandas de suas áreas, e que **administradores** tenham visibilidade total sobre todas as operações — incluindo relatórios consolidados, gestão de usuários e configuração de categorias. O sistema roda em container Docker na nuvem, utiliza banco de dados Firebase e armazena arquivos anexos de forma segura no serviço Cloudflare R2.

Em 2026-06-16 foi concluída uma **terceira rodada de auditoria técnica abrangente**, que avaliou testes automatizados, arquivos CSS, scripts operacionais e documentação auxiliar. As duas primeiras rodadas haviam identificado 49 achados (F-01 a F-49). Esta terceira rodada expandiu a cobertura para **82 achados no total (F-01 a F-82)**, sendo que os novos 33 achados (F-50 a F-82) incluem bugs ativos na suite de testes, scripts potencialmente destrutivos sem proteção e inconsistências no design system CSS.

O sistema continua demonstrando maturidade técnica sólida em seus fundamentos (**1435 testes automatizados**, **94,98% de cobertura**, zero erros de lint e zero vulnerabilidades de alta ou média severidade detectadas por bandit). A terceira auditoria revelou, adicionalmente, uma série de pontos positivos importantes: as regras do Firestore estão configuradas corretamente, o design system DTX Light está bem documentado, o `QA_DEBUG_PLAYBOOK.md` é um documento de alta qualidade totalmente atual, e a suíte `test_dtx_*` (invariants, i18n_smoke, route_matrix) constitui um diferencial de qualidade que lê os arquivos-fonte reais do projeto para validar invariantes estruturais.

**Sprint pós-auditoria (Grupos 0–7 + F-81) — concluído em 2026-06-18:** 61 dos 82 achados (F-01 a F-82) foram resolvidos. ~~Restam 21 itens em backlog~~ — **backlog zerado em 2026-06-22** (Ondas A/B/C + Ondas 1–4 concluídas; 82/82 resolvidos). Zero achados de Alta severidade abertos.

**Atualizações concluídas em 2026-06-17:** (1) F-15 (HTML injection). (2) Perfil `admin_global`. (3) Microsoft Graph API. (4) **Grupo 2:** F-01, F-13, F-14, F-04 — R-01, R-03, R-04, R-10 resolvidos. (5) **Grupo 3:** F-16, F-33 — R-06, R-07 resolvidos. (6) **Grupo 0:** F-50, F-51, F-52, F-53, F-78, F-70. (7) **Grupo 1:** F-03, F-05, F-09, F-71, F-72. (8) **Grupo 5 (CSS):** F-64, F-65, F-66, F-67. (9) **Grupo 7 (docs):** F-35, F-39, F-40, F-45, F-47, F-49, F-77, F-79, F-80, F-82, F-73, F-74, F-32.

**Atualizações concluídas em 2026-06-18 — Grupo 4 (qualidade de testes):** S3-01 a S3-08 — `upload.py` 100%, `notifications.py` 98%, mocks inertes removidos, asserts exatos, testes de relatórios para supervisor — R-08, R-09, R-19, R-20, R-21, R-23, R-24 resolvidos.

**Atualizações concluídas em 2026-06-18 — Grupo 6 (confiabilidade):** S4-01 a S4-10 — Redis lock APScheduler, reset ranking semanal, cache de usuários no dashboard, limite Web Push, `@firebase_retry`, validação de área, tailwind no `.gitignore` — R-02, R-11, R-13 resolvidos.

**Melhorias de produto (`melhorias-sprint.md`):** Features 1–3 (multi-anexo, anti-self-ticket, Graph API) **implementadas**.

**Atualizações concluídas em 2026-06-18 — F-81 + Onda A + Fase 0 + Onda B + Onda C wave 1:** `ab_service.py` com split determinístico por UID; Onda A: F-20/F-23/F-25/F-26/F-29/F-58/F-59/F-61/F-63 (22 testes novos); Fase 0: F-69/F-76/F-82 (doc-only); Onda B: F-24 (batch N+1), F-22 (cache TTL gates), F-21 (round-robin Redis INCR); Onda C wave 1: F-75 (scripts dry-run/batch), F-48 (handlers inline CSP), F-60 (tour step invariants); total: **1143 testes**, 83,93% cobertura.

**Onda C wave 2 concluída em 2026-06-19 — F-31 + F-41 + F-68:** F-31: `limpar_contadores_antigos(dias=90)` + job APScheduler domingo 02h00 BRT + CLI `scripts/limpar_contadores_uso.py` (6 testes); F-41: guard `getElementById` no bloco `@keyframes fadeIn` de `dashboard_otimizacoes.js` (3 testes regressão); F-68: tokens `var(--color-surface-border)` em `dashboard.css` e `relatorios.css`, paridade `input.css ↔ tailwind.config.js` verificada (2 invariantes); total: **1171 testes**; 81/82 achados resolvidos.

**Ondas 1–4 de cobertura concluídas em 2026-06-22:** gate por módulo 85% atingido; 52/52 módulos OK; `database.py` 52%→100%, `__init__.py` 72%→98%; baseline 13/13 resolvido; 1435 testes passando, 0 falhas. Fix F-61 (i18n): `get_language_code` retorna `pt_BR` como padrão.

**Onda C wave 3 concluída em 2026-06-19 — F-30:** `utils_areas.py` refatorado para ler mapa de setores do Firestore (`config/setor_para_area`) com cache TTL 5 min e fallback estático; `invalidar_cache_setor_area()` exportado; ADR `docs/plans/adr-f30-setor-para-area.md`; script de migração `scripts/migrar_setor_area.py`; 12 testes novos (8 em `test_utils_areas.py` + 4 em `test_migrar_scripts.py`); total: **1183 testes**, **82/82 achados resolvidos**, 0 em backlog.

---

## 2. O que está funcionando bem

- **Testes automatizados robustos:** 1183 testes passando sem falhas, cobertura geral ≥ 80%, acima do gate mínimo estabelecido pelo projeto.
- **Código limpo e padronizado:** Zero erros de lint (ruff), código consistente com os padrões do projeto em toda a base de código.
- **Segurança sem vulnerabilidades críticas (bandit):** Zero High e zero Medium — todos os 82 achados resolvidos.
- **Proteção contra ataques de senha:** O sistema possui bloqueio automático após múltiplas tentativas de login incorretas, protegendo contas de usuários contra ataques de força bruta.
- **Upload seguro de arquivos:** Todos os arquivos enviados passam por verificação dupla — extensão permitida e verificação do conteúdo real do arquivo (magic bytes) — evitando uploads maliciosos.
- **Controle de acesso bem definido:** Quatro perfis distintos (solicitante, supervisor, admin, **admin_global**) com permissões hierárquicas claramente separadas e verificadas em cada operação. O perfil `admin_global` herda automaticamente tudo do `admin` e adiciona governança de sub-admins.
- **Proteção contra falsificação de formulários (CSRF):** Todos os formulários do sistema possuem proteção contra ataques que tentam enganar o usuário a executar ações não intencionais.
- **Internacionalização:** O sistema suporta três idiomas (Português, Inglês e Espanhol) com fallback automático para PT-BR.
- **Auditoria de ações:** Histórico completo de alterações em cada chamado, com registro de usuário, data e hora.
- **Download seguro de anexos:** Links de download têm validade de 1 hora e verificam se o usuário tem permissão antes de permitir o acesso ao arquivo.
- **Rate limiting:** Proteção contra abuso de endpoints com limite de requisições por IP em produção (Redis).
- **Infraestrutura em nuvem:** Deploy via Docker, sem necessidade de gerenciamento manual de servidores.
- **Sistema de gamificação:** Pontuação e conquistas para engajar solicitantes e supervisores com o sistema.
- **Web Push:** Notificações em tempo real via Service Worker e VAPID, sem depender de e-mail.

---

## 3. Pontos fortes identificados — 3ª rodada

A terceira rodada identificou elementos do projeto que merecem reconhecimento explícito por sua qualidade. Esses pontos não geram achados — são referências positivas a serem mantidas:

| Item | Status | Observação |
|---|---|---|
| `firestore.rules` (`allow read, write: if false`) | **Correto e seguro** | Regras negam tudo por padrão — política de deny-all para acesso externo direto ao banco |
| `docs/plans/2026-06-12-dtx-light-design-system.md` | **Atual e consistente** | Totalmente alinhado com `tailwind.config.js` e `input.css` — referência confiável |
| `docs/QA_DEBUG_PLAYBOOK.md` | **Excelente qualidade** | Documento completo, totalmente atual, de alta utilidade operacional |
| `tailwind.config.js` vs. `input.css` | **100% consistentes** | Tokens do design system DTX Light corretamente definidos e aplicados |
| `tests/test_dtx_*` (invariants, i18n_smoke, route_matrix) | **Diferencial de qualidade** | Suite sofisticada que lê arquivos-fonte reais para validar invariantes estruturais do projeto |
| `docs/TESTES_REGRESSAO.md` | **Consistente** | Alinhado com a estrutura real de testes do projeto |
| `docs/ANALISE_REQUISITOS_QA.md` | **Bom estado** | Apenas omite o status "Cancelado" — lacuna menor |
| `docs/TESTES_USABILIDADE.md` | **Bom estado** | Totalmente atual |
| `docs/onboarding.md` | **Alinhado com o código** | Documenta corretamente a implementação existente |
| Perfil `admin_global` + herança de permissões | **✅ Implementado 2026-06-17** | `@requer_admin_global`, `is_admin_or_above`, proteção de criação de sub-admin, rota `/admin-global` exclusiva |
| Migração de e-mail para Microsoft Graph API | **✅ Implementado 2026-06-17** | `notifications.py` usa exclusivamente Graph API; Brevo/SMTP removidos; `notify_retry.py` com backoff exponencial |
| `_tabela_html` com `html.escape()` em `report_service.py` | **✅ Corrigido 2026-06-16** | F-15 resolvido — HTML injection no relatório semanal eliminado |

---

## 4. Riscos identificados

> **Atenção:** Os itens marcados como "Alto" requerem ação imediata. Estão em produção agora e podem ser explorados.

### Riscos de Alta Severidade

| # | Risco | Probabilidade | Impacto | Severidade | Status |
|---|---|---|---|---|---|
| R-01 | Proteção anti-invasão pode ser burlada por falsificação de endereço IP | Média | Alto | **Alto** | ✅ **Resolvido 2026-06-17** — ProxyFix adicionado; `get_client_ip()` usa `remote_addr` (S1-01) |
| R-02 | Em cenário com múltiplos servidores, alertas automáticos podem ser disparados em duplicidade | Baixa | Médio | **Alto** | ✅ **Resolvido 2026-06-18** — `scheduler_lock.py` com Redis lock em todos os jobs APScheduler (S4-01) |
| R-03 | Race condition em contador de uso diário — limite pode ser burlado em requisições simultâneas | Média | Alto | **Alto** | ✅ **Resolvido 2026-06-17** — `@firestore.transactional` implementado (S2-01) |
| R-04 | Race condition no sistema de gamificação — pontos podem ser perdidos ou duplicados em requisições simultâneas | Média | Médio | **Alto** | ✅ **Resolvido 2026-06-17** — `Increment(pontos)` atômico (S2-02) |
| R-05 | HTML injection em e-mail de relatório semanal — conteúdo de chamados inserido sem tratamento de segurança | Média | Alto | **Alto** | ✅ **Resolvido 2026-06-16** |
| R-06 | Dicionário global de traduções sem proteção para múltiplas threads simultâneas — pode corromper traduções em produção | Média | Alto | **Alto** | **Resolvido 2026-06-17** — `threading.RLock` em `translation_service.py` |
| R-07 | Sistema de cancelamento de chamado usa janela de diálogo bloqueante (`window.prompt`) — bloqueado em navegadores modernos e inacessível para tecnologias assistivas | Alta | Médio | **Alto** | **Resolvido 2026-06-17** — modal `<dialog>` acessível em `dashboard.html` |
| R-08 | Funcionalidade de upload de arquivos com baixa cobertura de testes (47%) | Alta | Médio | Médio | ✅ **Resolvido 2026-06-18** — cobertura 47% → 100% (S3-01) |
| R-17 | Alerta crítico de billing vencido no INCIDENT_RUNBOOK.md (prazo 19/06/2026 — já vencido) | Alta | Alto | **Alto** | ✅ **Resolvido 2026-06-17** — seção removida; runbook migrado para Docker (S5-01 / F-40) |
| **R-19** | **Tautologia em `tests/test_i18n.py:29` — o teste nunca falha, dando falsa garantia de qualidade (F-50)** | **Alta** | **Médio** | **Alto** | ✅ **Resolvido 2026-06-17** (S0-01) |
| **R-20** | **URLs incorretas nos testes E2E (`/relatorios` em vez de `/admin/relatorios`) — testes E2E passam em rota errada (F-51, F-52)** | **Alta** | **Médio** | **Alto** | ✅ **Resolvido 2026-06-17** (S0-02) |
| **R-21** | **Scripts destrutivos (`atualizar_firebase.py`, `atualizar_setores_from_print.py`) sem dry-run e sem confirmação — risco de apagar dados de produção acidentalmente (F-71, F-72)** | **Média** | **Alto** | **Alto** | ✅ **Resolvido 2026-06-17** — flags `--dry-run` e `--apply` (S1-07, S1-08) |

### Riscos de Média Severidade

| # | Risco | Probabilidade | Impacto | Severidade | Status |
|---|---|---|---|---|---|
| R-09 | Sistema de e-mails com baixa cobertura de testes (53%) | Alta | Médio | Médio | ✅ **Resolvido 2026-06-18** — cobertura 72% → 98% (S3-02) |
| R-10 | Uso de função depreciada de data/hora — pode parar de funcionar em versões futuras do Python | Baixa | Baixo | Médio | ✅ **Resolvido 2026-06-17** — `datetime.utcnow()` substituído por `datetime.now(UTC)` em `analytics.py` (S1-02 / F-04) |
| R-11 | Ranking de gamificação nunca é zerado automaticamente (exp_semanal acumulado indefinidamente) | Alta | Baixo | Médio | ✅ **Resolvido 2026-06-18** — `resetar_ranking_semanal()` agendado domingo 23h59 (S4-02) |
| R-12 | Round-robin de atribuição de chamados não funciona em ambiente multi-worker (contador em memória por processo) | Alta | Médio | Médio | ✅ **Resolvido 2026-06-18** — Redis INCR + fallback em memória, `_atribuir_round_robin` (Onda B) |
| R-13 | Inscrições de Web Push sem limite por usuário — possível acúmulo ilimitado | Média | Baixo | Médio | ✅ **Resolvido 2026-06-18** — `MAX_INSCRICOES=20` (S4-04) |
| R-14 | Verificação de gates de categoria sem cache — pode sobrecarregar o Firestore | Média | Baixo | Médio | ✅ **Resolvido 2026-06-18** — `get_static_cached("gates_validos_set", ttl=300)` em `gates_service.py` (Onda B, F-22) |
| **R-22** | **`test_solicitante.py` legado coexiste com `test_fluxo_solicitante.py` — duplicação e possível confusão nos resultados de CI (F-53)** | **Alta** | **Baixo** | **Médio** | ✅ **Resolvido 2026-06-17** — legado marcado com `pytest.mark.skip` (S0-03) |
| **R-23** | **Mocks suspeitos em `patch("app.routes.api.db")` inertes para early-return 400 — falsa impressão de isolamento nos testes (F-54, C-01, C-02)** | **Média** | **Médio** | **Médio** | ✅ **Resolvido 2026-06-18** (S3-05) |
| **R-24** | **Asserts permissivos do tipo `status_code in (200, 404)` mascaram 404 como sucesso em testes de contrato (F-55, F-56)** | **Alta** | **Médio** | **Médio** | ✅ **Resolvido 2026-06-18** (S3-06, S3-07) |
| R-25 | `table-filters.css` usa valores de cor hardcoded que divergem dos tokens do design system DTX Light (F-64) | Alta | Baixo | Médio | **Fechado** (2026-06-17) — cores migradas para tokens |
| R-26 | `DEPLOYMENT_PLAN.md` descrevia Cloud Run (plataforma anterior) — limite de upload incorreto; real é 10 MB/arquivo (F-77) | Alta | Baixo | Médio | **Fechado** (2026-06-17) — doc migrada para Docker; limite corrigido para 10 MB |

### Riscos de Baixa Severidade / Dívida Técnica

| # | Risco | Probabilidade | Impacto | Severidade | Status |
|---|---|---|---|---|---|
| R-15 | Divergência entre documentação de infraestrutura e configuração real | Alta | Médio | Baixo | ✅ **Resolvido 2026-06-17/18** — docs operacionais sincronizados (Grupo 7) |
| R-16 | Documentação operacional (INCIDENT_RUNBOOK.md) completamente baseada em plataforma anterior (Cloud Run/GCP) | Alta | Alto | Baixo | ✅ **Resolvido 2026-06-17** (S5-01) |
| R-18 | Strings de interface do usuário hardcoded em português, causando erros exibidos em PT-BR mesmo para usuários de outros idiomas | Média | Baixo | Baixo | ✅ **Resolvido 2026-06-17** — `DTX_MSGS`/`DTX_URLS`/`DTX_STATUS_VALIDOS` via servidor (S3-03, S3-04) |
| **R-27** | **`app/static/dist/` contém bundle SPA não referenciado pelos templates Flask e não documentado — possivelmente não deveria estar no repositório (F-70)** | **Baixa** | **Baixo** | **Baixo** | ✅ **Resolvido 2026-06-17** — adicionado ao `.gitignore` (S0-05) |
| **R-28** | **`confirmacao-solicitante.md` na raiz do projeto em vez de `docs/plans/` — fora de lugar (F-78)** | **Alta** | **Baixo** | **Baixo** | ✅ **Resolvido 2026-06-17** (S0-04) |

### Detalhamento dos riscos de alta prioridade

**R-01 — Falsificação de endereço IP** ✅ **Resolvido 2026-06-17**

~~O sistema usa o endereço IP do usuário para bloquear tentativas excessivas de login. Porém, a forma como o IP era obtido poderia ser enganada por um atacante que manipulasse um cabeçalho específico da requisição.~~ `ProxyFix` (Werkzeug) foi adicionado em `create_app()` com `x_for=1`, garantindo que `request.remote_addr` reflita o IP real do cliente. `get_client_ip()` foi simplificado para ler apenas `remote_addr`.

**R-03 — Race condition em contador de uso diário** ✅ **Resolvido 2026-06-17**

~~O sistema controla quantas vezes cada usuário pode executar determinadas ações por dia. Essa verificação era feita em dois passos separados: primeiro lê o contador atual, depois escreve o novo valor — se dois requests chegassem ao mesmo tempo, ambos passavam da verificação.~~ A função `_verificar_incrementar_tx` em `contadores_uso.py` foi reescrita com `@firestore.transactional`, garantindo que a leitura, verificação e incremento são feitos atomicamente.

**R-04 — Race condition no sistema de gamificação** ✅ **Resolvido 2026-06-17**

~~O sistema de pontuação sofria do mesmo problema: `_adicionar_exp` lia o valor atual e escrevia o novo sem garantia de exclusividade.~~ A função agora usa `Increment(pontos)` do Firestore para `exp_total` e `exp_semanal`, aplicando o delta atomicamente no servidor — requests simultâneos não sobrescrevem uns aos outros.

**R-05 — HTML injection em e-mail de relatório semanal** ✅ **Resolvido 2026-06-16**

~~O relatório semanal enviado por e-mail montava uma tabela HTML inserindo diretamente os dados dos chamados sem aplicar nenhum tratamento de segurança.~~ A função `_tabela_html` em `report_service.py` foi corrigida: `categoria`, `tipo`, `solicitante` e `data_abertura_fmt` agora passam por `html.escape()` antes de serem inseridos no HTML. Chamados com conteúdo malicioso geram output escapado (`&lt;script&gt;`), sem execução de código.

**R-10 — Função de data/hora depreciada** ✅ **Resolvido 2026-06-17**

~~`datetime.utcnow()` em `analytics.py` (linhas 87 e 216) estava depreciado no Python 3.12+.~~ Substituído por `datetime.now(UTC)` (com `.replace(tzinfo=None)` quando comparado com datetimes naive). Teste `test_obter_sla_para_exibicao_nao_usa_utcnow_deprecated` garante ausência de `DeprecationWarning`.

~~**R-06 — Traduções sem proteção de thread**~~ **Resolvido 2026-06-17**

~~O dicionário de traduções do sistema é um objeto global compartilhado que pode ser modificado em tempo de execução.~~ `translation_service.py` agora protege `TRANSLATION_MAP` com `threading.RLock` em leituras e escritas; chamadas à API MyMemory ocorrem fora do lock. Teste `test_translation_map_concorrencia_50_threads` valida 50 threads simultâneas.

~~**R-07 — window.prompt para cancelamento**~~ **Resolvido 2026-06-17**

~~O cancelamento de chamados exibe uma janela de diálogo nativa do navegador (`window.prompt`) para capturar o motivo.~~ O dashboard usa `<dialog id="modal-cancelamento">` com focus trap, Escape para fechar e mensagens i18n via `DTX_MSGS`. Não há mais `window.prompt()` em `app/static/js/`.

**R-17 — Alerta de billing vencido no runbook** ✅ **Resolvido 2026-06-17**

A seção de billing GCP foi removida do `INCIDENT_RUNBOOK.md` e o documento foi reescrito para a infraestrutura Docker atual.

**R-19 — Tautologia em testes** ✅ **Resolvido 2026-06-17**

O assert tautológico em `tests/test_i18n.py:29` foi substituído por verificação do valor esperado real (S0-01 / F-50).

**R-20 — URLs incorretas nos testes E2E** ✅ **Resolvido 2026-06-17**

URLs corrigidas de `/relatorios` para `/admin/relatorios` em `test_fluxo_supervisor.py` e `test_fluxo_admin.py` (S0-02 / F-51, F-52).

**R-21 — Scripts destrutivos sem proteção** ✅ **Resolvido 2026-06-17**

Ambos os scripts receberam flags `--dry-run` (padrão) e `--apply` (execução explícita). `atualizar_firebase.py` marcado como obsoleto em `scripts/README.md`.

**R-02 — Alertas automáticos em duplicidade** ✅ **Resolvido 2026-06-18**

Todos os jobs APScheduler são envolvidos por `executar_job_com_lock()` de `scheduler_lock.py`, garantindo execução única por instância de job em ambiente multi-worker via Redis lock (S4-01 / F-02).

---

## 5. Ações prioritárias

> **Dica:** As ações abaixo estão ordenadas por impacto. Os primeiros blocos são críticos para segurança e qualidade e devem ser executados com prioridade máxima.

### Ações Triviais — Quick fixes (Semana 0 — menos de 1 dia total)

| # | Ação | Esforço | Achado |
|---|---|---|---|
| 0 | Corrigir tautologia em `test_i18n.py:29` (`assert A or not A`) — P0 trivial | 15 min | F-50 |
| 0 | Corrigir URLs E2E: `/relatorios` → `/admin/relatorios` | 10 min | F-51, F-52 |
| 0 | Remover ou marcar `test_solicitante.py` legado como skip | 5 min | F-53 |
| 0 | Corrigir `cor="#gray"` → `"#808080"` em `models_categorias.py:272` | 5 min | F-28 |
| 0 | Adicionar `console.error` no catch silencioso do `sw.js` | 5 min | F-43 |
| 0 | Mover `confirmacao-solicitante.md` para `docs/plans/` | 2 min | F-78 |
| 0 | Marcar `atualizar_firebase.py` como obsoleto (comentário de cabeçalho + README) | 10 min | F-71, F-74 |

### Ações Imediatas (Semana 1 — P0)

| # | Ação | Prazo sugerido | Complexidade |
|---|---|---|---|
| 1 | ~~Corrigir a forma como o sistema obtém o endereço IP do usuário para evitar falsificação~~ | — | ✅ **Concluído 2026-06-17** (S1-01 / F-01) |
| 2 | ~~Corrigir race condition nos contadores de uso diário usando transação atômica do Firestore~~ | — | ✅ **Concluído 2026-06-17** (S2-01 / F-13) |
| 3 | ~~Corrigir race condition no sistema de gamificação usando transação atômica do Firestore~~ | — | ✅ **Concluído 2026-06-17** (S2-02 / F-14) |
| ~~4~~ | ~~Corrigir HTML injection no relatório semanal~~ | — | ✅ **Concluído 2026-06-16** (F-15) |
| 5 | ~~Verificar situação do billing GCP referenciado no INCIDENT_RUNBOOK.md (prazo vencido)~~ | — | ✅ **Concluído 2026-06-17** (S5-01 / F-40) |
| **6** | ~~Adicionar dry-run e confirmação interativa em `atualizar_firebase.py` e `atualizar_setores_from_print.py`~~ | — | ✅ **Concluído 2026-06-17** (S1-07, S1-08 / F-71, F-72) |

### Ações de Curto Prazo (Semanas 2–3 — P1)

| # | Ação | Prazo sugerido | Complexidade |
|---|---|---|---|
| ~~7~~ | ~~Adicionar proteção de thread (lock) ao dicionário global de traduções~~ | — | ✅ **Concluído 2026-06-17** (S2-04 / F-16) |
| ~~8~~ | ~~Substituir `window.prompt` por modal HTML acessível para captura de motivo de cancelamento~~ | — | ✅ **Concluído 2026-06-17** (S2-05 / F-33) |
| ~~9~~ | ~~Aumentar cobertura de testes da funcionalidade de upload de arquivos de 47% para 80%~~ | — | ✅ **Concluído 2026-06-18** (S3-01 — 100%) |
| ~~10~~ | ~~Aumentar cobertura de testes do sistema de e-mails de 53% para 80%~~ | — | ✅ **Concluído 2026-06-18** (S3-02 — 98%) |
| 11 | ~~Substituir função de data/hora depreciada pelo equivalente moderno~~ | — | ✅ **Concluído 2026-06-17** (S1-02 / F-04) |
| 12 | ~~Implementar trava distribuída para evitar duplicação de alertas automáticos~~ | — | ✅ **Concluído 2026-06-18** (S4-01 / F-02) |
| ~~13~~ | ~~Corrigir mocks suspeitos `patch("app.routes.api.db")` para o módulo correto do serviço~~ | — | ✅ **Concluído 2026-06-18** (S3-05 — 3 mocks inertes removidos) |
| ~~14~~ | ~~Substituir asserts permissivos `in (200, 404)` por asserts exatos~~ | — | ✅ **Concluído 2026-06-18** (S3-06/S3-07) |

### Ações de CSS e Design System (Semana de Qualidade)

| # | Ação | Achado |
|---|---|---|
| 15 | ~~Tokenizar `table-filters.css` com variáveis `var(--color-dtx-*)` em vez de valores hexadecimais hardcoded~~ | F-64 | ✅ **Concluído 2026-06-17** |
| 16 | ~~Padronizar focus ring em um único token no `input.css` — eliminar os três padrões divergentes~~ | F-67 | ✅ **Concluído 2026-06-17** |
| 17 | ~~Adicionar `app/static/dist/` ao `.gitignore` (artefato de build SPA não documentado)~~ | F-70 | ✅ **Concluído 2026-06-17** |
| 18 | ~~Converter sintaxe `rgba()` com vírgula para `rgb()` / `rgba()` com barra em `relatorios.css`~~ | F-66 | ✅ **Concluído 2026-06-17** |

### Ações de Documentação (Semana 4 — P2)

| # | Ação | Achado |
|---|---|---|
| 19 | ✅ Atualizar `INCIDENT_RUNBOOK.md` completamente (Cloud Run → Docker, Firebase Storage → R2) | F-39, F-40 |
| 20 | ✅ Atualizar `DEPLOYMENT_PLAN.md` (Docker; limite real 10 MB/arquivo) | F-77 |
| 21 | ✅ Atualizar `PLANO_DE_TESTES.md` (Python 3.12+, E2E no escopo) | F-80 |
| 22 | ✅ Atualizar `TESTES_API.md` (endpoints reais) | F-79 |
| 23 | ✅ Mover `confirmacao-solicitante.md` da raiz para `docs/plans/` | F-78 |

### Cronograma visual (atualizado 2026-06-18)

```
Semana 0  │ ✅ Quick fixes (F-50, F-51, F-52, F-53, F-28, F-43, F-78, F-70)
Semana 1  │ ✅ P0: IP spoofing, race conditions, dry-run scripts (F-71, F-72)
Semana 2  │ ✅ P1: lock traduções, modal cancelamento
Semana 3  │ ✅ Cobertura upload/e-mail + strings hardcoded JS
Semana 4  │ ✅ APScheduler lock + reset ranking + quick wins (S4-01 a S4-10)
Semana 4.5│ ✅ CSS tokens e design system (S4.5-01 a S4.5-04)
Semana 5  │ ✅ Documentação operacional (S5-01 a S5-11)
Ondas A/B/C│ ✅ 82/82 resolvidos (2026-06-19) — backlog zerado
```

---

## 6. Métricas de saúde do sistema

> **Dica:** Essas métricas são coletadas automaticamente a cada alteração no código e servem como indicador de saúde contínuo.

### Painel de métricas (2026-06-22)

| Indicador | Resultado | Meta | Status |
|---|---|---|---|
| Testes automatizados | 1435 passando / 1435 total | 100% passando | Atingido |
| Cobertura de código | **94,98%** (gate: 85%) | >= 85% | Atingido |
| Erros de qualidade de código (lint) | 0 erros | 0 erros | Atingido |
| Vulnerabilidades críticas de segurança (bandit) | 0 | 0 | Atingido |
| Vulnerabilidades de média severidade (bandit) | 0 | 0 | Atingido |
| Vulnerabilidades de baixa severidade (bandit) | 0 | <= 5 | Atingido |
| Achados de auditoria resolvidos (F-01 a F-82) | **82 / 82** | 82 | **Atingido** |
| Achados de Alta severidade abertos | 0 | 0 | Atingido |
| **Total de achados ativos** | **0** | 0 | **Atingido** |
| False positives em testes | 0 (F-50 resolvido) | 0 | Atingido |
| Aviso de código depreciado | 0 (F-04 resolvido) | 0 | Atingido |

### Interpretação

O sistema está em estado **SAUDÁVEL** para operação. Os indicadores de qualidade (1435 testes, cobertura 94,98%, gate 52/52 módulos, zero High/Medium no bandit) estão dentro ou acima das metas. O sprint pós-auditoria + Ondas A/B/C + Ondas 1–4 resolveu **82 dos 82 achados** e zerou o baseline de cobertura — **backlog zerado**.

### Cobertura de testes por módulo crítico

| Módulo / Funcionalidade | Cobertura atual | Meta |
|---|---|---|
| Upload de arquivos | **100%** ✅ | 80% |
| Sistema de e-mails | **98%** ✅ | 80% |
| Relatórios e métricas | 60% | 80% |
| Painel administrativo | 67% | 80% |
| Criação de chamados | 83% | 80% |
| **Geral** | **94,98%** | **85%** |

### Lacunas de cobertura identificadas na 3ª rodada

> **Superada — suite 1183 testes (2026-06-19).** Todos os achados abaixo foram resolvidos na Onda A e Onda C wave 1.

| Funcionalidade | Situação | Achado |
|---|---|---|
| Supervisor acessando `/admin/relatorios` | ✅ Testado | F-57 resolvido |
| Race condition em `gerar_numero_chamado` | ✅ **Resolvido 2026-06-18** — `test_gerar_numero_chamado_concorrencia_gera_numeros_unicos` (Onda A) | F-58 |
| CSV injection via `/exportar` | ✅ **Resolvido 2026-06-18** — `test_exportar_csv_injection_*` (Onda A) | F-59 |
| Contagem exata de passos de onboarding por perfil (5/6/7) | ✅ **Resolvido 2026-06-18** — 9 testes em `test_dtx_onboarding_js.py` (Onda C wave 1) | F-60 |
| Idioma inválido em `?lang=xyz` | ✅ **Resolvido 2026-06-18** — `test_lang_invalido_*` (Onda A) | F-61 |
| Transições de status inválidas (ex: Concluido → Aberto) | ✅ **Resolvido 2026-06-18** — `test_transicao_status_invalida_*` (Onda A) | F-63 |

---

## 7. Próximos passos recomendados

> **Atualizado 2026-06-19:** Sprint completo — Ondas A, B, C (waves 1–3) concluídas. **82/82 achados resolvidos, backlog zerado.** Foco: operação em produção e monitoramento contínuo.

1. ~~**Corrigir tautologia e URLs E2E**~~ ✅ Concluído 2026-06-17 (S0-01, S0-02).

2. ~~**Proteger scripts destrutivos**~~ ✅ Concluído 2026-06-17 (S1-07, S1-08).

3. ~~**Resolver race conditions**~~ ✅ Concluído 2026-06-17 (S2-01, S2-02).

4. ~~**Corrigir HTML injection em e-mails**~~ ✅ Concluído 2026-06-16 (F-15).

5. ~~**Corrigir vulnerabilidade de IP**~~ ✅ Concluído 2026-06-17 (S1-01).

6. ~~**Verificar billing GCP**~~ ✅ Concluído 2026-06-17 — seção removida do runbook (S5-01).

7. ~~**Corrigir mocks e asserts nos testes**~~ ✅ Concluído 2026-06-18 (S3-05 a S3-08).

8. ~~**Tokenizar CSS**~~ ✅ Concluído 2026-06-17 (S4.5-01 a S4.5-04).

9. ~~**Aumentar cobertura de upload e e-mail**~~ ✅ Concluído 2026-06-18 — 100% e 98% respectivamente.

10. ~~**Implementar lock APScheduler + reset ranking**~~ ✅ Concluído 2026-06-18 (S4-01, S4-02).

11. ~~**Backlog — performance e arquitetura:** F-20 (aleatório), F-21 (round-robin Redis), F-22 (cache gates), F-23/F-24 (queries N+1).~~ ✅ Concluído — Onda A (F-20, F-23) + Onda B (F-21, F-22, F-24) 2026-06-18.

12. ~~**Backlog — testes adicionais:** F-58 a F-63 (concorrência, CSV injection, onboarding, i18n, transições de status).~~ ✅ Concluído — Onda A (F-58, F-59, F-61, F-63) + Onda C wave 1 (F-60) 2026-06-18.

13. ~~**Implementar AB test (F-81):**~~ ✅ Concluído 2026-06-18 — `app/services/ab_service.py` (split determinístico por UID + experimento), integração em `chamados.py` (GET + 3 caminhos POST), template `formulario.html` com variante B (placeholder contextual + contador JS com nonce CSP), logging de evento `descricao_insuficiente` em `validators.py`, 7 testes novos (5 unitários + 2 de rota).

14. ~~**Onda A (F-20, F-23, F-25, F-26, F-29, F-58, F-59, F-61, F-63):**~~ ✅ Concluído 2026-06-18 — 9 achados resolvidos; 22 testes novos.
15. ~~**Fase 0 (F-69, F-76, F-82):**~~ ✅ Concluído 2026-06-18 — doc-only, 3 achados fechados.
16. ~~**Onda B (F-24, F-22, F-21):**~~ ✅ Concluído 2026-06-18 — N+1 batch, cache TTL gates, Redis INCR round-robin; 5 testes novos.
17. ~~**Onda C wave 1 (F-75, F-48, F-60):**~~ ✅ Concluído 2026-06-18 — scripts com dry-run/batch, handlers CSP removidos, invariantes de tour; 23 testes novos. Total: **1143 testes**.
18. ~~**Onda C wave 2 (F-31, F-41, F-68):**~~ ✅ Concluído 2026-06-19 — cleanup contadores_uso, dedup CSS JS, tokens de borda; 28 testes novos. Total: **1171 testes**.
19. ~~**Onda C wave 3 (F-30):**~~ ✅ Concluído 2026-06-19 — `utils_areas.py` → Firestore `config/setor_para_area` + cache TTL 5 min + fallback + script migração; 12 testes novos. Total: **1183 testes**. **82/82 achados resolvidos. Backlog zerado.**
20. ~~**Ondas 1–4 de cobertura (2026-06-22):**~~ ✅ Concluído — 13/13 módulos baseline elevados a ≥85%; CI alinhado (gate 85% + script por módulo); fix i18n pt_BR padrão; 1435 testes, 94,98% global, 52/52 módulos OK. Ver `docs/CHECKLIST_SEGURANCA.md` v3.4 e `docs/plans/adr-database-testabilidade.md`.

---

## 8. Nota sobre documentação desatualizada

A soma das três rodadas de auditoria revelou múltiplos documentos técnicos do projeto desatualizados em pontos importantes. Abaixo está um resumo das divergências mais críticas:

> **Status (2026-06-18):** todas as divergências críticas foram corrigidas no sprint Grupos 0–7. **F-81 concluído 2026-06-18** — `ab_service.py` implementado, plano e checklist atualizados.

| Documento | Principal divergência | Risco operacional |
|---|---|---|
| `docs/INCIDENT_RUNBOOK.md` | ✅ Comandos migrados de `gcloud run` para Docker | Resolvido |
| `docs/INCIDENT_RUNBOOK.md` | ✅ Seção de billing GCP removida | Resolvido |
| `docs/INCIDENT_RUNBOOK.md` | ✅ Storage atualizado para Cloudflare R2 | Resolvido |
| `docs/DEPLOYMENT_PLAN.md` | ✅ Migrado para Docker; limite real 10 MB/arquivo | Resolvido — F-77 |
| `docs/ANALISE_COMPLETA_SISTEMA.md` | ✅ Deploy, auth e e-mail atualizados | Resolvido — F-35 |
| `docs/PLANO_DE_TESTES.md` | ✅ Python 3.12+ e E2E no escopo | Resolvido — F-80 |
| `docs/TESTES_API.md` | ✅ Alinhado com `test_api_contract.py` | Resolvido — F-79 |
| `docs/AB_TEST_PLAN.md` | ✅ `ab_service.py` implementado; plano e checklist atualizados | Resolvido — F-81 |
| `docs/ENV.md` | ✅ R2 como storage primário; variáveis documentadas | Resolvido — F-45 |
| `docs/DEV_SETUP.md` | ✅ Node.js 20+ e `npm run build:css` | Resolvido — F-49 |
| `docs/API.md` | ✅ URLs consistentes | Resolvido — F-47 |
| `docs/plans/confirmacao-solicitante.md` | ✅ Movido da raiz para `docs/plans/` | Resolvido — F-78 |

A verificação do billing e a atualização do INCIDENT_RUNBOOK.md foram concluídas na Semana 1/5 do sprint (S5-01, F-40).

---

## 9. Glossário

| Termo | Significado simples |
|---|---|
| **Lint / ruff** | Ferramenta que revisa o código em busca de erros de estilo e problemas comuns, como um "corretor ortográfico" para programadores |
| **Bandit** | Ferramenta que analisa o código em busca de vulnerabilidades de segurança conhecidas |
| **pytest** | Ferramenta que executa os testes automatizados e verifica se o sistema funciona como esperado |
| **Cobertura de testes** | Percentual do código que é verificado pelos testes automatizados. Quanto maior, menor o risco de bugs passarem despercebidos |
| **CSRF** | Ataque que tenta fazer o sistema executar ações em nome de um usuário sem o conhecimento dele. A proteção CSRF impede isso |
| **Rate limiting** | Limite de quantas vezes um usuário pode acessar uma função em um período de tempo, impedindo ataques automatizados |
| **Magic bytes** | Verificação do conteúdo real de um arquivo para confirmar que ele é do tipo que diz ser (ex: um arquivo .pdf realmente contém um PDF) |
| **Firestore** | Banco de dados em nuvem do Google, onde são armazenados todos os dados do sistema |
| **Docker** | Tecnologia que empacota o sistema em container isolado — plataforma de deploy atual |
| **Cloudflare R2** | Servico de armazenamento de arquivos (anexos) em nuvem, similar ao Google Drive mas para sistemas |
| **Microsoft Graph API** | API da Microsoft usada pelo sistema para envio de e-mails transacionais via Microsoft 365 |
| **Redis** | Sistema de armazenamento rápido em memória usado para controlar limites de acesso e cache |
| **APScheduler** | Componente responsável por executar tarefas automáticas em horários programados (ex: envio de relatórios semanais) |
| **IP spoofing** | Técnica usada por atacantes para falsificar o endereço de rede de origem e enganar sistemas de segurança |
| **Race condition** | Situação em que dois processos simultâneos interferem um no outro por acessar os mesmos dados ao mesmo tempo, causando resultados incorretos |
| **Transação atômica** | Operação do banco de dados que garante que uma sequência de passos seja executada de forma indivisível — nenhum outro processo pode interferir no meio |
| **HTML injection** | Técnica de inserir código HTML malicioso em páginas ou e-mails que não tratam corretamente o conteúdo enviado pelo usuário |
| **Thread / multi-thread** | Forma de o servidor processar múltiplas requisições ao mesmo tempo. Sem proteção adequada, threads simultâneas podem corromper dados compartilhados |
| **Lock (trava de thread)** | Mecanismo que garante que apenas um processo por vez acessa um recurso compartilhado |
| **window.prompt** | Janela de diálogo nativa do navegador, bloqueada por padrão em muitos contextos modernos e inacessível a tecnologias assistivas |
| **Blueprint** | Forma de organizar rotas (URLs) em módulos separados dentro do Flask |
| **Deploy** | Processo de publicar uma nova versão do sistema em produção |
| **Docker** | Tecnologia que empacota o sistema e todas as suas dependências em um contêiner isolado e portátil |
| **IDOR** | Vulnerabilidade que permite a um usuário acessar dados de outro usuário manipulando identificadores na URL |
| **LGPD** | Lei Geral de Proteção de Dados — lei brasileira que regula o uso de dados pessoais |
| **PII** | Informação de Identificação Pessoal — dados que identificam uma pessoa (nome, e-mail, CPF, etc.) |
| **Gamificação** | Sistema de pontuação e ranking para engajar usuários nas atividades do sistema |
| **SLO** | Service Level Objective — meta de disponibilidade e desempenho do sistema |
| **Worker / Gunicorn** | Processo do servidor que atende às requisições dos usuários. Múltiplos workers atendem mais usuários simultaneamente |
| **VAPID / Web Push** | Tecnologia que permite ao servidor enviar notificações ao navegador do usuário mesmo quando a aba do sistema está fechada |
| **Service Worker** | Script que roda em segundo plano no navegador, responsável por receber e exibir notificações push |
| **Cloud Run** | Plataforma de hospedagem do Google Cloud — usada anteriormente, substituída por Docker |
| **False positive (teste)** | Teste que deveria detectar um problema mas passa sempre — geralmente por um assert incorreto que nunca falha |
| **Tautologia** | Em lógica, uma expressão que é sempre verdadeira, independentemente dos valores das variáveis (ex: `A ou não-A`). Em testes, significa um assert que nunca falha, dando falsa garantia de qualidade ao módulo testado |
| **Token CSS** | Variável CSS que armazena um valor de design (cor, espaçamento, sombra) de forma centralizada — permite mudar o visual do sistema em um único lugar sem alterar cada arquivo individualmente |
| **Dry-run** | Modo de execução de um script que simula as operações sem efetivamente realizá-las — permite verificar o impacto antes de confirmar a execução real com `--apply` ou equivalente |
| **Artefato de build** | Arquivo gerado automaticamente durante o processo de compilação ou build (ex: `tailwind.min.css`, bundle JS minimizado). Geralmente não deveria ser commitado no repositório git pois pode ser regenerado |
| **Design token** | Sinônimo de token CSS neste contexto — variável que centraliza valores do design system (cores, tipografia, espaçamentos) para garantir consistência visual em todo o sistema |

---

*Documento atualizado em 2026-06-17 — DTX Aerospace, Engenharia de Software*
*Versão 3.1 — Incorpora achados da 3ª rodada (F-50 a F-82) + resolução de F-15 + admin_global + Graph API*
*Próxima auditoria recomendada: 2026-09-16*
