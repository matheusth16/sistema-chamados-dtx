"""
Serviço de Filtros para Dashboard de Chamados

Aplicar múltiplos filtros a queries do Firestore para buscar chamados específicos.
Usa indexação Firestore para performance, com fallback para filtros em memória.

**Filtros Disponíveis:**

| Parâmetro | Exemplos | Comportamento |
|-----------|----------|---------------|
| `status` | 'Aberto', 'Em Atendimento', 'Concluído' | Filtra por status exato |
| `categoria` | 'Projetos', 'Manutenção' | Filtra por categoria |
| `gate` | 'Gate 1', 'Gate 2' | Filtra por gate (produção) |
| `responsavel` | User ID | Chamados atribuídos a supervisor |
| `search` | Qualquer texto | Busca em descrição, código RL, etc (case-insensitive) |
| Valor 'Todos'/'Todas' | Qualquer filtro | Ignora o filtro (retorna tudo) |

**Estratégia de Performance:**

1. **Índices Firestore:** Status, gate, responsavel usam índices compostos (rápido)
2. **Filtros em Memória:** Categoria, search aplicados após buscar do Firestore (mais flexível)
3. **Cursor-Based Pagination:** Uso de snapshots para paginação eficiente (sem offset)

**Exemplos de Uso:**

```python
# Chamados abertos da última semana
filtros = {'status': 'Aberto', 'data_inicio': datetime.now() - timedelta(days=7)}
docs = aplicar_filtros_dashboard_com_paginacao(
    chamados_query, 
    filtros=filtros,
    pagina=1
)

# Chamados de um supervisor específico com busca
filtros = {'responsavel': 'userId123', 'search': 'falha'}
docs = aplicar_filtros_dashboard(chamados_query, filtros)

# Paginação com cursor
resultado = aplicar_filtros_dashboard_com_paginacao(
    query_ref=chamados_query,
    args={'status': 'Concluído'},
    limite=50,
    cursor='ultimo_doc_id_da_pagina_anterior'
)
if resultado['tem_proxima']:
    # Buscar próxima página usando resultado['proximo_cursor']
```

**Notas Importantes:**
- Filtros são case-sensitive para status/categoria
- Search é substring match (parcial)
- Valor vazio em status/gate ignora o filtro
- Cursor vazio ou inválido reinicia do início
"""

def _construir_query_base(query_ref, args):
    """
    OTIMIZAÇÃO 1: Aplica filtros baseados em índices Firestore
    
    Retorna: (query_filtrada, categoria_filtrada, categoria, status, gate)
    """
    status = args.get('status')
    gate = args.get('gate')
    categoria = args.get('categoria')
    responsavel = args.get('responsavel', '').strip()

    query_filtrada = query_ref

    if status and status not in ['', 'Todos']:
        query_filtrada = query_filtrada.where('status', '==', status)

    if gate and gate not in ['', 'Todos']:
        query_filtrada = query_filtrada.where('gate', '==', gate)

    if responsavel:
        query_filtrada = query_filtrada.where('responsavel', '==', responsavel)

    categoria_filtrada = categoria and categoria not in ['', 'Todas']

    return query_filtrada, categoria_filtrada, categoria, status, gate


def construir_query_para_contagem(query_ref, args):
    """
    Retorna a query com os mesmos filtros por índice usados no dashboard.

    Use com obter_total_por_contagem() para obter o total de documentos sem
    carregar todos em memória (agregação no Firestore). Quando há filtros
    em memória (categoria, search), o total retornado pode ser maior que o
    número real de resultados exibidos.
    """
    query_filtrada, _, _, _, _ = _construir_query_base(query_ref, args)
    return query_filtrada


def _aplicar_filtros_em_memoria(docs, status, gate, categoria, search):
    """
    OTIMIZAÇÃO 2: Filtros que não podem usar índices compostos
    
    Nota: Esses filtros são aplicados APÓS buscar o limite de documentos.
    Para manter performance, eles funcionam apenas nos documentos recuperados.
    """
    resultado = docs
    
    # Filtro de categoria (inclui Projetos no topo se necessário)
    if categoria and categoria not in ['', 'Todas']:
        resultado = [d for d in resultado if d.to_dict().get('categoria') == categoria]
    
    # Busca por texto (case-insensitive)
    if search:
        termo = search.lower()
        resultado = [
            doc for doc in resultado
            if (
                termo in str(doc.to_dict().get('descricao', '')).lower() or
                termo in str(doc.to_dict().get('rl_codigo', '')).lower() or
                termo in str(doc.to_dict().get('responsavel', '')).lower() or
                termo in str(doc.to_dict().get('numero_chamado', '')).lower() or
                termo in doc.id.lower()
            )
        ]
    
    return resultado


def aplicar_filtros_dashboard_com_paginacao(query_ref, args, limite=50, cursor=None):
    """
    OTIMIZAÇÃO 3: Paginação por cursor (cursor-based pagination)
    
    Ao invés de usar offset, que é ineficiente no Firestore,
    usamos documentos "cursor" para saber por onde começar.
    
    Args:
        query_ref: Referência da coleção Firestore
        args: Argumentos da URL (filtros)
        limite: Documentos por página (padrão: 50)
        cursor: ID do último documento da página anterior (para paginação)
    
    Returns:
        {
            'docs': [DocumentSnapshot, ...],
            'proximo_cursor': ID do último documento,
            'tem_proxima': bool (há mais documentos?)
        }
    """
    query_filtrada, categoria_filtrada, categoria, status, gate = _construir_query_base(query_ref, args)
    search = args.get('search')
    
    # Se há um cursor, começa depois daquele documento
    q = query_filtrada
    if cursor:
        try:
            cursor_doc = query_ref.document(cursor).get()
            if cursor_doc.exists:
                q = q.start_after(cursor_doc)
        except:
            # Se cursor é inválido, ignora e começa do início
            pass
    
    # Busca LIMITE + 1 para saber se há próxima página
    docs_stream = list(q.limit(limite + 1).stream())
    
    tem_proxima = len(docs_stream) > limite
    if tem_proxima:
        docs_stream = docs_stream[:limite]
    
    # Se há filtros em memória, aplica (como ele filt também pode reduzir docs)
    docs_filtrados = _aplicar_filtros_em_memoria(docs_stream, status, gate, categoria, search)
    
    proximo_cursor = None
    if docs_filtrados:
        proximo_cursor = docs_filtrados[-1].id
    
    return {
        'docs': docs_filtrados,
        'proximo_cursor': proximo_cursor,
        'tem_proxima': tem_proxima and len(docs_filtrados) == limite
    }


def aplicar_filtros_dashboard(query_ref, args):
    """
    OTIMIZAÇÃO 4: Função legada mantida para compatibilidade
    
    Usa paginação com limite padrão de 50 documentos
    Não usa cursor (começa do início sempre)
    
    IMPORTANTE: Para usar cursor-based pagination, use aplicar_filtros_dashboard_com_paginacao()
    """
    resultado = aplicar_filtros_dashboard_com_paginacao(query_ref, args, limite=50, cursor=None)
    return resultado['docs']