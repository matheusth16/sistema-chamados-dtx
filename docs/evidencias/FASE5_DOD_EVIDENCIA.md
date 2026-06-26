# FASE 5 — Perfil Gestor + Dashboard Read-Only: Evidência DoD

**Data de conclusão:** 2026-06-25
**Implementado por:** Matheus Costa + Claude Sonnet 4.6

---

## Resumo executivo

A Fase 5 adiciona o campo `nivel_gestao` no modelo `Usuario`, dois novos decoradores de acesso (`@requer_gestor`, `@requer_gestor_ou_admin`), bloqueio de mutações para gestores (fail-closed), a rota `GET /gestor/dashboard` com template read-only, integração no login redirect e navbar, o campo `nivel_gestao` no form de admin de usuários e o bloco `GESTOR_EMAILS` em `config.py` (prep Fase 6).

---

## Checklist de aceite

### Funcional

- [x] `nivel_gestao` persiste Firestore (to_dict/from_dict) — valores inválidos → None
- [x] Gestor acessa `/gestor/dashboard`; supervisor comum recebe 302 redirect
- [x] Admin acessa `/gestor/dashboard` e mantém edição operacional
- [x] Gestor recebe 403/redirect ao tentar `POST /api/atualizar-status` (via `verificar_permissao_mudanca_status`)
- [x] `supervisor_pode_alterar_chamado` retorna False para gestor_only
- [x] `editar_chamado_pagina` redireciona gestor_only para `/gestor/dashboard`
- [x] Dashboard gestor exibe filtros: atrasados, Aberto sem resposta, multi-setor travado
- [x] Template gestor sem checkboxes, select de status, botões de ação
- [x] `pode_editar=False` em `visualizar_detalhe_chamado` para gestor_only
- [x] Admin consegue atribuir `nivel_gestao` no form de usuário (`editar_usuario`)
- [x] `GESTOR_EMAILS` parseado em `config.py` (default: `{}`, JSON inválido → `{}`)
- [x] Supervisor com `nivel_gestao` redirecionado para `/gestor/dashboard` após login
- [x] Link "Painel Gerencial" na navbar visível para gestor e admin
- [x] `usuario_pode_ver_chamado` retorna True para gestor (visão ampliada)

### Qualidade

| Gate | Resultado |
|------|-----------|
| `pytest --tb=short -q` | ✅ **1831 passed** (0 failed) |
| Testes novos Fase 5 | ✅ **22 passed** |
| `ruff check app/ tests/ --fix` | ✅ sem violações |
| `ruff format app/ tests/` | ✅ sem mudanças pendentes |
| `bandit -r app/ -ll` | ✅ sem alertas |
| Coverage gate (54 módulos >= 85%) | ✅ **54/54 OK** |

---

## Arquivos criados

| Arquivo | Descrição |
|---------|-----------|
| `app/services/gestor_dashboard_service.py` | Serviço read-only com filtros atrasados/aberto/multi-setor |
| `app/templates/gestor_dashboard.html` | Template read-only (sem dark:, sem botões de ação) |
| `tests/test_routes/test_gestor_dashboard.py` | 7 testes de rota (acesso, filtro, bloqueio) |

## Arquivos modificados

| Arquivo | Mudança |
|---------|---------|
| `app/models_usuario.py` | `nivel_gestao`, `is_gestor`, `is_gestor_only`, `NIVEIS_GESTAO_VALIDOS` |
| `app/decoradores.py` | `@requer_gestor`, `@requer_gestor_ou_admin` |
| `app/services/permission_validation.py` | Bloqueio gestor_only em `verificar_permissao_mudanca_status` e `supervisor_pode_alterar_chamado` |
| `app/services/permissions.py` | Gestor vê chamados ampliado (read-only) |
| `app/routes/dashboard.py` | Rota `GET /gestor/dashboard`, bloqueio gestor em `editar_chamado_pagina`, `pode_editar` |
| `app/routes/auth.py` | Login redirect gestor → `/gestor/dashboard` |
| `app/routes/usuarios.py` | Campo `nivel_gestao` na edição de usuário |
| `app/templates/components/navbar.html` | Link "Painel Gerencial" para gestor/admin |
| `app/templates/usuario_form.html` | Select `nivel_gestao` no form admin |
| `config.py` | `GESTOR_EMAILS`, `get_gestor_email()` |
| `.env.example` | Documentação `GESTOR_EMAILS` |
| `tests/conftest.py` | `client_logado_gestor` fixture; `is_gestor=False`, `is_gestor_only=False` nos mocks |
| `tests/test_services/test_models_usuario.py` | 8 testes nivel_gestao |
| `tests/test_services/test_permission_validation.py` | 3 testes bloqueio gestor |
| `tests/test_config_production.py` | 4 testes GESTOR_EMAILS |
| `docs/MATRIZ_ROTAS_PERFIL.md` | `/gestor/dashboard` movido de [planejado] para implementado |
| `app/translations.json` | Chave `nav_management_board` (PT/EN/ES) |

---

## Decisões técnicas

1. **`is True` em vez de truthy** — `MagicMock()` retorna objetos truthy para qualquer atributo não explicitamente setado. Todo check de `is_gestor` e `is_gestor_only` usa `getattr(user, "prop", None) is True` para não quebrar testes com mocks legados.

2. **`nivel_gestao` em lista fechada (`NIVEIS_GESTAO_VALIDOS`)** — valores inválidos são silenciosamente normalizados para `None` no `__init__` (fail-safe, sem exception).

3. **`gestor_dashboard_service.py` independente** — sem filtro de área (gestor vê tudo); reuso de `Chamado.from_dict`; limita query a 500 docs na v1.

4. **`pode_editar` com `is True` não usado** — `getattr(current_user, "is_gestor_only", False)` na rota Flask trabalha com o objeto real (não MagicMock), então truthy check simples é seguro.

---

## Restrições mantidas

- Não implementada Fase 6–8 (sla_escalacao_service, job scheduler, Escada B)
- Não criado perfil Firestore "gestor" — `nivel_gestao` no doc existente
- Isolamento supervisor (Fase 2) intacto no `/painel` operacional
- Sem `editar_chamado_service` refatorado além do mínimo necessário

---

## Limitações conhecidas v1

### `_is_aberto_sem_resposta` — ~~60 minutos corridos, não úteis~~ — **RESOLVIDO na Fase 6**

> **Resolução (2026-06-25):** `_is_aberto_sem_resposta` em `gestor_dashboard_service.py` foi
> refatorado na Fase 6 para usar `business_time.minutos_uteis_entre(data_abertura, agora) >= 60`.
> A função auxiliar wall-clock `_minutos_desde` foi removida. Ver `FASE6_DOD_EVIDENCIA.md §Task 6.4`.

~~**Localização:** `app/services/gestor_dashboard_service.py:_is_aberto_sem_resposta`~~

~~O filtro "Aberto sem resposta" usa 60 minutos de relógio (wall-clock via `_minutos_desde`) como proxy para "1 hora útil sem atendimento". Consequências:~~

~~- Um chamado aberto às 16:29 (59 min antes do fim do expediente) aparece como "sem resposta" às 17:29, mesmo que o expediente tenha encerrado às 16:30.~~
~~- Chamados abertos na madrugada ou no fim de semana são marcados imediatamente ao completar 60 min, ignorando que não há expediente.~~

~~**Correção planejada (Fase 6):** substituir `_minutos_desde(data_abertura) >= 60` por `business_time.minutos_uteis_entre(data_abertura, now) >= 60`, usando o mesmo motor SLA da Escada A.~~

---

## Lacunas pós-revisão fechadas

**Data:** 2026-06-25
**Gate final:** 1874 passed (0 failed) | ruff CLEAN | bandit 0 High/Medium | 54/54 módulos >= 85%

### Lacuna 1 — POST /api/bulk-status bypassa read-only
- **Fix:** bloqueio imediato (`is_gestor_only is True → 403`) antes do loop em `bulk_atualizar_status` (`app/routes/api.py`)
- **Testes:** `test_gestor_bulk_status_retorna_403`, `test_supervisor_bulk_status_nao_regrediu`

### Lacuna 2 — POST /painel e /admin bypassam read-only
- **Fix:** check `is_gestor_only` no início do bloco POST de `_render_dashboard` (`dashboard.py`) → redirect 302 para `/gestor/dashboard` sem chamar `atualizar_status_chamado`
- **Testes:** `test_gestor_post_painel_nao_altera_status`

### Lacuna 3 — Gestor acessa /painel operacional (GET)
- **Fix:** redirect preemptivo em `painel()` (`dashboard.py`) + navbar oculta link `/painel` para `is_gestor_only` via `{% if not current_user.is_gestor_only %}`
- **Testes:** `test_gestor_get_painel_redireciona_gestor_dashboard`

### Lacuna 5 — POST /api/editar-chamado bypassa read-only

- **Problema:** `api_editar_chamado` verificava apenas `is_supervisor_or_above` (True para gestor), permitindo que gestores mutassem chamados via API direta, bypassando `pode_editar=False` na UI.
- **Fix rota:** bloqueio imediato (`is_gestor_only is True → 403`) em `api_editar_chamado` (`app/routes/api.py`), mesmo padrão de `bulk_atualizar_status`
- **Fix serviço (defesa em profundidade):** chamada a `usuario_pode_mutar_chamado(usuario_atual)` no início de `processar_edicao_chamado` (`app/services/edicao_chamado_service.py`) — antes de qualquer acesso ao Firestore
- **Testes:** `test_gestor_api_editar_chamado_retorna_403`, `test_supervisor_api_editar_chamado_nao_regrediu` (em `test_api_gaps.py`) + `test_processar_edicao_chamado_bloqueia_gestor_defesa_em_profundidade` (em `test_permission_validation.py`)

### Lacuna 4 — Rotas de escalonamento sem bloqueio gestor
- **Fix:** novo helper `usuario_pode_mutar_chamado` em `permission_validation.py` + chamado nas 4 rotas: `api_transferir_area`, `api_escalonar_colega`, `api_incluir_participantes`, `api_concluir_minha_parte`
- **Testes:** `test_gestor_transferir_area_403`, `test_gestor_escalonar_colega_403`, `test_gestor_incluir_participantes_403`, `test_gestor_concluir_minha_parte_403_mesmo_sendo_participante`

### Arquivos alterados nas lacunas
| Arquivo | Mudança |
|---------|---------|
| `app/services/permission_validation.py` | +`usuario_pode_mutar_chamado` helper central |
| `app/routes/api.py` | +bloqueio gestor em `bulk_atualizar_status` e nas 4 rotas de escalonamento |
| `app/routes/dashboard.py` | +bloqueio POST em `_render_dashboard` + redirect GET em `painel()` |
| `app/templates/components/navbar.html` | link `/painel` oculto para `is_gestor_only` |
| `tests/test_routes/test_api_gaps.py` | +11 testes gestor (Lacunas 1–5) |
| `tests/test_services/test_permission_validation.py` | +6 testes: `usuario_pode_mutar_chamado` + defesa em profundidade `processar_edicao_chamado` |

### Checklist de aceite — lacunas
- [x] Gestor não altera status via POST /api/bulk-status
- [x] Gestor não altera status via POST /painel
- [x] Gestor não acessa /painel operacional (GET redirect)
- [x] Gestor não executa transferir/escalonar/incluir-participantes/concluir-minha-parte
- [x] Admin e supervisor comum não regrediram
- [x] Navbar: gestor-only não vê link operacional /painel
- [x] Gestor não muta chamados via POST /api/editar-chamado (rota + serviço bloqueiam)
- [x] Testes novos passando (11 em test_api_gaps.py + 6 em test_permission_validation.py)
