# Política de Segurança e Conformidade LGPD

Este documento descreve as medidas de segurança e o alinhamento do **Sistema de Chamados** à Lei Geral de Proteção de Dados (LGPD - Lei nº 13.709/2018).

---

## 1. Base legal e finalidade

- **Base legal**: Execução de contrato e legítimo interesse (gestão de chamados, atendimento e auditoria interna).
- **Finalidade**: Tratamento de dados pessoais apenas para operação do sistema (identificação de usuários, responsáveis, solicitantes e registro de histórico de chamados).
- **Minimização**: Coletamos apenas o estritamente necessário: nome, e-mail, perfil e áreas de atuação para usuários; dados de chamados e histórico para auditoria.

---

## 2. Dados tratados

| Categoria              | Exemplos                    | Onde são armazenados | Finalidade                    |
|------------------------|----------------------------|----------------------|------------------------------|
| Dados cadastrais       | Nome, e-mail, perfil, áreas| Firestore (usuarios) | Autenticação e gestão        |
| Dados de chamados      | Descrição, responsável, anexos | Firestore (chamados) | Atendimento e rastreamento   |
| Histórico de ações     | Quem alterou, quando, valor anterior/novo | Firestore (historico) | Auditoria e conformidade     |
| Credenciais            | Hash de senha (nunca senha em texto) | Firestore (usuarios) | Autenticação                 |
| Inscrições Web Push    | Endpoint e chaves (p256dh, auth) | Firestore (push_subscriptions) | Notificações no navegador   |

---

## 3. Segurança dos dados

### 3.1 Criptografia em repouso

- **Senhas**: Armazenadas apenas como hash (Werkzeug/bcrypt), nunca em texto claro.
- **Campos de dados pessoais (PII)**: `nome` e `email` dos usuários são armazenados **criptografados com Fernet (AES-128-CBC + HMAC-SHA256)** no Firestore quando `ENCRYPT_PII_AT_REST=true`. Um hash determinístico (`email_lookup_hash = sha256(email)`) permite busca/login sem descriptografar o índice. Formato: `fernet:v1:<token>`.
  - Default `ENCRYPT_PII_AT_REST=false`: plaintext (retrocompatível) — ativar via procedimento em `docs/ENV.md`.
  - Implementado na **Onda 4** (2026-06-23). Ver ADR: `docs/adr/001-criptografia-pii-fernet.md`.
- **Firestore**: Acesso apenas pelo backend (Firebase Admin SDK). Regras do Firestore negam leitura/escrita direta do cliente.

### 3.2 Criptografia em trânsito

- **Aplicação**: Em produção, a aplicação deve ser servida exclusivamente via **HTTPS**.
  - Cookies de sessão: `SESSION_COOKIE_SECURE=True`, `HttpOnly`, `SameSite=Lax`.
  - Header **HSTS** (Strict-Transport-Security) é aplicado nas respostas em produção.
- **E-mail**: Uso de **TLS** para SMTP (`MAIL_USE_TLS`).
- **APIs externas**: Firebase e demais integrações utilizam HTTPS.

### 3.3 Outras medidas

- **CSRF**: Proteção CSRF (Flask-WTF) em formulários e APIs sensíveis; token no header `X-CSRFToken` para requisições AJAX.
- **Origin/Referer**: Validação em rotas POST sensíveis quando `APP_BASE_URL` está definida.
- **Rate limiting**: Limite de requisições por IP (ex.: login 5/min; APIs configuráveis).
- **Timeout de sessão**: Encerramento automático após 15 minutos de inatividade.
- **Headers de segurança**: `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Permissions-Policy` (câmera, microfone, geolocalização desabilitados). Em produção: **Content-Security-Policy (CSP)** para mitigar XSS.
- **Upload de anexos**: validação por extensão e por **magic bytes** (conteúdo real); tamanho máximo 10 MB.
- **Logs**: em produção, e-mails não são registrados em texto claro; usa-se mascaramento (ex.: `u***@dominio.com`) para conformidade e menor exposição de PII.

---

## 4. Direitos do titular (LGPD)

A organização que opera o sistema deve garantir os direitos previstos na LGPD, preferencialmente com processos e canal de contato (ex.: e-mail do DPO ou suporte):

| Direito        | Art. LGPD | Como atender                                                                 |
|----------------|-----------|-------------------------------------------------------------------------------|
| **Acesso**     | Art. 18, I | **Implementado** — página `/meus-dados` (`app/routes/auth.py:meus_dados`): qualquer usuário autenticado vê nome, e-mail, perfil, áreas, MFA e forma de login. |
| **Correção**   | Art. 18, III | Permitir edição de dados incompletos/desatualizados (ex.: tela de edição de usuário). |
| **Exclusão**   | Art. 18, VI | **Implementado em duas etapas** — ver detalhe abaixo (desativação reversível → anonimização sob demanda). |
| **Portabilidade** | Art. 18, V | Fornecer dados em formato estruturado (ex.: export em JSON/planilha) — não implementado; ver backlog. |
| **Revogação do consentimento** | Art. 18, IX | Onde houver tratamento baseado em consentimento, permitir revogação.   |

**Exclusão de dados — fluxo em duas etapas (implementado):**

1. **Desativação** (`POST /admin/usuarios/<id>/desativar`) — reversível. Marca `ativo=False`, bloqueia login e invalida sessão ativa. Os dados pessoais (nome, e-mail) permanecem intactos, permitindo reverter via `/admin/usuarios/<id>/ativar`.
2. **Anonimização** (`POST /admin/usuarios/<id>/anonimizar`) — **irreversível**, ação separada e deliberada do admin. Só é permitida para contas já desativadas. Sobrescreve `nome` para "Usuário Removido" e `email` para um valor sintético (`removido-<id>@anonimizado.invalid`), preservando o registro do chamado/histórico associado (sem dado pessoal identificável). Toda ação (criação, edição, desativação, ativação, exclusão, anonimização) fica registrada em `historico_usuarios` (`app/services/historico_usuario_service.py`) com admin responsável e timestamp, para auditoria.

Não existe exclusão física imediata de linha no Firestore ao desativar — isso é intencional: a anonimização é o mecanismo de "esquecimento" real, e é acionada manualmente pelo admin quando desejado, não automaticamente ao desativar.

---

## 5. Retenção e armazenamento

- **Retenção**: Definir política de retenção (ex.: chamados e histórico por X anos; logs por Y meses), documentada internamente.
- **Armazenamento**: Dados em ambiente cloud (Firebase/Firestore e Storage) sob controle de acesso restrito e configurações de segurança do provedor.
- **Backup**: Procedimentos de backup devem seguir a mesma política de segurança e retenção.

---

## 6. Encarregado de Dados (DPO)

A organização deve indicar um **Encarregado de Dados (DPO)** e divulgar canal de contato (e-mail/portal) para:

- Pedidos de titulares (acesso, correção, exclusão, portabilidade, revogação).
- Comunicação com a ANPD quando aplicável.
- Orientação interna sobre práticas de privacidade e segurança.

---

## 7. Conformidade e revisão

- Esta política deve ser revisada periodicamente e sempre que houver mudança relevante no tratamento de dados ou na legislação.
- Manter registro das medidas técnicas e organizacionais (incluindo criptografia, controle de acesso e logs) para demonstração de conformidade à ANPD.

---

## 8. Referências no projeto

| Medida                    | Onde está no código / config                              |
|---------------------------|------------------------------------------------------------|
| Criptografia Fernet (PII) | **Implementado — Onda 4 (2026-06-23).** `nome` e `email` criptografados em repouso no Firestore quando `ENCRYPT_PII_AT_REST=true`. Ver `app/services/pii_encryption.py`, `app/models_usuario.py`, `scripts/migrations/migrar_pii_criptografia.py` e [`docs/adr/001-criptografia-pii-fernet.md`](adr/001-criptografia-pii-fernet.md). Default `false` (ativação via ops, ver `docs/ENV.md`). |
| Hash de senha             | `app/models_usuario.py` (Werkzeug)                         |
| Cookies e HSTS            | `config.py` (session), `app/__init__.py` (headers)          |
| CSP e Permissions-Policy  | `app/__init__.py` (headers em produção)                     |
| CSRF e Origin             | `app/__init__.py`, rotas em `app/routes/`                  |
| Rate limit e timeout      | `app/limiter.py`, `app/__init__.py` (timeout sessão)        |
| Upload (extensão + magic bytes) | `app/services/validators.py`, `app/services/upload.py`; tamanho máx. 10 MB em `config.py` |
| Mascaramento de PII em logs | `app/utils.py` (mask_email_for_log), `app/routes/auth.py` |
| Firestore (somente backend) | `firestore.rules`, `app/database.py`                     |

A criptografia Fernet de PII em repouso foi **implementada na Onda 4** (2026-06-23) via `app/services/pii_encryption.py`. O default `ENCRYPT_PII_AT_REST=false` garante zero breaking change; a ativação exige migração prévia dos dados existentes com `scripts/migrations/migrar_pii_criptografia.py` e criação do índice Firestore em `email_lookup_hash`. Ver procedimento completo em `docs/ENV.md` e `docs/DEPLOYMENT_PLAN.md`.
