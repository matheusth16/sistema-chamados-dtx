## Onboarding Interativo — Visão de Produto

### Objetivo

O onboarding interativo foi criado para:

- **Acelerar a adoção** do sistema por novos usuários.
- **Guiar visualmente** pelos principais pontos da interface (dashboard, criação de chamados, filtros, etc.).
- **Reduzir erros iniciais**, mostrando boas práticas logo no primeiro acesso.

Ele é exibido apenas para usuários autenticados que ainda **não concluíram** o tour.

---

### Quando o onboarding aparece

O fluxo é controlado no backend pelo modelo `Usuario` (`app/models_usuario.py`), usando dois campos:

- `onboarding_perfis_vistos: list[str]` — lista dos perfis para os quais o usuário já viu (ou pulou) o tour. Um usuário `admin_global`, por exemplo, pode ter visto o tour de `admin` mas não o de outro perfil.
- `onboarding_passo: int` — passo atual em que o usuário parou dentro do tour do perfil ativo (permite retomar de onde parou).

> `onboarding_completo: bool` existe só como campo de leitura de retrocompatibilidade (`app/models_usuario.py:203`) para documentos antigos do Firestore, gerados antes do "Onboarding tour v2". Nunca é mais escrito — não usar como referência de comportamento atual.

Regra de exibição, implementada em `app/templates/base.html:65`:

```jinja
{% if current_user.is_authenticated and (onboarding_replay or (request.endpoint == perfil_home_endpoint and current_user.perfil not in current_user.onboarding_perfis_vistos)) %}
```

1. **Usuário autenticado, na home do próprio perfil (`perfil_home_endpoint`), com `current_user.perfil` fora de `onboarding_perfis_vistos`**
   - O template base inclui `components/onboarding.html` e o JS `static/js/onboarding.js`.
   - O overlay/guias são renderizados sobre a UI existente.
   - Fora da home do perfil, o onboarding não aparece — mesmo que o perfil ainda não tenha sido visto.
2. **Query param `?onboarding_replay=1`**
   - Força a exibição do tour em qualquer página, independente de `onboarding_perfis_vistos` — usado pra revisitar o tour manualmente.
3. **Usuário autenticado, perfil já em `onboarding_perfis_vistos`, sem replay**
   - O componente de onboarding não é incluído.
4. **Usuário não autenticado**
   - Nunca vê o onboarding.

---

### Etapas do tour

O tour **não é único** — cada perfil tem sua própria sequência de passos, definida em `app/static/js/onboarding.js` (objeto `TOURS`, por perfil + idioma, com fallback pra `pt_BR`). O componente `app/templates/components/onboarding.html` só monta o overlay; o conteúdo de cada passo vem do JS.

Contagem de passos por perfil (ver `project_onboarding_tour_v2` para o desenho original):
- `solicitante` — 5 passos
- `supervisor` — 6 passos
- `admin` — 7 passos

Cada passo é identificado por um índice inteiro (`passo`) no JavaScript; esse índice é o valor enviado à API para persistência. Ao editar o conteúdo de um tour, alterar `app/static/js/onboarding.js`; a estrutura do overlay em si só muda em `components/onboarding.html`.

---

### API de controle de onboarding

Três rotas em `app/routes/api.py`, todas delegando para `app/services/onboarding_service.py`:

- **POST** `/api/onboarding/avancar`
  - Salva o passo atual via `avancar_passo(user_id, passo)` → `db.collection("usuarios").document(user_id).update({"onboarding_passo": passo})`.
  - Não marca conclusão — só avança o índice do passo.
- **POST** `/api/onboarding/concluir`
  - Chama `concluir_onboarding(current_user.id, current_user.perfil)`.
  - Adiciona o perfil atual a `onboarding_perfis_vistos` via `firestore.ArrayUnion([perfil])` (idempotente — não duplica) e zera `onboarding_passo`.
- **POST** `/api/onboarding/pular`
  - Chama a mesma `concluir_onboarding` — pular e concluir têm efeito idêntico no backend (perfil marcado como visto).

Não existe lógica de "último passo dispara conclusão automaticamente" — a conclusão só acontece quando o frontend chama `/concluir` ou `/pular` explicitamente.

---

### Persistência de estado no modelo `Usuario`

O modelo `Usuario` (`app/models_usuario.py`) expõe e persiste o estado de onboarding:

- No construtor (`__init__`):
  - Recebe `onboarding_perfis_vistos: list | None = None` e `onboarding_passo: int = 0`; a lista é filtrada contra `PERFIS_VALIDOS`.
- Em `to_dict()`:
  - Serializa `onboarding_perfis_vistos` e `onboarding_passo` para o documento armazenado no Firestore.
- Em `from_dict()`:
  - Lê `onboarding_perfis_vistos` do documento; se ausente, faz retrocompat a partir de `onboarding_completo` (bool antigo) — ver bloco acima.
- No método de atualização (linha ~341):
  - Permite que o serviço de onboarding atualize `onboarding_perfis_vistos` (com filtro de `PERFIS_VALIDOS`) e `onboarding_passo` de forma incremental.

Isso garante que o tour seja **idempotente** e resistente a refresh de página: o usuário sempre retoma do passo correto, por perfil.

---

### Como reiniciar o onboarding para um usuário

Em ambientes de QA ou suporte, pode ser útil **resetar** o tour de um usuário específico (por exemplo, para mostrar novamente o tour em uma sessão de treinamento).

Há duas abordagens recomendadas:

#### 1. Via script de manutenção (recomendado para admin/ops)

Criar um script na pasta `scripts/` (ex.: `scripts/reset_onboarding_usuario.py`) que:

1. Recebe um identificador de usuário (`id` ou email).
2. Faz lookup do documento correspondente no Firestore.
3. Atualiza os campos:
   - `onboarding_perfis_vistos = []` (reset total) ou remove só o perfil específico da lista (reset parcial)
   - `onboarding_passo = 0`

Exemplo de lógica (alto nível — reset total de todos os perfis):

```python
from app.models_usuario import Usuario

def reset_onboarding(user_id: str) -> None:
    usuario = Usuario.get_by_id(user_id)
    if not usuario:
        print("Usuário não encontrado")
        return

    usuario.update_fields(
        onboarding_perfis_vistos=[],
        onboarding_passo=0,
    )
    print(f"Onboarding resetado para usuário {usuario.email}")
```

> Observação: a implementação exata deve seguir os utilitários já usados no projeto para leitura/gravação de usuários.

#### 2. Via rota administrativa protegida

Alternativamente (ou adicionalmente), pode-se implementar uma rota administrativa:

- Exemplo: **POST** `/admin/onboarding/reset`
  - Somente perfis `admin` podem acessar.
  - Corpo JSON ou formulário com `user_id` / `email`.
  - Internamente, reutiliza a lógica do serviço de onboarding para setar:
    - `onboarding_perfis_vistos = []`
    - `onboarding_passo = 0`

Isso facilita que administradores façam o reset diretamente pela interface web, sem precisar de acesso à linha de comando.

---

### Idioma e experiência de onboarding

O sistema trabalha com **i18n** e hoje a configuração está:

- Idioma padrão: **inglês (`en`)**.
- Outras opções: `pt_BR`, `es`, etc., conforme definido em `app/i18n.py` e `translations.json`.
- O idioma é escolhido:
  - Pelo parâmetro de URL `?lang=<código>` (ex.: `?lang=pt_BR`).
  - Ou pelo valor armazenado em `session['language']`.

No onboarding, isso significa que:

- Os textos do tour e da interface seguem o idioma atual da sessão.
- O seletor de idioma na navbar é um dos primeiros passos do tour, reforçando para o usuário que ele pode escolher o idioma que preferir.

---

### Boas práticas de uso

- Em produção, evite mudar a ordem/quantidade de passos em `onboarding.js` sem checar se o frontend ainda chama `/api/onboarding/concluir` (ou `/pular`) no ponto certo — o backend não infere sozinho quando o tour terminou.
- Para testes automatizados (`tests/test_routes/test_onboarding.py`), use usuários dedicados a QA, para que o estado de onboarding possa ser manipulado livremente.
- Sempre que fizer alterações visuais significativas na navbar, dashboard ou fluxo de criação de chamados, avalie se o onboarding precisa ser ajustado para refletir a nova experiência.
