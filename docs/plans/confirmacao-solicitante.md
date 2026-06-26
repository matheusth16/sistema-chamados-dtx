# Confirmação de Resolução pelo Solicitante

## Goal
Quando o supervisor marcar um chamado como "Concluído", o solicitante deve confirmar
se o problema foi resolvido ou reabrir o chamado com um motivo.

## Fluxo
```
Supervisor → "Concluído"
                ↓
  confirmacao_solicitante = "pendente"
                ↓
  Solicitante vê botões em visualizar_chamado.html
        ↓                        ↓
  ✅ Confirmar             ❌ Reabrir
  confirmacao="confirmado"  status="Aberto"
                            confirmacao="reaberto"
                            comentário no histórico
```

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
