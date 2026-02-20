# Scripts de manutenção

Execute sempre **a partir da raiz do projeto** (onde está o `run.py`).

## init_categorias.py

Inicializa categorias padrão no Firestore (setores, gates, impactos) se o banco estiver vazio.

```bash
python scripts/init_categorias.py
```

## atualizar_firebase.py

Atualiza as collections `categorias_setores` e `categorias_impactos` no Firebase com os dados exatos do formulário (limpa as antigas e recria). Use com cuidado em produção.

```bash
python scripts/atualizar_firebase.py
```

Requer `credentials.json` na raiz do projeto.
