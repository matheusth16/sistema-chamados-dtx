# Matriz Rota × Perfil — sistema_chamados

> Artefato CWI 1.2 — gerado em 2026-06-22
> **Onda 6 (Escalonamento + SLA Gerencial) — Aceite Fase 8: 2026-06-26 — 1930 testes passando, gate 54/54 módulos ≥ 85%**
> Fonte: `app/routes/*.py` (decoradores e checks inline)

## Legenda

| Símbolo | Significado |
|---------|-------------|
| ✅ | Acesso permitido |
| ❌ | Acesso negado (403 ou redirect) |
| — | Sem restrição de perfil (apenas autenticação) |
| † | Check inline adicional após o decorador |

## Rotas públicas (sem autenticação)

| Rota | Métodos | Decorador(es) | Observação |
|------|---------|---------------|------------|
| `/login` | GET, POST | `@limiter.limit("10 per minute", methods=["POST"])` | Rate limit apenas em POST |
| `/sw.js` | GET | — | Service worker |
| `/health` | GET | — | Health-check |
| `/api/csp-report` | POST | `@limiter.limit("20 per minute", methods=["POST"])` | CSP violation report; sem auth |

## Rotas autenticadas — todos os perfis

| Rota | Métodos | Decorador(es) | Perfis | Obs. |
|------|---------|---------------|--------|------|
| `/logout` | GET | `@login_required` | solicitante, supervisor, admin, admin_global | |
| `/alterar-senha-obrigatoria` | GET, POST | `@login_required` | solicitante, supervisor, admin, admin_global | |
| `/chamado/<chamado_id>` | GET | `@login_required` | todos autenticados† | Check inline: `usuario_pode_ver_chamado` — solicitante só vê o próprio; supervisor só vê da sua área |
| `/api/notificacoes` | GET | `@login_required` | todos autenticados | |
| `/api/notificacoes/contar` | GET | `@login_required` | todos autenticados | |
| `/api/notificacoes/<id>/ler` | POST | `@login_required` | todos autenticados | |
| `/api/notificacoes/ler-todas` | POST | `@login_required` | todos autenticados | |
| `/api/push-vapid-public` | GET | `@login_required` | todos autenticados | |
| `/api/push-subscribe` | POST | `@login_required` | todos autenticados | |
| `/api/chamado/<chamado_id>` | GET | `@login_required` | todos autenticados† | Check inline: `usuario_pode_ver_chamado` (IDOR guard) |
| `/api/chamados/paginar` | GET | `@login_required` | todos autenticados† | `_aplicar_filtro_perfil`: solicitante→próprios; supervisor→áreas; supervisor sem áreas→lista vazia |
| `/api/carregar-mais` | POST | `@login_required` | todos autenticados† | Mesma lógica de `_aplicar_filtro_perfil` |
| `/api/atualizar-status` | POST | `@login_required`, `@limiter.limit("30 per minute")` | todos autenticados† | Check inline: `verificar_permissao_mudanca_status` — solicitante só cancela o próprio; supervisor só sua área |
| `/api/chamado/<id>/confirmar-resolucao` | POST | `@login_required` | solicitante† | Check inline: `perfil == "solicitante"` e `solicitante_id == current_user.id` |
| `/api/onboarding/avancar` | POST | `@login_required` | todos autenticados | |
| `/api/onboarding/concluir` | POST | `@login_required` | todos autenticados | |
| `/api/onboarding/pular` | POST | `@login_required` | todos autenticados | |
| `/api/supervisores/lista` | GET | `@login_required` | todos autenticados | Filtra `u.id != current_user.id` (anti-self-ticket) |

## Rotas exclusivas do solicitante

| Rota | Métodos | Decorador(es) | Perfis |
|------|---------|---------------|--------|
| `/` | GET, POST | `@requer_solicitante` | solicitante |
| `/meus-chamados` | GET | `@requer_solicitante` | solicitante |

> `@requer_solicitante` bloqueia supervisor e admin (redirect para `/painel` ou `/admin`).

## Rotas supervisor ou acima

| Rota | Métodos | Decorador(es) | Perfis |
|------|---------|---------------|--------|
| `/admin` | GET, POST | `@requer_supervisor_area` | supervisor, admin, admin_global |
| `/painel` | GET, POST | `@requer_supervisor_area` | supervisor, admin, admin_global |
| `/chamado/<id>/historico` | GET | `@requer_supervisor_area` | supervisor, admin, admin_global |
| `/exportar` | GET | `@requer_supervisor_area` | supervisor, admin, admin_global |
| `/exportar-avancado` | GET | `@requer_supervisor_area` | supervisor, admin, admin_global |
| `/admin/relatorios` | GET | `@requer_supervisor_area` | supervisor, admin, admin_global |
| `/chamado/editar` | POST | `@login_required`† | supervisor, admin, admin_global | Check inline: `is_supervisor_or_above` + `usuario_pode_ver_chamado` |
| `/api/editar-chamado` | POST | `@login_required`† | supervisor, admin, admin_global | Check inline: `is_supervisor_or_above` |
| `/api/bulk-status` | POST | `@login_required`, `@limiter.limit("10 per minute")`† | supervisor, admin, admin_global | Check inline: `is_supervisor_or_above`; supervisor limitado à própria área |

## Rotas admin ou acima

| Rota | Métodos | Decorador(es) | Perfis |
|------|---------|---------------|--------|
| `/admin/usuarios` | GET, POST | `@requer_perfil("admin")` | admin, admin_global |
| `/admin/usuarios/novo` | GET | `@requer_perfil("admin")` | admin, admin_global |
| `/admin/usuarios/<id>/editar` | GET, POST | `@requer_perfil("admin")` | admin, admin_global |
| `/admin/usuarios/<id>/deletar` | POST | `@requer_perfil("admin")` | admin, admin_global |
| `/admin/usuarios/<id>/resetar-senha` | POST | `@requer_perfil("admin")` | admin, admin_global |
| `/admin/usuarios/<id>/desativar` | POST | `@requer_perfil("admin")` | admin, admin_global |
| `/admin/usuarios/<id>/ativar` | POST | `@requer_perfil("admin")` | admin, admin_global |
| `/admin/usuarios/<id>/reset-exp` | POST | `@requer_perfil("admin")` | admin, admin_global |
| `/admin/categorias` | GET | `@requer_perfil("admin")` | admin, admin_global |
| `/admin/categorias/setor/nova` | POST | `@requer_perfil("admin")` | admin, admin_global |
| `/admin/categorias/gate/nova` | POST | `@requer_perfil("admin")` | admin, admin_global |
| `/admin/categorias/impacto/nova` | POST | `@requer_perfil("admin")` | admin, admin_global |
| `/admin/categorias/setor/<id>/editar` | POST | `@requer_perfil("admin")` | admin, admin_global |
| `/admin/categorias/setor/<id>/excluir` | POST | `@requer_perfil("admin")` | admin, admin_global |
| `/admin/categorias/gate/<id>/editar` | POST | `@requer_perfil("admin")` | admin, admin_global |
| `/admin/categorias/gate/<id>/excluir` | POST | `@requer_perfil("admin")` | admin, admin_global |
| `/admin/categorias/impacto/<id>/editar` | POST | `@requer_perfil("admin")` | admin, admin_global |
| `/admin/categorias/impacto/<id>/excluir` | POST | `@requer_perfil("admin")` | admin, admin_global |
| `/admin/indices-firestore` | GET | `@login_required`, `@requer_perfil("admin")` | admin, admin_global |

> `@requer_perfil("admin")` auto-expande para incluir `admin_global` (ver `app/decoradores.py`).

## Rotas exclusivas do admin_global

| Rota | Métodos | Decorador(es) | Perfis |
|------|---------|---------------|--------|
| `/admin-global` | GET | `@login_required`† | admin_global | Check inline: `perfil == "admin_global"` |
| `/admin-global/admins/<id>/rebaixar` | POST | `@login_required`† | admin_global | Check inline: `perfil == "admin_global"` |
| `/admin-global/admins/<id>/promover` | POST | `@login_required`† | admin_global | Check inline: `perfil == "admin_global"` |

> Nota: essas rotas usam `@login_required` + guard inline em vez de `@requer_admin_global` porque `requer_perfil("admin_global")` não expande para `admin` — é intencional.

## Mapeamento perfil → rotas acessíveis

| Perfil | Grupos de acesso |
|--------|-----------------|
| `solicitante` | Público + Autenticados + Solicitante |
| `supervisor` | Público + Autenticados + Supervisor-ou-acima |
| `admin` | Público + Autenticados + Supervisor-ou-acima + Admin-ou-acima |
| `admin_global` | Todos os grupos acima + Admin-global exclusivo |
| `gestor` (nível_gestao) | Público + Autenticados + `/gestor/dashboard` (read-only) |

---

## Rotas implementadas — Onda Escalonamento (ADR-004) `[Fase 3 ✓]`

### Rotas de escalonamento — supervisor ou acima

| Rota | Método | Decorador | Perfis | Checks inline |
|------|--------|-----------|--------|---------------|
| `/api/chamado/<id>/transferir-area` | POST | `@requer_supervisor_area` | supervisor (owner), admin, admin_global | `usuario_pode_ver_chamado` (owner ou admin); `supervisor_id` destino obrigatório; `motivo` não vazio; invariante anti-órfão; serviço: `escalonamento_service.transferir_area` |
| `/api/chamado/<id>/escalonar-colega` | POST | `@requer_supervisor_area` | supervisor (owner), admin, admin_global | `usuario_pode_ver_chamado`; `supervisor_id` destino obrigatório; `motivo` não vazio; destino ≠ atual; área inalterada; serviço: `escalonamento_service.escalonar_colega` |

## Rotas Fase 4 — Multi-setor com Participantes (implementado 2026-06-25)

### Rotas de participantes — supervisor ou acima / participante

| Rota | Método | Decorador | Perfis | Checks inline |
|------|--------|-----------|--------|---------------|
| `/api/chamado/<id>/incluir-participantes` | POST | `@requer_supervisor_area` | supervisor (owner), admin, admin_global | `usuario_pode_ver_chamado`; `responsavel_id == current_user.id OR is_admin_or_above`; lista não vazia; cada `supervisor_id` pertence à `area`; owner não incluído como participante; sem duplicação |
| `/api/chamado/<id>/concluir-minha-parte` | POST | `@login_required` | supervisor participante | `current_user.id in participantes[*].supervisor_id`; status participante `!= "concluido"` |

## Rotas Fase 5 — Perfil Gestor `[implementado 2026-06-25]`

### Rota de dashboard gerencial — gestor ou admin

| Rota | Método | Decorador | Perfis | Obs. |
|------|--------|-----------|--------|------|
| `/gestor/dashboard` | GET | `@login_required` + `@requer_gestor_ou_admin` | supervisor com `nivel_gestao`, admin, admin_global | Read-only; sem ações de edição de status; filtros: atrasados, Aberto sem resposta, multi-setor travado |

**Bloqueios write implementados (gestor_only):**
- `verificar_permissao_mudanca_status` → retorna False se `is_gestor_only`
- `supervisor_pode_alterar_chamado` → retorna False se `is_gestor_only`
- `editar_chamado_pagina` → redireciona para `/gestor/dashboard`
- `pode_editar = False` em `visualizar_detalhe_chamado` para gestor_only

### Comportamento de visibilidade pós-implementação (Fase 2)

Após a Fase 2, a função `usuario_pode_ver_chamado` em `app/services/permissions.py` e o filtro `_aplicar_filtro_perfil` em `app/routes/api.py` passarão a usar a lógica composta:

| Condição | Supervisor vê? | Admin vê? | Gestor vê? |
|----------|---------------|-----------|------------|
| `responsavel_id == user.id` | Sim (owner) | Sim | Sim (read-only) |
| `area in user.areas AND responsavel_id is None` | Sim (fila) | Sim | Sim (read-only) |
| `user.id in participantes[*].supervisor_id` | Sim (participante) | Sim | Sim (read-only) |
| Outro supervisor da mesma área como owner | **Não** | Sim | Sim (read-only) |

### Campos de modelo novos a gravar (documentar, não implementar aqui)

```python
# Firestore — documento chamados
data_em_atendimento           # datetime — set ao 1º Em Atendimento; nada reseta
escalacao_resposta_nivel      # int 0–4 — Escada A (congelado ao virar Em Atendimento)
escalacao_resolucao_nivel     # int 0–4 — Escada B pós-estouro deadline
alerta_supervisor_50_enviado  # bool | datetime — idempotência aviso 50%
alerta_supervisor_80_enviado  # bool | datetime — idempotência aviso 80%
participantes                 # list[{supervisor_id, area, status, concluido_em}]
motivo_ultima_escalacao       # str — motivo da última ação formal

# Firestore — documento usuarios
nivel_gestao                  # str | None — gestor_setor | gerente_producao | assistente_gm | gm
```

### Decoradores novos a criar (Fase 5)

| Decorador | Arquivo | Comportamento |
|-----------|---------|---------------|
| `@requer_gestor` | `app/decoradores.py` | Exige `current_user.nivel_gestao is not None`; redirect 403 senão |
| `@requer_gestor_ou_admin` | `app/decoradores.py` | `nivel_gestao is not None` OR `perfil in ("admin", "admin_global")` |
