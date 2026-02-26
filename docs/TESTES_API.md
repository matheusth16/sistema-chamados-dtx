# Testes de API – Sistema de Chamados DTX

**Documento:** Validação da comunicação entre frontend e backend (contrato e códigos HTTP)  
**Projeto:** Sistema de Chamados DTX  
**Referência:** [API.md](API.md)  

---

## 1. Objetivo

Validar que os **endpoints da API** respondem conforme o contrato documentado: códigos HTTP corretos, estrutura JSON esperada e comportamento com/sem autenticação.

---

## 2. Escopo dos Testes de API

| Endpoint | Autenticação | Testes de contrato |
|----------|--------------|---------------------|
| GET `/health` | Não | 200, `{"status":"ok"}` |
| GET `/sw.js` | Não | 200, Content-Type JavaScript |
| POST `/api/atualizar-status` | Sim | 401 sem login; 400 payload inválido; 404 chamado inexistente; 200 sucesso |
| POST `/api/bulk-status` | Sim (supervisor/admin) | 401 sem login; 403 solicitante; 400 payload inválido; 200 estrutura (sucesso, atualizados, erros) |
| POST `/api/editar-chamado` | Sim (supervisor/admin) | 401 sem login; 403 solicitante; 400 sem chamado_id; 404 inexistente; 200 sucesso |
| GET `/api/chamados/paginar` | Sim | 401 sem login; 200 com `chamados`, `paginacao` |
| POST `/api/carregar-mais` | Sim | 401 sem login; 200 com `chamados`, `cursor_proximo`, `tem_proxima` |
| GET `/api/chamado/<id>` | Sim | 401 sem login; 403 sem permissão; 404 inexistente; 200 com `chamado` |
| GET `/api/notificacoes` | Sim | 401 sem login; 200 com `notificacoes`, `total_nao_lidas` |
| POST `/api/notificacoes/<id>/ler` | Sim | 401 sem login; 200 `{"sucesso": true/false}` |
| GET `/api/push-vapid-public` | Sim | 401 sem login; 200 com `vapid_public_key` |
| POST `/api/push-subscribe` | Sim | 401 sem login; 400 subscription inválida; 200 sucesso |
| GET `/api/supervisores/disponibilidade` | Sim | 401 sem login; 200 com `sucesso`, `supervisores`, `area` |

---

## 3. Implementação

Os testes de contrato e validação estão em:

- **`tests/test_routes/test_api_contract.py`** – testes marcados com `@pytest.mark.api`

Cada endpoint é validado para:

1. **Sem autenticação:** rotas protegidas retornam 401 com corpo JSON (ex.: `requer_login: true`).
2. **Payload inválido:** 400 com campo `erro` ou mensagem clara.
3. **Recurso inexistente ou sem permissão:** 403/404 conforme documentação.
4. **Sucesso:** 200 com estrutura JSON documentada (chaves obrigatórias presentes).

---

## 4. Execução

```bash
# Todos os testes de API (contrato)
pytest tests/test_routes/test_api_contract.py -v

# Apenas testes marcados como api (se outros arquivos usarem o marker)
pytest -m api -v
```

---

## 5. Manutenção

- Ao alterar [API.md](API.md), atualizar os testes de contrato em `test_api_contract.py` e este documento.
- Novos endpoints devem ter ao menos: teste 401 (se protegido), teste 200 com estrutura esperada (mock quando necessário).
