# QA Debug Playbook — sistema_chamados

> **Objetivo:** Triagem sistemática de falhas de teste. Classifique o tipo, aplique o padrão de correção, adicione um teste de prevenção.

---

## 1. Classificação rápida de falhas

Ao ver uma falha, responda a estas perguntas:

| Pergunta | Resposta → Tipo |
|----------|-----------------|
| O teste falha só em CI, passa localmente? | **Timing / Ambiente** |
| O erro é `PermissionError`, `403`, `401`, `redirect to login`? | **Permissão** |
| O erro é `KeyError`, `AttributeError` em mock, `assert False`? | **Dados** |
| O erro é `ConnectionError`, `Timeout`, `firebase_admin` exception? | **Dependência externa** |
| O erro é `AssertionError` em resposta de API (status code / JSON)? | **Contrato de API** |
| O erro é `ImportError` ou `ModuleNotFoundError`? | **Ambiente / Dependências** |

---

## 2. Tipo: DADOS

### Sintomas
- `KeyError: 'campo'` ao acessar `r.json()`
- `AssertionError: assert None is not None` — mock retornou estrutura errada
- `dict.to_dict()` retorna campos diferentes do esperado pelo template

### Causa raiz mais comum
O mock não replica a estrutura real do documento Firestore. Um campo foi adicionado ao modelo mas o mock não foi atualizado.

### Checklist de triagem

```bash
# 1. Veja o contrato atual do modelo
grep -n "to_dict\|from_dict" app/models_usuario.py

# 2. Compare com o dict usado no mock do teste
# 3. Rode só o teste com -s para ver o traceback completo
pytest tests/path/to/test.py::test_name -s --tb=long
```

### Padrão de correção

```python
# ❌ Mock frágil — campos hardcoded ad-hoc
mock_doc.to_dict.return_value = {"nome": "Fulano"}

# ✅ Mock robusto — use a helper que replica to_dict() real
def _usuario_dict_fake(**overrides):
    base = {
        "uid": "u1", "nome": "Fulano", "email": "f@dtx.com",
        "perfil": "solicitante", "setor": "TI", "ativo": True,
        "onboarding_completo": False, "onboarding_passo": 0,
    }
    return {**base, **overrides}
```

### Teste de prevenção

Adicione um teste de contrato de `to_dict` / `from_dict` no arquivo de testes do modelo:

```python
def test_usuario_from_dict_roundtrip():
    dados = _usuario_dict_fake()
    u = Usuario.from_dict(dados, uid="u1")
    assert u.to_dict() == dados
```

---

## 3. Tipo: TIMING

### Sintomas
- Falha intermitente em CI (`flaky`)
- `TimeoutError` em testes E2E com Playwright
- `assert resultado == "ok"` — falha 1 de cada 5 execuções

### Causa raiz mais comum
- E2E: `page.goto()` sem `wait_for_load_state("networkidle")`
- Unitário: código assíncrono sem `await` correto; `time.sleep()` real não mockado
- CI: banco de dados de teste não inicializado antes do primeiro teste da session

### Checklist de triagem

```bash
# Rodar o teste 5x para confirmar flakiness
pytest tests/path/to/test.py::test_name --count=5

# Verificar se sleep está mockado
grep -n "time.sleep" tests/path/to/test.py
```

### Padrão de correção

```python
# ❌ E2E sem espera explícita
page.click("[data-testid='submit-btn']")
expect(page.get_by_testid("success-msg")).to_be_visible()

# ✅ Espera determinística
page.click("[data-testid='submit-btn']")
page.wait_for_load_state("networkidle")
expect(page.get_by_testid("success-msg")).to_be_visible(timeout=10_000)

# ❌ sleep real em teste unitário de retry
result = executar_com_retry(func, max_tentativas=3)

# ✅ Mockar sleep
with patch("app.services.notify_retry.time.sleep"):
    result = executar_com_retry(func, max_tentativas=3)
```

### Teste de prevenção

Marque o teste como `@pytest.mark.flaky` (instale `pytest-rerunfailures`) até a causa ser resolvida. Nunca feche o ticket sem o fix determinístico.

---

## 4. Tipo: PERMISSÃO

### Sintomas
- `assert r.status_code == 200` falha com `302`
- `assert r.location` contém `"login"`
- `AssertionError` em rota que exige `@requer_admin` mas fixture é `client_logado_solicitante`

### Causa raiz mais comum
- Fixture de cliente errada para o perfil exigido pela rota
- Decorador `@requer_*` adicionado sem atualizar os testes existentes
- `get_by_id` retorna `None` durante `@login_required` — usuário não carregado

### Checklist de triagem

```bash
# Confirmar qual decorador a rota usa
grep -n "@requer_" app/routes/dashboard.py

# Confirmar qual fixture o teste usa
grep -n "client_logado" tests/test_routes/test_dashboard.py

# Ver a fixture e o perfil mockado
grep -A 10 "client_logado_solicitante" tests/conftest.py
```

### Mapa de fixtures × rotas permitidas

| Rota / decorador | Fixture correta |
|------------------|-----------------|
| `@requer_solicitante` | `client_logado_solicitante` |
| `@requer_supervisor_area` | `client_logado_supervisor` |
| `@requer_admin` | `client_logado_admin` |
| `@login_required` (qualquer perfil) | qualquer `client_logado_*` |

### Padrão de correção

```python
# ❌ Fixture errada
def test_admin_lista_usuarios(client_logado_solicitante):
    r = client_logado_solicitante.get("/admin/usuarios")
    assert r.status_code == 200  # FALHA: solicitante não tem acesso

# ✅ Fixture correta + teste de controle negativo separado
def test_admin_lista_usuarios(client_logado_admin):
    r = client_logado_admin.get("/admin/usuarios")
    assert r.status_code == 200

def test_solicitante_nao_acessa_admin_usuarios(client_logado_solicitante):
    r = client_logado_solicitante.get("/admin/usuarios", follow_redirects=False)
    assert r.status_code == 302
```

### Teste de prevenção

Para cada nova rota, adicionar **dois** testes: acesso autorizado + acesso negado.

---

## 5. Tipo: DEPENDÊNCIA EXTERNA

### Sintomas
- `google.api_core.exceptions.GoogleAPIError` / `firebase_admin._auth_utils.UserNotFoundError`
- `ConnectionRefusedError` no CI para Firestore / SMTP / push notifications
- Teste passa com credenciais reais mas falha em CI sem Firebase configurado

### Causa raiz mais comum
- Mock de Firestore no caminho errado (patch no módulo que importa, não no módulo de origem)
- Código de produção chama `db` diretamente numa rota sem passar pelo service
- Teste de integração sem `@pytest.mark.e2e` tentando conectar a serviço real

### Checklist de triagem

```bash
# Confirmar onde db é importado no módulo sob teste
grep -n "^from app.database\|^import app.database\|from app import" app/services/X.py

# O patch deve ser no caminho de uso, não de definição:
# Se o serviço faz `from app.database import db`, o patch é:
# patch("app.services.X.db")
# NÃO: patch("app.database.db")
```

### Padrão de correção

```python
# ❌ Patch no caminho errado
with patch("app.database.db") as mock_db:
    result = minha_funcao()
# Se a função importa `db` localmente, este patch não funciona

# ✅ Patch no caminho de uso
with patch("app.services.meu_service.db") as mock_db:
    result = minha_funcao()

# ✅ Para imports inline nas rotas (padrão deste projeto):
with patch("app.routes.dashboard.db") as mock_db:
    r = client.get("/admin")
```

### Tabela de caminhos de patch — módulos comuns

| Módulo | Caminho de patch |
|--------|-----------------|
| `app/services/chamados_criacao_service.py` | `app.services.chamados_criacao_service.db` |
| `app/services/dashboard_service.py` | `app.services.dashboard_service.db` |
| `app/services/notifications.py` | `app.services.notifications.db` |
| `app/routes/dashboard.py` (import inline) | `app.routes.dashboard.db` |
| `app/models_categorias.py` | `app.models_categorias.db` |
| `app/models_grupo_rl.py` | `app.models_grupo_rl.db` |

### Teste de prevenção

```python
# Garantir que o mock é chamado — se não for, o patch está errado
def test_listar_chamados_chama_firestore(client_logado_admin):
    with patch("app.services.dashboard_service.db") as mock_db:
        mock_db.collection.return_value.stream.return_value = []
        client_logado_admin.get("/admin")
    mock_db.collection.assert_called()  # falha se patch estava no lugar errado
```

---

## 6. Tipo: CONTRATO DE API

### Sintomas
- `assert r.json()["sucesso"] is True` falha com `KeyError: 'sucesso'`
- Status code diferente do esperado (ex.: 500 em vez de 400)
- Campo renomeado/removido na response quebra múltiplos testes

### Causa raiz mais comum
- Estrutura de response alterada em `api.py` sem atualizar testes
- Handler de exceção retorna HTML (Flask default 500) em vez de JSON

### Checklist de triagem

```bash
# Verificar o contrato atual da rota
grep -A 20 "def api_" app/routes/api.py | grep "return jsonify"

# Rodar com -s e ver o body real
pytest tests/test_routes/test_api_contract.py -s --tb=short
```

### Padrão de correção

Toda response JSON deve seguir o contrato do projeto:

```python
# Contrato obrigatório (definido em CLAUDE.md)
{"sucesso": bool, "erro"?: str, "dados"?: obj}

# ❌ Inconsistente
return jsonify({"ok": True, "message": "criado"})

# ✅ Consistente
return jsonify({"sucesso": True, "dados": {"id": chamado_id}})
```

### Teste de prevenção

```python
def test_contrato_response_api_chamado():
    r = client_logado_admin.post("/api/chamado/status", json={...})
    body = r.get_json()
    assert "sucesso" in body
    assert isinstance(body["sucesso"], bool)
    if not body["sucesso"]:
        assert "erro" in body
```

---

## 7. Template de incidente de regressão

Use este template ao registrar uma regressão crítica (no issue tracker ou em `docs/incidents/`):

```markdown
## Incidente de Regressão — [DATA]

### Identificação
- **Commit que introduziu:** `git bisect` ou `git log --oneline -20`
- **Teste que falhou:** `tests/path/to/test.py::test_name`
- **Ambiente:** CI / local / staging
- **Tipo de falha:** Dados / Timing / Permissão / Dependência externa / Contrato de API

### Sintoma
[Mensagem de erro exata + traceback resumido]

### Causa raiz
[O que mudou no código de produção que causou a falha]

### Correção aplicada
- Arquivo alterado: `app/...`
- Natureza da mudança: [fix no código / fix no teste / ambos]

### Teste de prevenção adicionado
- Arquivo: `tests/...`
- Teste: `test_nome_descritivo_da_regressao`

### Verificação
- [ ] `pytest --tb=short -q` passa localmente
- [ ] Coverage gate >= 70% mantido
- [ ] `ruff check` + `bandit` passam
```

---

## 8. Fluxo de triagem em 5 passos

```
1. REPRODUZIR
   pytest tests/.../test_X.py::test_nome -s --tb=long
   ↓
2. CLASSIFICAR
   Erro → qual tipo? (seção 2 acima)
   ↓
3. ISOLAR
   Menor trecho de código que reproduz o problema
   ↓
4. CORRIGIR
   Fix mínimo no código de produção OU no teste (não nos dois ao mesmo tempo)
   ↓
5. PREVENIR
   Adicionar/ajustar teste de regressão → commit com mensagem `fix:` ou `test:`
```

---

## 9. Comandos de diagnóstico rápido

```bash
# Rodar apenas os testes que falharam na última execução
pytest --lf --tb=short

# Ver cobertura de um arquivo específico
pytest --cov=app/services/notifications --cov-report=term-missing tests/test_services/test_notifications.py

# Identificar testes lentos (>1s)
pytest --durations=10 -q

# Confirmar que mock foi chamado com os argumentos corretos
# (usar dentro do teste após a chamada)
mock_obj.assert_called_once_with(expected_arg)
mock_obj.assert_any_call(partial_arg)

# Verificar se patch está no caminho certo (mock chamado = True)
assert mock_db.collection.called, "db.collection não foi chamado — patch incorreto"

# Rodar só testes de um tipo
pytest -m smoke -q
pytest -m regression -q
pytest -m "not e2e" -q
```

---

## 10. Referência rápida — anti-patterns mais comuns neste projeto

| Anti-pattern | Por que falha | Correção |
|---|---|---|
| `patch("app.database.db")` em service com import inline | Import já resolvido; patch não afeta o nome local | `patch("app.services.X.db")` |
| Mock de `to_dict()` com campos incompletos | Template acessa campo ausente → `UndefinedError` | Use helper `_*_dict_fake()` com todos os campos |
| `client.get(rota)` sem `follow_redirects=False` | Redirect seguido mascara 302 esperado | Sempre passar `follow_redirects=False` em testes de acesso |
| `side_effect=[val1, val2]` em `get_by_id` | Flask-Login chama `get_by_id` em cada request | Usar `side_effect=lambda uid: mapa[uid]` |
| Test sem assert (só chamada) | Teste nunca falha — não testa nada | Sempre incluir `assert` ou `mock.assert_called_*` |
| Testar implementação em vez de comportamento | Acoplamento frágil a internals | Testar input → output, não chamadas intermediárias |
