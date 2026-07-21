# ADR-001 — Criptografia de PII em Repouso com Fernet (LGPD / CWI 2.3)

| Campo | Valor |
|---|---|
| **Status** | Aceita |
| **Data** | 2026-06-23 |
| **Autores** | Matheus Costa — DTX Aerospace Engineering |
| **Relacionado** | ADR-003 (fail-fast config produção); `docs/POLITICA_SEGURANCA_LGPD.md`; CWI 2.3 |

---

## Contexto

A LGPD (Lei nº 13.709/2018) exige que dados pessoais sejam protegidos com medidas técnicas adequadas. O Sistema de Chamados armazena `nome` e `email` de usuários no Firestore, em plaintext. O CWI 2.3 (controle interno de segurança DTX) requer minimização de PII e proteção em repouso.

A Onda 3b implementou a parte de ocultação nas respostas HTTP (`to_public_dict()`). A Onda 4 fecha o CWI 2.3 com criptografia dos campos no banco.

---

## Decisão

### Algoritmo: Fernet (symmetric, authenticated encryption)

- Biblioteca: `cryptography>=45.0.3` (já em `requirements.txt`)
- Algoritmo: AES-128-CBC + HMAC-SHA256 (Fernet)
- Vantagem: autenticado (detecta adulteração), simples de usar, sem gestão de IV manual

### Campos criptografados

| Campo Firestore | Tipo | Comportamento |
|---|---|---|
| `email` | string | Criptografado: `fernet:v1:<token>` |
| `nome` | string | Criptografado: `fernet:v1:<token>` |
| `email_lookup_hash` | string (novo) | sha256(email.strip().lower()) em hex |

### Formato de armazenamento

Optou-se por prefixo inline nos campos originais (`fernet:v1:<token>`) em vez de campos separados (`email_enc`, `nome_enc`). Motivo: não exige migração de schema; `from_dict()` detecta o prefixo e descriptografa on-the-fly; campos sem prefixo são tratados como legado.

### Login e busca por email

Quando encryption ON:
- `get_by_email()` consulta `FieldFilter("email_lookup_hash", "==", sha256(email))`
- O campo `email` criptografado não pode ser indexado/pesquisado diretamente

**Índice Firestore obrigatório:** single-field index em `email_lookup_hash` (criado antes do `--apply` em produção).

### Dual-read legado

Documentos sem prefixo `fernet:v1:` são retornados como plaintext (compatibilidade retroativa). O sistema funciona com documentos mistos durante a migração — docs migrados e legado coexistem sem erros.

> **Nota:** durante a migração com `ENCRYPT_PII_AT_REST=false`, o login de usuários migrados continua funcionando via campo `email` plaintext (ainda presente enquanto flag=false). Após ativar `ENCRYPT_PII_AT_REST=true`, todos os usuários devem estar migrados (100% dos docs com `email_lookup_hash`), caso contrário usuários sem hash não conseguem logar.

### `get_all()` e ordenação

`order_by("nome")` do Firestore falha quando `nome` está criptografado (valores opacos). Solução mínima:
- Quando encryption ON: `stream()` sem `order_by` + `sorted(usuarios, key=lambda u: u.nome.lower())` em Python após decrypt
- Impacto de performance: aceitável para volume atual (< 1000 usuários)

### Default

`ENCRYPT_PII_AT_REST=false` (default) — zero breaking change até ops ativar.

---

## Consequências

### Positivas
- Conformidade LGPD: PII criptografado em repouso
- CWI 2.3 completo
- Retrocompatível: encryption OFF = comportamento idêntico ao estado anterior
- Migração incremental: documentos legado e criptografados coexistem

### Negativas / Riscos mitigados

| Risco | Mitigação |
|---|---|
| Login quebrado após migração parcial | dual-read + `email_lookup_hash` para docs migrados |
| Índice Firestore ausente | `fieldOverrides` em `firestore.indexes.json`; deploy via `firebase deploy --only firestore:indexes`; checklist em `docs/DEPLOYMENT_PLAN.md §Criptografia PII` |
| Performance `get_all()` | ordenação em Python; aceitável para < 1000 usuários |
| Perda da ENCRYPTION_KEY | backups obrigatórios antes do `--apply`; ver procedimento de rotação abaixo |
| Key inválida em produção | fail-fast no boot (`config.py:_validar_fernet_key`) |

---

## Impacto em notificações por e-mail

E-mails de notificação (`app/services/notifications.py`) leem `usuario.email` via `from_dict()`, que descriptografa on-the-fly quando `ENCRYPT_PII_AT_REST=true`. Nenhuma alteração necessária no serviço de notificações — o campo `email` está sempre em plaintext em memória após `from_dict()`.

---

## Procedimento de ativação (ops)

> **Ordem obrigatória:** migração 100% ANTES de ativar o flag.
> Usuários sem `email_lookup_hash` não conseguem logar com `ENCRYPT_PII_AT_REST=true`.
> Ver checklist completo em `docs/DEPLOYMENT_PLAN.md §Criptografia PII`.

```bash
# 1. Gerar chave (guardar em local seguro)
python scripts/gerar_chave_criptografia.py
# Adicionar ao .env: ENCRYPTION_KEY=<chave>
# Manter ENCRYPT_PII_AT_REST=false até após o --apply

# 2. Criar índice Firestore (ANTES de --apply — login usa este índice)
#    firebase deploy --only firestore:indexes
#    OU Firebase Console > Firestore > Indexes > Single field: email_lookup_hash (ASC)

# 3. Dry-run (lista documentos a migrar, sem alterar)
python scripts/migrations/migrar_pii_criptografia.py

# 4. Aplicar migração (app pode estar rodando; dual-read garante compatibilidade)
ENCRYPT_PII_AT_REST=true ENCRYPTION_KEY=<chave> python scripts/migrations/migrar_pii_criptografia.py --apply

# 5. Smoke test: tentar login com usuário migrado

# 6. Somente após 100% migrado: ativar flag e reiniciar
#    ENCRYPT_PII_AT_REST=true no .env → docker compose up -d --build
```

---

## Procedimento de rotação de chave (manual — não automatizado nesta onda)

1. Gerar nova chave: `python scripts/gerar_chave_criptografia.py`
2. Adicionar nova chave ao `.env` como `ENCRYPTION_KEY_NEW`
3. Rodar script de re-encriptação (a criar em sprint futura):
   - Para cada doc: decrypt com key antiga → encrypt com key nova
4. Substituir `ENCRYPTION_KEY` pela nova chave no `.env`
5. Remover `ENCRYPTION_KEY_NEW`
6. Reiniciar a aplicação

**Até ter um script de rotação automatizado:** manter backups diários do Firestore e da chave. Não rotacionar a chave sem ter o script.

---

## Alternativas consideradas

| Alternativa | Motivo descartado |
|---|---|
| Campos separados `email_enc` + `nome_enc` | Exigiria migração de schema + refactor maior |
| GCP CMEK (Customer-Managed Encryption Keys) | Custo adicional; overkill para volume atual |
| Vault / KMS externo | Dependência externa desnecessária; Fernet suficiente para o contexto |
| AES-GCM manual | Mais complexo que Fernet sem benefício adicional |
