# ADR — Testabilidade de app/database.py

**Data:** 2026-06-22
**Status:** Aceito
**Onda:** 4 (Infraestrutura)

## Problema

`app/database.py` executa código de inicialização Firebase/Firestore no nível do módulo (linhas 134–150) como efeito colateral do import. Isso cria dois desafios para testes:

1. **Função `_inicializar_firebase_com_retry`** — ramo já importado; qualquer chamada direta funciona, mas precisa de mocks pesados nos nomes `firebase_admin.*`, `os.getenv` e `os.path.exists`.

2. **Linhas module-level (137–142 e 148–150)** — só executam quando o módulo é recarregado. Para cobri-las é necessário `importlib.reload(app.database)` dentro de um contexto de mocks que simule falha na inicialização ou no `firestore.client()`.

## Opções consideradas

| Opção | Prós | Contras |
|---|---|---|
| **A — Reload isolado** (escolhida) | Zero mudança no código de produção; restauração simples via helper | Risco de estado global entre testes se cleanup falhar |
| **B — Lazy init (factory)** | Código mais testável, sem reload | Refactor invasivo; quebra `from app.database import db` em todo o codebase |
| **C — Aceitar miss** | Simples | Não atinge 85% no módulo; gate falha |

## Decisão

**Opção A** — manter o código de produção intacto e usar `importlib.reload` com mocks totais para cobrir os ramos module-level.

Justificativa: O refactor (opção B) exigiria mudar como `db` é importado em ~30 arquivos de service/route sem nenhum benefício funcional. O reload isolado é simples e não afeta outros testes quando seguido de `_restaurar_database()` no cleanup.

## Implementação

- `tests/test_database.py` testa `_inicializar_firebase_com_retry` diretamente via mocks de `firebase_admin.*`.
- Dois testes de reload (`test_modulo_inicializacao_critica_levanta`, `test_firestore_client_falha_levanta`) usam `importlib.reload(app.database)` dentro de contexto de mocks e chamam `_restaurar_database()` logo após para repor `app.database.db` como `MagicMock`.
- A fixture `mock_firestore` do conftest (`patch("app.database.db", MagicMock())`) não é afetada porque patcha o atributo do módulo em runtime, após qualquer reload.

## Consequências

- `app/database.py` atingiu **100%** de cobertura sem alteração de produção.
- Testes de reload são frágeis a mudanças na estrutura do módulo — se o módulo for refatorado para lazy init no futuro, estes testes podem ser removidos.
- O helper `_restaurar_database()` deve ser chamado após cada teste de reload para garantir estado consistente.
