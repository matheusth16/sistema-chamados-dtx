/**
 * Lógica do Modal de Visualização Ampliada
 * Agora lê os dados diretamente dos atributos 'data-' do botão HTML.
 */

const DEBUG = Boolean(window.DTX_DEBUG) || (
    window.location && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
);

function debugLog() {
    if (!DEBUG || !window.console) return;
    console.log.apply(console, arguments);
}

window.abrirModal = function abrirModal(botao) {
    // 1. Coleta os dados dos atributos do botão
    // O 'dataset' pega tudo que começa com 'data-' no HTML
    const dados = {
        id: botao.dataset.id,
        numero: botao.dataset.numero,
        categoria: botao.dataset.categoria,
        tipo: botao.dataset.tipo,
        gate: botao.dataset.gate,
        data_abertura: botao.dataset.data,
        responsavel: botao.dataset.responsavel,
        solicitante_nome: botao.dataset.solicitanteNome,
        descricao: botao.dataset.descricao,
        rl_codigo: botao.dataset.rl,
        anexo: botao.dataset.anexo,
        anexos: botao.dataset.anexos,
        status: botao.dataset.status
    };

    // Debug: Validar que dados foram lidos
    debugLog('🔍 Abrindo modal, dados coletados:', dados);

    // 2. Preenche os Dados Básicos (Cabeçalho)
    document.getElementById('modal-titulo').innerText = `Visualizando Chamado ${dados.numero}`;
    document.getElementById('modal-categoria').innerText = translateCategory(dados.categoria);
    document.getElementById('modal-setor').innerText = translateSector(dados.tipo);
    document.getElementById('modal-data').innerText = dados.data_abertura;

    // Mostra o solicitante (quem abriu o chamado)
    const solicitanteText = dados.solicitante_nome ? dados.solicitante_nome : dados.responsavel;
    document.getElementById('modal-autor').innerText = solicitanteText;

    // 3. Preenche a Descrição Completa (agora é um textarea editável)
    const descTextarea = document.getElementById('modal-descricao');
    if (descTextarea) {
        descTextarea.value = dados.descricao;
    }

    // 4. Tratamento Inteligente do Código RL
    const elRl = document.getElementById('modal-rl-container');
    const txtRl = document.getElementById('modal-rl-texto');

    if (dados.rl_codigo && dados.rl_codigo !== 'None' && dados.rl_codigo !== '') {
        txtRl.innerText = `Código RL: ${dados.rl_codigo}`;
        elRl.classList.remove('hidden');
    } else {
        elRl.classList.add('hidden');
    }

    // 5. Tratamento dos Anexos
    const divAnexos = document.getElementById('modal-area-anexos');
    const listaAnexos = document.getElementById('modal-lista-anexos');

    if (listaAnexos) listaAnexos.innerHTML = '';

    // Ler a lista de anexos (pode vir como 'file1.txt,file2.txt')
    let listaAnexosArray = [];
    if (dados.anexos && dados.anexos !== 'None' && dados.anexos !== '') {
        listaAnexosArray = dados.anexos.split(',');
    } else if (dados.anexo && dados.anexo !== 'None' && dados.anexo !== '') {
        // Fallback pro caso de não ter 'anexos' populado (chamados antigos)
        listaAnexosArray = [dados.anexo];
    }

    if (listaAnexosArray.length > 0 && divAnexos && listaAnexos) {
        listaAnexosArray.forEach(anx => {
            const link = document.createElement('a');
            link.href = `/static/uploads/${anx}`;
            link.target = '_blank';
            link.className = 'inline-flex flex-wrap items-center px-4 py-2 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-blue-700 bg-white hover:bg-gray-50 mr-2 mb-2 max-w-full truncate';
            link.innerText = `📎 Baixar Anexo (${anx})`;
            link.title = anx;
            listaAnexos.appendChild(link);
        });
        divAnexos.classList.remove('hidden');
    } else if (divAnexos) {
        divAnexos.classList.add('hidden');
    }

    const statusDisplayEl = document.getElementById('modal-status-display');
    const statusSelectEl = document.getElementById('select-status-modal');
    const responsavelDisplayEl = document.getElementById('modal-responsavel-display');
    const responsavelSelectEl = document.getElementById('select-responsavel-modal');
    const inputIdEl = document.getElementById('input-chamado-id');

    // Define o ID do chamado no formulário
    if (inputIdEl) {
        inputIdEl.value = dados.id;
    }

    // Define a cor do badge de status (visualização)
    if (statusDisplayEl) {
        statusDisplayEl.innerText = dados.status;
        statusDisplayEl.className = 'inline-flex px-3 py-1 rounded-full text-sm font-bold';

        if (dados.status === 'Concluído') {
            statusDisplayEl.classList.add('bg-green-100', 'text-green-800');
        } else if (dados.status === 'Em Atendimento') {
            statusDisplayEl.classList.add('bg-yellow-100', 'text-yellow-800');
        } else {
            statusDisplayEl.classList.add('bg-gray-100', 'text-gray-800');
        }
    }

    // Pré-seleciona o status atual no select
    if (statusSelectEl) {
        statusSelectEl.value = dados.status;
    }

    // Exibe o responsável atual em modo texto
    if (responsavelDisplayEl) {
        responsavelDisplayEl.innerText = dados.responsavel ? dados.responsavel : 'Nenhum';
    }

    // Reseta o select de responsável para "Sem alteração"
    if (responsavelSelectEl) {
        responsavelSelectEl.value = '';
    }

    // Debug: Validar que dados estão corretos
    debugLog('📋 Modal aberto com dados:', {
        chamado_id: dados.id,
        status_atual: dados.status,
        numero: dados.numero,
        responsavel: dados.responsavel
    });

    // 7. Exibe o Modal
    const modal = document.getElementById('modal-overlay');
    modal.classList.remove('hidden');
    modal.classList.add('flex');
}

window.fecharModal = function fecharModal() {
    const modal = document.getElementById('modal-overlay');
    if (!modal) {
        debugLog('❌ Modal não encontrado!');
        return;
    }

    const inputId = document.getElementById('input-chamado-id');
    const chamadoId = inputId ? inputId.value : 'N/A';

    debugLog('❌ Fechando modal (Chamado: ' + chamadoId + ')');

    modal.classList.add('hidden');
    modal.classList.remove('flex');
}

window.onclick = function (event) {
    const modal = document.getElementById('modal-overlay');
    if (event.target === modal) {
        fecharModal();
    }
}

// Log de confirmação de carregamento (apenas em DEBUG mode)
debugLog('✅ modal_chamado.js carregado com sucesso');
debugLog('Funções disponíveis:', { 
    abrirModal: typeof window.abrirModal, 
    fecharModal: typeof window.fecharModal 
});

// Debug adicional
if (DEBUG) {
    debugLog('🔧 DEBUG MODE ativado');
}