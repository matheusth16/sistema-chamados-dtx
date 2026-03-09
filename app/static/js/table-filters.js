/**
 * Sistema de Ordenação e Filtros para Tabelas de Chamados
 * 
 * Permite ordenar colunas (ID, Data, SLA) e filtrar por valores (Categoria, Status, Setor)
 * com persistência de estado via sessionStorage.
 */

(function() {
    'use strict';

    // Estado global dos filtros e ordenação
    let state = {
        sortColumn: null,
        sortDirection: 'asc',
        filters: {}
    };

    // Identificador da página para sessionStorage
    const PAGE_KEY = window.location.pathname;

    /**
     * Inicializa o sistema ao carregar a página
     */
    function init() {
        loadState();
        applyStoredState();
    }

    /**
     * Carrega estado salvo do sessionStorage
     */
    function loadState() {
        try {
            const stored = sessionStorage.getItem(`tableState_${PAGE_KEY}`);
            if (stored) {
                state = JSON.parse(stored);
            }
        } catch (e) {
            console.warn('Erro ao carregar estado:', e);
        }
    }

    /**
     * Salva estado no sessionStorage
     */
    function saveState() {
        try {
            sessionStorage.setItem(`tableState_${PAGE_KEY}`, JSON.stringify(state));
        } catch (e) {
            console.warn('Erro ao salvar estado:', e);
        }
    }

    /**
     * Aplica estado armazenado (ordenação e filtros)
     */
    function applyStoredState() {
        // Aplica ordenação armazenada
        if (state.sortColumn !== null) {
            const table = document.querySelector('table tbody');
            if (table) {
                sortTableByColumn(state.sortColumn, state.sortDirection, false);
            }
        }

        // Aplica filtros armazenados
        Object.keys(state.filters).forEach(columnIndex => {
            applyFilter(parseInt(columnIndex), state.filters[columnIndex]);
        });
    }

    /**
     * Ordena tabela por coluna
     * @param {number} columnIndex - Índice da coluna (0-based)
     * @param {string} type - Tipo: 'number', 'date', 'text'
     */
    window.sortTable = function(columnIndex, type) {
        // Alterna direção se já está ordenando por esta coluna
        if (state.sortColumn === columnIndex) {
            state.sortDirection = state.sortDirection === 'asc' ? 'desc' : 'asc';
        } else {
            state.sortColumn = columnIndex;
            state.sortDirection = 'asc';
        }

        sortTableByColumn(columnIndex, state.sortDirection, true, type);
        saveState();
    };

    /**
     * Executa a ordenação da tabela
     */
    function sortTableByColumn(columnIndex, direction, updateIcons, type) {
        const table = document.querySelector('table tbody');
        if (!table) return;

        // Pega todas as linhas, exceto cabeçalhos de grupo RL
        const rows = Array.from(table.querySelectorAll('tr:not(.rl-header-row)'));

        const sortFn = (a, b) => {
            const aCell = a.cells[columnIndex];
            const bCell = b.cells[columnIndex];
            if (!aCell || !bCell) return 0;

            let aValue = getCellValue(aCell, type);
            let bValue = getCellValue(bCell, type);

            let comparison = 0;
            if (type === 'number') {
                comparison = aValue - bValue;
            } else if (type === 'date') {
                comparison = aValue - bValue;
            } else {
                comparison = aValue.localeCompare(bValue, 'pt-BR');
            }
            return direction === 'asc' ? comparison : -comparison;
        };

        // Separa Projetos (prioridade=0) das demais para manter Projetos sempre acima
        const projetos = rows.filter(r => r.dataset.prioridade === '0');
        const outros = rows.filter(r => r.dataset.prioridade !== '0');

        projetos.sort(sortFn);
        outros.sort(sortFn);

        // Reinsere: Projetos primeiro, depois os demais
        [...projetos, ...outros].forEach(row => table.appendChild(row));

        // Reposiciona cabeçalhos RL antes do primeiro ticket do seu grupo
        table.querySelectorAll('tr.rl-header-row').forEach(header => {
            const rl = header.dataset.rl;
            const firstTicket = table.querySelector(`tr[data-rl-codigo="${rl}"]`);
            if (firstTicket) {
                table.insertBefore(header, firstTicket);
            }
        });

        if (updateIcons) {
            updateSortIcons(columnIndex, direction);
        }
    }

    /**
     * Extrai valor da célula conforme o tipo
     */
    function getCellValue(cell, type) {
        const text = cell.textContent.trim();

        if (type === 'number') {
            // Extrai números de strings como "CHM-0001"
            const match = text.match(/\d+/);
            return match ? parseInt(match[0]) : 0;
        } else if (type === 'date') {
            // Converte datas no formato DD/MM/YYYY HH:MM para timestamp
            const dateMatch = text.match(/(\d{2})\/(\d{2})\/(\d{4})/);
            if (dateMatch) {
                const [_, day, month, year] = dateMatch;
                return new Date(`${year}-${month}-${day}`).getTime();
            }
            return 0;
        }

        return text;
    }

    /**
     * Atualiza ícones de ordenação nos cabeçalhos
     */
    function updateSortIcons(activeColumn, direction) {
        document.querySelectorAll('th.sortable').forEach(th => {
            const colIndex = parseInt(th.dataset.column);
            const icon = th.querySelector('.sort-icon');
            if (!icon) return;

            if (colIndex === activeColumn) {
                icon.innerHTML = direction === 'asc' ? '↑' : '↓';
                icon.classList.add('active');
            } else {
                icon.innerHTML = '↕';
                icon.classList.remove('active');
            }
        });
    }

    /**
     * Mostra dropdown de filtro para uma coluna
     * @param {number} columnIndex - Índice da coluna
     * @param {HTMLElement} headerElement - Elemento <th> que foi clicado
     */
    window.showFilterDropdown = function(columnIndex, headerElement) {
        // Remove dropdown existente
        const existing = document.querySelector('.filter-dropdown');
        if (existing) existing.remove();

        const table = document.querySelector('table tbody');
        if (!table) return;

        // Coleta valores únicos da coluna
        const values = new Set();
        const rows = table.querySelectorAll('tr:not(.rl-header-row)');
        
        rows.forEach(row => {
            const cell = row.cells[columnIndex];
            if (cell) {
                let value = cell.textContent.trim();
                // Remove ícones de status (bolinhas)
                value = value.replace(/[●○]/g, '').trim();
                if (value && value !== '—') {
                    values.add(value);
                }
            }
        });

        // Cria dropdown
        const dropdown = createFilterDropdown(Array.from(values).sort(), columnIndex);
        
        // Posiciona abaixo do cabeçalho
        const rect = headerElement.getBoundingClientRect();
        dropdown.style.position = 'absolute';
        dropdown.style.top = `${rect.bottom + window.scrollY}px`;
        dropdown.style.left = `${rect.left + window.scrollX}px`;
        dropdown.style.minWidth = `${rect.width}px`;

        document.body.appendChild(dropdown);

        // Fecha ao clicar fora
        setTimeout(() => {
            document.addEventListener('click', function closeDropdown(e) {
                if (!dropdown.contains(e.target) && e.target !== headerElement) {
                    dropdown.remove();
                    document.removeEventListener('click', closeDropdown);
                }
            });
        }, 0);
    };

    /**
     * Cria elemento HTML do dropdown de filtro
     */
    function createFilterDropdown(values, columnIndex) {
        const dropdown = document.createElement('div');
        dropdown.className = 'filter-dropdown';
        
        let html = '<div class="filter-dropdown-header">Filtrar</div>';
        html += '<div class="filter-dropdown-options">';
        
        // Opção "Todos"
        html += `<label class="filter-option">
            <input type="radio" name="filter-${columnIndex}" value="" ${!state.filters[columnIndex] ? 'checked' : ''}>
            <span>Todos</span>
        </label>`;

        // Opções dos valores únicos
        values.forEach(value => {
            const isChecked = state.filters[columnIndex] === value;
            html += `<label class="filter-option">
                <input type="radio" name="filter-${columnIndex}" value="${escapeHtml(value)}" ${isChecked ? 'checked' : ''}>
                <span>${escapeHtml(value)}</span>
            </label>`;
        });

        html += '</div>';
        dropdown.innerHTML = html;

        // Event listeners para as opções
        dropdown.querySelectorAll('input[type="radio"]').forEach(radio => {
            radio.addEventListener('change', (e) => {
                const value = e.target.value;
                if (value) {
                    state.filters[columnIndex] = value;
                    applyFilter(columnIndex, value);
                } else {
                    delete state.filters[columnIndex];
                    clearFilter(columnIndex);
                }
                saveState();
                updateFilterBadge(columnIndex);
            });
        });

        return dropdown;
    }

    /**
     * Aplica filtro a uma coluna
     */
    function applyFilter(columnIndex, filterValue) {
        const table = document.querySelector('table tbody');
        if (!table) return;

        const rows = table.querySelectorAll('tr:not(.rl-header-row)');
        
        rows.forEach(row => {
            const cell = row.cells[columnIndex];
            if (!cell) return;

            let cellText = cell.textContent.trim().replace(/[●○]/g, '').trim();
            
            // Checa todos os filtros ativos
            let showRow = true;
            Object.keys(state.filters).forEach(colIdx => {
                const checkCell = row.cells[parseInt(colIdx)];
                if (checkCell) {
                    let checkText = checkCell.textContent.trim().replace(/[●○]/g, '').trim();
                    if (!checkText.includes(state.filters[colIdx])) {
                        showRow = false;
                    }
                }
            });

            row.style.display = showRow ? '' : 'none';
        });

        updateRlHeadersVisibility();
        updateFilterBadge(columnIndex);
    }

    /**
     * Atualiza visibilidade dos cabeçalhos de RL: esconde o cabeçalho quando
     * não há nenhum chamado visível naquele grupo (respeitando os filtros ativos).
     */
    function updateRlHeadersVisibility() {
        const table = document.querySelector('table tbody');
        if (!table) return;

        const ticketRows = table.querySelectorAll('tr:not(.rl-header-row)');
        table.querySelectorAll('tr.rl-header-row').forEach(header => {
            const rl = header.getAttribute('data-rl') || '';
            const hasVisibleTicket = Array.from(ticketRows).some(row => {
                const rowRl = row.getAttribute('data-rl-codigo') || '';
                if (rowRl !== rl) return false;
                return row.style.display !== 'none';
            });
            header.style.display = hasVisibleTicket ? '' : 'none';
        });
    }

    /**
     * Remove filtro de uma coluna
     */
    function clearFilter(columnIndex) {
        const table = document.querySelector('table tbody');
        if (!table) return;

        // Se não há mais filtros ativos, mostra todas as linhas e todos os cabeçalhos RL
        if (Object.keys(state.filters).length === 0) {
            const rows = table.querySelectorAll('tr:not(.rl-header-row)');
            rows.forEach(row => row.style.display = '');
            table.querySelectorAll('tr.rl-header-row').forEach(h => { h.style.display = ''; });
        } else {
            // Reaplica os filtros restantes
            Object.keys(state.filters).forEach(colIdx => {
                applyFilter(parseInt(colIdx), state.filters[colIdx]);
            });
        }

        updateFilterBadge(columnIndex);
    }

    /**
     * Atualiza badge de filtro ativo no cabeçalho
     */
    function updateFilterBadge(columnIndex) {
        const header = document.querySelector(`th.filterable[data-column="${columnIndex}"]`);
        if (!header) return;

        let badge = header.querySelector('.filter-badge');

        if (state.filters[columnIndex]) {
            if (!badge) {
                badge = document.createElement('span');
                badge.className = 'filter-badge';
                header.appendChild(badge);
            }
        } else {
            if (badge) badge.remove();
        }
    }

    /**
     * Escapa HTML para prevenir XSS
     */
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Limpa todos os filtros
     */
    window.clearAllFilters = function() {
        state.filters = {};
        saveState();

        const table = document.querySelector('table tbody');
        if (table) {
            const rows = table.querySelectorAll('tr:not(.rl-header-row)');
            rows.forEach(row => row.style.display = '');
            table.querySelectorAll('tr.rl-header-row').forEach(h => { h.style.display = ''; });
        }

        // Remove todos os badges
        document.querySelectorAll('.filter-badge').forEach(badge => badge.remove());
    };

    // Inicializa quando o DOM estiver pronto
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
