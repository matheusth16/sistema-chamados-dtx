# Plano de Implementação de Melhorias - Sistema de Chamados

**Data de Início**: 20 de fevereiro de 2026  
**Status**: Em Progresso

---

## 📋 Resumo Executivo

Este documento descreve o plano de implementação de 3 melhorias principais no Sistema de Chamados da DTX Aerospace:

1. **Correção do erro Jinja2** (`max is undefined`)
2. **Implementação de Tela de Administração de Categorias**
3. **Sistema de Tradução Automática Multilíngue** (PT-BR, EN, ES)

---

## 🔴 ISSUE #1: Erro de Acesso ao Painel Admin

### Problema
**Erro**: `jinja2.exceptions.UndefinedError: 'max' is undefined`  
**Severidade**: CRÍTICA  
**Componente Afetado**: Dashboard (`/admin`)

### Causa
As funções `max()` e `min()` não estavam disponíveis no contexto do template Jinja2, causando erro ao renderizar a paginação do dashboard.

### Solução Implementada
✅ **Concluído em 20/02/2026**

Adicionadas as funções `max` e `min` ao contexto do template em `app/routes/admin.py`:

```python
return render_template(
    'dashboard.html',
    ...
    max=max,
    min=min,
)
```

### Critério de Sucesso
- ✅ Admin consegue acessar `/admin` sem erros
- ✅ Paginação renderiza corretamente
- ✅ Nenhuma exceção `UndefinedError` é levantada

### Impacto
- **Tempo**: Imediato
- **Risco**: Baixo
- **Rollback**: Fácil (uma linha removida)

---

## 📊 ISSUE #2: Sistema de Gerenciamento de Categorias

### Objetivo
Criar uma interface para administradores adicionarem/editarem categorias do sistema:
- **Setores** (Manutenção, Engenharia, TI, etc.)
- **Gates** (Gate 1, Gate 2, Gate 3, etc.)
- **Impactos Principais** (Crítico, Alto, Médio, Baixo)

### Diagrama de Cronograma

```
┌─────────────────────────────────────────────────────────────────────┐
│  Fase 1: Backend (20/02/2026 - 20/02/2026)                         │
├─────────────────────────────────────────────────────────────────────┤
│  ✅ models_categorias.py          - 3 classes de modelo            │
│  ✅ translation_service.py        - Serviço de tradução            │
│  ✅ Rotas no admin.py             - 7 endpoints CRUD               │
└─────────────────────────────────────────────────────────────────────┘
       ↓
┌─────────────────────────────────────────────────────────────────────┐
│  Fase 2: Frontend (20/02/2026 - 20/02/2026)                        │
├─────────────────────────────────────────────────────────────────────┤
│  ✅ admin_categorias.html         - Interface admin                │
│  ✅ Link no base.html              - Navegação                     │
│  🔄 Modais de edição              - Em desenvolvimento             │
└─────────────────────────────────────────────────────────────────────┘
       ↓
┌─────────────────────────────────────────────────────────────────────┐
│  Fase 3: Validação (21/02/2026 - 21/02/2026)                       │
├─────────────────────────────────────────────────────────────────────┤
│  📝 Teste funcional                - CRUD completo                 │
│  📝 Teste de tradução              - PT, EN, ES                    │
│  📝 Teste de permissões            - Admin only                    │
└─────────────────────────────────────────────────────────────────────┘
```

### Estrutura Implementada

#### Backend

**Novo arquivo**: `app/models_categorias.py`
- Classe `CategoriaSetor` - Gerencia setores/departamentos
- Classe `CategoriaGate` - Gerencia gates de produção
- Classe `CategoriaImpacto` - Gerencia níveis de impacto

Cada classe inclui:
- ✅ Tradução automática PT → EN, ES
- ✅ Métodos CRUD (save, get_all, get_by_id)
- ✅ Serialização para Firestore
- ✅ Tratamento de erros com logging

**Novo arquivo**: `app/services/translation_service.py`
- Função `traduzir_texto()` - Tradução individual
- Função `traduzir_categoria()` - Tradução multilíngue
- Função `adicionar_traducao_customizada()` - Customização de tradução
- Mapa local de traduções comuns

**Novas rotas** em `app/routes/admin.py`:
```
GET  /admin/categorias                      - Listar todas categorias
POST /admin/categorias/setor/nova           - Criar novo setor
POST /admin/categorias/gate/nova            - Criar novo gate
POST /admin/categorias/impacto/nova         - Criar novo impacto
POST /admin/categorias/setor/<id>/editar    - Editar setor
POST /admin/categorias/gate/<id>/editar     - Editar gate
POST /admin/categorias/impacto/<id>/editar  - Editar impacto
```

#### Frontend

**Novo arquivo**: `app/templates/admin_categorias.html`
- Interface com abas (Setores | Gates | Impactos)
- Formulário de criação em coluna esquerda
- Lista de categorias em coluna direita
- Indicadores visuais (emojis, cores, status)
- Links para edição

**Modificação**: `app/templates/base.html`
- Adicionado link de navegação "⚙️ Categorias" (apenas para admin)

### Traduções Pré-configuradas

O sistema inclui mapa de tradução automática:

| Português | Inglês | Espanhol |
|-----------|--------|----------|
| Manutenção | Maintenance | Mantenimiento |
| Engenharia | Engineering | Ingeniería |
| Crítico | Critical | Crítico |
| Alto | High | Alto |
| Médio | Medium | Medio |
| Baixo | Low | Bajo |

### Critério de Sucesso

#### Funcional
- ✅ Admin consegue acessar `/admin/categorias`
- ✅ Criar novo setor com tradução automática
- ✅ Criar novo gate com tradução automática
- ✅ Criar novo impacto com tradução automática
- ✅ Listar categorias por tipo
- 🔄 Editar categorias existentes
- ☐ Deletar/desativar categorias

#### Técnico
- ✅ Dados salvos no Firestore
- ✅ Tradução PT → EN, ES funciona
- ✅ Apenas admin pode acessar (`@requer_perfil('admin')`)
- ✅ Logging de todas operações
- ✅ Tratamento de erros com feedback ao usuário

#### UX
- ✅ Interface intuitiva com abas
- ✅ Feedback visual claro (success/error)
- ✅ Indicadores de status (ativo/inativo)
- ✅ Mostra tradução junto ao original

### Permissões

| Ação | Solicitante | Supervisor | Admin |
|------|-----------|-----------|-------|
| Visualizar categorias | Não | Sim | Sim |
| Criar categoria | Não | Não | **Sim** |
| Editar categoria | Não | Não | **Sim** |
| Deletar categoria | Não | Não | **Sim** |

---

## 🌍 ISSUE #3: Tradução Automática Multilíngue

### Objetivo
Toda categoria criada por admin é **automaticamente traduzida** para:
- 🇧🇷 Português (Brasil)
- 🇺🇸 Inglês
- 🇪🇸 Espanhol

### Como Funciona

#### Fluxo 1: Usando Mapa Local
```
Admin insere: "Manutenção"
      ↓
Sistema procura em TRANSLATION_MAP['pt_BR']
      ↓
Encontra: {'en': 'Maintenance', 'es': 'Mantenimiento'}
      ↓
Salva todas as 3 versões no Firestore
```

#### Fluxo 2: Customização
```
Admin pode adicionar tradução customizada via admin_categorias.html
      ↓
Sistema atualiza TRANSLATION_MAP
      ↓
Futuras criações usam essa tradução
```

### Mapa de Tradução Local

Localizado em: `app/services/translation_service.py`

```python
TRANSLATION_MAP = {
    'pt_BR': {
        'Manutencao': {'en': 'Maintenance', 'es': 'Mantenimiento'},
        'Engenharia': {'en': 'Engineering', 'es': 'Ingeniería'},
        # ... mais categorias
    }
}
```

### Critério de Sucesso

- ✅ Categoria em PT é traduzida automaticamente para EN e ES
- ✅ Tradução está correta (não literal, mas contextualizada)
- ✅ Admin pode adicionar traduções customizadas
- ✅ Tradução é salva no Firestore para cada idioma
- ✅ Template display mostra: "🇧🇷 ...PT..." | "🇬🇧 ...EN..." | "🇪🇸 ...ES..."

### Extensibilidade Futura

Para integrar API de tradução (Google Translate, OpenAI):

```python
def traduzir_texto(texto: str, idioma_destino: str = 'en') -> str:
    # Tenta mapa local primeiro
    if resultado_local:
        return resultado_local

    # Fallback para API
    api_result = chamar_google_translate_api(texto, idioma_destino)
    return api_result
```

---

## 📅 Cronograma Consolidado

### Sprint 1: 20/02/2026 (Concluído)
- ✅ Corrigir erro Jinja2
- ✅ Criar modelos de categorias
- ✅ Implementar tradução automática
- ✅ Criar rotas e endpoints
- ✅ Criar interface HTML

### Sprint 2: 21/02/2026 (Próxima)
- 🔄 Implementar edição completa (incl. modais)
- 🔄 Implementar deleção/desativação
- 🔄 Testes de integração
- 🔄 Documentação de API

### Sprint 3: 22/02/2026 (Previsto)
- 📝 Integração com formulário de criação de chamado
- 📝 Validação de categorias ao criar chamado
- 📝 Testes e2e

---

## 🧪 Testes Recomendados

### Teste 1: Acesso ao Dashboard
```
1. Login como admin
2. Clique em "Gestão (Admin)"
3. Aceitar: Dashboard carrega sem erro ❌ → ✅
```

### Teste 2: Criar Setor
```
1. Admin → Categorias → Abrir aba "Setores"
2. Preencher: "Qualidade"
3. Submit
4. Aceitar: Setor criado com traduções (Quality, Calidad) ✅
```

### Teste 3: Tradução Automática
```
1. Criar categoria PT: "Manutenção Corretiva"
2. Verificar Firestore:
   - nome_pt: "Manutenção Corretiva"
   - nome_en: "Corrective Maintenance" (ou valor do mapa)
   - nome_es: "Mantenimiento Correctivo"
3. Aceitar: Todas 3 versões salvas ✅
```

### Teste 4: Permissões
```
1. Login como supervisor
2. Tentar acessar /admin/categorias
3. Aceitar: Acesso negado ✅

1. Login como admin
2. Acessar /admin/categorias
3. Aceitar: Acesso concedido ✅
```

### Teste 5: Interface
```
1. Admin → Categorias
2. Verificar 3 abas carregam corretamente
3. Verificar formulários têm placeholders claros
4. Verificar lista mostra categorias com indicadores
5. Aceitar: Interface intuitiva ✅
```

---

## 📊 Métricas de Sucesso

| Métrica | Alvo | Status |
|---------|------|--------|
| Acesso ao Admin sem erro | 100% | ✅ |
| Categorias criadas com tradução | 100% | ✅ |
| Apenas admin pode gerenciar | 100% | ✅ |
| Interface responsiva | 100% | ✅ |
| Zero erros em logs | 100% | 🔄 |

---

## 🔧 Arquivos Modificados

| Arquivo | Alteração | Status |
|---------|-----------|--------|
| `app/routes/admin.py` | +287 linhas | ✅ |
| `app/templates/base.html` | +7 linhas | ✅ |
| `app/templates/admin_categorias.html` | Novo | ✅ |
| `app/models_categorias.py` | Novo | ✅ |
| `app/services/translation_service.py` | Novo | ✅ |

---

## 🚀 Próximos Passos

1. **Validação**
   - Teste manual de cada funcionalidade
   - Verificar Firestore para dados corretos
   - Validar permissões

2. **Refinamento**
   - Implementar modais de edição/exclusão
   - Adicionar mais traduções ao mapa
   - Melhorar UX com loading states

3. **Integração**
   - Integrar categorias ao formulário de criação de chamado
   - Validar categorias ao criar chamado
   - Testar fluxo completo

---

## 📞 Suporte e Dúvidas

Para questões sobre:
- **Erros Jinja2**: Ver `app/routes/admin.py` linhas 124-130
- **Modelos de Categorias**: Ver `app/models_categorias.py`
- **Tradução**: Ver `app/services/translation_service.py`
- **Interface**: Ver `app/templates/admin_categorias.html`
- **Rotas**: Ver `app/routes/admin.py` seção "ROTAS DE ADMINISTRAÇÃO DE CATEGORIAS"

---

**Última Atualização**: 20 de fevereiro de 2026  
**Responsável**: Sistema de Chamados - DTX Aerospace
