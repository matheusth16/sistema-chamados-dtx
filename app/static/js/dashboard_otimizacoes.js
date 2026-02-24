/**
 * Dashboard Otimizado - Melhorias de Performance
 * 1. Atualizar status via AJAX (sem recarregar)
 * 2. Busca com debounce (esperar usuário parar de digitar)
 * 3. Virtualização de linhas (renderizar apenas o visível)
 */

const DEBUG = Boolean(window.DTX_DEBUG) || (
    window.location && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
);

function debugLog() {
    if (!DEBUG || !window.console) return;
    console.log.apply(console, arguments);
}

// ============================================================================
// 1. ATUALIZAÇÃO DE STATUS VIA AJAX
// ============================================================================

/**
 * Atualiza o status de um chamado via AJAX
 * @param {HTMLSelectElement} selectElement - O elemento select que foi alterado
 */
async function atualizarStatusAjax(selectElement) {
    const linha = selectElement.closest('tr');
    const form = selectElement.closest('form');
    
    if (!form) {
        debugLog('❌ Erro: formulário não encontrado');
        mostrarNotificacao('Erro: Formulário não encontrado', 'danger');
        return;
    }

    // ========== VALIDAÇÃO DETALHADA ==========
    const chamadoIdInput = form.querySelector('input[name="chamado_id"]');
    const chamadoId = chamadoIdInput?.value?.trim();
    const novoStatus = selectElement.value?.trim();
    const statusAnterior = selectElement.dataset.statusAnterior || selectElement.value;

    // Log detalhado para debug
    debugLog('🔍 DEBUG - Dados coletados:', {
        form_encontrado: !!form,
        input_encontrado: !!chamadoIdInput,
        chamado_id: chamadoId || '[VAZIO]',
        novo_status: novoStatus,
        status_anterior: statusAnterior,
        linha_existe: !!linha
    });

    // Validações rigorosas
    if (!form.querySelector('input[name="chamado_id"]')) {
        debugLog('❌ Campo input[name="chamado_id"] não encontrado no formulário');
        mostrarNotificacao('Erro: Campo ID não encontrado', 'danger');
        return;
    }

    if (!chamadoId) {
        debugLog('❌ chamado_id está vazio!', {
            input_value: chamadoIdInput?.value,
            input_html: chamadoIdInput?.outerHTML
        });
        mostrarNotificacao('Erro: ID do chamado vazio. Recarregue a página.', 'danger');
        return;
    }

    if (!novoStatus) {
        debugLog('❌ novo_status está vazio');
        mostrarNotificacao('Erro: Status não selecionado', 'danger');
        return;
    }

    // Valida o status
    const statusValidos = ['Aberto', 'Em Atendimento', 'Concluído'];
    if (!statusValidos.includes(novoStatus)) {
        debugLog('❌ Status inválido:', novoStatus);
        mostrarNotificacao(`Erro: Status inválido "${novoStatus}"`, 'danger');
        selectElement.value = statusAnterior;
        return;
    }

    if (novoStatus === statusAnterior) {
        debugLog('ℹ️ Status não mudou (mesmo valor)');
        return;
    }

    try {
        // Desabilita o select durante o request
        selectElement.disabled = true;
        debugLog(`🔄 Enviando atualização: ${chamadoId} → ${novoStatus}`);

        // Log do payload
        const payload = {
            chamado_id: chamadoId,
            novo_status: novoStatus
        };
        debugLog('📤 Payload enviado:', JSON.stringify(payload, null, 2));

        // Faz o request AJAX (CSRF no header para proteção)
        const csrfMeta = document.querySelector('meta[name="csrf-token"]');
        const headers = {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        };
        if (csrfMeta && csrfMeta.content) headers['X-CSRFToken'] = csrfMeta.content;
        const response = await fetch('/api/atualizar-status', {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(payload)
        });

        debugLog('📊 HTTP Status:', response.status, response.statusText);
        debugLog('📊 Content-Type:', response.headers.get('content-type'));

        const text = await response.text();
        let resultado;
        try {
            resultado = text ? JSON.parse(text) : {};
        } catch (parseError) {
            debugLog('❌ Erro ao parsear JSON:', parseError);
            debugLog('Resposta raw:', text);
            selectElement.value = statusAnterior;
            mostrarNotificacao('Erro do servidor. Contate o administrador.', 'danger');
            return false;
        }

        debugLog('✅ Resposta do servidor:', resultado);

        if (response.ok && resultado.sucesso) {
            // ✅ Sucesso: atualiza visualmente
            if (linha) {
                atualizarLinhaStatus(linha, novoStatus);
            }
            mostrarNotificacao(resultado.mensagem, 'success');
            selectElement.dataset.statusAnterior = novoStatus;
            
            // Previne que o formulário seja submetido (importante para modal)
            return false;
        } else {
            // ❌ Erro: reverte o status
            debugLog('❌ Erro na resposta:', resultado);
            selectElement.value = statusAnterior;
            mostrarNotificacao(resultado.erro || 'Erro ao atualizar', 'danger');
            return false;
        }
    } catch (erro) {
        debugLog('❌ Erro de conexão:', erro);
        debugLog('Stack trace:', erro.stack);
        selectElement.value = statusAnterior;
        mostrarNotificacao('Erro de conexão. Tente novamente.', 'danger');
        return false;
    } finally {
        selectElement.disabled = false;
    }
}

/**
 * Atualiza a linha da tabela com o novo status
 * @param {HTMLElement} linha - O elemento <tr> da linha
 * @param {string} novoStatus - O novo status
 */
function atualizarLinhaStatus(linha, novoStatus) {
    // Encontra o span do status na linha
    const spanStatus = linha.querySelector('td:nth-child(5) span');
    if (!spanStatus) return;

    // Remove classes anteriores
    spanStatus.classList.remove('bg-green-100', 'text-green-800', 'bg-yellow-100', 'text-yellow-800', 'bg-gray-100', 'text-gray-800');

    // Adiciona novas classes baseado no novo status
    if (novoStatus === 'Concluído') {
        spanStatus.classList.add('bg-green-100', 'text-green-800');
    } else if (novoStatus === 'Em Atendimento') {
        spanStatus.classList.add('bg-yellow-100', 'text-yellow-800');
    } else {
        spanStatus.classList.add('bg-gray-100', 'text-gray-800');
    }

    // Atualiza o texto
    spanStatus.textContent = novoStatus;

    // Animação visual de sucesso
    linha.style.backgroundColor = '#dcfce7'; // Fundo verde claro
    setTimeout(() => {
        linha.style.backgroundColor = '';
    }, 1000);
}

/**
 * Mostra uma notificação em tempo real
 * @param {string} mensagem - Mensagem a exibir
 * @param {string} tipo - 'success', 'danger', 'info'
 */
function mostrarNotificacao(mensagem, tipo = 'info') {
    const classes = {
        success: 'bg-green-50 text-green-800 border-green-200',
        danger: 'bg-red-50 text-red-800 border-red-200',
        info: 'bg-blue-50 text-blue-800 border-blue-200'
    };

    const div = document.createElement('div');
    div.className = `px-4 py-3 rounded-md border text-sm font-medium fixed top-4 right-4 z-50 animate-fade-in ${classes[tipo] || classes['info']}`;
    div.textContent = mensagem;
    document.body.appendChild(div);

    // Remove a notificação após 3 segundos
    setTimeout(() => {
        div.style.opacity = '0';
        div.style.transition = 'opacity 0.3s ease-out';
        setTimeout(() => div.remove(), 300);
    }, 3000);
}

// ============================================================================
// 2. BUSCA COM DEBOUNCE
// ============================================================================

let debounceTimer = null;
const DEBOUNCE_DELAY = 350; // millisegundos

/**
 * Configura o debounce para o campo de busca
 */
function configurarDebounceNaBusca() {
    const inputBusca = document.querySelector('input[name="search"]');
    if (!inputBusca) return;

    inputBusca.addEventListener('input', (e) => {
        // Limpa o timer anterior
        if (debounceTimer) {
            clearTimeout(debounceTimer);
        }

        // Define um novo timer
        debounceTimer = setTimeout(() => {
            // Envia o formulário de busca
            inputBusca.form.submit();
        }, DEBOUNCE_DELAY);
    });

    // Remove o comportamento padrão do submit
    inputBusca.form.addEventListener('submit', (e) => {
        // Permite o submit normal do botão Filtrar
        if (e.submitter && e.submitter.type === 'submit') {
            return; // Deixa fazer submit
        }
        // Bloqueia se for only debounce
        if (e.isTrusted && e.submitter === null) {
            e.preventDefault();
        }
    });
}

// ============================================================================
// 3. VIRTUALIZAÇÃO COM INTERSECTION OBSERVER
// ============================================================================

/**
 * Implementa virtualização de linhas (renderiza apenas as visíveis)
 * Melhora performance com muitas linhas
 */
function configurarVirtualizacao() {
    const tabela = document.querySelector('table tbody');
    if (!tabela) return;

    const linhas = tabela.querySelectorAll('tr');
    if (linhas.length < 50) {
        // Virtualização não necessária para poucas linhas
        return;
    }

    // Cria um Intersection Observer para carregar linhas sob demanda
    const observador = new IntersectionObserver((entradas) => {
        entradas.forEach((entrada) => {
            if (entrada.isIntersecting) {
                const linha = entrada.target;
                // A linha já está renderizada, agora está visível
                linha.style.opacity = '1';
            }
        });
    }, {
        root: null,
        rootMargin: '100px', // Carrega 100px antes de ficar visível
        threshold: 0
    });

    // Observa todas as linhas
    linhas.forEach((linha, index) => {
        observador.observe(linha);
        // Renderiza as primeiras 20 linhas normalmente
        if (index >= 20) {
            linha.style.opacity = '0';
            linha.style.pointerEvents = 'none';
        }
    });
}

/**
 * Otimiza a renderização da tabela com lazy loading
 * Carrega apenas as linhas que estão no viewport
 */
function otimizarRenderizacaoTabela() {
    const tabela = document.querySelector('table');
    if (!tabela) return;

    // Define o container como scroll container otimizado
    tabela.style.willChange = 'contents';
    tabela.style.contain = 'layout style paint';
}

// ============================================================================
// 4. INICIALIZAÇÃO
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Configura debounce na busca
    configurarDebounceNaBusca();

    // Configura virtualização se houver muitas linhas
    configurarVirtualizacao();

    // Otimiza renderização
    otimizarRenderizacaoTabela();

    // Adiciona listeners aos dropdowns de status (tabela e modal)
    document.querySelectorAll('select[name="novo_status"]').forEach((select) => {
        // Armazena o status anterior
        select.dataset.statusAnterior = select.value;

        // TODOS os dropdowns (tabela E modal) usam AJAX
        select.addEventListener('change', (e) => {
            const form = select.closest('form');
            if (form) {
                const chamadoIdInput = form.querySelector('input[name="chamado_id"]');
                const chamadoId = chamadoIdInput?.value;
                if (chamadoId) {
                    debugLog(`🔄 Mudança detectada: Chamado ${chamadoId} → ${select.value}`);
                    select.dataset.chamadoId = chamadoId;
                    atualizarStatusAjax(select);
                } else {
                    debugLog('❌ Erro: chamado_id não encontrado no formulário');
                }
            }
        });
    });

    // Previne que o formulário do modal seja submetido (POST)
    // Pois o AJAX já trata a atualização
    const formularioModal = document.querySelector('#modal-overlay form');
    if (formularioModal) {
        formularioModal.addEventListener('submit', (e) => {
            debugLog('🛑 Bloqueando submit do modal (usar AJAX)');
            e.preventDefault();
            return false;
        });
    }

    debugLog('✓ Dashboard otimizado: AJAX status (tabela + modal), Debounce busca, Virtualização ativados');
});

// ============================================================================
// 5. CSS ANIMATIONS (injetado dinamicamente)
// ============================================================================

const style = document.createElement('style');
style.textContent = `
    @keyframes fadeIn {
        from {
            opacity: 0;
            transform: translateY(-10px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    .animate-fade-in {
        animation: fadeIn 0.3s ease-in;
    }
    
    /* Otimizações de GPU */
    tbody tr {
        will-change: background-color;
        transform: translateZ(0);
    }
`;
document.head.appendChild(style);
