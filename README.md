# Sistema de Chamados DTX

> Sistema web de gerenciamento de chamados integrado com Firebase/Firestore, construído com Python/Flask.

## 🚀 Características

- **Paginação Otimizada**: Cursor-based pagination para performance com grandes volumes
- **Índices Firestore**: Índices compostos para máxima velocidade de queries
- **Atualização em Tempo Real**: Status atualiza sem recarregar a página
- **Dashboard Completo**: Visualização, filtros e histórico de alterações
- **Autenticação Segura**: Login com Firebase Authentication
- **Upload de Anexos**: Suporte a arquivos (PDFs, imagens, etc)
- **Logs Estruturados**: Rastreamento completo de ações
- **Rate Limiting**: Proteção contra abuso de requisições

## 📋 Requisitos

- Python 3.8+
- Firebase Account com Firestore
- pip (gerenciador de pacotes Python)

## 🔧 Instalação

### 1. Clone o repositório

```bash
git clone https://github.com/matheusth16/sistema-chamados-dtx.git
cd sistema-chamados-dtx
```

### 2. Crie um ambiente virtual

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS/Linux
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Instale as dependências

```bash
pip install -r requirements.txt
```

### 4. Configure credenciais do Firebase

1. Vá para [Firebase Console](https://console.firebase.google.com)
2. Baixe `credentials.json` da sua conta de serviço
3. Coloque na raiz do projeto

### 5. Configure variáveis de ambiente

Copie o exemplo e preencha (veja **ENV.md** para a lista completa):

```bash
cp .env.example .env
# Edite .env e defina ao menos SECRET_KEY e FLASK_ENV
# Em produção: defina FLASK_ENV=production e use SECRET_KEY forte (ex: openssl rand -hex 32)
```

Documentação das variáveis: **[ENV.md](ENV.md)**

### 6. Inicie a aplicação

```bash
python run.py
```

Acesse: `http://localhost:5000`

## 📚 APIs Disponíveis

### GET `/health`
Health check para load balancer e monitoramento. Retorna `200` e `{"status": "ok"}` quando a aplicação está no ar.

### GET `/api/chamados/paginar`
Paginação inteligente de chamados com cursor

**Query Params:**
- `limite`: 1-100 documentos por página (padrão: 50)
- `cursor`: ID do último documento (para próxima página)
- `status`: Filtrar por status (Aberto, Em Atendimento, Concluído)
- `categoria`: Filtrar por categoria
- `gate`: Filtrar por gate
- `search`: Busca full-text

**Response:**
```json
{
  "sucesso": true,
  "chamados": [...],
  "paginacao": {
    "cursor_proximo": "doc123",
    "tem_proxima": true,
    "total_pagina": 50,
    "limite": 50
  }
}
```

### POST `/api/carregar-mais`
Carregar mais registros (infinite scroll)

**Body:**
```json
{
  "cursor": "doc123",
  "limite": 20
}
```

### POST `/api/atualizar-status`
Atualizar status de um chamado sem recarregar a página

**Body:**
```json
{
  "chamado_id": "doc123",
  "novo_status": "Concluído"
}
```

## 🏗️ Estrutura do Projeto

```
sistema-chamados-dtx/
├── app/
│   ├── services/
│   │   ├── filters.py           # Filtros Firestore otimizados
│   │   ├── pagination.py        # Serviço de paginação
│   │   ├── validators.py        # Validações
│   │   ├── upload.py            # Upload de arquivos
│   │   └── ...
│   ├── templates/
│   │   ├── dashboard.html       # Painel administrativo
│   │   ├── formulario.html      # Formulário de novo chamado
│   │   ├── historico.html       # Histórico de alterações
│   │   ├── indices_firestore.html
│   │   └── ...
│   ├── static/
│   │   ├── js/                  # Scripts JavaScript
│   │   ├── css/                 # Estilos
│   │   └── uploads/             # Uploads de usuários
│   ├── models.py                # Modelos de dados
│   ├── routes.py                # Rotas e endpoints
│   ├── database.py              # Configuração Firebase
│   └── ...
├── config.py                     # Configurações da app
├── run.py                        # Ponto de entrada
├── requirements.txt             # Dependências
├── firestore.indexes.json       # Índices Firestore
├── firestore.rules              # Regras de segurança
└── README.md
```

## ⚡ Performance

### Impacto das Otimizações

| Operação | Antes | Depois | Melhoria |
|---|---|---|---|
| Carregar dashboard | 3-5s | 200-400ms | **15x** |
| Mudar status | 2-3s | 100-200ms | **20x** |
| Filtrar (com índice) | 2-5s | 50-100ms | **50x** |
| Busca full-text | 3-4s | 300-500ms | **10x** |

### Índices Firestore Recomendados

Para máxima performance, crie os seguintes índices no Firestore Console:

1. `categoria` + `status` + `data_abertura`
2. `status` + `data_abertura`
3. `categoria` + `prioridade` + `data_abertura`
4. `gate` + `status` + `data_abertura`

Ou via CLI:
```bash
firebase deploy --only firestore:indexes --project seu-projeto-id
```

## 🔒 Segurança

- ✅ Autenticação realizada em todas as rotas sensíveis
- ✅ Rate limiting habilitado
- ✅ Validação rigorosa de entrada
- ✅ CSRF protection ativado
- ✅ Passwords hasheados com werkzeug
- ✅ Logs de auditoria completos
- ✅ Credenciais Firebase não são versionadas
- ✅ Em produção, `SECRET_KEY` é obrigatória (valor forte e único)
- ✅ Headers de segurança: `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, HSTS em HTTPS
- ✅ Validação de Origin/Referer em POST sensíveis quando `APP_BASE_URL` está definido

## 📖 Documentação

- **Firestore Rules:** Ver `firestore.rules`
- **Índices:** Ver `firestore.indexes.json`
- **Configuração:** Ver `config.py`

## 🐛 Troubleshooting

### Erro: "FAILED_PRECONDITION" em query

**Causa:** Índice composto faltando  
**Solução:** Criar índice no Firebase Console ou via CLI

### Dashboard carrega lento

**Causa:** Firestore indexando em background  
**Solução:** Esperar 15 minutos após criar índices

### Erro de conexão com Firebase

**Causa:** `credentials.json` não encontrado  
**Solução:** Adicionar arquivo de credenciais na raiz do projeto

### Erro ao subir em produção: "SECRET_KEY must be set"

**Causa:** Em `FLASK_ENV=production` a aplicação exige `SECRET_KEY` no ambiente.  
**Solução:** Defina `SECRET_KEY` com um valor forte (ex: `openssl rand -hex 32`) nas variáveis de ambiente.

### Dependências e vulnerabilidades

Execute periodicamente para checar dependências:

```bash
pip install -U pip
pip audit
```

Atualize pacotes quando necessário: `pip install -r requirements.txt --upgrade` (teste após atualizar).

## 📝 Commit Config

User: Matheus Costa  
Email: matheus@dtx-aerospace.com

## 🤝 Contribuindo

1. Faça um Fork do projeto
2. Crie uma branch para sua feature (`git checkout -b feature/AmazingFeature`)
3. Commit suas mudanças (`git commit -m 'Add some AmazingFeature'`)
4. Push para a branch (`git push origin feature/AmazingFeature`)
5. Abra um Pull Request

## 📄 Licença

Este projeto é propriedade da DTX Aerospace.

## 👤 Autor

**Matheus Costa**
- GitHub: [@matheusth16](https://github.com/matheusth16)
- Email: matheus@dtx-aerospace.com

## 🎯 Roadmap

- [ ] Frontend com "Carregar Mais" visual
- [ ] Infinite scroll automático
- [ ] Cache local com IndexedDB
- [ ] Caching na API (Redis)
- [ ] Export em múltiplos formatos
- [ ] Relatórios avançados
- [ ] Mobile app
- [ ] Notificações em tempo real (WebSocket)

---

**Feito com ❤️ por Matheus Costa**
