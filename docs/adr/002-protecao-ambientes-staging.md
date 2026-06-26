# ADR-002: Proteção de Ambientes Staging/HML

## Status

Accepted — 2026-06-23

---

## Context

O sistema de chamados DTX possui ambiente de produção e ambientes não-produtivos (HML/staging) usados para QA e homologação. O critério CWI 4.1 exige que ambientes de teste não sejam acessíveis publicamente sem controle de acesso — um ambiente HML exposto na internet sem proteção pode:

- Revelar features em desenvolvimento antes do lançamento
- Ser usado por terceiros para mapear a API e arquitetura interna
- Receber dados reais (por erro do operador) sem as mesmas salvaguardas de produção
- Confundir usuários finais que acessam o URL errado

O DTX opera com deploy Docker em servidor local/on-premise. A proteção de ambientes não-prod deve ser simples, confiável e não interferir no fluxo de desenvolvimento (pytest) nem no ambiente de produção.

---

## Decision Drivers

- **CWI 4.1:** Ambiente de teste não acessível publicamente sem controle
- **Não impactar testes automatizados:** pytest nunca deve ser bloqueado por Basic Auth
- **Não impactar produção:** produção tem sua própria camada de autenticação (Flask-Login); Basic Auth extra seria redundante e confuso
- **Simplicidade operacional:** configuração via variáveis de ambiente, sem infraestrutura adicional
- **Defense in depth:** Basic Auth como fallback de app, não como controle único

---

## Considered Options

### Opção A: Apenas VPN / firewall de rede (controle de infra)

Bloquear acesso ao ambiente HML no nível de rede — firewall, VPN corporativa ou ACL de IP no servidor.

- **A favor:** Controle mais robusto (atacante nem alcança a app); padrão CWI recomendado
- **A favor:** Sem impacto no código da aplicação
- **Contra:** Requer configuração de infra que pode não existir em todos os cenários
- **Contra:** Não fornece evidência automatizada em testes

### Opção B: HTTP Basic Auth na aplicação (fallback de app)

Middleware `before_request` que exige Basic Auth quando `STAGING_AUTH_ENABLED=true` e `ENV != production`.

- **A favor:** Funciona mesmo sem VPN configurada
- **A favor:** Testável automaticamente (7 testes no pytest)
- **A favor:** Opt-in explícito, não afeta produção nem testes
- **Contra:** Basic Auth sobre HTTP sem TLS expõe credenciais (mitigação: usar HTTPS no HML)
- **Contra:** Menor robustez que controle de rede

### Opção C: Token de API no header (ex: `X-Staging-Token`)

Header customizado obrigatório em todas as requisições ao ambiente HML.

- **A favor:** Não aparece em caches ou proxies de forma óbvia
- **Contra:** Não é um padrão suportado nativamente por browsers; requer JS customizado para enviar em cada request
- **Contra:** Mais complexo de implementar sem frameworks

---

## Decision

**Duas camadas complementares:**

### Camada 1 — Primária (CWI, documentada em ops): VPN / Firewall de rede

- Controle no nível de rede antes de qualquer request alcançar a app
- **Procedimento QA CWI 4.1:** acessar URL do ambiente HML a partir de computador pessoal (sem VPN/rede corporativa) — deve ser bloqueado pelo firewall antes de chegar à aplicação
- Este é o controle que atende formalmente o CWI 4.1

### Camada 2 — Fallback (app): HTTP Basic Auth via env vars

Implementado em `app/__init__.py:_proteger_staging()` como `before_request`.

**Regras de ativação (fail-closed):**

| Condição | Comportamento |
|---|---|
| `ENV=production` | Basic Auth **nunca** aplicado |
| `TESTING=True` (pytest) | Basic Auth **nunca** aplicado |
| `STAGING_AUTH_ENABLED` ausente ou `false` | Basic Auth desativado (default seguro) |
| `STAGING_AUTH_USER` ou `STAGING_AUTH_PASSWORD` ausentes | Basic Auth desativado (misconfiguration = desativado) |
| `STAGING_AUTH_ENABLED=true` + credenciais definidas + `ENV != production` | Basic Auth **ativo** |

**Rotas excluídas do Basic Auth:**
- `GET /health` — healthcheck para monitoramento externo (deve sempre responder)
- `GET /login` — fluxo de autenticação da app (não pode ser bloqueado antes do login)
- `GET /sw.js` — Service Worker (deve ser acessível sem auth pelo browser)

**Segurança:**
- Comparação timing-safe: `hmac.compare_digest(user)` e `hmac.compare_digest(senha)`
- Senha nunca logada
- Mensagem de erro genérica (sem vazar qual campo falhou)
- Resposta 401 + `WWW-Authenticate: Basic realm="DTX Staging"`

---

## Consequences

### Positivo

- CWI 4.1 atendido em duas camadas (VPN primária + Basic Auth fallback)
- Testes automatizados nunca bloqueados (`TESTING=True` → skip middleware)
- Produção inalterada (`ENV=production` → skip middleware)
- Opt-in explícito via `STAGING_AUTH_ENABLED=true` — default seguro (desativado)
- 7 testes automatizados cobrem todos os cenários críticos

### Negativo

- Basic Auth transmite credencial codificada em Base64 (não criptografada) → exige HTTPS no ambiente HML
- Credenciais em env vars exigem cuidado para não vazar em logs ou dashboards de CI
- Não substitui controle de rede como camada primária

### Riscos e Mitigações

| Risco | Mitigação |
|---|---|
| Basic Auth interceptado em HTTP | Usar HTTPS no ambiente HML; VPN como camada primária |
| Credenciais fracas em env vars | Documentado: gerar com `secrets.token_urlsafe(32)` |
| Bloquear /health e impedir monitoramento | Rota `/health` explicitamente excluída |
| Pytest bloqueado | `TESTING=True` → middleware inativo (testado em `test_staging_auth_desativado_em_testing`) |

---

## Implementation Notes

- Middleware registrado em `app/__init__.py:_proteger_staging()` — chamado após `_configurar_seguranca()`
- Lê `STAGING_AUTH_ENABLED`, `STAGING_AUTH_USER`, `STAGING_AUTH_PASSWORD` de `os.environ` em request time (permite patch em testes sem reload)
- Lê `ENV` de `current_app.config` (já carregado no boot via `Config`)
- Testes: `tests/test_routes/test_staging_auth.py` (7 testes)
- Vars documentadas em: `.env.example`, `docs/ENV.md`, `docs/DEPLOYMENT_PLAN.md`

---

## Related Decisions

- [ADR-003](003-fail-fast-config-producao.md) — Fail-fast em configuração de produção (CWI 2.1)

---

## References

- [Checklist CWI para QAs — item 4.1](https://cwi.com.br/blog/testes-de-seguranca-para-qas/)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- `docs/CHECKLIST_SEGURANCA.md §10.4` — checklist de proteção de ambientes
- `docs/DEPLOYMENT_PLAN.md §Staging` — procedimento QA VPN
