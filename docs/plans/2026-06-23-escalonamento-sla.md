# Escalonamento e SLA Gerencial — Implementation Plan

> **For Claude:** Implementar Fases 1–8 task-by-task (TDD). Usar skills `writing-plans` + `verification-before-completion` em cada fase.

**Goal:** Implementar isolamento por supervisor, colaboração multi-setor com participantes estruturados, motor de tempo útil DTX, Escadas A e B de SLA gerencial, perfil gestor e notificações completas (in-app + e-mail Graph API + Web Push) — conforme decisões fechadas no ADR-004.

**Architecture:** Novos serviços `business_time.py`, `escalonamento_service.py` e `sla_escalacao_service.py`; extensão de `permissions.py`, `status_service.py`, `dashboard_service.py` e `notifications.py`; job APScheduler a cada 10 min substituindo o diário; modelo `participantes[]` estruturado no Firestore substituindo `setores_adicionais`.

**Tech Stack:** Flask 3, Firestore (firebase-admin), APScheduler, Microsoft Graph API (e-mail), Web Push (`webpush_service.py`), pytest + unittest.mock

---

## Resumo executivo

### Contexto e lacunas

O sistema atual expõe todos os tickets de uma área para qualquer supervisor daquela área (`area in areas_do_usuario`). Dois supervisores da mesma área veem mutuamente os chamados um do outro. O campo `setores_adicionais: list[str]` não rastreia quem respondeu, qual status cada participante tem nem bloqueia o encerramento com partes pendentes. O SLA é calculado em dias corridos sem respeitar o expediente DTX (07:00–16:30, seg–sex, pausa almoço 11:30–13:00), gerando alertas inúteis fora de horário.

### O que será construído

| Fase | Componente | Arquivo principal |
|------|-----------|-------------------|
| 1 | Motor de tempo útil | `app/services/business_time.py` |
| 2 | Isolamento supervisor + claim | `app/services/permissions.py`, `status_service.py` |
| 3 | Transferir área + escalonar colega | `app/services/escalonamento_service.py` |
| 4 | Participantes multi-setor | `app/models.py`, `escalonamento_service.py` |
| 5 | Perfil gestor + dashboard | `app/models_usuario.py`, `app/routes/dashboard.py` |
| 6 | Escada A — resposta gerencial | `app/services/sla_escalacao_service.py` |
| 7 | Escada B — resolução + avisos | `app/services/sla_escalacao_service.py` |
| 8 | Aceite final + docs + QA | ciclo CLAUDE.md |

### Decisões fechadas (ADR-004) — não renegociar

- **Teto horário:** `16:30` (não 17:30) — evita alertas após saída da produção
- **Prazo resolução:** fixo desde `data_em_atendimento`; **nada reseta** (edições, anexos, "Concluí minha parte")
- **Visibilidade pós-transferência:** ex-owner perde acesso operacional; novo owner ganha imediatamente (invariante anti-órfão)
- **Sábado/domingo:** excluídos v1 (flag `SLA_INCLUI_FIM_DE_SEMANA` para exceções futuras)
- **Almoço 11:30–13:00:** relógio pausa; job não envia e-mail nesse intervalo
- **Notificações:** in-app + e-mail (Graph API) + Web Push em todas as escaladas e mudanças de participantes
- **Supervisor obrigatório** na criação quando a área tem supervisores cadastrados
- **Timezone:** todos os cálculos de SLA usam `America/Sao_Paulo` (BRT); datetimes naive nos testes representam horário local DTX — nunca UTC

### Dependências entre fases

```
F1[business_time] → F2[permissoes] → F3[transferir]
                                   → F4[participantes] → F8[Aceite]
                                   → F5[gestor]        → F8
               F1 → F6[EscadaA]   → F7[EscadaB]       → F8
               F2 → F6
```

**Ordem recomendada:** 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8
**Paralelização possível:** Fase 5 pode começar após Fase 2, em paralelo com Fases 3–4.

---

## Fase 1 — Motor de Tempo Útil

**Skills:** `writing-plans`, `verification-before-completion`
**Pré-requisito:** Fase 0 (esta documentação) concluída.

### Task 1.1: Constantes de configuração

**Arquivos:**
- Modificar: `config.py`
- Modificar: `.env.example`

**Passo 1: Adicionar bloco SLA em `config.py`**

```python
# SLA / Tempo útil DTX
SLA_HORARIO_INICIO = os.getenv("SLA_HORARIO_INICIO", "07:00")
SLA_HORARIO_FIM = os.getenv("SLA_HORARIO_FIM", "16:30")
SLA_ALMOCO_INICIO = os.getenv("SLA_ALMOCO_INICIO", "11:30")
SLA_ALMOCO_FIM = os.getenv("SLA_ALMOCO_FIM", "13:00")
SLA_DIAS_RESOLUCAO_PROJETOS = int(os.getenv("SLA_DIAS_RESOLUCAO_PROJETOS", "2"))
SLA_DIAS_RESOLUCAO_PADRAO = int(os.getenv("SLA_DIAS_RESOLUCAO_PADRAO", "3"))
SLA_ESCALADA_A_HORAS_UTEIS = [1, 2, 3, 4]
SLA_ESCALADA_B_HORAS_UTEIS = [0, 4, 8, 12]
SLA_INCLUI_FIM_DE_SEMANA = os.getenv("SLA_INCLUI_FIM_DE_SEMANA", "false").lower() == "true"
SLA_TIMEZONE = os.getenv("SLA_TIMEZONE", "America/Sao_Paulo")
```

**Passo 2: Documentar em `.env.example`** (adicionar seção `# SLA / Escalonamento` com todas as vars acima, incluindo `SLA_TIMEZONE=America/Sao_Paulo`)

**Passo 3: Confirmar testes existentes passando**
```
pytest --tb=short -q
```
Esperado: nenhum teste quebrado por adição de constante.

**Passo 4: Commit**
```
chore(config): Adicionar constantes SLA e tempo útil DTX
```

---

### Task 1.2: `dentro_janela_util` e `pode_enviar_notificacao_agora`

**Arquivos:**
- Criar: `app/services/business_time.py`
- Criar: `tests/test_services/test_business_time.py`

**Passo 1: Escrever testes falhando**

```python
from datetime import datetime
from app.services.business_time import dentro_janela_util, pode_enviar_notificacao_agora

def test_dentro_janela_util_manha():
    assert dentro_janela_util(datetime(2026, 6, 22, 9, 0)) is True   # segunda 09:00

def test_fora_janela_apos_teto_1630():
    assert dentro_janela_util(datetime(2026, 6, 22, 16, 31)) is False  # 16:31

def test_fora_janela_almoco():
    assert dentro_janela_util(datetime(2026, 6, 22, 12, 0)) is False   # 12:00

def test_fora_janela_sabado():
    assert dentro_janela_util(datetime(2026, 6, 20, 9, 0)) is False    # sábado

def test_dentro_janela_tarde():
    assert dentro_janela_util(datetime(2026, 6, 22, 14, 0)) is True    # tarde

def test_nao_envia_notificacao_sexta_1645():
    # Caso de negócio crítico: sexta 16:45 BRT → não disparar e-mail
    assert pode_enviar_notificacao_agora(datetime(2026, 6, 19, 16, 45)) is False

def test_nao_envia_notificacao_almoco():
    assert pode_enviar_notificacao_agora(datetime(2026, 6, 22, 11, 45)) is False

def test_envia_notificacao_dentro_janela():
    assert pode_enviar_notificacao_agora(datetime(2026, 6, 22, 10, 0)) is True

def test_sexta_1645_brt_fora_janela():
    # Garante que o timezone BRT (America/Sao_Paulo) é respeitado
    # sexta 2026-06-19 16:45 BRT deve retornar False (após teto 16:30)
    from zoneinfo import ZoneInfo
    dt_aware = datetime(2026, 6, 19, 16, 45, tzinfo=ZoneInfo("America/Sao_Paulo"))
    assert dentro_janela_util(dt_aware) is False
```

**Passo 2: Rodar e confirmar falha**
```
pytest tests/test_services/test_business_time.py -v
```
Esperado: `ImportError` (módulo não existe ainda).

**Passo 3: Implementar em `business_time.py`**

> **Timezone obrigatório:** toda entrada deve ser normalizada para BRT antes de extrair hora/weekday. Implementar helper interno `_as_local(dt: datetime) -> datetime`:
> - Se `dt` é naive: interpretar como BRT via `dt.replace(tzinfo=ZoneInfo(SLA_TIMEZONE))`
> - Se `dt` é aware: converter para BRT via `dt.astimezone(ZoneInfo(SLA_TIMEZONE))`
> Nunca usar `datetime.utcnow()` — usar `datetime.now(ZoneInfo(SLA_TIMEZONE))`.

Lógica de `dentro_janela_util(dt: datetime) -> bool`:
1. Normalizar `dt` → BRT via `_as_local(dt)`
2. Se `dt.weekday() >= 5` (sáb/dom) → `False`
3. Se hora < `SLA_HORARIO_INICIO` ou hora >= `SLA_HORARIO_FIM` → `False`
4. Se `SLA_ALMOCO_INICIO` <= hora < `SLA_ALMOCO_FIM` → `False`
5. Senão → `True`

`pode_enviar_notificacao_agora` é alias direto de `dentro_janela_util`.

**Passo 4: Rodar e confirmar verde**
```
pytest tests/test_services/test_business_time.py -v
```

**Passo 5: Commit**
```
feat(business-time): dentro_janela_util + pode_enviar_notificacao_agora
```

---

### Task 1.3: `minutos_uteis_entre`

**Arquivos:**
- Modificar: `app/services/business_time.py`
- Modificar: `tests/test_services/test_business_time.py`

**Passo 1: Escrever testes falhando (casos de borda obrigatórios)**

```python
from app.services.business_time import minutos_uteis_entre

def test_minutos_uteis_simples():
    # segunda 09:00 → 10:00 = 60 min
    assert minutos_uteis_entre(datetime(2026, 6, 22, 9, 0), datetime(2026, 6, 22, 10, 0)) == 60

def test_minutos_uteis_cruzando_almoco():
    # 11:00 → 13:30: 30 min manhã (11:00–11:30) + 30 min tarde (13:00–13:30) = 60 min úteis
    # NÃO 150 min (que seria 13:30 − 11:00 em minutos corridos)
    assert minutos_uteis_entre(datetime(2026, 6, 22, 11, 0), datetime(2026, 6, 22, 13, 30)) == 60

def test_minutos_uteis_cruzando_fim_de_semana():
    # sexta 16:00 → segunda 07:30: 30 min sexta + 30 min segunda = 60 min úteis
    assert minutos_uteis_entre(datetime(2026, 6, 19, 16, 0), datetime(2026, 6, 22, 7, 30)) == 60

def test_minutos_uteis_inicio_igual_fim():
    dt = datetime(2026, 6, 22, 9, 0)
    assert minutos_uteis_entre(dt, dt) == 0
```

**Passo 2: Rodar e confirmar falha** (`ImportError`)

**Passo 3: Implementar `minutos_uteis_entre(inicio, fim)`**

Estratégia: iterar minuto a minuto entre `inicio` e `fim`; para cada minuto verificar `dentro_janela_util`. Aceitável para volume DTX (janela máxima ~450 min/dia). Otimização futura por intervalo de dia se necessário.

**Passo 4: Rodar e confirmar verde**
```
pytest tests/test_services/test_business_time.py -v
```

**Passo 5: Commit**
```
feat(business-time): minutos_uteis_entre com pausa almoço e fim de semana
```

---

### Task 1.4: `adicionar_minutos_uteis` e `adicionar_dias_uteis`

**Arquivos:**
- Modificar: `app/services/business_time.py`
- Modificar: `tests/test_services/test_business_time.py`

**Passo 1: Escrever testes falhando**

```python
from app.services.business_time import adicionar_minutos_uteis, adicionar_dias_uteis

def test_adicionar_minutos_uteis_simples():
    resultado = adicionar_minutos_uteis(datetime(2026, 6, 22, 9, 0), 60)
    assert resultado == datetime(2026, 6, 22, 10, 0)

def test_adicionar_minutos_uteis_cruzando_almoco():
    # +1h útil a partir de 11:00 = 13:30 (não 12:30)
    resultado = adicionar_minutos_uteis(datetime(2026, 6, 22, 11, 0), 60)
    assert resultado == datetime(2026, 6, 22, 13, 30)

def test_adicionar_minutos_uteis_cruzando_fim_de_semana():
    # sexta 16:00 + 60 min úteis = segunda 07:30
    # (teto 16:30 exclusivo: 30 min na sexta 16:00–16:29; + 30 min na segunda 07:00–07:29)
    resultado = adicionar_minutos_uteis(datetime(2026, 6, 19, 16, 0), 60)
    assert resultado == datetime(2026, 6, 22, 7, 30)

def test_adicionar_dias_uteis_projetos_2_dias():
    # segunda + 2 dias úteis = terça 16:30
    # (dia de inicio conta como dia 1: segunda=1, terça=2)
    resultado = adicionar_dias_uteis(datetime(2026, 6, 22, 9, 0), 2)
    assert resultado == datetime(2026, 6, 23, 16, 30)

def test_adicionar_dias_uteis_cruzando_fim_de_semana():
    # sexta + 3 dias úteis = terça seguinte às 16:30
    # (dia de inicio conta como dia 1: sexta=1, segunda=2, terça=3)
    resultado = adicionar_dias_uteis(datetime(2026, 6, 19, 9, 0), 3)
    assert resultado == datetime(2026, 6, 23, 16, 30)
```

**Passo 2: Rodar e confirmar falha**

**Passo 3: Implementar**

`adicionar_minutos_uteis(inicio, minutos)`: avançar de minuto em minuto, contando apenas os que estão em janela útil.

`adicionar_dias_uteis(inicio, n)`: encontrar o N-ésimo dia útil (seg–sex) a partir de `inicio` **inclusive** (o dia de `inicio` conta como dia 1 se for dia útil; fins de semana são pulados); retornar esse dia às `16:30` (teto DTX). Exemplo: segunda + 2 = terça 16:30; sexta + 3 = terça 16:30.

**Passo 4: Rodar e confirmar verde**

**Passo 5: Rodar gate de cobertura**
```
pytest tests/test_services/test_business_time.py --cov=app/services/business_time --cov-report=term-missing
```
Esperado: `business_time.py` >= 85%

**Passo 6: Commit**
```
feat(business-time): adicionar_minutos_uteis + adicionar_dias_uteis (deadline 16:30)
```

---

### Task 1.5: `percentual_prazo_resolucao`

**Arquivos:**
- Modificar: `app/services/business_time.py`
- Modificar: `tests/test_services/test_business_time.py`

**Passo 1: Escrever testes**

```python
from app.services.business_time import percentual_prazo_resolucao

def test_percentual_prazo_inicio():
    # Recém virou Em Atendimento — 0%
    data_em_atendimento = datetime(2026, 6, 22, 7, 0)
    pct = percentual_prazo_resolucao(data_em_atendimento, "Projetos", datetime(2026, 6, 22, 7, 1))
    assert pct < 0.05

def test_percentual_prazo_apos_deadline():
    # Bem além do deadline — >= 1.0
    data_em_atendimento = datetime(2026, 6, 22, 7, 0)
    agora = datetime(2026, 6, 30, 16, 30)  # muitos dias depois
    pct = percentual_prazo_resolucao(data_em_atendimento, "Projetos", agora)
    assert pct >= 1.0

def test_percentual_prazo_categoria_padrao_usa_3_dias():
    data_em_atendimento = datetime(2026, 6, 22, 7, 0)  # segunda
    # Deadline demais = quarta 16:30; Projetos = terça 16:30
    pct_padrao = percentual_prazo_resolucao(data_em_atendimento, "Manutenção", datetime(2026, 6, 23, 16, 30))
    pct_projetos = percentual_prazo_resolucao(data_em_atendimento, "Projetos", datetime(2026, 6, 23, 16, 30))
    assert pct_padrao < pct_projetos  # Manutenção tem deadline mais longo
```

**Passo 2: Implementar** — usa `minutos_uteis_entre` e `adicionar_dias_uteis`; categoria "Projetos" usa `SLA_DIAS_RESOLUCAO_PROJETOS`, demais usam `SLA_DIAS_RESOLUCAO_PADRAO`.

**Passo 3: Rodar e confirmar verde**

**Passo 4: Commit**
```
feat(business-time): percentual_prazo_resolucao por categoria
```

**Critério de aceite Fase 1:**
```bash
pytest tests/test_services/test_business_time.py -v        # todos verdes
python scripts/check_coverage_per_module.py --json-only    # business_time >= 85%
```

**Fase 1 concluída em: 2026-06-24 — evidência: 42 testes passando, business_time.py 95.8% — docs/evidencias/FASE1_DOD_EVIDENCIA.md**

---

## Fase 2 — Isolamento por Supervisor + Claim

**Skills:** `auth-implementation-patterns`, `verification-before-completion`
**Pré-requisito:** Fase 1 concluída.

### Task 2.1: `permissions.py` — isolamento supervisor

**Arquivos:**
- Modificar: `app/services/permissions.py`
- Criar/Modificar: `tests/test_services/test_permissions.py`

**Passo 1: Escrever testes falhando**

```python
# Júlia e Matheus: mesma área, supervisores diferentes
def test_supervisor_nao_ve_ticket_atribuido_a_colega():
    chamado = mock_chamado(area="Engenharia", responsavel_id="id_matheus")
    julia = mock_usuario(perfil="supervisor", areas=["Engenharia"], id="id_julia")
    assert usuario_pode_ver_chamado(chamado, julia) is False

def test_supervisor_ve_ticket_atribuido_a_si():
    chamado = mock_chamado(area="Engenharia", responsavel_id="id_julia")
    julia = mock_usuario(perfil="supervisor", areas=["Engenharia"], id="id_julia")
    assert usuario_pode_ver_chamado(chamado, julia) is True

def test_supervisor_ve_fila_sem_owner():
    chamado = mock_chamado(area="Engenharia", responsavel_id=None)
    julia = mock_usuario(perfil="supervisor", areas=["Engenharia"], id="id_julia")
    assert usuario_pode_ver_chamado(chamado, julia) is True

def test_supervisor_ve_ticket_onde_e_participante():
    chamado = mock_chamado(
        area="Planejamento", responsavel_id="id_outro",
        participantes=[{"supervisor_id": "id_julia", "status": "em_atendimento"}]
    )
    julia = mock_usuario(perfil="supervisor", areas=["Engenharia"], id="id_julia")
    assert usuario_pode_ver_chamado(chamado, julia) is True

def test_admin_ve_todos():
    chamado = mock_chamado(area="Engenharia", responsavel_id="id_matheus")
    admin = mock_usuario(perfil="admin", id="id_admin")
    assert usuario_pode_ver_chamado(chamado, admin) is True
```

**Passo 2: Rodar e confirmar falha** (testes de colega devem falhar pois a lógica atual não isola)

**Passo 3: Atualizar `usuario_pode_ver_chamado` em `permissions.py`**

Nova lógica para supervisor:
- `responsavel_id == user.id` → True (owner)
- `area in user.areas AND responsavel_id is None` → True (fila)
- `user.id in [p["supervisor_id"] for p in chamado.participantes]` → True (participante)
- Caso contrário → False

Admin/admin_global: sempre True.

**Passo 4: Rodar e confirmar verde**

**Passo 5: Commit**
```
feat(permissions): Isolamento supervisor — owner, fila da área e participante ativo
```

---

### Task 2.2: `dashboard_service.py` — query composta

**Arquivos:**
- Modificar: `app/services/dashboard_service.py`
- Modificar: `app/routes/api.py` (função `_aplicar_filtro_perfil`)
- Modificar: `firestore.indexes.json`
- Criar/Modificar: `tests/test_services/test_dashboard_service.py`

**Passo 1: Escrever teste**

```python
def test_supervisor_so_ve_proprios_e_fila(mock_db):
    # mock_db contém: ticket de Julia (resp=julia), ticket fila (resp=None), ticket de Matheus (resp=matheus)
    matheus = mock_usuario(perfil="supervisor", areas=["Engenharia"], id="id_matheus")
    chamados = listar_chamados_por_perfil(matheus)
    ids = [c.id for c in chamados]
    assert "ticket_julia" not in ids
    assert "ticket_fila" in ids
    assert "ticket_matheus" in ids
```

**Passo 2: Implementar query composta** em `_aplicar_filtro_perfil`:
- Substituir `where("area", "in", areas)` por query usando `supervisor_ids_com_acesso`
- Query principal: `array_contains("supervisor_ids_com_acesso", user.id)` (campo desnormalizado — ADR-004 corrigido)
- Índice Firestore: single-field `supervisor_ids_com_acesso` (array index) — adicionar em `firestore.indexes.json`

**Nota Firestore — sem OR entre campos distintos:** o Firestore não suporta `OR` entre campos diferentes na mesma query. **Estratégia adotada (ver ADR-004):** campo desnormalizado `supervisor_ids_com_acesso: list[str]`, atualizado atomicamente em toda mutação de owner (criação, claim, transferência) e de participantes (inclusão/remoção). Dashboard query usa `array_contains` nativo. Para chamados na fila sem owner, garantir que `supervisor_ids_com_acesso` inclua todos os supervisores da área — atualizar ao criar/mover para fila. Alternativa de fallback: duas queries separadas (por `responsavel_id` + por `area` sem owner) com merge em Python.

**Passo 3: Rodar e confirmar verde**

**Passo 4: Commit**
```
feat(dashboard): Query isolada por supervisor (owner + fila) + índice Firestore
```

---

### Task 2.3: Claim ao 1º Em Atendimento + `data_em_atendimento`

**Arquivos:**
- Modificar: `app/services/status_service.py`
- Modificar: `tests/test_services/test_status_service.py`

**Passo 1: Escrever testes**

```python
def test_claim_atribui_owner_ao_em_atendimento(mock_db):
    chamado = mock_chamado(status="Aberto", responsavel_id=None)
    julia = mock_usuario(id="id_julia", perfil="supervisor")
    atualizar_status("id_chamado", "Em Atendimento", julia)
    doc = mock_db.get("id_chamado")
    assert doc["responsavel_id"] == "id_julia"
    assert doc["data_em_atendimento"] is not None

def test_claim_nao_sobrescreve_owner_existente(mock_db):
    chamado = mock_chamado(status="Aberto", responsavel_id="id_julia")
    matheus = mock_usuario(id="id_matheus", perfil="supervisor")
    atualizar_status("id_chamado", "Em Atendimento", matheus)
    assert mock_db.get("id_chamado")["responsavel_id"] == "id_julia"  # não sobrescreve

def test_escada_a_congelada_ao_em_atendimento(mock_db):
    chamado = mock_chamado(status="Aberto", escalacao_resposta_nivel=2)
    julia = mock_usuario(perfil="supervisor")
    atualizar_status("id_chamado", "Em Atendimento", julia)
    # nível congelado — Escada A não incrementa mais
    assert mock_db.get("id_chamado")["escalacao_resposta_nivel"] == 2
```

**Passo 2: Implementar em `status_service.py`** na transição `Aberto → Em Atendimento`:
- Se `responsavel_id is None`: set `responsavel_id = current_user.id`
- Set `data_em_atendimento = datetime.utcnow()`
- Não incrementar `escalacao_resposta_nivel` a partir daqui

**Passo 3: Rodar e confirmar verde**

**Passo 4: Commit**
```
feat(status): Claim ao Em Atendimento + data_em_atendimento + corte Escada A
```

---

### Task 2.4: Supervisor obrigatório na criação

**Arquivos:**
- Modificar: `app/services/chamados_criacao_service.py`
- Modificar: `app/templates/formulario.html`
- Modificar: `tests/test_routes/test_chamados.py`

**Passo 1: Escrever teste**

```python
def test_criacao_falha_sem_supervisor_quando_area_tem_supervisores(client_logado_solicitante, mock_db):
    mock_db.supervisores_por_area["Engenharia"] = [{"id": "id_julia"}]
    resp = client_logado_solicitante.post("/", data={
        "area": "Engenharia", "titulo": "Teste", "supervisor_id": ""
    })
    data = resp.get_json()
    assert data["sucesso"] is False
    assert "supervisor" in data["erro"].lower()

def test_criacao_ok_sem_supervisores_na_area(client_logado_solicitante, mock_db):
    mock_db.supervisores_por_area["Almoxarifado"] = []
    resp = client_logado_solicitante.post("/", data={
        "area": "Almoxarifado", "titulo": "Teste", "supervisor_id": ""
    })
    assert resp.status_code == 200
```

**Passo 2: Implementar validação em `chamados_criacao_service.py`** — checar count de supervisores via `/api/supervisores/lista` antes de persistir

**Passo 3: Atualizar `formulario.html`** — JS marca campo supervisor como `required` dinamicamente quando `lista.length > 0`

**Passo 4: Rodar e confirmar verde**

**Passo 5: Commit**
```
feat(chamados): Supervisor obrigatório na criação quando área tem supervisores
```

**Critério de aceite Fase 2:**
- Matheus não vê ticket da Júlia (mesma área, responsável diferente)
- Fila sem owner visível para supervisor da área
- Claim funciona: Em Atendimento com responsavel_id=None → atribui ao usuário logado
- `data_em_atendimento` gravado; Escada A congelada após Em Atendimento
- Supervisor obrigatório na criação quando área tem supervisores
- `pytest --tb=short -q` verde; `ruff check` + `bandit` limpos

**Fase 2 concluída em: 2026-06-24 — evidência: 1723 testes passando (0 falhas), cobertura permissions.py 90.9% / status_service.py 94.1% / chamados_criacao_service.py 88.1% / edicao_chamado_service.py 91.3% — migração documentada em scripts/README.md e docs/evidencias/FASE2_DOD_EVIDENCIA.md.**

---

## Fase 3 — Transferir Área + Escalonar para Colega

**Skills:** `api-design-principles`, `acceptance-orchestrator`
**Pré-requisito:** Fase 2 concluída.

### Task 3.1: `escalonamento_service.py` — `transferir_area`

**Arquivos:**
- Criar: `app/services/escalonamento_service.py`
- Criar: `tests/test_services/test_escalonamento_service.py`

**Passo 1: Escrever testes**

```python
def test_transferir_area_muda_area_e_owner(mock_db):
    chamado = mock_chamado(area="Engenharia", responsavel_id="id_julia")
    transferir_area("id_chamado", "Planejamento", "id_matheus", "Precisa de PPCP", julia)
    doc = mock_db.get("id_chamado")
    assert doc["area"] == "Planejamento"
    assert doc["responsavel_id"] == "id_matheus"

def test_transferir_area_ex_owner_perde_acesso(mock_db):
    chamado = mock_chamado(area="Engenharia", responsavel_id="id_julia")
    transferir_area("id_chamado", "Planejamento", "id_matheus", "motivo", julia)
    julia_sup = mock_usuario(id="id_julia", areas=["Engenharia"])
    chamado_atualizado = Chamado.from_dict(mock_db.get("id_chamado"))
    assert usuario_pode_ver_chamado(chamado_atualizado, julia_sup) is False

def test_transferir_area_novo_owner_ganha_acesso(mock_db):
    chamado = mock_chamado(area="Engenharia", responsavel_id="id_julia")
    transferir_area("id_chamado", "Planejamento", "id_matheus", "motivo", julia)
    matheus_sup = mock_usuario(id="id_matheus", areas=["Planejamento"])
    chamado_atualizado = Chamado.from_dict(mock_db.get("id_chamado"))
    assert usuario_pode_ver_chamado(chamado_atualizado, matheus_sup) is True

def test_anti_orfao_supervisor_id_obrigatorio(mock_db):
    with pytest.raises(ValueError, match="supervisor_id obrigatório"):
        transferir_area("id_chamado", "Planejamento", None, "motivo", julia)

def test_transferir_area_registra_historico(mock_db, mock_historico):
    transferir_area("id_chamado", "Planejamento", "id_matheus", "motivo", julia)
    entrada = mock_historico.get_ultimo("id_chamado")
    assert entrada["acao"] == "transferencia_area"
    assert "Planejamento" in entrada["detalhes"]
```

**Passo 2: Rodar e confirmar falha** (`ImportError`)

**Passo 3: Implementar `transferir_area(chamado_id, area, supervisor_id, motivo, usuario)`**:
- Validar `supervisor_id is not None` (anti-órfão)
- Validar `motivo` não vazio
- Update atômico Firestore: `area`, `responsavel_id`, `motivo_ultima_escalacao`
- Registrar em `models_historico.py`: `acao="transferencia_area"`

**Passo 4: Rodar e confirmar verde**

**Passo 5: Commit**
```
feat(escalonamento): transferir_area com anti-órfão, histórico e visibilidade
```

---

### Task 3.2: `escalonar_colega`

**Arquivos:**
- Modificar: `app/services/escalonamento_service.py`
- Modificar: `tests/test_services/test_escalonamento_service.py`

**Passo 1: Escrever testes**

```python
def test_escalonar_colega_troca_responsavel(mock_db):
    chamado = mock_chamado(area="Engenharia", responsavel_id="id_julia")
    escalonar_colega("id_chamado", "id_matheus", "Matheus tem especialidade X", julia)
    assert mock_db.get("id_chamado")["responsavel_id"] == "id_matheus"

def test_escalonar_colega_area_permanece(mock_db):
    chamado = mock_chamado(area="Engenharia", responsavel_id="id_julia")
    escalonar_colega("id_chamado", "id_matheus", "motivo", julia)
    assert mock_db.get("id_chamado")["area"] == "Engenharia"

def test_escalonar_colega_registra_historico(mock_db, mock_historico):
    escalonar_colega("id_chamado", "id_matheus", "motivo", julia)
    entrada = mock_historico.get_ultimo("id_chamado")
    assert entrada["acao"] == "escalonamento_colega"

def test_escalonar_colega_motivo_obrigatorio(mock_db):
    with pytest.raises(ValueError, match="motivo"):
        escalonar_colega("id_chamado", "id_matheus", "", julia)
```

**Passo 2: Implementar `escalonar_colega(chamado_id, supervisor_id, motivo, usuario)`**

**Passo 3: Rodar e confirmar verde**

**Passo 4: Commit**
```
feat(escalonamento): escalonar_colega (mesma área, troca responsável + histórico)
```

---

### Task 3.3: Rotas POST + notificações

**Arquivos:**
- Modificar: `app/routes/api.py`
- Modificar: `app/services/notifications.py`
- Modificar: `app/services/email_templates.py`
- Criar: `tests/test_routes/test_api_escalonamento.py`

**Passo 1: Escrever testes de rota**

```python
def test_rota_transferir_area_sucesso(client_logado_supervisor, mock_db):
    resp = client_logado_supervisor.post("/api/chamado/id123/transferir-area", json={
        "area": "Planejamento", "supervisor_id": "id_dest", "motivo": "Motivo válido"
    })
    assert resp.status_code == 200
    assert resp.get_json()["sucesso"] is True

def test_rota_transferir_area_sem_motivo(client_logado_supervisor):
    resp = client_logado_supervisor.post("/api/chamado/id123/transferir-area", json={
        "area": "Planejamento", "supervisor_id": "id_dest", "motivo": ""
    })
    assert resp.status_code == 400
    assert resp.get_json()["sucesso"] is False

def test_rota_transferir_area_nao_autorizado_solicitante(client_logado_solicitante):
    resp = client_logado_solicitante.post("/api/chamado/id123/transferir-area", json={})
    assert resp.status_code == 403

def test_rota_escalonar_colega_sucesso(client_logado_supervisor, mock_db):
    resp = client_logado_supervisor.post("/api/chamado/id123/escalonar-colega", json={
        "supervisor_id": "id_colega", "motivo": "Motivo válido"
    })
    assert resp.status_code == 200
    assert resp.get_json()["sucesso"] is True
```

**Passo 2: Implementar rotas em `api.py`**:
- `POST /api/chamado/<id>/transferir-area` com `@requer_supervisor_area`
- `POST /api/chamado/<id>/escalonar-colega` com `@requer_supervisor_area`
- Resposta sempre `{"sucesso": bool, "erro": str?, "dados": obj?}`

**Passo 3: Adicionar templates de e-mail e chamadas em `notifications.py`**

**Passo 4: Rodar e confirmar verde**

**Passo 5: Commit**
```
feat(api): Rotas /transferir-area e /escalonar-colega + notificações e-mail
```

**Critério de aceite Fase 3:**
- Transferência Eng→Planejamento: ex-owner Eng não vê; novo owner Planejamento vê
- Escalonamento Júlia→Matheus mesma área: `responsavel_id = id_matheus`
- Motivo obrigatório nas duas ações; histórico registrado
- Teste anti-órfão passa
- E-mail mockado via Graph API verificado nos testes

**Fase 3 concluída em: 2026-06-24 — evidência: 1765 passed + docs/evidencias/FASE3_DOD_EVIDENCIA.md**

> Bug L1 corrigido (área destino no e-mail de transferência). 5 lacunas de teste fechadas.
> `escalonamento_service.py` 98% cobertura. Ruff CLEAN, Bandit 0 HIGH/MEDIUM.

---

## Fase 4 — Multi-setor com Participantes

**Skills:** `workflow-orchestration-patterns`, `api-design-principles`
**Pré-requisito:** Fase 3 concluída.

### Task 4.1: Modelo `participantes[]` em `models.py`

**Arquivos:**
- Modificar: `app/models.py`
- Criar/Modificar: `tests/test_models.py`

**Passo 1: Escrever testes**

```python
def test_chamado_from_dict_com_participantes():
    data = {
        "titulo": "Teste", "area": "Eng", "status": "Aberto",
        "participantes": [
            {"supervisor_id": "id_julia", "area": "TI", "status": "pendente", "concluido_em": None}
        ]
    }
    c = Chamado.from_dict(data)
    assert len(c.participantes) == 1
    assert c.participantes[0]["status"] == "pendente"

def test_chamado_from_dict_sem_participantes_lista_vazia():
    data = {"titulo": "Teste", "area": "Eng", "status": "Aberto"}
    c = Chamado.from_dict(data)
    assert c.participantes == []

def test_chamado_to_dict_inclui_participantes():
    chamado = Chamado(titulo="T", area="E", status="Aberto",
                      participantes=[{"supervisor_id": "x", "area": "TI", "status": "pendente"}])
    d = chamado.to_dict()
    assert "participantes" in d
    assert d["participantes"][0]["supervisor_id"] == "x"
```

**Passo 2: Adicionar `participantes: list = field(default_factory=list)` em `Chamado`** com `from_dict`/`to_dict` correspondentes

**Passo 3: Rodar e confirmar verde**

**Passo 4: Commit**
```
feat(models): Campo participantes[] estruturado (substitui setores_adicionais)
```

---

### Task 4.2: `incluir_participantes`, `concluir_minha_parte`, `pode_concluir_global`

**Arquivos:**
- Modificar: `app/services/escalonamento_service.py`
- Modificar: `app/services/status_service.py`
- Modificar: `tests/test_services/test_escalonamento_service.py`

**Passo 1: Escrever testes**

```python
def test_incluir_participantes_adiciona(mock_db):
    chamado = mock_chamado(participantes=[])
    incluir_participantes("id", [{"supervisor_id": "id_julia", "area": "TI"}], matheus)
    assert any(p["supervisor_id"] == "id_julia" for p in mock_db.get("id")["participantes"])

def test_concluir_minha_parte_muda_status(mock_db):
    chamado = mock_chamado(participantes=[
        {"supervisor_id": "id_julia", "area": "TI", "status": "em_atendimento", "concluido_em": None}
    ])
    concluir_minha_parte("id", julia)
    p = next(x for x in mock_db.get("id")["participantes"] if x["supervisor_id"] == "id_julia")
    assert p["status"] == "concluido"
    assert p["concluido_em"] is not None

def test_owner_nao_conclui_com_participantes_pendentes(mock_db):
    chamado = mock_chamado(
        status="Em Atendimento",
        participantes=[{"supervisor_id": "id_julia", "status": "pendente"}]
    )
    with pytest.raises(PermissionError, match="participantes pendentes"):
        atualizar_status("id", "Concluído", matheus)

def test_owner_conclui_quando_todos_concluidos(mock_db):
    chamado = mock_chamado(
        status="Em Atendimento",
        participantes=[{"supervisor_id": "id_julia", "status": "concluido", "concluido_em": "..."}]
    )
    atualizar_status("id", "Concluído", matheus)
    assert mock_db.get("id")["status"] == "Concluído"
```

**Passo 2: Implementar** em `escalonamento_service.py` e bloquear `status_service.py` se `len([p for p in participantes if p["status"] != "concluido"]) > 0`

**Passo 3: Adicionar rotas**:
- `POST /api/chamado/<id>/incluir-participantes`
- `POST /api/chamado/<id>/concluir-minha-parte`

**Passo 4: Rodar e confirmar verde**

**Passo 5: Commit**
```
feat(participantes): incluir, concluir-minha-parte, bloqueio conclusão global
```

---

### Task 4.3: Notificações "todos concluíram" + `confirmacao_solicitante`

**Arquivos:**
- Verificar/Modificar: `app/services/status_service.py`
- Modificar: `app/services/notifications.py`
- Modificar: `tests/test_services/test_status_service.py`

**Passo 1: Escrever testes**

```python
def test_concluido_grava_confirmacao_pendente(mock_db):
    chamado = mock_chamado(status="Em Atendimento", participantes=[])
    atualizar_status("id", "Concluído", matheus)
    assert mock_db.get("id")["confirmacao_solicitante"] == "pendente"

def test_todos_concluiram_dispara_notificacao_owner(mock_db, mock_notif, mock_webpush):
    chamado = mock_chamado(participantes=[
        {"supervisor_id": "id_julia", "status": "em_atendimento"}
    ])
    concluir_minha_parte("id", julia)
    # Quando o último participante conclui → notificar owner
    assert mock_notif.inapp_enviado_para("id_owner")
    assert mock_webpush.push_enviado_para("id_owner")
```

**Passo 2: Integrar fluxo existente de `confirmacao_solicitante`** em `status_service.py`

**Passo 3: Adicionar broadcast Web Push + e-mail + in-app ao owner quando `pode_concluir_global()` torna-se `True`**

**Passo 4: Rodar e confirmar verde**

**Passo 5: Commit**
```
feat(participantes): confirmacao_solicitante + notificações todos-concluiram
```

**Critério de aceite Fase 4:**
- Cenário 3 setores: owner não fecha até todos concluírem
- "Concluí minha parte" atualiza status individual e data
- `confirmacao_solicitante = "pendente"` após Concluído global
- Web Push + e-mail + in-app ao owner quando todos concluem

**Fase 4 concluída em: 2026-06-25 — evidência: docs/evidencias/FASE4_DOD_EVIDENCIA.md**

---

## Fase 5 — Perfil Gestor + Dashboard Read-Only

**Skills:** `auth-implementation-patterns`, `api-design-principles`
**Pré-requisito:** Fase 2 concluída. (Pode executar em paralelo com Fases 3–4.)

### Task 5.1: `nivel_gestao` e decoradores

**Arquivos:**
- Modificar: `app/models_usuario.py`
- Modificar: `app/decoradores.py`
- Criar/Modificar: `tests/test_models_usuario.py`

**Passo 1: Escrever testes**

```python
def test_usuario_from_dict_com_nivel_gestao():
    u = Usuario.from_dict({"id": "1", "nome": "Carlos", "perfil": "supervisor",
                            "nivel_gestao": "gerente_producao"})
    assert u.nivel_gestao == "gerente_producao"

def test_usuario_from_dict_sem_nivel_gestao():
    u = Usuario.from_dict({"id": "1", "nome": "Ana", "perfil": "solicitante"})
    assert u.nivel_gestao is None
```

**Passo 2: Adicionar `nivel_gestao: str | None = None` em `Usuario`**

**Passo 3: Adicionar `@requer_gestor` e `@requer_gestor_ou_admin` em `decoradores.py`**

**Passo 4: Rodar e confirmar verde**

**Passo 5: Commit**
```
feat(usuario): nivel_gestao + decoradores @requer_gestor e @requer_gestor_ou_admin
```

---

### Task 5.2: Rota `/gestor/dashboard` e template

**Arquivos:**
- Modificar: `app/routes/dashboard.py`
- Criar: `app/templates/gestor_dashboard.html`
- Criar: `tests/test_routes/test_gestor_dashboard.py`

**Passo 1: Escrever testes**

```python
def test_gestor_acessa_dashboard(client_logado_gestor):
    resp = client_logado_gestor.get("/gestor/dashboard")
    assert resp.status_code == 200

def test_gestor_nao_muda_status(client_logado_gestor):
    resp = client_logado_gestor.post("/api/atualizar-status",
                                     json={"chamado_id": "x", "novo_status": "Concluído"})
    assert resp.status_code == 403

def test_supervisor_bloqueado_no_gestor_dashboard(client_logado_supervisor):
    resp = client_logado_supervisor.get("/gestor/dashboard")
    assert resp.status_code in (302, 403)
```

**Passo 2: Implementar `GET /gestor/dashboard` com `@requer_gestor_ou_admin`**

**Passo 3: Criar `gestor_dashboard.html`** — filtros: atrasados, Aberto sem resposta, multi-setor travado

**Passo 4: Rodar e confirmar verde**

**Passo 5: Commit**
```
feat(gestor): Dashboard /gestor/dashboard read-only + template
```

**Critério de aceite Fase 5:**
- Gestor vê métricas do time; admin mantém acesso total
- Gestor não edita chamados (403 em tentativa de mudança de status)
- `nivel_gestao` persistido em Firestore via `to_dict`/`from_dict`

**Fase 5 concluída em: 2026-06-25 — evidência: docs/evidencias/FASE5_DOD_EVIDENCIA.md**

---

## Fase 6 — Escada A (Resposta Gerencial)

**Fase 6 concluída em: 2026-06-25 — evidência: 47 testes passando, sla_escalacao_service.py 95% cobertura — docs/evidencias/FASE6_DOD_EVIDENCIA.md**

**Skills:** `workflow-orchestration-patterns`, `verification-before-completion`
**Pré-requisito:** Fases 1 e 2 concluídas.

### Task 6.1: `sla_escalacao_service.py` — `processar_escada_a`

**Arquivos:**
- Criar: `app/services/sla_escalacao_service.py`
- Criar: `tests/test_services/test_sla_escalacao_service.py`

**Passo 1: Escrever testes com timestamps mockados**

```python
from unittest.mock import patch
from datetime import datetime

def test_escada_a_dispara_gerente_setor_apos_1h(mock_db, mock_notif):
    chamado = mock_chamado(status="Aberto", escalacao_resposta_nivel=0,
                           data_abertura=datetime(2026, 6, 22, 9, 0))
    with patch("app.services.sla_escalacao_service.datetime") as mock_dt:
        mock_dt.utcnow.return_value = datetime(2026, 6, 22, 10, 1)  # 61 min úteis
        processar_escada_a()
    assert mock_db.get("id")["escalacao_resposta_nivel"] == 1
    assert mock_notif.email_enviado_para("gestor_setor@dtx.com")

def test_escada_a_nao_dispara_durante_almoco(mock_db, mock_notif):
    chamado = mock_chamado(status="Aberto", escalacao_resposta_nivel=0,
                           data_abertura=datetime(2026, 6, 22, 11, 0))
    with patch("app.services.sla_escalacao_service.datetime") as mock_dt:
        mock_dt.utcnow.return_value = datetime(2026, 6, 22, 12, 0)  # almoço
        processar_escada_a()
    assert mock_db.get("id")["escalacao_resposta_nivel"] == 0
    assert len(mock_notif.emails_enviados) == 0

def test_escada_a_ignora_em_atendimento(mock_db):
    chamado = mock_chamado(status="Em Atendimento", escalacao_resposta_nivel=0,
                           data_abertura=datetime(2026, 6, 22, 9, 0))
    with patch(...) as mock_dt:
        mock_dt.utcnow.return_value = datetime(2026, 6, 22, 10, 1)
        processar_escada_a()
    assert mock_db.get("id")["escalacao_resposta_nivel"] == 0

def test_escada_a_sexta_1645_nao_envia(mock_db, mock_notif):
    chamado = mock_chamado(status="Aberto", escalacao_resposta_nivel=0,
                           data_abertura=datetime(2026, 6, 19, 16, 0))  # sexta
    with patch(...) as mock_dt:
        mock_dt.utcnow.return_value = datetime(2026, 6, 19, 16, 45)  # fora de janela
        processar_escada_a()
    assert len(mock_notif.emails_enviados) == 0

def test_escada_a_idempotente(mock_db, mock_notif):
    # Já no nível 1 — não deve incrementar de novo
    chamado = mock_chamado(status="Aberto", escalacao_resposta_nivel=1,
                           data_abertura=datetime(2026, 6, 22, 9, 0))
    with patch(...) as mock_dt:
        mock_dt.utcnow.return_value = datetime(2026, 6, 22, 10, 30)  # 90 min
        processar_escada_a()
    assert mock_db.get("id")["escalacao_resposta_nivel"] == 1  # não incrementa (já no nível correto)
```

**Passo 2: Rodar e confirmar falha**

**Passo 3: Implementar `processar_escada_a()`**:
- Buscar chamados `status == "Aberto"` com `escalacao_resposta_nivel < 4`
- Para cada um: `minutos = minutos_uteis_entre(data_abertura, agora)` (usando `_as_local` BRT)
- Se `minutos >= SLA_ESCALADA_A_HORAS_UTEIS[nivel_atual] * 60` E `pode_enviar_notificacao_agora()`: incrementar nível + enviar e-mail ao gerente correspondente
- Idempotência: só incrementar se `nivel_atual < nivel_esperado`
- Resolver destinatário via `GESTOR_EMAILS[chave_do_nivel]` — chaves: `gestor_setor` (nível 1), `gerente_producao` (2), `assistente_gm` (3), `gm` (4)
- **Regra de categoria:** mesma lógica para todos — Escada A não distingue "Projetos" de demais

**Passo 4: Rodar e confirmar verde**

**Passo 5: Commit**
```
feat(sla): processar_escada_a — resposta gerencial por minutos úteis com idempotência
```

---

### Task 6.2: Job APScheduler a cada 10 min

**Arquivos:**
- Modificar: `app/__init__.py`
- Verificar: `app/services/scheduler_lock.py`

**Passo 1: Localizar job diário** em `app/__init__.py` e substituir por `IntervalTrigger(minutes=10)`

**Passo 2: Adicionar chamadas a `processar_escada_a()` no job**

**Passo 3: Verificar que `scheduler_lock.py` previne execuções paralelas** (já existente per ADR-003)

**Passo 4: Commit**
```
feat(scheduler): Job escalada a cada 10 min (substitui job diário 8h)
```

**Critério de aceite Fase 6:**
- +1h útil → Gerente Setor (`gestor_setor`); +2h → Gerente Produção (`gerente_producao`); +3h → Assistente GM (`assistente_gm`); +4h → GM (`gm`)
- Em Atendimento cancela incrementos futuros da Escada A
- Nenhum e-mail fora de janela útil, no almoço ou após 16:30 (BRT)
- Idempotência: cada nível escalado exatamente uma vez
- **Projetos e demais categorias usam a mesma Escada A** (+1h/+2h/+3h/+4h úteis — sem distinção de categoria na resposta)

---

## Fase 7 — Escada B (Resolução + Avisos 50%/80%)

**Skills:** `acceptance-orchestrator`, `verification-before-completion`
**Pré-requisito:** Fases 1 e 6 concluídas.

### Task 7.1: `processar_avisos_resolucao` (50%/80%)

**Arquivos:**
- Modificar: `app/services/sla_escalacao_service.py`
- Modificar: `tests/test_services/test_sla_escalacao_service.py`

**Passo 1: Escrever testes**

```python
def test_aviso_50_enviado_ao_responsavel(mock_db, mock_notif, mock_webpush):
    chamado = mock_chamado(status="Em Atendimento", categoria="Projetos",
                           data_em_atendimento=datetime(2026, 6, 22, 7, 0),
                           alerta_supervisor_50_enviado=False)
    # Projetos: deadline terça 16:30; 50% = ~225 min úteis
    with patch(...) as mock_dt:
        mock_dt.utcnow.return_value = datetime(2026, 6, 22, 10, 45)  # ~225 min
        processar_avisos_resolucao()
    assert mock_db.get("id")["alerta_supervisor_50_enviado"] is not False
    assert mock_notif.email_enviado_para("responsavel@dtx.com")
    assert mock_webpush.push_enviado_para("id_responsavel")

def test_aviso_50_nao_reenviado_idempotente(mock_db, mock_notif):
    chamado = mock_chamado(alerta_supervisor_50_enviado=True)  # já enviado
    processar_avisos_resolucao()
    assert len(mock_notif.emails_enviados) == 0

def test_prazo_nao_reseta_com_edicao(mock_db):
    data_original = datetime(2026, 6, 22, 9, 0)
    chamado = mock_chamado(status="Em Atendimento", data_em_atendimento=data_original)
    # Simular edição de descrição
    from app.services.edicao_chamado_service import editar_chamado
    editar_chamado("id", {"descricao": "nova descrição editada"}, matheus)
    assert mock_db.get("id")["data_em_atendimento"] == data_original  # não mudou
```

**Passo 2: Implementar `processar_avisos_resolucao()`**:
- Chamados `status == "Em Atendimento"` com `data_em_atendimento` definido
- `pct = percentual_prazo_resolucao(data_em_atendimento, categoria, agora)`
- `pct >= 0.5` e `not alerta_supervisor_50_enviado`: in-app + e-mail + Web Push ao `responsavel_id`
- `pct >= 0.8` e `not alerta_supervisor_80_enviado`: idem

**Passo 3: Verificar `edicao_chamado_service.py`** — garantir que `data_em_atendimento` não é tocado em edições de descrição/título/prioridade

**Passo 4: Rodar e confirmar verde**

**Passo 5: Commit**
```
feat(sla): processar_avisos_resolucao 50%/80% com Web Push e idempotência
```

---

### Task 7.2: `processar_escada_b` (pós-estouro deadline)

**Arquivos:**
- Modificar: `app/services/sla_escalacao_service.py`
- Modificar: `tests/test_services/test_sla_escalacao_service.py`

**Passo 1: Escrever testes**

```python
def test_escada_b_projetos_deadline_2_dias_uteis(mock_db, mock_notif):
    chamado = mock_chamado(status="Em Atendimento", categoria="Projetos",
                           data_em_atendimento=datetime(2026, 6, 22, 9, 0),  # segunda
                           escalacao_resolucao_nivel=0)
    # Deadline Projetos = terça 16:30
    with patch(...) as mock_dt:
        mock_dt.utcnow.return_value = datetime(2026, 6, 23, 16, 31)  # pós-estouro
        processar_escada_b()
    assert mock_db.get("id")["escalacao_resolucao_nivel"] == 1
    assert mock_notif.email_enviado_para("gestor_setor@dtx.com")

def test_escada_b_demais_deadline_3_dias_uteis(mock_db):
    chamado = mock_chamado(status="Em Atendimento", categoria="Manutenção",
                           data_em_atendimento=datetime(2026, 6, 22, 9, 0),
                           escalacao_resolucao_nivel=0)
    # Deadline Manutenção = quarta 16:30
    with patch(...) as mock_dt:
        mock_dt.utcnow.return_value = datetime(2026, 6, 24, 16, 29)  # antes do estouro
        processar_escada_b()
    assert mock_db.get("id")["escalacao_resolucao_nivel"] == 0  # ainda não estouro

def test_escada_b_nao_reseta_com_concluir_minha_parte(mock_db):
    data_original = datetime(2026, 6, 22, 9, 0)
    chamado = mock_chamado(status="Em Atendimento", data_em_atendimento=data_original,
                           participantes=[{"supervisor_id": "id_julia", "status": "em_atendimento"}])
    concluir_minha_parte("id", julia)
    assert mock_db.get("id")["data_em_atendimento"] == data_original

def test_escada_b_sequencial_4h_entre_niveis(mock_db, mock_notif):
    chamado = mock_chamado(status="Em Atendimento", categoria="Projetos",
                           data_em_atendimento=datetime(2026, 6, 22, 9, 0),
                           escalacao_resolucao_nivel=1)  # já no nível 1
    # +4h úteis após nível 1 → nível 2
    with patch(...) as mock_dt:
        mock_dt.utcnow.return_value = datetime(2026, 6, 24, 7, 1)  # bem além do deadline
        processar_escada_b()
    assert mock_db.get("id")["escalacao_resolucao_nivel"] == 2
```

**Passo 2: Implementar `processar_escada_b()`**:
- Deadline = `adicionar_dias_uteis(data_em_atendimento, N)` (N=2 Projetos, N=3 demais)
- Se `agora < deadline`: skip
- Se `agora >= deadline`: calcular nível esperado baseado em `SLA_ESCALADA_B_HORAS_UTEIS` a partir do deadline
- Enviar e-mail ao gerente do nível + incrementar `escalacao_resolucao_nivel`
- Parar em `Concluído`/`Cancelado`

**Passo 3: Integrar `processar_avisos_resolucao` e `processar_escada_b` no job 10 min**

**Passo 4: Rodar e confirmar verde**

**Passo 5: Commit**
```
feat(sla): processar_escada_b — deadline fixo, escalada gerencial sequencial pós-estouro
```

**Critério de aceite Fase 7:**
- Projetos: deadline 2 dias úteis às 16:30; demais: 3 dias úteis às 16:30
- Avisos 50%/80% ao responsável (in-app + e-mail + Web Push)
- Escada B apenas após deadline; sequencial +0h/+4h/+8h/+12h entre níveis
- Edição de descrição NÃO altera `data_em_atendimento`
- "Concluí minha parte" NÃO altera `data_em_atendimento`
- Concluído/Cancelado para a escada

**Fase 7 concluída em: 2026-06-26 — evidência: 141 testes passando, sla_escalacao_service.py 92% cobertura — docs/evidencias/FASE7_DOD_EVIDENCIA.md**

---

## Fase 8 — Aceite Final e Documentação

**Skills:** `acceptance-orchestrator`, `verification-before-completion`, ciclo CLAUDE.md

**Pré-requisito:** Fases 3, 4, 5 e 7 concluídas.

### Task 8.1: Ciclo de qualidade completo

```bash
# 1. Lint + format
ruff check app/ tests/ --fix
ruff format app/ tests/

# 2. Segurança
bandit -r app/ -ll

# 3. Testes
pytest --tb=short -q

# 4. Gate de cobertura por módulo (>= 85%)
python scripts/check_coverage_per_module.py --json-only
```

**Módulos novos com gate obrigatório:**
- `app/services/business_time.py` — >= 85%
- `app/services/escalonamento_service.py` — >= 85%
- `app/services/sla_escalacao_service.py` — >= 85%

**Módulos estendidos a verificar:**
- `app/services/permissions.py`
- `app/services/status_service.py`
- `app/services/dashboard_service.py`

---

### Task 8.2: Atualizar documentação

**Arquivos:**
- `docs/API.md` — adicionar seções para rotas novas (POST transferir-area, escalonar-colega, incluir-participantes, concluir-minha-parte; GET gestor/dashboard)
- `docs/CASOS_DE_TESTE.md` — cenários de escalonamento, multi-setor, tempo útil, Escadas A e B
- `docs/ENV.md` — variáveis SLA (`SLA_HORARIO_FIM`, `SLA_ALMOCO_INICIO`, `SLA_DIAS_RESOLUCAO_PROJETOS`, etc.)
- `docs/INDICES_FIRESTORE.md` — novos índices compostos adicionados na Fase 2
- `docs/MATRIZ_ROTAS_PERFIL.md` — mover rotas planejadas para secção "implementada"
- `firestore.indexes.json` — já atualizado na Fase 2; verificar consistência

---

### Task 8.3: Evidência QA

```bash
python scripts/executar_qa_escalonamento.py
```

Checklist mínimo de cenários manuais:
- [ ] Supervisor Júlia não vê ticket de Matheus (mesma área)
- [ ] Fila sem owner visível para supervisor da área
- [ ] Claim: Em Atendimento sem owner → atribuído ao logado
- [ ] Transferência Eng→Planejamento: ex-owner some do dashboard; novo owner aparece
- [ ] Escalonamento para colega: troca responsável na mesma área
- [ ] Participante conclui parte; owner não consegue fechar enquanto pendente
- [ ] +1h útil abertura 11:00 → gerente notificado às 13:30 (não 12:30)
- [ ] Sexta 16:45: nenhum e-mail disparado
- [ ] Editar descrição: `data_em_atendimento` inalterada
- [ ] Gestor acessa `/gestor/dashboard`; recebe 403 ao tentar mudar status

Saída: `docs/evidencias/ONDA6_ESCALONAMENTO_EVIDENCIA.md`

---

### Task 8.4: Commit final

```
feat(escalonamento): Onda 6 completa — multi-setor, SLA gerencial, Escadas A/B

Co-Authored-By: Claude <noreply@anthropic.com>
```

**Fase 8 concluída em: 2026-06-26 — evidência: 1930 testes passando, gate 54/54 módulos ≥ 85% — docs/evidencias/ONDA6_ESCALONAMENTO_EVIDENCIA.md**

---

## DoD produto (critérios globais de aceite)

| # | Critério | Fase |
|---|---------|------|
| 1 | Supervisor isolado: Júlia/Matheus não veem tickets um do outro | 2 |
| 2 | Claim: fila → Em Atendimento atribui owner | 2 |
| 3 | Multi-setor: participantes concluem partes; owner fecha por último | 4 |
| 4 | Transferência: área + supervisor + motivo obrigatórios; ex-owner perde visão; novo owner sempre vê | 3 |
| 5 | Escada A: 4 degraus úteis; corte em Em Atendimento; sem e-mail após 16:30 ou almoço | 6 |
| 6 | Escada B: deadline fixo sem reset; avisos 50%/80%; gerentes sequenciais pós-estouro | 7 |
| 7 | Gestor: dashboard read-only + e-mails; não edita tickets | 5 |
| 8 | Concluído → `confirmacao_solicitante = "pendente"`; solicitante confirma ou reabre | 4 |
| 9 | `pytest` verde; cobertura >= 85% nos módulos novos; docs atualizados | 8 |

---

## Mapa de skills por fase

| Fase | Skills obrigatórias | Skills de apoio |
|------|---------------------|-----------------|
| 1 | `writing-plans`, `verification-before-completion` | — |
| 2 | `auth-implementation-patterns`, `verification-before-completion` | `review-security` |
| 3 | `api-design-principles`, `acceptance-orchestrator` | `writing-plans` |
| 4 | `workflow-orchestration-patterns`, `api-design-principles` | `writing-plans` |
| 5 | `auth-implementation-patterns` | `api-design-principles` |
| 6 | `workflow-orchestration-patterns`, `verification-before-completion` | `async-python-patterns` |
| 7 | `acceptance-orchestrator`, `verification-before-completion` | `workflow-orchestration-patterns` |
| 8 | `acceptance-orchestrator`, `verification-before-completion`, `review-security` | ciclo CLAUDE.md |

**Regra transversal (todas as fases):** TDD — nenhum código de produção sem teste falhando primeiro; `verification-before-completion` antes de marcar cada fase como concluída.
