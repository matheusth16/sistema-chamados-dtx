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

- **Senhas**: Armazenadas apenas como hash (Werkzeug), nunca em texto claro.
- **Campos sensíveis (PII)**: O sistema suporta criptografia de campos como o **nome** do usuário no banco, mediante configuração:
  - Variável de ambiente `ENCRYPTION_KEY`: chave Fernet (base64, 32 bytes).  
    Geração: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
  - Variável `ENCRYPT_PII_AT_REST=true` para ativar a criptografia do campo nome na coleção de usuários.
- **Firestore**: Acesso apenas pelo backend (Firebase Admin SDK). Regras do Firestore negam leitura/escrita direta do cliente.

### 3.2 Criptografia em trânsito

- **Aplicação**: Em produção, a aplicação deve ser servida exclusivamente via **HTTPS**.
  - Cookies de sessão: `SESSION_COOKIE_SECURE=True`, `HttpOnly`, `SameSite=Lax`.
  - Header **HSTS** (Strict-Transport-Security) é aplicado nas respostas em produção.
- **E-mail**: Uso de **TLS** para SMTP (`MAIL_USE_TLS`).
- **APIs externas**: Resend, Firebase e demais integrações utilizam HTTPS.

### 3.3 Outras medidas

- **CSRF**: Proteção CSRF (Flask-WTF) em formulários e APIs sensíveis; token no header `X-CSRFToken` para requisições AJAX.
- **Origin/Referer**: Validação em rotas POST sensíveis quando `APP_BASE_URL` está definida.
- **Rate limiting**: Limite de requisições por IP (ex.: login 5/min; APIs configuráveis).
- **Timeout de sessão**: Encerramento automático após 15 minutos de inatividade.
- **Headers de segurança**: `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`.

---

## 4. Direitos do titular (LGPD)

A organização que opera o sistema deve garantir os direitos previstos na LGPD, preferencialmente com processos e canal de contato (ex.: e-mail do DPO ou suporte):

| Direito        | Art. LGPD | Como atender                                                                 |
|----------------|-----------|-------------------------------------------------------------------------------|
| **Acesso**     | Art. 18, I | Fornecer cópia dos dados pessoais do titular (exportação por usuário/admin). |
| **Correção**   | Art. 18, III | Permitir edição de dados incompletos/desatualizados (ex.: tela de edição de usuário). |
| **Exclusão**   | Art. 18, VI | Excluir dados quando não houver base legal (ex.: remoção de usuário e anonimização de histórico). |
| **Portabilidade** | Art. 18, V | Fornecer dados em formato estruturado (ex.: export em JSON/planilha).        |
| **Revogação do consentimento** | Art. 18, IX | Onde houver tratamento baseado em consentimento, permitir revogação.   |

**Sugestão de implementação** (opcional no código):

- Endpoint ou script para **exportação dos dados do titular** (por e-mail ou ID), em formato legível.
- Processo de **exclusão/anonymização** de usuário e vínculos (chamados/histórico), com registro em log para auditoria.

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
| Criptografia (Fernet)     | `app/services/crypto.py`, `config.ENCRYPTION_KEY`, `ENCRYPT_PII_AT_REST` |
| Hash de senha             | `app/models_usuario.py` (Werkzeug)                         |
| Cookies e HSTS            | `config.py` (session), `app/__init__.py` (headers)          |
| CSRF e Origin             | `app/__init__.py`, rotas em `app/routes/`                  |
| Rate limit e timeout      | `app/limiter.py`, `app/__init__.py` (timeout sessão)        |
| Firestore (somente backend) | `firestore.rules`, `app/database.py`                     |

Para ativar criptografia de PII em repouso, configure no `.env`:

```env
ENCRYPTION_KEY=<chave_base64_fernet>
ENCRYPT_PII_AT_REST=true
```

**Importante**: A chave `ENCRYPTION_KEY` é sensível. Mantenha-a em repositório seguro (variáveis de ambiente ou cofre de segredos) e nunca a inclua no controle de versão.
