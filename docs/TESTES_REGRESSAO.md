# Testes de Regressão – Sistema de Chamados DTX

**Documento:** Garantir que novas funcionalidades ou alterações não quebrem recursos existentes  
**Projeto:** Sistema de Chamados DTX  

---

## 1. Objetivo

Executar um conjunto **estável e repetível** de testes que cubra os fluxos e contratos críticos do sistema. Qualquer falha indica possível regressão (quebra de comportamento já existente).

---

## 2. Escopo da Suite de Regressão

A suite de regressão cobre:

| Área | Cenários críticos |
|------|-------------------|
| **Health / Infra** | GET `/health` retorna 200 e `{"status":"ok"}`; GET `/sw.js` retorna JavaScript. |
| **Autenticação** | Login sem credenciais → permanece em login; Login válido (solicitante) → redirect `/`; Login válido (supervisor) → redirect `/admin`; Logout → redirect login; Acesso a `/` sem login → redirect login. |
| **Criação de chamado** | POST `/` sem login → redirect login; POST com dados válidos (mock) → redirect. |
| **API – Status** | POST atualizar-status sem login → 401; Payload inválido (sem chamado_id) → 400; Bulk-status como solicitante → 403. |
| **API – Edição** | POST editar-chamado como solicitante → 403; Sem chamado_id → 400. |
| **API – Listagem** | POST carregar-mais sem login → 401; Com login → 200 e estrutura (chamados, cursor_proximo, tem_proxima). |
| **API – Notificações** | GET notificacoes sem login → 401; Com login → 200 e estrutura (notificacoes, total_nao_lidas). |
| **Permissões** | Admin pode ver qualquer chamado; Supervisor só vê chamados da sua área. |
| **Validação** | Formulário novo chamado: descrição obrigatória, Projetos exige RL; extensão de anexo inválida → erro. |

---

## 3. Como Executar

### Suite dedicada de regressão (recomendado)

```bash
pytest tests/test_regression/ -v
```

Todos os testes em `tests/test_regression/` são considerados de regressão e devem passar antes de merge/deploy.

### Marcar testes existentes como regressão

Testes em outros módulos podem ser marcados com `@pytest.mark.regression`. Para rodar apenas esses:

```bash
pytest -m regression -v
```

(Requer registro do marker em `conftest.py`; veja seção 4.)

### Suite completa (smoke + regressão)

Para máxima segurança, rode toda a suíte antes de release:

```bash
pytest tests/ -v
# ou
python scripts/verificar_dependencias.py --no-audit
```

---

## 4. Configuração do marker (opcional)

No `conftest.py` está registrado o marker `regression`:

```python
def pytest_configure(config):
    config.addinivalue_line("markers", "regression: testes críticos de regressão (suite de smoke).")
```

Assim, é possível marcar testes em qualquer arquivo com `@pytest.mark.regression` e executá-los com `pytest -m regression`.

---

## 5. Critérios de Sucesso

- **Todos** os testes da pasta `tests/test_regression/` devem passar.
- Nenhum teste que antes passava deve falhar após uma alteração (investigar como regressão).
- Em CI/CD: executar a suite de regressão em todo commit na branch principal ou antes do deploy.

---

## 6. Quando Atualizar a Suite

- Incluir novo teste em `test_regression/` (ou marcar com `@pytest.mark.regression`) quando houver **novo fluxo crítico** ou **novo contrato de API** que deva ser garantido em toda release.
- Remover ou ajustar testes obsoletos quando um recurso for descontinuado ou o comportamento for alterado por design.

Este documento deve ser revisado quando o escopo de regressão for ampliado ou reduzido.
