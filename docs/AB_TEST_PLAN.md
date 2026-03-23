# Plano de Experimento A/B — sistema_chamados

> **Escopo:** 1 experimento de baixo risco, orientado a UX, com hipótese formal, métrica primária e guarda de qualidade integrada ao processo de testes.

---

## Experimento: Formulário de Abertura de Chamado — Campo de Descrição Guiado

### ID
`AB-001`

### Status
`planejado`

---

## 1. Hipótese

> **Se** exibirmos um placeholder contextual + contador de caracteres no campo "Descrição" do formulário de abertura de chamado,
> **então** a taxa de chamados descartados por descrição insuficiente (`< 30 chars`) vai cair ≥ 20%,
> **porque** usuários terão feedback imediato sobre o que escrever e quanta informação já forneceram.

### Variantes

| Variante | Descrição |
|----------|-----------|
| **Controle (A)** | Campo `<textarea>` atual — sem placeholder, sem contador |
| **Tratamento (B)** | Campo com `placeholder="Ex.: Impressora do 2º andar não liga desde ontem..."` + contador `X / 500 caracteres` em tempo real (JS puro, sem dependência nova) |

---

## 2. Métrica primária

**Taxa de chamados com descrição insuficiente** (`len(descricao.strip()) < 30`) no momento da submissão.

```
métrica = chamados_rejeitados_por_descricao / total_tentativas_criacao
```

- Fonte dos dados: `app/services/validators.py` — erro `"Descrição muito curta"` já retornado
- Logging necessário: registrar cada tentativa de criação (mesmo as rejeitadas) com flag `descricao_insuficiente: bool`

### Métricas secundárias (guardiãs)

| Métrica | Direção esperada | Limiar de alerta |
|---------|-----------------|-----------------|
| Taxa de conclusão de chamado (criação com sucesso) | Manter ou subir | Não cair > 5% vs controle |
| Tempo médio de preenchimento do formulário | Manter ou reduzir | Não subir > 10s |
| Taxa de erros de validação totais | Manter ou reduzir | Não subir |

---

## 3. Critérios de sucesso

| Critério | Definição |
|----------|-----------|
| **Primário** | Redução ≥ 20% na taxa de descrição insuficiente (variante B vs A) |
| **Guardiã de qualidade** | Taxa de conclusão do formulário não cai > 5% na variante B |
| **Duração mínima** | 2 semanas ou 200 submissões por variante (o que vier primeiro) |
| **Significância estatística** | p-value < 0,05 (teste qui-quadrado) |

---

## 4. Implementação técnica

### 4.1 Mecanismo de split

Divisão pelo `uid` do usuário autenticado (determinístico, sem cookie extra):

```python
# app/services/ab_service.py
import hashlib

def get_variante(uid: str, experimento_id: str, split: float = 0.5) -> str:
    """Retorna 'A' ou 'B' de forma determinística por usuário."""
    hash_val = int(hashlib.md5(f"{experimento_id}:{uid}".encode()).hexdigest(), 16)
    return "B" if (hash_val % 100) < int(split * 100) else "A"
```

```python
# app/routes/chamados.py — na rota GET /
from app.services.ab_service import get_variante

variante = get_variante(current_user.uid, "AB-001")
return render_template("formulario.html", ..., ab_variante=variante)
```

### 4.2 Template (formulario.html)

```html
<!-- Controle (A) — sem alteração -->
{% if ab_variante == "A" %}
<textarea name="descricao" id="descricao" rows="4"></textarea>

<!-- Tratamento (B) — placeholder + contador -->
{% else %}
<textarea
  name="descricao"
  id="descricao"
  rows="4"
  placeholder="Ex.: Impressora do 2º andar não liga desde ontem. Luz de power pisca 3x e apaga."
  maxlength="500"
  data-testid="descricao-textarea"
></textarea>
<p class="text-sm text-gray-400 mt-1">
  <span id="desc-contador">0</span> / 500 caracteres
</p>
<script>
  const ta = document.getElementById("descricao");
  const cnt = document.getElementById("desc-contador");
  ta.addEventListener("input", () => { cnt.textContent = ta.value.length; });
</script>
{% endif %}
```

### 4.3 Logging de evento

```python
# app/services/validators.py — ao detectar descrição insuficiente
import logging
logger = logging.getLogger(__name__)

if len(descricao.strip()) < 30:
    logger.info(
        "ab_event",
        extra={
            "experimento": "AB-001",
            "variante": variante,  # passado como parâmetro
            "evento": "descricao_insuficiente",
            "uid": uid,
        },
    )
```

---

## 5. Guardiãs de qualidade — integração com testes

### 5.1 Testes unitários do split (escrever antes de implementar — TDD)

```python
# tests/test_services/test_ab_service.py

def test_get_variante_e_deterministica():
    """Mesma entrada sempre retorna mesma variante."""
    from app.services.ab_service import get_variante
    v1 = get_variante("uid-123", "AB-001")
    v2 = get_variante("uid-123", "AB-001")
    assert v1 == v2

def test_get_variante_retorna_a_ou_b():
    from app.services.ab_service import get_variante
    variante = get_variante("uid-xyz", "AB-001")
    assert variante in ("A", "B")

def test_get_variante_distribui_50_50():
    """Com 1000 UIDs aleatórios, distribuição aproximada de 50/50."""
    from app.services.ab_service import get_variante
    resultados = [get_variante(f"uid-{i}", "AB-001") for i in range(1000)]
    pct_b = resultados.count("B") / 1000
    assert 0.40 <= pct_b <= 0.60, f"Distribuição fora de 40–60%: {pct_b:.1%}"

def test_get_variante_isolada_por_experimento():
    """Mesmo UID em experimentos diferentes pode ter variantes diferentes."""
    from app.services.ab_service import get_variante
    v1 = get_variante("uid-abc", "AB-001")
    v2 = get_variante("uid-abc", "AB-002")
    # Não garante que são diferentes — garante que são válidas
    assert v1 in ("A", "B")
    assert v2 in ("A", "B")
```

### 5.2 Teste de não-regressão do formulário

```python
# tests/test_routes/test_chamados.py — adicionar

def test_formulario_variante_b_renderiza_placeholder(client_logado_solicitante):
    """Variante B inclui placeholder e contador no HTML."""
    with (
        patch("app.routes.chamados.get_static_cached", return_value=[]),
        patch("app.routes.chamados.obter_total_por_contagem", return_value=0),
        patch("app.routes.chamados.get_variante", return_value="B"),
    ):
        r = client_logado_solicitante.get("/", follow_redirects=False)
    assert r.status_code == 200
    assert b"desc-contador" in r.data or b"placeholder" in r.data

def test_formulario_variante_a_sem_contador(client_logado_solicitante):
    """Variante A não inclui contador."""
    with (
        patch("app.routes.chamados.get_static_cached", return_value=[]),
        patch("app.routes.chamados.obter_total_por_contagem", return_value=0),
        patch("app.routes.chamados.get_variante", return_value="A"),
    ):
        r = client_logado_solicitante.get("/", follow_redirects=False)
    assert r.status_code == 200
    assert b"desc-contador" not in r.data
```

### 5.3 Checklist antes de ativar

- [ ] Testes unitários de `ab_service.py` passando (TDD: escrever antes)
- [ ] Testes de não-regressão do formulário passando
- [ ] Coverage gate 70% mantido após novos testes
- [ ] Logging de evento ativo em staging
- [ ] Rollback documentado (basta remover `ab_variante` do template → Variante A para todos)

---

## 6. Análise e encerramento

### Coleta de dados

```python
# Query nos logs para calcular a métrica primária:
# Para cada variante, contar eventos "descricao_insuficiente" / total submissões
```

### Quando encerrar

- **Vencedor claro (B superior):** Variante B vira padrão, remover feature flag, deletar código de split.
- **Sem diferença estatística:** Manter variante A (controle), fechar experimento, registrar aprendizado.
- **B prejudicial (guarda de qualidade ativada):** Rollback imediato, investigar antes de nova iteração.

### Template de resultado

```markdown
## Resultado AB-001 — [DATA]

- **Duração:** DD/MM/YYYY → DD/MM/YYYY
- **Amostras:** A=X submissões, B=Y submissões
- **Métrica primária:**
  - A: X% descrições insuficientes
  - B: Y% descrições insuficientes
  - Variação: Z% (p-value: P)
- **Métricas guardiãs:** [OK / ALERTA — detalhar]
- **Decisão:** [Adotar B / Manter A / Iteração]
- **Próximo passo:** [link para issue ou PR]
```

---

## 7. Próximos experimentos candidatos

| ID | Hipótese | Risco |
|----|----------|-------|
| AB-002 | Botão "Abrir Chamado" fixo no rodapé mobile aumenta taxa de criação em mobile | Baixo |
| AB-003 | Categorias exibidas como cards visuais (vs dropdown) reduzem seleção incorreta | Médio |
| AB-004 | E-mail de confirmação com ETA de SLA aumenta satisfação (NPS) | Baixo |
