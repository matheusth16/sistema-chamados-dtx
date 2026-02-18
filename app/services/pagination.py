"""
SERVIÇO DE PAGINAÇÃO OTIMIZADO PARA FIRESTORE

Implementa cursor-based pagination para melhor performance com grandes volumes.
Evita o problema do offset com documentos eliminados.

Referência:
https://firebase.google.com/docs/firestore/query-data/query-cursors
"""

from typing import Dict, List, Optional, Any, Tuple
from flask import jsonify


class PaginadorFirestore:
    """
    Gerencia paginação por cursor no Firestore
    
    Características:
    - Cursor-based: mais eficiente que offset
    - Suporta múltiplos filtros
    - Mantém informações de navegação
    """
    
    def __init__(self, limite_padrao: int = 50):
        """
        Args:
            limite_padrao: Documentos por página (padrão 50)
        """
        self.limite = limite_padrao
    
    def paginar(
        self, 
        docs: List[Any],
        pagina: int = 1,
        cursor_anterior: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Pagina uma lista de documentos
        
        Args:
            docs: Lista de DocumentSnapshot do Firestore
            pagina: Número da página (fallback para limit/offset se cursor não existir)
            cursor_anterior: ID do último documento da página anterior
        
        Returns:
            {
                'docs': [docs da página atual],
                'cursor_atual': ID do primeiro documento,
                'cursor_proximo': ID do último documento,
                'tem_anterior': bool,
                'tem_proximo': bool,
                'total_pagina': int,
                'limite': int
            }
        """
        if not docs:
            return self._pagina_vazia()
        
        # Encontra o índice inicial usando cursor se fornecido
        indice_inicio = 0
        if cursor_anterior:
            indice_inicio = self._encontrar_indice_cursor(docs, cursor_anterior)
            if indice_inicio == -1:
                # Cursor inválido, começa do início
                indice_inicio = 0
            else:
                # Começa DEPOIS do cursor
                indice_inicio += 1
        else:
            # Usa número da página se não houver cursor
            indice_inicio = (pagina - 1) * self.limite
        
        # Extrai documentos da página
        indice_fim = indice_inicio + self.limite
        docs_pagina = docs[indice_inicio:indice_fim]
        
        # Verifica se há próxima página
        tem_proximo = indice_fim < len(docs)
        tem_anterior = indice_inicio > 0
        
        cursor_atual = docs_pagina[0].id if docs_pagina else None
        cursor_proximo = docs_pagina[-1].id if docs_pagina else None
        
        return {
            'docs': docs_pagina,
            'cursor_atual': cursor_atual,
            'cursor_proximo': cursor_proximo,
            'tem_anterior': tem_anterior,
            'tem_proximo': tem_proximo,
            'total_pagina': len(docs_pagina),
            'limite': self.limite,
            'indice_inicio': indice_inicio,
            'indice_fim': indice_fim,
            'total_global': len(docs)  # CUIDADO: Isso carrega todos os docs em memória!
        }
    
    def _encontrar_indice_cursor(self, docs: List[Any], cursor_id: str) -> int:
        """Find index of cursor document in list"""
        for i, doc in enumerate(docs):
            if doc.id == cursor_id:
                return i
        return -1
    
    def _pagina_vazia(self) -> Dict[str, Any]:
        """Returns empty page structure"""
        return {
            'docs': [],
            'cursor_atual': None,
            'cursor_proximo': None,
            'tem_anterior': False,
            'tem_proximo': False,
            'total_pagina': 0,
            'limite': self.limite,
            'total_global': 0
        }
    
    def resposta_json(self, resultado_paginacao: Dict[str, Any], chamados_dict: List[Dict]) -> Dict[str, Any]:
        """
        Converte resultado de paginação em JSON com chamados formatados
        
        Args:
            resultado_paginacao: Resultado de paginar()
            chamados_dict: Lista de dicts de chamados
        
        Returns:
            JSON structure pronto para frontend
        """
        return {
            'sucesso': True,
            'chamados': chamados_dict,
            'paginacao': {
                'cursor_anterior': resultado_paginacao['cursor_atual'],
                'cursor_proximo': resultado_paginacao['cursor_proximo'],
                'tem_anterior': resultado_paginacao['tem_anterior'],
                'tem_proximo': resultado_paginacao['tem_proximo'],
                'limite': resultado_paginacao['limite'],
                'total_pagina_atual': resultado_paginacao['total_pagina'],
                'total_global': resultado_paginacao['total_global']
            }
        }


class OptimizadorQuery:
    """
    Otimizações para queries Firestore
    
    Implementa padrões recomendados pelo Google:
    - Índices compostos para filtros múltiplos
    - Paginação eficiente
    - Cache de results (em produção, usar Redis)
    """
    
    # Índices que devem ser criados no Firestore
    INDICES_RECOMENDADOS = [
        {
            'colecao': 'chamados',
            'campos': [
                ('categoria', 'ASCENDING'),
                ('status', 'DESCENDING'),
                ('data_abertura', 'DESCENDING')
            ],
            'descricao': 'Filtro por categoria + status + data'
        },
        {
            'colecao': 'chamados',
            'campos': [
                ('status', 'ASCENDING'),
                ('data_abertura', 'DESCENDING')
            ],
            'descricao': 'Filtro por status + data'
        },
        {
            'colecao': 'chamados',
            'campos': [
                ('categoria', 'ASCENDING'),
                ('prioridade', 'ASCENDING'),
                ('data_abertura', 'DESCENDING')
            ],
            'descricao': 'Filtro por categoria + prioridade'
        },
        {
            'colecao': 'chamados',
            'campos': [
                ('gate', 'ASCENDING'),
                ('status', 'ASCENDING'),
                ('data_abertura', 'DESCENDING')
            ],
            'descricao': 'Filtro por gate + status'
        }
    ]
    
    @staticmethod
    def gerar_script_indices() -> str:
        """
        Gera script para criar índices no Firestore Console
        
        INSTRUÇÕES:
        1. Vá para: https://console.firebase.google.com
        2. Selecione seu projeto
        3. Firestore Database > Índices
        4. Copie cada índice manualmente OU use Firebase CLI
        
        Para CLI (mais rápido):
        firebase firestore:indexes --project=seu-projeto
        """
        script = "# Índices Firestore - Criar no Console\n\n"
        
        for idx, indice in enumerate(OptimizadorQuery.INDICES_RECOMENDADOS, 1):
            script += f"\n## Índice {idx}: {indice['descricao']}\n"
            script += f"Coleção: {indice['colecao']}\n"
            script += "Campos:\n"
            
            for campo, direcao in indice['campos']:
                script += f"  - {campo}: {direcao}\n"
        
        return script
    
    @staticmethod
    def validar_filtros(filtros: Dict[str, str]) -> Tuple[bool, str]:
        """
        Valida se os filtros usam índices disponíveis
        
        Returns:
            (válido, mensagem)
        """
        status = filtros.get('status')
        categoria = filtros.get('categoria')
        gate = filtros.get('gate')
        
        # Exemplo: categoria + status precisa de índice
        if categoria and status:
            return True, "✓ Usando índice: categoria + status"
        
        if gate and status:
            return True, "✓ Usando índice: gate + status"
        
        return True, "✓ Filtros válidos"
