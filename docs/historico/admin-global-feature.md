# Admin Global — Nova Camada de Acesso Privilegiado

## Goal
Criar o perfil `admin_global` acima do `admin` atual. Apenas Matheus terá esse perfil.
Sub-admins (`admin`) mantêm tudo que têm hoje. Rotas exclusivas do admin_global ficam
completamente invisíveis e inacessíveis a qualquer outro perfil — incluindo outros admins.

---

## Decisões arquiteturais (antes de codificar)

| Decisão | Escolha | Motivo |
|---|---|---|
| Nome do perfil | `"admin_global"` | Segue convenção do projeto (snake_case PT) |
| Herança de permissão | `admin_global` recebe tudo de `admin` automaticamente | Sem duplicação de decoradores |
| Como fazer a herança | `requer_perfil` expande `"admin"` → `["admin", "admin_global"]` internamente | 1 linha no decorador, zero mudança nas rotas existentes |
| Acesso a rotas inline (templates/routes) | Propriedades `is_admin_or_above`, `is_supervisor_or_above` no modelo | Elimina strings hardcoded espalhadas |
| Quem cria `admin_global` | Só via script Python direto no Firestore — nunca via UI | Garante que só 1 usuário terá esse perfil |
| Criar outros `admin_global` via UI | Impossível — o form de usuários só permite até `admin` | Isolamento total |

---

## Contexto do código atual relevante

- `app/decoradores.py` — `requer_perfil("admin")` é o guard de todas as rotas admin
- `app/routes/usuarios.py:58,149` — validação de perfil no form: `["solicitante", "supervisor", "admin"]` (não inclui `admin_global` — correto)
- `app/routes/auth.py:89,153` — bypass de must_change_password checado via `perfil == "admin"`
- `app/routes/api.py:188,247` e `app/routes/dashboard.py` — inline checks `perfil not in ("supervisor", "admin")`
- `app/templates/components/navbar.html:38,74,79,219` — `perfil == 'admin'` para mostrar links

---

## Tasks

- [ ] **T1 — RED (testes):** Escrever testes falhando antes de qualquer código
  - Arquivo: `tests/test_routes/test_admin_global.py`
  - Cobrir: GET `/admin-global` retorna 200 para `admin_global` e 403 para `admin`/`supervisor`/`solicitante`
  - Cobrir: `is_admin_or_above` e `is_supervisor_or_above` no modelo
  - Cobrir: `requer_perfil("admin")` também aceita `admin_global`
  - Verificar: `pytest tests/test_routes/test_admin_global.py` → todos falham (RED)

- [ ] **T2 — Modelo:** `app/models_usuario.py`
  - Linha 39: comentário `# 'solicitante', 'supervisor', 'admin' ou 'admin_global'`
  - Adicionar 2 properties: `is_admin_or_above` → `perfil in ("admin", "admin_global")` e `is_supervisor_or_above` → `perfil in ("supervisor", "admin", "admin_global")`
  - Verificar: `pytest tests/test_services/test_models_usuario.py` passa

- [ ] **T3 — Decorador:** `app/decoradores.py`
  - Em `requer_perfil`: logo após montar `perfis_lista`, se `"admin"` estiver nela → adicionar `"admin_global"` automaticamente
  - Em `requer_supervisor_area`: trocar `["supervisor", "admin"]` → `["supervisor", "admin", "admin_global"]`
  - Em `requer_solicitante`: trocar `("solicitante", "supervisor", "admin")` → adicionar `"admin_global"`
  - Verificar: `pytest tests/` — nenhum teste existente deve quebrar

- [ ] **T4 — Inline checks nas rotas:** substituir strings hardcoded por properties do modelo
  - `app/routes/api.py:188,247` — `perfil not in ("supervisor", "admin")` → `not current_user.is_supervisor_or_above`
  - `app/routes/auth.py:89,153` — `perfil != "admin"` / `perfil == "admin"` → `.is_admin_or_above`
  - `app/routes/dashboard.py` — todos os `perfil in ("supervisor", "admin")` → `is_supervisor_or_above`
  - Verificar: `pytest --tb=short -q` — 1001+ testes passando

- [ ] **T5 — Rotas exclusivas:** `app/routes/admin_global.py` (arquivo novo)
  - Decorator novo: `requer_admin_global` = `requer_perfil("admin_global")` (sem expansão automática)
  - `GET /admin-global` — dashboard com: total de usuários por perfil, total de chamados, lista de sub-admins
  - `GET /admin-global/admins` — listar e gerenciar todos os `admin` (o que sub-admins não podem ver)
  - `POST /admin-global/admins/<id>/promover` — promover `supervisor`→`admin` (exclusivo)
  - `POST /admin-global/admins/<id>/rebaixar` — admin→supervisor (exclusivo)
  - Registrar blueprint em `app/routes/__init__.py`
  - Verificar: GET `/admin-global` com `client_logado_admin` retorna 403

- [ ] **T6 — Template:** `app/templates/admin_global.html`
  - Herda de `base.html`
  - Banner visual distinto (badge "Admin Global", cor diferente do admin normal)
  - Cards: Total usuários, Total chamados, Sub-admins ativos
  - Tabela de sub-admins com ações de promover/rebaixar
  - Verificar: renderiza sem erro no contexto de `admin_global`

- [ ] **T7 — Navbar:** `app/templates/components/navbar.html`
  - Trocar `perfil == 'admin'` → `current_user.is_admin_or_above` (4 ocorrências: linhas 38, 74, 79, 219)
  - Adicionar link "Admin Global" visível **somente** para `current_user.perfil == 'admin_global'`
  - Verificar: login como admin não vê o link; login como admin_global vê

- [ ] **T8 — Proteger criação de admin via form:** `app/routes/usuarios.py`
  - Linhas 58 e 149: se `perfil == "admin"` e `current_user.perfil != "admin_global"` → retornar erro 403
  - Sub-admins só podem criar `solicitante` e `supervisor`
  - Verificar: POST `/admin/usuarios` com `perfil=admin` por sub-admin → flash de erro

- [ ] **T9 — Script de promoção:** `scripts/promover_admin_global.py`
  - Arg: `--email matheus00237@gmail.com`
  - Busca usuário no Firestore, atualiza `perfil = "admin_global"`
  - Exige confirmação interativa antes de gravar
  - Verificar: `python scripts/promover_admin_global.py --email matheus00237@gmail.com --dry-run` mostra o que faria

- [ ] **T10 — Qualidade e commit:**
  - `ruff check app/ tests/ --fix && ruff format app/ tests/`
  - `bandit -r app/ -ll`
  - `pytest --tb=short -q`
  - Commit: `feat(auth): perfil admin_global com rotas exclusivas e proteção de sub-admins`

---

## Done When

- [ ] `GET /admin-global` → 200 para `admin_global`, 403 para `admin`
- [ ] Sub-admin não consegue criar outro admin via formulário
- [ ] Admin global vê link exclusivo na navbar; admin normal não vê
- [ ] `requer_perfil("admin")` aceita `admin_global` sem mudar nenhuma rota existente
- [ ] Script de promoção funciona com `--dry-run`
- [ ] 1001+ testes passando, ruff e bandit limpos

---

## Exclusivo para Admin Global (MVP)

| Feature | Rota |
|---|---|
| Dashboard sistêmico | `GET /admin-global` |
| Listar e gerenciar sub-admins | `GET /admin-global/admins` |
| Promover usuário → admin | `POST /admin-global/admins/<id>/promover` |
| Rebaixar admin → supervisor | `POST /admin-global/admins/<id>/rebaixar` |
| Criar novo usuário com perfil `admin` | via form `/admin/usuarios` (bloqueado para sub-admins) |

## Roadmap futuro (fora deste sprint)

- Auditoria de ações de admin (quem mudou status de qual chamado)
- Gestão multi-tenant (organizações separadas)
- Configurações globais do sistema via painel
- Forçar reset de senha de qualquer usuário (incluindo sub-admins)
