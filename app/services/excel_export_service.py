"""
Serviço Avançado de Exportação para Excel

Fornece exportação de chamados em formato XLSX com múltiplas abas,
formatação profissional, estilos, e análises.

**Funcionalidades:**

1. **Export Completo:**
   - Múltiplas abas: Resumo, Detalhes, Histórico
   - Formatação: cabeçalhos em cores, alinhamento, bordas
   - Styles: Cores indicando status/prioridade

2. **Configurações de Estilo:**
   - Cores padronizadas por tipo de dado (sucesso, alerta, info)
   - Fonte Calibri com tamanhos apropriados
   - Bordas e preenchimentos profissionais
   - Freeze panes para cabeçalhos

3. **Análise Histórica:**
   - Tempo de resolução (data abertura → conclusão)
   - Estatísticas por categoria/supervisor
   - Gráficos de tendência (pode ser adicionado com openpyxl)

**Uso Básico:**

```python
from app.services.excel_export_service import gerar_relatorio_excel

# Obter lista de chamados (usar MAX_EXPORT_CHAMADOS para não estourar cota Firestore)
chamados = db.collection('chamados').limit(MAX_EXPORT_CHAMADOS).stream()

# Gerar Excel
excel_bytes = gerar_relatorio_excel(
    chamados=list(chamados),
    tipo='completo',  # ou 'basico', 'analise'
    titulo='Relatório de Chamados - Fevereiro 2026'
)

# Enviar como download
response.data = excel_bytes
response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
response.headers['Content-Disposition'] = 'attachment; filename=chamados.xlsx'
return response
```

**Formatos Disponíveis:**
- `completo`: Todas as colunas e análises
- `basico`: Colunas essenciais apenas
- `analise`: Foco em histórico e duração
"""


import logging

# Limite de chamados na exportação. Aumentar esse valor aumenta as leituras no
# Firestore e pode aproximar do limite do plano Spark (50k leituras/dia).
# Manter controle para não estourar cota sem necessidade.
MAX_EXPORT_CHAMADOS = 100

import io
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from firebase_admin import firestore

logger = logging.getLogger(__name__)


@dataclass
class ConfiguradorExcel:
    """Configuração de estilos e formatação para Excel"""
    
    # Cores
    COR_HEADER = "1F4E78"  # Azul escuro
    COR_TITULO = "2F5233"  # Verde escuro
    COR_ALERTA = "C65911"  # Laranja
    COR_SUCESSO = "70AD47"  # Verde
    COR_INFO = "4472C4"    # Azul
    
    # Fontes
    FONTE_HEADER = Font(name='Calibri', size=11, bold=True, color="FFFFFF")
    FONTE_TITULO = Font(name='Calibri', size=14, bold=True, color="FFFFFF")
    FONTE_SUBTITULO = Font(name='Calibri', size=11, bold=True)
    FONTE_NORMAL = Font(name='Calibri', size=10)
    
    # Preenchimentos
    PREENCHIMENTO_HEADER = PatternFill(start_color=COR_HEADER, end_color=COR_HEADER, fill_type="solid")
    PREENCHIMENTO_TITULO = PatternFill(start_color=COR_TITULO, end_color=COR_TITULO, fill_type="solid")
    PREENCHIMENTO_LINHA_ALT = PatternFill(start_color="E7E6E6", end_color="E7E6E6", fill_type="solid")
    
    # Bordas
    BORDA_PADRAO = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    # Alinhamentos
    ALINHAMENTO_CENTER = Alignment(horizontal='center', vertical='center', wrap_text=True)
    ALINHAMENTO_LEFT = Alignment(horizontal='left', vertical='center', wrap_text=True)
    ALINHAMENTO_RIGHT = Alignment(horizontal='right', vertical='center', wrap_text=True)


class ExportadorExcelAvancado:
    """Exportador profissional de relatórios em Excel"""
    
    def __init__(self):
        self.db = None
        self.config = ConfiguradorExcel()
    
    def get_db(self):
        """Lazy initialization do Firestore"""
        if self.db is None:
            self.db = firestore.client()
        return self.db
    
    def exportar_relatorio_completo(
        self, 
        chamados: List[Any],
        metricas_gerais: Dict[str, Any],
        metricas_supervisores: List[Dict[str, Any]],
        filtros_aplicados: Dict[str, str]
    ) -> io.BytesIO:
        """Exporta relatório completo com múltiplas abas"""
        wb = Workbook()
        wb.remove(wb.active)  # Remove sheet padrão
        
        # Cria abas
        self._aba_resumo_executivo(wb, metricas_gerais, filtros_aplicados)
        self._aba_chamados_detalhados(wb, chamados)
        self._aba_performance_supervisores(wb, metricas_supervisores)
        self._aba_analise_status(wb, chamados)
        self._aba_analise_categorias(wb, chamados)
        
        # Salva em bytes
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output
    
    def _aba_resumo_executivo(
        self,
        wb: Workbook,
        metricas: Dict[str, Any],
        filtros: Dict[str, str]
    ) -> None:
        """Cria aba de resumo executivo com KPIs"""
        ws = wb.create_sheet("📊 Resumo Executivo", 0)
        ws.sheet_properties.tabColor = "1F4E78"
        
        # Configurar larguras das colunas
        ws.column_dimensions['A'].width = 35
        ws.column_dimensions['B'].width = 25
        ws.column_dimensions['C'].width = 25
        
        # Título
        ws['A1'] = "RESUMO EXECUTIVO - RELATÓRIO DE CHAMADOS"
        ws['A1'].font = self.config.FONTE_TITULO
        ws['A1'].fill = self.config.PREENCHIMENTO_TITULO
        ws['A1'].alignment = self.config.ALINHAMENTO_CENTER
        ws.merge_cells('A1:C1')
        ws.row_dimensions[1].height = 25
        
        # Data de geração
        ws['A2'] = f"Relatório gerado em: {datetime.now().strftime('%d/%m/%Y às %H:%M')}"
        ws['A2'].font = Font(name='Calibri', size=9, italic=True)
        ws.merge_cells('A2:C2')
        
        # Filtros aplicados
        if filtros:
            ws['A3'] = "Filtros Aplicados:"
            ws['A3'].font = self.config.FONTE_SUBTITULO
            linha = 4
            for chave, valor in filtros.items():
                ws[f'A{linha}'] = f"  • {chave}: {valor}"
                ws[f'A{linha}'].font = self.config.FONTE_NORMAL
                linha += 1
            linha += 1
        else:
            linha = 4
        
        # KPIs Principais
        ws[f'A{linha}'] = "INDICADORES PRINCIPAIS"
        ws[f'A{linha}'].font = self.config.FONTE_SUBTITULO
        ws[f'A{linha}'].fill = self.config.PREENCHIMENTO_HEADER
        ws.merge_cells(f'A{linha}:C{linha}')
        
        linha += 1
        
        # Dados de KPI
        kpis = [
            ("Total de Chamados", metricas.get('total_chamados', 0)),
            ("Abertos", metricas.get('abertos', 0)),
            ("Em Andamento", metricas.get('em_andamento', 0)),
            ("Concluídos", metricas.get('concluidos', 0)),
            ("Taxa de Resolução", f"{metricas.get('taxa_resolucao_percentual', 0):.1f}%"),
            ("Tempo Médio de Resolução", f"{metricas.get('tempo_medio_resolucao_horas', 0):.1f}h"),
        ]
        
        for chave, valor in kpis:
            ws[f'A{linha}'] = chave
            ws[f'A{linha}'].font = self.config.FONTE_NORMAL
            ws[f'B{linha}'] = valor
            ws[f'B{linha}'].font = Font(name='Calibri', size=10, bold=True)
            ws[f'B{linha}'].alignment = self.config.ALINHAMENTO_RIGHT
            
            # Adiciona borda
            for col in ['A', 'B', 'C']:
                ws[f'{col}{linha}'].border = self.config.BORDA_PADRAO
            
            # Alternancia de cor
            if linha % 2 == 0:
                for col in ['A', 'B', 'C']:
                    ws[f'{col}{linha}'].fill = self.config.PREENCHIMENTO_LINHA_ALT
            
            linha += 1
        
        # Distribuição por prioridade
        linha += 2
        ws[f'A{linha}'] = "DISTRIBUIÇÃO POR PRIORIDADE"
        ws[f'A{linha}'].font = self.config.FONTE_SUBTITULO
        ws[f'A{linha}'].fill = self.config.PREENCHIMENTO_HEADER
        ws.merge_cells(f'A{linha}:C{linha}')
        
        linha += 1
        distribuicao = metricas.get('distribuicao_prioridade', {})
        for prioridade, quantidade in distribuicao.items():
            ws[f'A{linha}'] = f"Prioridade {prioridade}"
            ws[f'B{linha}'] = quantidade
            ws[f'B{linha}'].alignment = self.config.ALINHAMENTO_RIGHT
            
            for col in ['A', 'B', 'C']:
                ws[f'{col}{linha}'].border = self.config.BORDA_PADRAO
            
            if linha % 2 == 0:
                for col in ['A', 'B', 'C']:
                    ws[f'{col}{linha}'].fill = self.config.PREENCHIMENTO_LINHA_ALT
            
            linha += 1
    
    def _aba_chamados_detalhados(self, wb: Workbook, chamados: List[Any]) -> None:
        """Cria aba com lista detalhada de chamados"""
        ws = wb.create_sheet("📋 Chamados", 1)
        ws.sheet_properties.tabColor = "4472C4"
        
        # Colunas
        colunas = [
            ('Chamado', 15),
            ('Categoria', 12),
            ('Tipo', 15),
            ('Status', 12),
            ('Responsável', 18),
            ('Solicitante', 15),
            ('Área', 12),
            ('Prioridade', 10),
            ('Data Abertura', 15),
            ('Data Conclusão', 15),
            ('Impacto', 10),
        ]
        
        # Header
        for col_num, (titulo, largura) in enumerate(colunas, 1):
            col_letter = get_column_letter(col_num)
            ws.column_dimensions[col_letter].width = largura
            
            cell = ws.cell(row=1, column=col_num, value=titulo)
            cell.font = self.config.FONTE_HEADER
            cell.fill = self.config.PREENCHIMENTO_HEADER
            cell.alignment = self.config.ALINHAMENTO_CENTER
            cell.border = self.config.BORDA_PADRAO
        
        ws.row_dimensions[1].height = 20
        ws.freeze_panes = 'A2'
        
        # Dados
        for numero_linha, chamado in enumerate(chamados, 2):
            dados_linha = [
                chamado.numero_chamado,
                chamado.categoria,
                chamado.tipo_solicitacao,
                chamado.status,
                chamado.responsavel,
                chamado.solicitante_nome or '-',
                chamado.area or '-',
                chamado.prioridade,
                chamado.data_abertura_formatada(),
                chamado.data_conclusao_formatada(),
                chamado.impacto or '-',
            ]
            
            for col_num, valor in enumerate(dados_linha, 1):
                cell = ws.cell(row=numero_linha, column=col_num, value=valor)
                cell.font = self.config.FONTE_NORMAL
                cell.alignment = self.config.ALINHAMENTO_LEFT
                cell.border = self.config.BORDA_PADRAO
                
                # Alternancia de cor
                if numero_linha % 2 == 0:
                    cell.fill = self.config.PREENCHIMENTO_LINHA_ALT
                
                # Colorir status
                if col_num == 4:  # Status
                    if valor == 'Concluído':
                        cell.font = Font(name='Calibri', size=10, color="70AD47", bold=True)
                    elif valor == 'Aberto':
                        cell.font = Font(name='Calibri', size=10, color="C65911", bold=True)
                    elif valor == 'Em Atendimento':
                        cell.font = Font(name='Calibri', size=10, color="4472C4", bold=True)
    
    def _aba_performance_supervisores(
        self,
        wb: Workbook,
        supervisores: List[Dict[str, Any]]
    ) -> None:
        """Cria aba de performance de supervisores"""
        ws = wb.create_sheet("👥 Performance", 2)
        ws.sheet_properties.tabColor = "70AD47"
        
        # Colunas
        colunas = [
            ('Supervisor', 18),
            ('Total Atribuídos', 14),
            ('Concluídos', 12),
            ('Abertos', 12),
            ('Taxa Resolução %', 16),
            ('Tempo Médio (h)', 14),
        ]
        
        for col_num, (titulo, largura) in enumerate(colunas, 1):
            col_letter = get_column_letter(col_num)
            ws.column_dimensions[col_letter].width = largura
            
            cell = ws.cell(row=1, column=col_num, value=titulo)
            cell.font = self.config.FONTE_HEADER
            cell.fill = self.config.PREENCHIMENTO_HEADER
            cell.alignment = self.config.ALINHAMENTO_CENTER
            cell.border = self.config.BORDA_PADRAO
        
        ws.row_dimensions[1].height = 20
        ws.freeze_panes = 'A2'
        
        # Dados ordenados por taxa de resolução (decrescente)
        supervisores_ordenados = sorted(
            supervisores,
            key=lambda x: x.get('taxa_resolucao', 0),
            reverse=True
        )
        
        for numero_linha, sup in enumerate(supervisores_ordenados, 2):
            dados_linha = [
                sup.get('supervisor_nome', 'N/A'),
                sup.get('total', 0),
                sup.get('concluidos', 0),
                sup.get('abertos', 0),
                round(sup.get('taxa_resolucao', 0), 1),
                round(sup.get('tempo_medio_resolucao', 0), 1),
            ]
            
            for col_num, valor in enumerate(dados_linha, 1):
                cell = ws.cell(row=numero_linha, column=col_num, value=valor)
                cell.font = self.config.FONTE_NORMAL
                cell.border = self.config.BORDA_PADRAO
                
                # Alternancia de cor
                if numero_linha % 2 == 0:
                    cell.fill = self.config.PREENCHIMENTO_LINHA_ALT
                
                # Alinhar números à direita
                if col_num > 1:
                    cell.alignment = self.config.ALINHAMENTO_RIGHT
                else:
                    cell.alignment = self.config.ALINHAMENTO_LEFT
    
    def _aba_analise_status(self, wb: Workbook, chamados: List[Any]) -> None:
        """Cria aba de análise por status"""
        ws = wb.create_sheet("📊 Status", 3)
        ws.sheet_properties.tabColor = "F79646"
        
        # Agrupar por status
        status_counts = {}
        status_tempo_medio = {}
        
        for chamado in chamados:
            status = chamado.status
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Header
        ws['A1'] = "ANÁLISE DE STATUS"
        ws['A1'].font = self.config.FONTE_TITULO
        ws['A1'].fill = self.config.PREENCHIMENTO_TITULO
        ws.merge_cells('A1:C1')
        
        ws['A2'] = "Status"
        ws['B2'] = "Quantidade"
        ws['C2'] = "Percentual"
        
        for col in ['A', 'B', 'C']:
            ws[f'{col}2'].font = self.config.FONTE_HEADER
            ws[f'{col}2'].fill = self.config.PREENCHIMENTO_HEADER
            ws[f'{col}2'].alignment = self.config.ALINHAMENTO_CENTER
            ws[f'{col}2'].border = self.config.BORDA_PADRAO
        
        ws.column_dimensions['A'].width = 20
        ws.column_dimensions['B'].width = 12
        ws.column_dimensions['C'].width = 12
        
        total = len(chamados)
        linha = 3
        
        for status, quantidade in sorted(status_counts.items()):
            percentual = (quantidade / total * 100) if total > 0 else 0
            
            ws[f'A{linha}'] = status
            ws[f'B{linha}'] = quantidade
            ws[f'C{linha}'] = f'{percentual:.1f}%'
            
            for col in ['A', 'B', 'C']:
                ws[f'{col}{linha}'].border = self.config.BORDA_PADRAO
                ws[f'{col}{linha}'].font = self.config.FONTE_NORMAL
                
                if linha % 2 == 0:
                    ws[f'{col}{linha}'].fill = self.config.PREENCHIMENTO_LINHA_ALT
            
            # Alinhar números
            ws[f'B{linha}'].alignment = self.config.ALINHAMENTO_RIGHT
            ws[f'C{linha}'].alignment = self.config.ALINHAMENTO_RIGHT
            
            linha += 1
    
    def _aba_analise_categorias(self, wb: Workbook, chamados: List[Any]) -> None:
        """Cria aba de análise por categoria"""
        ws = wb.create_sheet("🏷️ Categorias", 4)
        ws.sheet_properties.tabColor = "9966FF"
        
        # Agrupar por categoria
        categoria_counts = {}
        categoria_status = {}
        
        for chamado in chamados:
            cat = chamado.categoria or 'Sem Categoria'
            categoria_counts[cat] = categoria_counts.get(cat, 0) + 1
            
            if cat not in categoria_status:
                categoria_status[cat] = {}
            
            status = chamado.status
            categoria_status[cat][status] = categoria_status[cat].get(status, 0) + 1
        
        # Header
        ws['A1'] = "ANÁLISE POR CATEGORIA"
        ws['A1'].font = self.config.FONTE_TITULO
        ws['A1'].fill = self.config.PREENCHIMENTO_TITULO
        ws.merge_cells('A1:E1')
        
        ws['A2'] = "Categoria"
        ws['B2'] = "Total"
        ws['C2'] = "Abertos"
        ws['D2'] = "Em Andamento"
        ws['E2'] = "Concluídos"
        
        for col in ['A', 'B', 'C', 'D', 'E']:
            ws[f'{col}2'].font = self.config.FONTE_HEADER
            ws[f'{col}2'].fill = self.config.PREENCHIMENTO_HEADER
            ws[f'{col}2'].alignment = self.config.ALINHAMENTO_CENTER
            ws[f'{col}2'].border = self.config.BORDA_PADRAO
        
        for col in ['A', 'B', 'C', 'D', 'E']:
            ws.column_dimensions[col].width = 15
        
        linha = 3
        
        for categoria in sorted(categoria_counts.keys()):
            ws[f'A{linha}'] = categoria
            ws[f'B{linha}'] = categoria_counts[categoria]
            ws[f'C{linha}'] = categoria_status[categoria].get('Aberto', 0)
            ws[f'D{linha}'] = categoria_status[categoria].get('Em Atendimento', 0)
            ws[f'E{linha}'] = categoria_status[categoria].get('Concluído', 0)
            
            for col in ['A', 'B', 'C', 'D', 'E']:
                ws[f'{col}{linha}'].border = self.config.BORDA_PADRAO
                ws[f'{col}{linha}'].font = self.config.FONTE_NORMAL
                
                if linha % 2 == 0:
                    ws[f'{col}{linha}'].fill = self.config.PREENCHIMENTO_LINHA_ALT
                
                # Alinhar números
                if col != 'A':
                    ws[f'{col}{linha}'].alignment = self.config.ALINHAMENTO_RIGHT
            
            linha += 1


# Instância global
exportador_excel = ExportadorExcelAvancado()
