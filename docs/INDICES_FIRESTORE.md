# Índices Firestore — sistema de chamados

Este documento descreve os índices compostos usados pelo sistema e como implantá-los no Firebase (plano Spark).

## Implantação

1. **Via Firebase CLI (recomendado):** na raiz do projeto execute:
   ```bash
   firebase deploy --only firestore:indexes
   ```
   O arquivo `firestore.indexes.json` na raiz define todos os índices.

2. **Via Console:** quando uma query falhar por falta de índice, o Firestore costuma retornar um link direto para criar o índice. Use esse link para criar manualmente.

## Índices por funcionalidade

| Uso | Coleção | Campos | Observação |
|-----|---------|--------|------------|
| Meus chamados (solicitante) | chamados | solicitante_id ASC, data_abertura DESC | Listagem do solicitante ordenada por data |
| Meus chamados (com status) | chamados | solicitante_id ASC, status ASC, data_abertura DESC | Filtro por status em "Meus chamados" |
| Meus chamados (com RL) | chamados | solicitante_id ASC, rl_codigo ASC, data_abertura DESC | Filtro por código RL em "Meus chamados" |
| Dashboard (área + status) | chamados | area ASC, status ASC, data_abertura DESC | Dashboard de supervisores com filtros e paginação |
| Dashboard (área, sem status) | chamados | area ASC, data_abertura DESC | Dashboard supervisor ao abrir /admin sem filtro de status |
| Dashboard (gate, status, etc.) | chamados | gate ASC, status ASC, data_abertura DESC | Filtros por gate |
| Dashboard (responsável) | chamados | responsavel ASC, status ASC | Filtro por responsável |
| Relatórios / analytics | chamados | data_abertura ASC (ou DESC) + outros | Queries em analytics.py |
| Dashboard supervisor (isolamento Fase 2) | chamados | supervisor_ids_com_acesso ARRAY_CONTAINS, data_abertura DESC | Painel `/painel` — filtro por visibilidade + paginação ordenada por data (ADR-004, Fase 2) |
| Dashboard supervisor + status | chamados | supervisor_ids_com_acesso ARRAY_CONTAINS, status ASC, data_abertura DESC | Filtro de status no painel do supervisor |
| Dashboard supervisor + categoria/gate/responsável | chamados | supervisor_ids_com_acesso ARRAY_CONTAINS, categoria/gate/responsavel ASC, data_abertura DESC | Filtros adicionais no painel do supervisor |
| Histórico do chamado | historico | chamado_id ASC, data_acao DESC | Timeline do chamado |
| Notificações não lidas | notificacoes | usuario_id ASC, lida ASC | Listagem de notificações |
| Lembretes de confirmação (job 6 h) | chamados | status ASC, confirmacao_solicitante ASC | Query `status=="Concluído" AND confirmacao_solicitante=="pendente"` no job lembrete_confirmacao |
| Escada A — chamados sem resposta (Fase 6) | chamados | status ASC, escalacao_resposta_nivel ASC | Query `status=="Aberto" AND escalacao_resposta_nivel<4` no job sla_escalacao (10 min) |
| Escada B — chamados em atendimento vencidos (Fase 7) | chamados | status ASC, escalacao_resolucao_nivel ASC | Query `status=="Em Atendimento" AND escalacao_resolucao_nivel<4` no job sla_escalacao (10 min) |

## Verificação

Após o deploy, os índices podem levar alguns minutos para ficarem "Building". No Firebase Console: Firestore → Indexes. Quando o status for "Enabled", as queries que dependem deles deixarão de acionar fallback em memória e passarão a usar o índice (menos leituras e resposta mais rápida).
