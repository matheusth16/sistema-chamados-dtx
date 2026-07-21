# ADR-F30 — Externalizar `SETOR_PARA_AREA` para Firestore

| Campo | Valor |
|---|---|
| **Data** | 2026-06-19 |
| **Status** | Aceito |
| **Autor** | DTX Aerospace — Engenharia de Software |
| **Achado** | F-30 |

---

## Contexto

`app/utils_areas.py` contém um dicionário estático `SETOR_PARA_AREA` com apenas 2 mapeamentos
hardcoded (`"Material Indireto / Compras" → "Material"`, `"Manutenção" → "Manutencao"`).
Adicionar um novo setor requer alterar o código-fonte e fazer um novo deploy — ciclo desnecessariamente
caro para uma configuração de dados.

### Call sites (confirmados via grep em 2026-06-19)

| Arquivo | Uso |
|---|---|
| `app/services/assignment.py:94,277` | Resolve área antes de buscar supervisor (2 chamadas) |
| `app/services/chamados_criacao_service.py:58,138` | Área salva no chamado criado (2 chamadas) |
| `app/services/notifications.py:476` | Normaliza área ao notificar supervisores (inline import) |
| `app/routes/api.py:665` | Resolve `?area=` na rota `/api/supervisores/lista` |

Todos os call sites usam apenas `setor_para_area(str) -> str` — a assinatura pública é simples
e pode ser preservada integralmente.

---

## Opções avaliadas

### Opção A — Documento único `config/setor_para_area` (ESCOLHIDA)

Firestore como fonte de verdade. Um único documento armazena o mapa inteiro:

```
config/setor_para_area {
  mapa: {
    "Material Indireto / Compras": "Material",
    "Manutenção": "Manutencao"
    // novos setores adicionados sem deploy
  }
}
```

**Prós:**
- Estrutura mínima — sem modelo Python novo, sem coleção nova
- Edição via script CLI ou console Firebase — sem UI admin necessária agora
- Cache TTL 5 min via `get_static_cached` (mesmo padrão de `gates_service.py`)
- Fallback hardcoded se Firestore vazio/inacessível — resiliência total
- Migration script simples: grava o doc uma única vez

**Contras:**
- Sem UI admin integrada (acceptable — operação rara, admin pode usar console Firebase)
- Cache eventual — mudança leva até 5 min para propagar

### Opção B — Campo `area` em `categorias_setores`

Adicionar campo `area` em cada documento de `categorias_setores`.

**Prós:** CRUD já existe no admin.

**Contras:**
- Requer ALTER-schema em todos os docs de setor existentes
- Acoplamento entre "nome do setor no formulário" e "área do supervisor" — responsabilidades distintas
- Migration complexa; quebra se um setor não tiver o campo

### Opção C — Híbrido: cache + fallback hardcoded apenas

Manter SETOR_PARA_AREA estático, adicionar cache em memória para performance.

**Contras:** não resolve o problema original — deploy ainda necessário para adicionar mapeamento.

---

## Decisão: Opção A

A Opção A resolve o problema com complexidade mínima, reutiliza o padrão já consolidado em
`gates_service.py` e garante resiliência via fallback estático.

---

## Implementação

### Estrutura Firestore

```
Collection: config
Document:   setor_para_area
Fields:
  mapa: map<string, string>
    "Material Indireto / Compras" → "Material"
    "Manutenção"                  → "Manutencao"
```

### Comportamento de `setor_para_area()`

```
setor_para_area(setor_nome)
  └─ get_static_cached("setor_para_area_map", _carregar_mapa_firestore, TTL=300)
        └─ _carregar_mapa_firestore()
              ├─ Firestore disponível + doc existe + mapa não vazio → usa mapa do Firestore
              └─ Qualquer erro / vazio → fallback: dict(SETOR_PARA_AREA) hardcoded
  └─ mapa.get(setor_nome.strip(), setor_nome.strip())  # fallback: próprio nome
```

### Cache e invalidação

- Chave: `"setor_para_area_map"` (cache estático em memória, via `get_static_cached`)
- TTL: 300 s (5 min) — suficiente; mudanças são raras
- Invalidação: `invalidar_cache_setor_area()` exportado para uso futuro em rota admin

### Script de migração

`scripts/migrations/migrar_setor_area.py --apply` grava o documento inicial no Firestore.
Sem `--apply`: dry-run (mostra o que seria gravado, sem escrever).

---

## Rollback

Se o documento Firestore for removido ou corrompido, a função automaticamente usa o fallback
`SETOR_PARA_AREA` hardcoded — comportamento idêntico ao estado pré-F30. Nenhuma intervenção
adicional de código é necessária.

---

## Ordem de deploy recomendada

1. Fazer deploy da nova versão de `app/utils_areas.py` (com fallback = SETOR_PARA_AREA)
2. Executar `python scripts/migrations/migrar_setor_area.py --apply` (semeia o Firestore)
3. O cache se aquece no próximo request

Esta ordem garante que em produção nunca há uma janela onde o Firestore tem dados mas o código
ainda usa o estático — o fallback cobre os primeiros requests.

---

## Impacto em testes

- `tests/test_utils_areas.py` (7 existentes): passam via fallback automático quando Firestore não
  está disponível no ambiente de testes
- Novos testes mockam `app.utils_areas._carregar_mapa_firestore` diretamente (mais limpo que
  mockar toda a cadeia Firestore)
- `tests/test_services/test_notifications.py`: patcha `app.utils_areas.setor_para_area` no call
  site — inalterado
