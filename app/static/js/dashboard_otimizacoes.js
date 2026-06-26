/**
 * Dashboard Otimizado - Melhorias de Performance
 * 1. Atualizar status via AJAX (sem recarregar)
 * 2. Busca com debounce (esperar usuário parar de digitar)
 */

const DEBUG = Boolean(window.DTX_DEBUG) || (
    window.location && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
);

// i18n messages injected by the template via window.DTX_MSGS
const MSGS = window.DTX_MSGS || {
    cancellation_reason: 'Motivo do cancelamento',
    cancellation_reason_placeholder: 'Informe o motivo do cancelamento',
    cancel_reason_prompt: 'Informe o motivo do cancelamento:',
    cancel_requires_reason: 'O cancelamento exige um motivo.',
    back: 'Voltar',
    apply: 'Aplicar',
    error_form_not_found: 'Erro: Formulário não encontrado',
    error_id_not_found: 'Erro: Campo ID não encontrado',
    error_id_empty: 'Erro: ID do chamado vazio. Recarregue a página.',
    error_status_not_selected: 'Erro: Status não selecionado',
    error_invalid_status: 'Erro: Status inválido',
    error_server: 'Erro do servidor. Contate o administrador.',
    error_update: 'Erro ao atualizar',
    error_connection: 'Erro de conexão. Tente novamente.'
};

// Endpoints injected by the template via window.DTX_URLS (fallback para dev)
const URLS = window.DTX_URLS || {};
const URL_ATUALIZAR_STATUS = URLS.atualizar_status || '/api/atualizar-status';

// Status canônicos injetados pelo template (fonte única no servidor)
const STATUS_VALIDOS = window.DTX_STATUS_VALIDOS || ['Aberto', 'Em Atendimento', 'Concluído', 'Cancelado'];

function debugLog() {
    if (!DEBUG || !window.console) return;
    console.log.apply(console, arguments);
}

// ============================================================================
// MODAL DE CANCELAMENTO (substitui window.prompt — F-33 / S2-05)
// ============================================================================

let _cancelModalResolver = null;

/**
 * Abre modal acessível e aguarda motivo ou cancelamento do usuário.
 * @returns {Promise<string|null>} motivo confirmado, ou null se usuário voltou/fechou
 */
function solicitarMotivoCancelamento() {
    return new Promise((resolve) => {
        const modal = document.getElementById('modal-cancelamento');
        const textarea = document.getElementById('motivo-cancelamento-texto');
        const erroEl = document.getElementById('modal-cancelamento-erro');
        if (!modal || !textarea) {
            resolve(null);
            return;
        }

        textarea.value = '';
        if (erroEl) {
            erroEl.textContent = '';
            erroEl.classList.add('hidden');
        }

        _cancelModalResolver = resolve;
        if (typeof modal.showModal === 'function') {
            modal.showModal();
        } else {
            resolve(null);
            return;
        }
        textarea.focus();
    });
}

function fecharModalCancelamento(resultado) {
    const modal = document.getElementById('modal-cancelamento');
    const resolver = _cancelModalResolver;
    _cancelModalResolver = null;
    if (modal && modal.open) {
        modal.close();
    }
    if (resolver) {
        resolver(resultado);
    }
}

function initModalCancelamento() {
    const modal = document.getElementById('modal-cancelamento');
    const textarea = document.getElementById('motivo-cancelamento-texto');
    const btnConfirm = document.getElementById('btn-confirmar-cancelamento');
    const btnVoltar = document.getElementById('btn-voltar-cancelamento');
    const erroEl = document.getElementById('modal-cancelamento-erro');
    if (!modal || !textarea) return;

    btnConfirm.addEventListener('click', () => {
        const motivo = textarea.value.trim();
        if (!motivo) {
            if (erroEl) {
                erroEl.textContent = MSGS.cancel_requires_reason;
                erroEl.classList.remove('hidden');
            } else {
                mostrarNotificacao(MSGS.cancel_requires_reason, 'warning');
            }
            textarea.focus();
            return;
        }
        fecharModalCancelamento(motivo);
    });

    btnVoltar.addEventListener('click', () => fecharModalCancelamento(null));

    modal.addEventListener('cancel', (e) => {
        e.preventDefault();
        fecharModalCancelamento(null);
    });

    modal.addEventListener('keydown', (e) => {
        if (e.key !== 'Tab' || !modal.open) return;
        const focusables = modal.querySelectorAll(
            'button, textarea, [href], input, select, [tabindex]:not([tabindex="-1"])'
        );
        const list = Array.from(focusables).filter((el) => !el.disabled);
        if (!list.length) return;
        const first = list[0];
        const last = list[list.length - 1];
        if (e.shiftKey && document.activeElement === first) {
            e.preventDefault();
            last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault();
            first.focus();
        }
    });
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
        debugLog('Erro: formulário não encontrado');
        mostrarNotificacao(MSGS.error_form_not_found, 'danger');
        return;
    }

    // ========== VALIDAÇÃO DETALHADA ==========
    const chamadoIdInput = form.querySelector('input[name="chamado_id"]');
    const chamadoId = chamadoIdInput?.value?.trim();
    const novoStatus = selectElement.value?.trim();
    const statusAnterior = selectElement.dataset.statusAnterior || selectElement.value;

    // Log detalhado para debug
    debugLog('DEBUG - Dados coletados:', {
        form_encontrado: !!form,
        input_encontrado: !!chamadoIdInput,
        chamado_id: chamadoId || '[VAZIO]',
        novo_status: novoStatus,
        status_anterior: statusAnterior,
        linha_existe: !!linha
    });

    // Validações rigorosas
    if (!form.querySelector('input[name="chamado_id"]')) {
        debugLog('Campo input[name="chamado_id"] não encontrado no formulário');
        mostrarNotificacao(MSGS.error_id_not_found, 'danger');
        return;
    }

    if (!chamadoId) {
        debugLog('chamado_id está vazio!', {
            input_value: chamadoIdInput?.value,
            input_html: chamadoIdInput?.outerHTML
        });
        mostrarNotificacao(MSGS.error_id_empty, 'danger');
        return;
    }

    if (!novoStatus) {
        debugLog('novo_status está vazio');
        mostrarNotificacao(MSGS.error_status_not_selected, 'danger');
        return;
    }

    // Valida o status
    if (!STATUS_VALIDOS.includes(novoStatus)) {
        debugLog('Status inválido:', novoStatus);
        mostrarNotificacao(`${MSGS.error_invalid_status} "${novoStatus}"`, 'danger');
        selectElement.value = statusAnterior;
        return;
    }

    if (novoStatus === statusAnterior) {
        debugLog('Status não mudou (mesmo valor)');
        return;
    }

    let motivoCancelamento = '';
    if (novoStatus === 'Cancelado') {
        const motivo = await solicitarMotivoCancelamento();
        if (motivo === null) {
            selectElement.value = statusAnterior;
            return;
        }
        motivoCancelamento = motivo;
    }

    try {
        // Desabilita o select durante o request
        selectElement.disabled = true;
        debugLog('Enviando atualização:', chamadoId, '->', novoStatus);

        // Log do payload
        const payload = {
            chamado_id: chamadoId,
            novo_status: novoStatus
        };
        if (novoStatus === 'Cancelado' && motivoCancelamento) {
            payload.motivo_cancelamento = motivoCancelamento;
        }
        debugLog('Payload enviado:', JSON.stringify(payload, null, 2));

        // Faz o request AJAX (CSRF no header para proteção)
        const csrfMeta = document.querySelector('meta[name="csrf-token"]');
        const headers = {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        };
        if (csrfMeta && csrfMeta.content) headers['X-CSRFToken'] = csrfMeta.content;
        const response = await fetch(URL_ATUALIZAR_STATUS, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(payload)
        });

        debugLog('HTTP Status:', response.status, response.statusText);
        debugLog('Content-Type:', response.headers.get('content-type'));

        const text = await response.text();
        let resultado;
        try {
            resultado = text ? JSON.parse(text) : {};
        } catch (parseError) {
            debugLog('Erro ao parsear JSON:', parseError);
            debugLog('Resposta raw:', text);
            selectElement.value = statusAnterior;
            mostrarNotificacao(MSGS.error_server, 'danger');
            return false;
        }

        debugLog('Resposta do servidor:', resultado);

        if (response.ok && resultado.sucesso) {
            if (linha) {
                atualizarLinhaStatus(linha, novoStatus);
            }
            mostrarNotificacao(resultado.mensagem, 'success');
            selectElement.dataset.statusAnterior = novoStatus;
            return false;
        } else {
            debugLog('Erro na resposta:', resultado);
            selectElement.value = statusAnterior;
            mostrarNotificacao(resultado.erro || MSGS.error_update, 'danger');
            return false;
        }
    } catch (erro) {
        debugLog('Erro de conexão:', erro);
        debugLog('Stack trace:', erro.stack);
        selectElement.value = statusAnterior;
        mostrarNotificacao(MSGS.error_connection, 'danger');
        return false;
    } finally {
        selectElement.disabled = false;
    }
}

/**
 * Atualiza a célula de status da linha usando os tokens de cor do design system
 * @param {HTMLElement} linha - O elemento <tr> da linha
 * @param {string} novoStatus - O novo status
 */
function atualizarLinhaStatus(linha, novoStatus) {
    const statusCell = linha.querySelector('[data-cell="status"]');
    if (!statusCell) return;

    const label = typeof translateStatus === 'function'
        ? translateStatus(novoStatus)
        : novoStatus;

    if (typeof dtxStatusBadgeHtml === 'function') {
        statusCell.innerHTML = dtxStatusBadgeHtml(novoStatus, label);
    } else {
        const cls = novoStatus === 'Concluído'
            ? 'bg-status-done-bg text-status-done border-status-done-border'
            : novoStatus === 'Em Atendimento'
            ? 'bg-status-active-bg text-status-active border-status-active-border'
            : novoStatus === 'Cancelado'
            ? 'bg-status-cancelled-bg text-status-cancelled border-status-cancelled-border'
            : 'bg-status-open-bg text-status-open border-status-open-border';
        statusCell.innerHTML = `<span class="px-2.5 py-1 inline-flex items-center text-xs font-bold rounded-dtx-sm border ${cls}">${label}</span>`;
    }

    linha.classList.add('dtx-row-flash');
    setTimeout(() => linha.classList.remove('dtx-row-flash'), 1000);
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
        warning: 'bg-yellow-50 text-yellow-800 border-yellow-200',
        info: 'bg-blue-50 text-blue-800 border-blue-200'
    };

    const div = document.createElement('div');
    div.className = `px-4 py-3 rounded-md border text-sm font-medium fixed top-4 right-4 z-50 animate-fade-in ${classes[tipo] || classes['info']}`;
    div.textContent = mensagem;
    document.body.appendChild(div);

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
        if (debounceTimer) clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            inputBusca.form.submit();
        }, DEBOUNCE_DELAY);
    });

    inputBusca.form.addEventListener('submit', (e) => {
        if (e.submitter && e.submitter.type === 'submit') return;
        if (e.isTrusted && e.submitter === null) e.preventDefault();
    });
}

// ============================================================================
// 3. OTIMIZAÇÃO DE TABELA
// ============================================================================

/**
 * Aplica CSS containment na tabela para isolar reflows
 */
function otimizarRenderizacaoTabela() {
    const tabela = document.querySelector('table');
    if (!tabela) return;
    tabela.style.contain = 'layout style';
}

// ============================================================================
// 4. INICIALIZAÇÃO
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    initModalCancelamento();
    configurarDebounceNaBusca();
    otimizarRenderizacaoTabela();

    document.querySelectorAll('select[name="novo_status"]').forEach((select) => {
        select.dataset.statusAnterior = select.value;

        select.addEventListener('change', (e) => {
            const form = select.closest('form');
            if (form) {
                const chamadoIdInput = form.querySelector('input[name="chamado_id"]');
                const chamadoId = chamadoIdInput?.value;
                if (chamadoId) {
                    debugLog('Mudança detectada: Chamado', chamadoId, '->', select.value);
                    select.dataset.chamadoId = chamadoId;
                    atualizarStatusAjax(select);
                } else {
                    debugLog('Erro: chamado_id não encontrado no formulário');
                }
            }
        });
    });

    const formularioModal = document.querySelector('#modal-overlay form');
    if (formularioModal) {
        formularioModal.addEventListener('submit', (e) => {
            debugLog('Bloqueando submit do modal (usar AJAX)');
            e.preventDefault();
            return false;
        });
    }

    debugLog('Dashboard otimizado: AJAX status (tabela + modal), Debounce busca ativados');
});

// ============================================================================
// 5. CSS ANIMATIONS (injetado dinamicamente)
// ============================================================================

if (!document.getElementById('dtx-dashboard-fade-keyframes')) {
    const style = document.createElement('style');
    style.id = 'dtx-dashboard-fade-keyframes';
    style.textContent = `
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(-10px); }
        to   { opacity: 1; transform: translateY(0); }
    }
    .animate-fade-in { animation: fadeIn 0.3s ease-in; }
`;
    document.head.appendChild(style);
}
