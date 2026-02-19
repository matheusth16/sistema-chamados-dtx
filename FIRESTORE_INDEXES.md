# Índices Firestore – Sistema de Chamados

Este projeto usa índices compostos no Firestore para listagens, filtros e notificações. O arquivo `firestore.indexes.json` na raiz do projeto define todos os índices necessários.

## Deploy dos índices

### Via Firebase CLI (recomendado)

1. Instale o [Firebase CLI](https://firebase.google.com/docs/cli) e faça login:
   ```bash
   npm install -g firebase-tools
   firebase login
   ```

2. No diretório do projeto (onde está `firebase.json` e `.firebaserc`), execute:
   ```bash
   firebase deploy --only firestore:indexes
   ```

   Para um projeto específico:
   ```bash
   firebase deploy --only firestore:indexes --project sistema-de-chamados-dtx-aero
   ```

3. A construção dos índices pode levar alguns minutos. Acompanhe no [Console Firebase](https://console.firebase.google.com) em **Firestore Database > Índices**.

### Via Console Firebase

Se preferir criar manualmente, use a rota **Admin > Índices Firestore** no sistema; ela exibe os índices recomendados e um resumo. Depois crie cada índice em **Firestore Database > Índices > Criar índice** no console.

## Índices definidos

| Coleção      | Campos (ordem) | Uso |
|-------------|----------------|-----|
| **chamados** | categoria, status, data_abertura | Filtros do dashboard (categoria + status + data) |
| **chamados** | status, data_abertura | Listagem por status e data |
| **chamados** | categoria, prioridade, data_abertura | Filtro categoria + prioridade |
| **chamados** | gate, status, data_abertura | Filtro por gate e status |
| **chamados** | responsavel, status | Atribuição (chamados por responsável e status) |
| **notificacoes** | usuario_id, lida | Listar e contar notificações não lidas por usuário |
| **historico** | chamado_id, data_acao DESC | Histórico do chamado ordenado por data |
| **usuarios** | perfil, area | Supervisores por área (atribuição e relatórios) |

## Referência

- [Gerenciar índices no Firestore](https://firebase.google.com/docs/firestore/query-data/indexing)
- [Referência da definição de índices](https://firebase.google.com/docs/reference/firestore/indexes/)
