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

- `onboarding_completo: bool` — indica se o usuário já concluiu o tour.
- `onboarding_passo: int` — passo atual em que o usuário parou (permite retomar de onde parou).

Regras principais:

1. **Usuário autenticado + `onboarding_completo == False`**
   - O template base (`app/templates/base.html`) inclui `components/onboarding.html` e o JS `static/js/onboarding.js`.
   - O overlay/guias são renderizados sobre a UI existente.
2. **Usuário autenticado + `onboarding_completo == True`**
   - O componente de onboarding não é incluído.
3. **Usuário não autenticado**
   - Nunca vê o onboarding.

---

### Etapas do tour (exemplo)

O tour é composto por passos sequenciais, definidos no template `app/templates/components/onboarding.html` e controlados por `app/static/js/onboarding.js`. A ordem exata pode ser ajustada, mas o fluxo típico é:

1. **Boas-vindas**
   - Explica rapidamente o objetivo do sistema de chamados.
   - Indica que o tour é curto e pode ser finalizado a qualquer momento.
2. **Navbar e seleção de idioma**
   - Destaque para o seletor de linguagem (EN / PT-BR / ES).
   - Dica sobre como alterar o idioma da interface.
3. **Dashboard principal**
   - Mostra cards principais de status dos chamados.
   - Explica a lógica de cores e indicadores.
4. **Criação de chamados**
   - Foca no botão/área de “Novo Chamado”.
   - Orienta sobre campos obrigatórios e anexos.
5. **Filtros e busca**
   - Destaca filtros por status, categoria, gate, busca por texto.
   - Explica o impacto na performance (paginação com cursor).
6. **Painel do usuário**
   - Mostra nível, XP semanal e conquistas (gamificação).
7. **Conclusão**
   - Mensagem final e confirmação de que o tour foi concluído.

Cada passo é identificado por um índice inteiro (`passo`) no JavaScript; esse índice é o valor que é enviado à API para persistência.

---

### API de controle de onboarding

O frontend chama uma rota protegida no backend para registrar o progresso do usuário:

- **POST** `/api/onboarding/avancar`
  - Autenticação: requer usuário logado (`@login_required`).
  - Corpo (JSON):
    - `passo: int` — passo atual que o usuário atingiu.
  - Comportamento esperado (alto nível):
    - Atualiza `Usuario.onboarding_passo` com o valor informado (se maior ou igual ao atual).
    - Quando o último passo é atingido, marca `Usuario.onboarding_completo = True`.

Essa lógica é implementada em `app/routes/api.py` e delegada ao serviço `app/services/onboarding_service.py`.

---

### Persistência de estado no modelo `Usuario`

O modelo `Usuario` (`app/models_usuario.py`) expõe e persiste o estado de onboarding:

- No construtor (`__init__`):
  - Recebe `onboarding_completo: bool = False` e `onboarding_passo: int = 0`.
- Em `to_dict()`:
  - Serializa os campos para o documento armazenado no Firebase/Firestore.
- Em `from_dict()`:
  - Lê `onboarding_completo` e `onboarding_passo` do documento para reconstruir o objeto.
- Em `update_from_dict()` / métodos de atualização:
  - Permite que o serviço de onboarding atualize esses campos de forma incremental.

Isso garante que o tour seja **idempotente** e resistente a refresh de página: o usuário sempre retoma do passo correto.

---

### Como reiniciar o onboarding para um usuário

Em ambientes de QA ou suporte, pode ser útil **resetar** o tour de um usuário específico (por exemplo, para mostrar novamente o tour em uma sessão de treinamento).

Há duas abordagens recomendadas:

#### 1. Via script de manutenção (recomendado para admin/ops)

Criar um script na pasta `scripts/` (ex.: `scripts/reset_onboarding_usuario.py`) que:

1. Recebe um identificador de usuário (`id` ou email).
2. Faz lookup do documento correspondente no Firestore.
3. Atualiza os campos:
   - `onboarding_completo = False`
   - `onboarding_passo = 0`

Exemplo de lógica (alto nível):

```python
from app.models_usuario import Usuario

def reset_onboarding(user_id: str) -> None:
    usuario = Usuario.get_by_id(user_id)
    if not usuario:
        print("Usuário não encontrado")
        return

    usuario.update_fields(
        onboarding_completo=False,
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
    - `onboarding_completo = False`
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

- Em produção, evite mudar a ordem/quantidade de passos sem atualizar também a lógica de backend que determina o último passo (usado para marcar `onboarding_completo`).
- Para testes automatizados (`tests/test_routes/test_onboarding.py`), use usuários dedicados a QA, para que o estado de onboarding possa ser manipulado livremente.
- Sempre que fizer alterações visuais significativas na navbar, dashboard ou fluxo de criação de chamados, avalie se o onboarding precisa ser ajustado para refletir a nova experiência.
