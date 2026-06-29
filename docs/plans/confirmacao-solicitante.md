# Confirmação de Resolução pelo Solicitante

## Goal
Quando o supervisor marcar um chamado como "Concluído", o solicitante deve confirmar
se o problema foi resolvido ou reabrir o chamado com um motivo.

## Fluxo completo
```
Supervisor → "Concluído"
                ↓
  confirmacao_solicitante = "pendente"
  data_conclusao = SERVER_TIMESTAMP
  lembrete_confirmacao_1_enviado = False  ← resetado em toda conclusão
  lembrete_confirmacao_2_enviado = False  ← resetado em toda conclusão
                ↓
  E-mail imediato → notificar_solicitante_confirmacao_pendente (status_service)
                ↓
  Solicitante vê botões em visualizar_chamado.html
        ↓                                   ↓
  ✅ Confirmar                         ❌ Reabrir
  confirmacao="confirmado"              status="Aberto"
  🟢 e-mail ao responsável              confirmacao="reaberto"
     notificar_responsavel_             data_conclusao = None
     chamado_confirmado                 flags lembrete = False
     (header verde #059669)             comentário no histórico
                                        🔴 e-mail ao responsável
                                           notificar_supervisor_
                                           chamado_reaberto
                                           (header vermelho #dc2626)
```

### Simetria confirmar × reabrir

| Aspecto | Confirmar | Reabrir |
|---------|-----------|---------|
| Função de notificação | `notificar_responsavel_chamado_confirmado` | `notificar_supervisor_chamado_reaberto` |
| Cor do header | `#059669` (verde) | `#dc2626` (vermelho) |
| Helper na rota | `_enviar_notificacao_confirmar` | `_enviar_notificacao_reabrir` |
| Validação pós-update | `confirmacao_solicitante == "confirmado"` | `status == "Aberto"` + `confirmacao == "reaberto"` |
| Histórico | Não grava | Grava com motivo |

## Notificações in-app (sino) para o solicitante

Complementam e-mail e Web Push. São criadas pela collection `notificacoes` no Firestore e exibidas no sino da navbar.

### Tipos de notificação in-app

| Evento | `tipo` (Firestore) | Criado em |
|--------|-------------------|-----------|
| Supervisor → "Em Atendimento" | `status_em_atendimento` | `status_service._notificar_solicitante` |
| Supervisor → "Concluído" (confirmar) | `status_concluido_confirmar` | `status_service._notificar_solicitante` |
| Lembrete 24 h | `lembrete_confirmacao_1` | `lembrete_confirmacao_service._criar_inapp_lembrete` |
| Lembrete 48 h | `lembrete_confirmacao_2` | `lembrete_confirmacao_service._criar_inapp_lembrete` |

### Metadados gravados no doc (collection `notificacoes`)

```json
{
  "usuario_id": "<solicitante_id>",
  "chamado_id": "<id>",
  "numero_chamado": "CHM-001",
  "categoria": "TI",
  "tipo": "status_em_atendimento",
  "titulo": "<texto default no idioma do helper>",
  "mensagem": "<texto default>",
  "lida": false,
  "data_criacao": "<SERVER_TIMESTAMP>"
}
```

### Chaves de tradução (translations.json)

| Chave | Descrição |
|-------|-----------|
| `notification_status_in_progress_title` | Chamado {numero} em atendimento |
| `notification_status_in_progress_message` | Sua solicitação de {categoria} está sendo atendida |
| `notification_status_completed_confirm_title` | Chamado {numero} concluído — confirme |
| `notification_status_completed_confirm_message` | {categoria} — Por favor, confirme a resolução ou reabra |
| `notification_reminder_confirm_title` | Lembrete #{n}: confirme o chamado {numero} |
| `notification_reminder_confirm_message` | {categoria} — Aguardamos sua confirmação da resolução |

### Helpers principais

- `notifications_inapp.texto_notificacao_status_solicitante(numero, categoria, tipo_evento, language, numero_lembrete)` → `(titulo, mensagem)`
- `notifications_inapp.criar_notificacao_solicitante(solicitante_id, chamado_id, numero_chamado, categoria, tipo)` → `str | None`
- `notifications_inapp.localizar_notificacao(doc, language)` — traduz os novos tipos na leitura

### Comportamento de falha in-app

- **status_service**: se `criar_notificacao_solicitante` falha → `logger.warning`, e-mail e webpush não são afetados
- **lembrete_service**: se e-mail falha → in-app NÃO é criada (não spammar sem confirmação de e-mail); se e-mail OK e in-app falha → `logger.warning`, flag de e-mail é gravada normalmente (evita spam)

## Lembretes automáticos (job APScheduler a cada 6 h)

Serviço: `app/services/lembrete_confirmacao_service.py`

```
job lembrete_confirmacao (a cada 6 h)
  └─ query: status=="Concluído" AND confirmacao_solicitante=="pendente" (limit 500)
       ↓ para cada chamado:
       │  horas = agora − data_conclusao
       │
       ├─ se lembrete_1=False AND horas >= 24 h
       │    → envia e-mail (notificar_solicitante_lembrete_confirmacao #1)
       │    → se ok: grava lembrete_confirmacao_1_enviado=True
       │              cria notificação in-app tipo "lembrete_confirmacao_1"
       │    → se falha: flag NÃO gravada → retry na próxima execução
       │
       └─ se lembrete_1=True AND lembrete_2=False AND horas >= 48 h
            → envia e-mail (notificar_solicitante_lembrete_confirmacao #2)
            → se ok: grava lembrete_confirmacao_2_enviado=True
                      cria notificação in-app tipo "lembrete_confirmacao_2"
            → se falha: flag NÃO gravada → retry na próxima execução
```

**Variáveis de ambiente obrigatórias para envio:**
- `NOTIFY_EMAIL_ENABLED=true`
- `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`, `GRAPH_SENDER_EMAIL`

**Índice Firestore necessário:**
- Composto: `status ASC, confirmacao_solicitante ASC` (deploy: `firebase deploy --only firestore:indexes`)

## Tasks

- [ ] **1. Modelo** — Adicionar campo `confirmacao_solicitante: str | None` em `app/models.py`
      (valores: `None`, `"pendente"`, `"confirmado"`, `"reaberto"`)
      → Verificar: `Chamado.from_dict` e `to_dict` incluem o campo

- [ ] **2. Status service** — Em `app/services/status_service.py`, quando `novo_status == "Concluído"`,
      gravar `confirmacao_solicitante = "pendente"` no update do Firestore
      → Verificar: chamado no Firestore tem o campo após mudar para Concluído

- [ ] **3. Rota API** — Criar `POST /api/chamado/<id>/confirmar-resolucao` em `app/routes/api.py`
      com decorator `@requer_solicitante`, aceita `{"acao": "confirmar" | "reabrir", "motivo": str}`
      → Verificar: curl retorna `{"sucesso": true}`

- [ ] **4. Lógica da rota** — `confirmar` → grava `confirmacao_solicitante="confirmado"` + histórico.
      `reabrir` → muda status para `"Aberto"`, `confirmacao_solicitante="reaberto"`, motivo no histórico
      → Verificar: Firestore atualizado corretamente para cada ação

- [ ] **5. Template** — Em `visualizar_chamado.html`, quando `perfil == solicitante`
      e `chamado.confirmacao_solicitante == "pendente"`, exibir bloco com:
      mensagem + botão "Confirmar resolvido" + botão "Não foi resolvido" (com campo de motivo)
      → Verificar: bloco aparece para solicitante e está oculto para supervisor/admin

- [ ] **6. Testes** — Em `tests/test_routes/test_confirmacao_solicitante.py`:
      - confirmar: status permanece "Concluído", campo vira "confirmado"
      - reabrir: status volta "Aberto", campo vira "reaberto", motivo salvo
      - supervisor não consegue chamar a rota (403)
      - solicitante não consegue confirmar chamado de outro usuário (403)
      → Verificar: `pytest tests/test_routes/test_confirmacao_solicitante.py -v` passa

## Done When
- [ ] Supervisor muda para "Concluído" → solicitante vê os botões ao abrir o chamado
- [ ] Confirmar → chamado fecha definitivamente
- [ ] Reabrir → chamado volta para "Aberto" com motivo no histórico
- [ ] Todos os 4 testes passam
- [ ] Supervisor/admin não vê os botões de confirmação (UI limpa)
