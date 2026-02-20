/**
 * Lógica do Modal de Visualização Ampliada
 * Agora lê os dados diretamente dos atributos 'data-' do botão HTML.
 */

function abrirModal(botao) {
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
        status: botao.dataset.status
    };

    // Debug: Validar que dados foram lidos
    console.log('🔍 Abrindo modal, dados coletados:', dados);

    // 2. Preenche os Dados Básicos (Cabeçalho)
    document.getElementById('modal-titulo').innerText = `Visualizando Chamado ${dados.numero}`;
    document.getElementById('modal-categoria').innerText = translateCategory(dados.categoria);
    document.getElementById('modal-setor').innerText = translateSector(dados.tipo);
    document.getElementById('modal-data').innerText = dados.data_abertura;
    
    // Mostra o solicitante (quem abriu o chamado)
    const solicitanteText = dados.solicitante_nome ? dados.solicitante_nome : dados.responsavel;
    document.getElementById('modal-autor').innerText = solicitanteText;

    // 3. Preenche a Descrição Completa
    document.getElementById('modal-descricao').innerText = dados.descricao;

    // 4. Tratamento Inteligente do Código RL
    const elRl = document.getElementById('modal-rl-container');
    const txtRl = document.getElementById('modal-rl-texto');
    
    if (dados.rl_codigo && dados.rl_codigo !== 'None' && dados.rl_codigo !== '') {
        txtRl.innerText = `Código RL: ${dados.rl_codigo}`;
        elRl.classList.remove('hidden');
    } else {
        elRl.classList.add('hidden');
    }

    // 5. Tratamento do Anexo
    const divAnexo = document.getElementById('modal-area-anexo');
    const linkAnexo = document.getElementById('modal-link-anexo');
    
    if (dados.anexo && dados.anexo !== 'None' && dados.anexo !== '') {
        linkAnexo.href = `/static/uploads/${dados.anexo}`;
        linkAnexo.innerText = `📎 Baixar Anexo (${dados.anexo})`;
        divAnexo.classList.remove('hidden');
    } else {
        divAnexo.classList.add('hidden');
    }

    // 6. Preenche informações do status, responsável e formulário
    const statusDisplayEl = document.getElementById('modal-status-display');
    const statusSelectEl = document.getElementById('select-status-modal');
    const responsavelEl = document.getElementById('modal-responsavel');
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
    
    // Exibe o responsável
    if (responsavelEl) {
        responsavelEl.innerText = dados.responsavel;
    }
    
    // Debug: Validar que dados estão corretos
    console.log('📋 Modal aberto com dados:', {
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

function fecharModal() {
    const modal = document.getElementById('modal-overlay');
    if (!modal) {
        console.error('❌ Modal não encontrado!');
        return;
    }
    
    const inputId = document.getElementById('input-chamado-id');
    const chamadoId = inputId ? inputId.value : 'N/A';
    
    console.log('❌ Fechando modal (Chamado: ' + chamadoId + ')');
    
    modal.classList.add('hidden');
    modal.classList.remove('flex');
}

window.onclick = function(event) {
    const modal = document.getElementById('modal-overlay');
    if (event.target === modal) {
        fecharModal();
    }
}