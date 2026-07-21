/**
 * DTX Onboarding Tour — PT-BR · EN · ES
 *
 * Tour guiado em múltiplos passos para novos usuários.
 * Suporta os 3 perfis: solicitante, supervisor e admin.
 * Suporta os 3 idiomas: pt_BR, en, es (lido do data-lang).
 *
 * Arquitetura:
 *  - Backdrop escuro (z:8999) cobre toda a tela
 *  - Nav elevada (z:9000) para destacar links durante o tour
 *  - Card (z:9001) guia o usuário passo a passo
 *  - Progresso salvo via API (Firestore) em cada avanço
 */
(function () {
  'use strict';

  var root = document.getElementById('onboarding-root');
  if (!root) return;

  var PERFIL       = root.dataset.perfil || '';
  var NOME         = (root.dataset.nome || '').split(' ')[0];
  var LANG         = root.dataset.lang || 'pt_BR';
  var MODO         = root.dataset.modo || 'inicial';
  var IMG_BASE     = root.dataset.imgBase || '';
  var CSRF         = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';
  var URL_AVANCAR  = root.dataset.urlAvancar;
  var URL_CONCLUIR = root.dataset.urlConcluir;
  var URL_PULAR    = root.dataset.urlPular;
  var pasoAtual    = MODO === 'replay' ? 0 : (parseInt(root.dataset.passo, 10) || 0);

  // ─── Textos da UI por idioma ───────────────────────────────────────────────

  var UI = {
    pt_BR: { next: 'Próximo →', finish: 'Concluir', prev: '← Anterior', skip: 'Pular tour',
             done_title: 'Pronto para começar!', done_msg: 'O tour foi concluído. Agora é com você!' },
    en:    { next: 'Next →',    finish: 'Finish',   prev: '← Back',     skip: 'Skip tour',
             done_title: 'Ready to start!',      done_msg: 'Tour completed. Now it\'s up to you!' },
    es:    { next: 'Siguiente →', finish: 'Finalizar', prev: '← Atrás', skip: 'Omitir tour',
             done_title: '¡Listo para comenzar!', done_msg: '¡Tour completado. ¡Ahora es tu turno!' },
  };

  // ─── Definição dos tours por perfil e idioma ──────────────────────────────

  var TOURS = {

    // ── SOLICITANTE ──────────────────────────────────────────────────────────
    solicitante: {
      pt_BR: [
        {
          icon: 'wave',
          titulo: 'Bem-vindo ao Portal de Serviços.',
          descricao: 'Olá, {nome}! Este é o Portal de Serviços da DTX Aerospace, o canal único ' +
                     'para abrir e acompanhar chamados de suporte na empresa. Vamos te mostrar tudo ' +
                     'o que você pode fazer aqui em poucos passos.',
        },
        {
          icon: 'plus',
          titulo: 'Abrindo um Novo Chamado',
          descricao: 'Por aqui você abre um novo chamado para qualquer área de suporte: TI, ' +
                     'Manutenção, RH e outras. Escolha a categoria, descreva o problema com o ' +
                     'máximo de detalhes e anexe arquivos se precisar — nossa equipe é notificada ' +
                     'automaticamente.',
          selector: 'nav a[href="/"]',
          image: 'solicitante/02-novo-chamado.png',
        },
        {
          icon: 'clipboard',
          titulo: 'Acompanhando Seus Chamados',
          descricao: 'Em "Meus Chamados" você vê todos os chamados que abriu, com status ' +
                     'atualizado em tempo real: Aberto, Em Atendimento, Concluído ou Cancelado. ' +
                     'Use os filtros para encontrar um chamado específico rapidamente.',
          selector: 'nav a[href="/meus-chamados"]',
          image: 'solicitante/03-meus-chamados.png',
        },
        {
          icon: 'eye',
          titulo: 'Detalhes de um Chamado',
          descricao: 'Clique em qualquer chamado para ver o histórico completo: quem está ' +
                     'responsável, mudanças de status, comentários e anexos trocados durante o ' +
                     'atendimento.',
          image: 'solicitante/04-detalhe-chamado.png',
        },
        {
          icon: 'edit',
          titulo: 'Editando ou Cancelando um Chamado',
          descricao: 'Errou algo na descrição? Você pode editar um chamado recém-aberto dentro ' +
                     'dos primeiros 30 minutos. Mudou de ideia ou abriu por engano? É possível ' +
                     'cancelar o chamado informando o motivo.',
          image: 'solicitante/05-editar-cancelar.png',
        },
        {
          icon: 'check',
          titulo: 'Confirmando a Resolução',
          descricao: 'Quando seu chamado for marcado como Concluído, você recebe uma notificação ' +
                     'para confirmar se o problema foi realmente resolvido. Se não foi, você pode ' +
                     'reabrir o chamado direto pela mesma tela.',
          image: 'solicitante/06-confirmar-resolucao.png',
        },
        {
          icon: 'lightbulb',
          titulo: 'Dica: Mais detalhes = resposta mais rápida',
          descricao: 'Ao abrir um chamado, adicione uma descrição clara e anexos quando possível. ' +
                     'Quanto mais informação, mais rápida a resolução pela equipe!',
        },
        {
          icon: 'bell',
          titulo: 'Notificações e Idioma',
          descricao: 'O sino no topo avisa sobre atualizações dos seus chamados em tempo real. ' +
                     'Prefere outro idioma? Troque entre Português, Inglês e Espanhol a qualquer ' +
                     'momento pelo seletor ao lado do sino.',
          selector: '#btn-sino',
          image: 'solicitante/08-notificacoes.png',
        },
        {
          icon: 'rocket',
          titulo: 'Tudo pronto!',
          descricao: 'Que tal abrir seu primeiro chamado agora?',
          selector: 'nav a[href="/"]',
          cta: { label: 'Abrir primeiro chamado', href: '/' },
        },
      ],
      en: [
        {
          icon: 'wave',
          titulo: 'Welcome to Andon.',
          descricao: 'Hello, {nome}! This is Andon by DTX Aerospace, the single ' +
                     'channel to open and track support tickets across the company. Let\'s walk ' +
                     'through everything you can do here in a few steps.',
        },
        {
          icon: 'plus',
          titulo: 'Opening a New Ticket',
          descricao: 'Here you open a new ticket for any support area: IT, Maintenance, HR and ' +
                     'others. Choose the category, describe the issue in as much detail as ' +
                     'possible, and attach files if needed — our team is notified automatically.',
          selector: 'nav a[href="/"]',
          image: 'solicitante/02-novo-chamado.png',
        },
        {
          icon: 'clipboard',
          titulo: 'Tracking Your Tickets',
          descricao: 'In "My Tickets" you see every ticket you\'ve opened, with real-time status: ' +
                     'Open, In Progress, Completed or Cancelled. Use the filters to quickly find a ' +
                     'specific ticket.',
          selector: 'nav a[href="/meus-chamados"]',
          image: 'solicitante/03-meus-chamados.png',
        },
        {
          icon: 'eye',
          titulo: 'Ticket Details',
          descricao: 'Click any ticket to see the full history: who\'s assigned, status changes, ' +
                     'comments and attachments exchanged during handling.',
          image: 'solicitante/04-detalhe-chamado.png',
        },
        {
          icon: 'edit',
          titulo: 'Editing or Cancelling a Ticket',
          descricao: 'Made a mistake in the description? You can edit a ticket within the first ' +
                     '30 minutes after opening it. Changed your mind or opened it by accident? ' +
                     'You can cancel it and provide a reason.',
          image: 'solicitante/05-editar-cancelar.png',
        },
        {
          icon: 'check',
          titulo: 'Confirming the Resolution',
          descricao: 'When your ticket is marked Completed, you\'ll get a notification to confirm ' +
                     'the issue was really solved. If not, you can reopen the ticket right from ' +
                     'the same screen.',
          image: 'solicitante/06-confirmar-resolucao.png',
        },
        {
          icon: 'lightbulb',
          titulo: 'Tip: More details = faster response',
          descricao: 'When opening a ticket, add a clear description and attachments when possible. ' +
                     'The more information you provide, the faster the resolution!',
        },
        {
          icon: 'bell',
          titulo: 'Notifications and Language',
          descricao: 'The bell icon at the top alerts you about updates to your tickets in real ' +
                     'time. Prefer another language? Switch between Portuguese, English and ' +
                     'Spanish anytime using the selector next to the bell.',
          selector: '#btn-sino',
          image: 'solicitante/08-notificacoes.png',
        },
        {
          icon: 'rocket',
          titulo: 'All set!',
          descricao: 'How about opening your first ticket right now?',
          selector: 'nav a[href="/"]',
          cta: { label: 'Open first ticket', href: '/' },
        },
      ],
      es: [
        {
          icon: 'wave',
          titulo: 'Bienvenido al Portal de Servicios.',
          descricao: '¡Hola, {nome}! Este es el Portal de Servicios de DTX Aerospace, el canal ' +
                     'único para abrir y dar seguimiento a los tickets de soporte en la empresa. ' +
                     'Te mostraremos todo lo que puedes hacer aquí en pocos pasos.',
        },
        {
          icon: 'plus',
          titulo: 'Abriendo un Nuevo Ticket',
          descricao: 'Aquí puedes abrir un nuevo ticket para cualquier área de soporte: TI, ' +
                     'Mantenimiento, RRHH y otras. Elige la categoría, describe el problema con el ' +
                     'mayor detalle posible y adjunta archivos si es necesario — nuestro equipo es ' +
                     'notificado automáticamente.',
          selector: 'nav a[href="/"]',
          image: 'solicitante/02-novo-chamado.png',
        },
        {
          icon: 'clipboard',
          titulo: 'Seguimiento de Tus Tickets',
          descricao: 'En "Mis Tickets" ves todos los tickets que has abierto, con el estado ' +
                     'actualizado en tiempo real: Abierto, En Atención, Completado o Cancelado. ' +
                     'Usa los filtros para encontrar un ticket específico rápidamente.',
          selector: 'nav a[href="/meus-chamados"]',
          image: 'solicitante/03-meus-chamados.png',
        },
        {
          icon: 'eye',
          titulo: 'Detalles de un Ticket',
          descricao: 'Haz clic en cualquier ticket para ver el historial completo: quién está a ' +
                     'cargo, cambios de estado, comentarios y archivos adjuntos intercambiados ' +
                     'durante la atención.',
          image: 'solicitante/04-detalhe-chamado.png',
        },
        {
          icon: 'edit',
          titulo: 'Editando o Cancelando un Ticket',
          descricao: '¿Te equivocaste en la descripción? Puedes editar un ticket recién abierto ' +
                     'dentro de los primeros 30 minutos. ¿Cambiaste de opinión o lo abriste por ' +
                     'error? Puedes cancelarlo indicando el motivo.',
          image: 'solicitante/05-editar-cancelar.png',
        },
        {
          icon: 'check',
          titulo: 'Confirmando la Resolución',
          descricao: 'Cuando tu ticket se marque como Completado, recibirás una notificación para ' +
                     'confirmar si el problema realmente se resolvió. Si no fue así, puedes ' +
                     'reabrir el ticket desde la misma pantalla.',
          image: 'solicitante/06-confirmar-resolucao.png',
        },
        {
          icon: 'lightbulb',
          titulo: 'Consejo: Más detalles = respuesta más rápida',
          descricao: 'Al abrir un ticket, añade una descripción clara y archivos adjuntos cuando sea posible. ' +
                     '¡Cuanta más información proporciones, más rápida será la resolución!',
        },
        {
          icon: 'bell',
          titulo: 'Notificaciones e Idioma',
          descricao: 'La campana en la parte superior te avisa sobre actualizaciones de tus ' +
                     'tickets en tiempo real. ¿Prefieres otro idioma? Cambia entre Portugués, ' +
                     'Inglés y Español en cualquier momento con el selector junto a la campana.',
          selector: '#btn-sino',
          image: 'solicitante/08-notificacoes.png',
        },
        {
          icon: 'rocket',
          titulo: '¡Todo listo!',
          descricao: '¿Qué tal si abres tu primer ticket ahora mismo?',
          selector: 'nav a[href="/"]',
          cta: { label: 'Abrir primer ticket', href: '/' },
        },
      ],
    },

    // ── SUPERVISOR ───────────────────────────────────────────────────────────
    supervisor: {
      pt_BR: [
        {
          icon: 'wave',
          titulo: 'Bem-vindo, Supervisor!',
          descricao: 'Olá, {nome}! Como supervisor, você gerencia os chamados da sua área, ' +
                     'acompanha o desempenho da equipe e garante que os prazos de atendimento ' +
                     '(SLA) sejam cumpridos. Vamos conhecer as principais ferramentas.',
        },
        {
          icon: 'chart',
          titulo: 'Dashboard de Chamados',
          descricao: 'Aqui você vê todos os chamados da sua área em tempo real: quantidade por ' +
                     'status, tempo médio de atendimento e chamados com SLA em risco — tudo em ' +
                     'um só painel.',
          selector: 'nav a[href="/painel"]',
          image: 'supervisor/02-dashboard.png',
        },
        {
          icon: 'mouse',
          titulo: 'Interagindo com Chamados',
          descricao: 'Clique em qualquer linha da tabela para abrir os detalhes do chamado em ' +
                     'uma nova aba, atualizar o status, atribuir um responsável ou adicionar ' +
                     'comentários.',
        },
        {
          icon: 'filter',
          titulo: 'Filtros de SLA e Prioridade',
          descricao: 'Use os filtros no topo da tabela para isolar rapidamente chamados ' +
                     'críticos: por status, prioridade, categoria ou SLA. Chamados com SLA em ' +
                     'risco aparecem sinalizados em vermelho.',
          image: 'supervisor/04-filtros-sla.png',
        },
        {
          icon: 'trend',
          titulo: 'Relatórios e Métricas',
          descricao: 'Acesse métricas de SLA, volume de chamados por categoria e relatórios ' +
                     'semanais da sua área — visualize tendências e identifique gargalos ' +
                     'rapidamente.',
          selector: 'nav a[href*="relatorios"]',
        },
        {
          icon: 'download',
          titulo: 'Exportando Relatórios',
          descricao: 'Precisa compartilhar os números com sua liderança? Exporte os dados da ' +
                     'sua área em planilha Excel, pronta para apresentações e análises.',
          image: 'supervisor/06-exportar.png',
        },
        {
          icon: 'alert',
          titulo: 'Atenção ao SLA!',
          descricao: 'Use os filtros da tabela para encontrar chamados críticos rapidamente. ' +
                     'Chamados com SLA em risco são sinalizados em vermelho — priorize-os para ' +
                     'não descumprir prazos.',
        },
        {
          icon: 'check',
          titulo: 'Tudo pronto!',
          descricao: 'Comece revisando os chamados em aberto na sua área.',
          selector: 'nav a[href="/painel"]',
          cta: { label: 'Ir para o Dashboard', href: '/painel' },
        },
      ],
      en: [
        {
          icon: 'wave',
          titulo: 'Welcome, Supervisor!',
          descricao: 'Hello, {nome}! As a supervisor, you manage tickets for your area, track ' +
                     'team performance, and make sure service-level agreements (SLA) are met. ' +
                     'Let\'s tour the main tools.',
        },
        {
          icon: 'chart',
          titulo: 'Ticket Dashboard',
          descricao: 'Here you see all tickets for your area in real time: counts by status, ' +
                     'average handling time, and tickets with SLA at risk — all in one panel.',
          selector: 'nav a[href="/painel"]',
          image: 'supervisor/02-dashboard.png',
        },
        {
          icon: 'mouse',
          titulo: 'Interacting with Tickets',
          descricao: 'Click any row in the table to open the ticket details in a new tab, ' +
                     'update its status, assign an owner, or add comments.',
        },
        {
          icon: 'filter',
          titulo: 'SLA and Priority Filters',
          descricao: 'Use the filters at the top of the table to quickly isolate critical ' +
                     'tickets: by status, priority, category or SLA. Tickets with SLA at risk ' +
                     'are flagged in red.',
          image: 'supervisor/04-filtros-sla.png',
        },
        {
          icon: 'trend',
          titulo: 'Reports and Metrics',
          descricao: 'Access SLA metrics, ticket volume by category, and weekly reports for ' +
                     'your area — spot trends and bottlenecks quickly.',
          selector: 'nav a[href*="relatorios"]',
        },
        {
          icon: 'download',
          titulo: 'Exporting Reports',
          descricao: 'Need to share the numbers with leadership? Export your area\'s data to an ' +
                     'Excel spreadsheet, ready for presentations and analysis.',
          image: 'supervisor/06-exportar.png',
        },
        {
          icon: 'alert',
          titulo: 'Keep an eye on SLA!',
          descricao: 'Use the table filters to quickly find critical tickets. Tickets with SLA ' +
                     'at risk are flagged in red — prioritize them to avoid missing deadlines.',
        },
        {
          icon: 'check',
          titulo: 'All set!',
          descricao: 'Start by reviewing the open tickets in your area.',
          selector: 'nav a[href="/painel"]',
          cta: { label: 'Go to Dashboard', href: '/painel' },
        },
      ],
      es: [
        {
          icon: 'wave',
          titulo: '¡Bienvenido, Supervisor!',
          descricao: '¡Hola, {nome}! Como supervisor, gestionas los tickets de tu área, das ' +
                     'seguimiento al rendimiento del equipo y garantizas que los plazos de ' +
                     'atención (SLA) se cumplan. Vamos a conocer las principales herramientas.',
        },
        {
          icon: 'chart',
          titulo: 'Panel de Tickets',
          descricao: 'Aquí ves todos los tickets de tu área en tiempo real: cantidad por estado, ' +
                     'tiempo promedio de atención y tickets con SLA en riesgo — todo en un solo ' +
                     'panel.',
          selector: 'nav a[href="/painel"]',
          image: 'supervisor/02-dashboard.png',
        },
        {
          icon: 'mouse',
          titulo: 'Interactuando con Tickets',
          descricao: 'Haz clic en cualquier fila de la tabla para abrir los detalles del ticket ' +
                     'en una nueva pestaña, actualizar su estado, asignar un responsable o ' +
                     'agregar comentarios.',
        },
        {
          icon: 'filter',
          titulo: 'Filtros de SLA y Prioridad',
          descricao: 'Usa los filtros en la parte superior de la tabla para aislar rápidamente ' +
                     'tickets críticos: por estado, prioridad, categoría o SLA. Los tickets con ' +
                     'SLA en riesgo aparecen marcados en rojo.',
          image: 'supervisor/04-filtros-sla.png',
        },
        {
          icon: 'trend',
          titulo: 'Informes y Métricas',
          descricao: 'Accede a métricas de SLA, volumen de tickets por categoría e informes ' +
                     'semanales de tu área — identifica tendencias y cuellos de botella ' +
                     'rápidamente.',
          selector: 'nav a[href*="relatorios"]',
        },
        {
          icon: 'download',
          titulo: 'Exportando Informes',
          descricao: '¿Necesitas compartir los números con tu liderazgo? Exporta los datos de tu ' +
                     'área en una hoja de Excel, lista para presentaciones y análisis.',
          image: 'supervisor/06-exportar.png',
        },
        {
          icon: 'alert',
          titulo: '¡Atención al SLA!',
          descricao: 'Usa los filtros de la tabla para encontrar tickets críticos rápidamente. ' +
                     'Los tickets con SLA en riesgo están marcados en rojo — priorízalos para no ' +
                     'incumplir los plazos.',
        },
        {
          icon: 'check',
          titulo: '¡Todo listo!',
          descricao: 'Comienza revisando los tickets abiertos en tu área.',
          selector: 'nav a[href="/painel"]',
          cta: { label: 'Ir al Panel', href: '/painel' },
        },
      ],
    },

    // ── ADMIN ────────────────────────────────────────────────────────────────
    admin: {
      pt_BR: [
        {
          icon: 'wave',
          titulo: 'Bem-vindo, Administrador!',
          descricao: 'Olá, {nome}! Você tem acesso completo ao sistema: chamados de todas as ' +
                     'áreas, usuários, categorias e relatórios. Vamos apresentar as principais ' +
                     'funcionalidades.',
        },
        {
          icon: 'chart',
          titulo: 'Dashboard Geral',
          descricao: 'Visão consolidada de todos os chamados de todas as áreas, com métricas de ' +
                     'SLA, status em tempo real e distribuição por setor.',
          selector: 'nav a[href="/admin"]',
          image: 'admin/02-dashboard.png',
        },
        {
          icon: 'trend',
          titulo: 'Relatórios Avançados',
          descricao: 'Exporte dados em Excel, gere relatórios semanais automáticos e monitore a ' +
                     'performance de toda a operação, comparando áreas e períodos.',
          selector: 'nav a[href*="relatorios"]',
          image: 'admin/03-relatorios.png',
        },
        {
          icon: 'users',
          titulo: 'Gestão de Usuários',
          descricao: 'Crie, edite e gerencie os perfis de acesso de todos os colaboradores: ' +
                     'solicitante, supervisor ou admin. Defina a área de cada supervisor e ' +
                     'redefina senhas quando necessário.',
          selector: 'nav a[href*="admin/usuarios"]',
          image: 'admin/04-usuarios.png',
        },
        {
          icon: 'tag',
          titulo: 'Categorias',
          descricao: 'Configure a estrutura de categorias dos chamados: setores, gates e níveis ' +
                     'de impacto. Essa estrutura organiza como os chamados são classificados e ' +
                     'roteados.',
          selector: 'nav a[href*="admin/categorias"]',
          image: 'admin/05-categorias.png',
        },
        {
          icon: 'download',
          titulo: 'Exportando Relatórios Avançados',
          descricao: 'Exporte relatórios detalhados de toda a organização em Excel, com ' +
                     'múltiplas abas por área, categoria e período — ideal para apresentações ' +
                     'à diretoria.',
          image: 'admin/06-exportar.png',
        },
        {
          icon: 'settings',
          titulo: 'Configurações Iniciais Recomendadas',
          checklist: [
            'Criar as categorias dos chamados',
            'Cadastrar supervisores por área',
            'Configurar SLA por prioridade',
            'Adicionar os usuários solicitantes',
          ],
        },
        {
          icon: 'rocket',
          titulo: 'Tudo pronto para começar!',
          descricao: 'Comece cadastrando os usuários da sua equipe e configurando as áreas.',
          cta: { label: 'Gerenciar Usuários', href: '/usuarios' },
        },
      ],
      en: [
        {
          icon: 'wave',
          titulo: 'Welcome, Administrator!',
          descricao: 'Hello, {nome}! You have full access to the system: tickets from every ' +
                     'area, users, categories and reports. Let\'s walk through the main features.',
        },
        {
          icon: 'chart',
          titulo: 'General Dashboard',
          descricao: 'Consolidated view of all tickets from all areas, with SLA metrics, ' +
                     'real-time status, and distribution by sector.',
          selector: 'nav a[href="/admin"]',
          image: 'admin/02-dashboard.png',
        },
        {
          icon: 'trend',
          titulo: 'Advanced Reports',
          descricao: 'Export data to Excel, generate automatic weekly reports, and monitor the ' +
                     'performance of the entire operation, comparing areas and periods.',
          selector: 'nav a[href*="relatorios"]',
          image: 'admin/03-relatorios.png',
        },
        {
          icon: 'users',
          titulo: 'User Management',
          descricao: 'Create, edit and manage access profiles for all employees: requester, ' +
                     'supervisor or admin. Set each supervisor\'s area and reset passwords when ' +
                     'needed.',
          selector: 'nav a[href*="admin/usuarios"]',
          image: 'admin/04-usuarios.png',
        },
        {
          icon: 'tag',
          titulo: 'Categories',
          descricao: 'Configure the ticket category structure: sectors, gates and impact ' +
                     'levels. This structure organizes how tickets are classified and routed.',
          selector: 'nav a[href*="admin/categorias"]',
          image: 'admin/05-categorias.png',
        },
        {
          icon: 'download',
          titulo: 'Exporting Advanced Reports',
          descricao: 'Export detailed organization-wide reports to Excel, with multiple tabs ' +
                     'per area, category and period — ideal for leadership presentations.',
          image: 'admin/06-exportar.png',
        },
        {
          icon: 'settings',
          titulo: 'Recommended Initial Settings',
          checklist: [
            'Create ticket categories',
            'Register supervisors by area',
            'Configure SLA by priority',
            'Add requesting users',
          ],
        },
        {
          icon: 'rocket',
          titulo: 'All set to get started!',
          descricao: 'Start by registering your team\'s users and setting up the work areas.',
          cta: { label: 'Manage Users', href: '/usuarios' },
        },
      ],
      es: [
        {
          icon: 'wave',
          titulo: '¡Bienvenido, Administrador!',
          descricao: '¡Hola, {nome}! Tienes acceso completo al sistema: tickets de todas las ' +
                     'áreas, usuarios, categorías e informes. Vamos a presentar las principales ' +
                     'funcionalidades.',
        },
        {
          icon: 'chart',
          titulo: 'Panel General',
          descricao: 'Vista consolidada de todos los tickets de todas las áreas, con métricas ' +
                     'de SLA, estado en tiempo real y distribución por sector.',
          selector: 'nav a[href="/admin"]',
          image: 'admin/02-dashboard.png',
        },
        {
          icon: 'trend',
          titulo: 'Informes Avanzados',
          descricao: 'Exporta datos a Excel, genera informes semanales automáticos y monitorea ' +
                     'el rendimiento de toda la operación, comparando áreas y períodos.',
          selector: 'nav a[href*="relatorios"]',
          image: 'admin/03-relatorios.png',
        },
        {
          icon: 'users',
          titulo: 'Gestión de Usuarios',
          descricao: 'Crea, edita y gestiona los perfiles de acceso de todos los colaboradores: ' +
                     'solicitante, supervisor o admin. Define el área de cada supervisor y ' +
                     'restablece contraseñas cuando sea necesario.',
          selector: 'nav a[href*="admin/usuarios"]',
          image: 'admin/04-usuarios.png',
        },
        {
          icon: 'tag',
          titulo: 'Categorías',
          descricao: 'Configura la estructura de categorías de los tickets: sectores, gates y ' +
                     'niveles de impacto. Esta estructura organiza cómo se clasifican y ' +
                     'enrutan los tickets.',
          selector: 'nav a[href*="admin/categorias"]',
          image: 'admin/05-categorias.png',
        },
        {
          icon: 'download',
          titulo: 'Exportando Informes Avanzados',
          descricao: 'Exporta informes detallados de toda la organización en Excel, con ' +
                     'múltiples pestañas por área, categoría y período — ideal para ' +
                     'presentaciones a la dirección.',
          image: 'admin/06-exportar.png',
        },
        {
          icon: 'settings',
          titulo: 'Configuraciones Iniciales Recomendadas',
          checklist: [
            'Crear las categorías de los tickets',
            'Registrar supervisores por área',
            'Configurar SLA por prioridad',
            'Agregar usuarios solicitantes',
          ],
        },
        {
          icon: 'rocket',
          titulo: '¡Todo listo para comenzar!',
          descricao: 'Comienza registrando los usuarios de tu equipo y configurando las áreas de trabajo.',
          cta: { label: 'Gestionar Usuarios', href: '/usuarios' },
        },
      ],
    },

    // ── ADMIN GLOBAL ─────────────────────────────────────────────────────────
    // Corrige gap pré-existente: antes desta versão, admin_global não tinha tour
    // nenhum (TOURS não tinha essa chave e o guard de perfil desconhecido saía
    // silenciosamente). O tour é derivado do admin logo abaixo (buildAdminGlobalTours),
    // então não é definido aqui.
  };

  // Deriva o tour do admin_global a partir do tour do admin (mesmos passos +
  // 1 passo extra sobre o painel consolidado entre áreas), para as 3 línguas.
  (function buildAdminGlobalTours() {
    var extra = {
      pt_BR: {
        icon: 'globe',
        titulo: 'Painel Admin Global',
        descricao: 'Como Admin Global, você também acompanha e promove ou rebaixa outros ' +
                   'administradores entre as áreas, com uma visão consolidada de todas as ' +
                   'unidades da DTX Aerospace.',
        selector: 'nav a[href="/admin-global"]',
        image: 'admin_global/dashboard.png',
      },
      en: {
        icon: 'globe',
        titulo: 'Global Admin Panel',
        descricao: 'As a Global Admin, you can also review and promote or demote other ' +
                   'administrators across areas, with a consolidated view of all DTX Aerospace ' +
                   'units.',
        selector: 'nav a[href="/admin-global"]',
        image: 'admin_global/dashboard.png',
      },
      es: {
        icon: 'globe',
        titulo: 'Panel de Administrador Global',
        descricao: 'Como Administrador Global, también puedes revisar y promover o degradar a ' +
                   'otros administradores entre áreas, con una vista consolidada de todas las ' +
                   'unidades de DTX Aerospace.',
        selector: 'nav a[href="/admin-global"]',
        image: 'admin_global/dashboard.png',
      },
    };
    var langs = ['pt_BR', 'en', 'es'];
    var result = {};
    for (var i = 0; i < langs.length; i++) {
      var lang = langs[i];
      var adminSteps = TOURS.admin[lang];
      var lastStep = adminSteps[adminSteps.length - 1];
      var beforeLast = adminSteps.slice(0, adminSteps.length - 1);
      result[lang] = beforeLast.concat([extra[lang], lastStep]);
    }
    TOURS.admin_global = result;
  })();

  // ─── Mapa semântico → SVG ─────────────────────────────────────────────────

  var ONBOARDING_ICONS = {
    wave:      '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 11V6a2 2 0 0 0-2-2a2 2 0 0 0-2 2"></path><path d="M14 10V4a2 2 0 0 0-2-2a2 2 0 0 0-2 2v2"></path><path d="M10 10.5V6a2 2 0 0 0-2-2a2 2 0 0 0-2 2v8"></path><path d="M18 11a2 2 0 1 1 4 0v3a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15"></path></svg>',
    plus:      '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>',
    clipboard: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2"></path><rect x="9" y="3" width="6" height="4" rx="1"></rect></svg>',
    lightbulb: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18h6"></path><path d="M10 22h4"></path><path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 0 1 8.91 14"></path></svg>',
    rocket:    '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"></path><path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"></path><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"></path><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"></path></svg>',
    chart:     '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="6" y1="20" x2="6" y2="14"></line><line x1="2" y1="20" x2="22" y2="20"></line></svg>',
    mouse:     '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="2" width="14" height="20" rx="7"></rect><path d="M12 6v4"></path></svg>',
    trend:     '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"></polyline><polyline points="16 7 22 7 22 13"></polyline></svg>',
    alert:     '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"></path><path d="M12 9v4"></path><path d="M12 17h.01"></path></svg>',
    check:     '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>',
    users:     '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M22 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>',
    tag:       '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2H2v10l9.29 9.29c.94.94 2.48.94 3.42 0l6.58-6.58c.94-.94.94-2.48 0-3.42L12 2Z"></path><path d="M7 7h.01"></path></svg>',
    settings:  '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"></path><circle cx="12" cy="12" r="3"></circle></svg>',
    bell:      '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"></path><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"></path></svg>',
    filter:    '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"></polygon></svg>',
    download:  '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>',
    edit:      '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"></path><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4Z"></path></svg>',
    eye:       '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8Z"></path><circle cx="12" cy="12" r="3"></circle></svg>',
    globe:     '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10Z"></path></svg>',
  };

  // Seleciona o tour pelo perfil e idioma (fallback: pt_BR)
  var profileTours = TOURS[PERFIL];
  if (!profileTours) return;
  var steps = profileTours[LANG] || profileTours['pt_BR'] || [];
  if (!steps.length) return;

  var ui = UI[LANG] || UI['pt_BR'];

  // ─── Estado interno ────────────────────────────────────────────────────────

  var backdrop, card;
  var highlightedEl = null;
  var liftedNav     = null;
  var resizeTimer   = null;

  // ─── Inicialização ─────────────────────────────────────────────────────────

  function init() {
    backdrop = document.createElement('div');
    backdrop.id = 'onboarding-backdrop';
    Object.assign(backdrop.style, {
      position: 'fixed', inset: '0',
      background: 'rgba(15,23,42,0.35)',
      zIndex: '8999', pointerEvents: 'auto',
    });

    card = document.createElement('div');
    card.id = 'onboarding-card';
    card.setAttribute('role', 'dialog');
    card.setAttribute('aria-modal', 'true');
    card.setAttribute('aria-label', ui.done_title);
    card.setAttribute('tabindex', '-1');
    Object.assign(card.style, {
      position: 'fixed', zIndex: '9001',
      maxWidth: '400px', width: 'calc(100vw - 32px)',
      background: 'white', borderRadius: '20px',
      boxShadow: '0 8px 32px -4px rgba(0,0,0,0.18), 0 0 0 1px rgba(0,0,0,0.05)',
      fontFamily: 'Inter, sans-serif', overflow: 'hidden',
      pointerEvents: 'auto',
    });

    document.body.appendChild(backdrop);
    document.body.appendChild(card);

    document.addEventListener('keydown', onKeyDown);
    window.addEventListener('resize', onResize);

    if (typeof gsap !== 'undefined') {
      gsap.set(backdrop, { opacity: 0 });
      gsap.to(backdrop, { opacity: 1, duration: 0.35, ease: 'power2.out' });
    }

    renderStep(pasoAtual);
  }

  // ─── Teclado ───────────────────────────────────────────────────────────────

  function onKeyDown(e) {
    if (e.key === 'Escape') { skipTour(); return; }
    if (e.key === 'ArrowRight') nextStep();
    if (e.key === 'Tab') _trapFocus(e);
  }

  // Focus trap: Tab/Shift+Tab não deve sair do card enquanto o tour está aberto
  // (mesmo padrão usado nos modais de escalonamento em visualizar_chamado.html).
  function _trapFocus(e) {
    var focaveis = Array.prototype.slice
      .call(card.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'))
      .filter(function (el) { return !el.disabled && el.offsetParent !== null; });
    if (focaveis.length === 0) { e.preventDefault(); card.focus({ preventScroll: true }); return; }
    var primeiro = focaveis[0];
    var ultimo = focaveis[focaveis.length - 1];
    if (e.shiftKey && document.activeElement === primeiro) {
      ultimo.focus();
      e.preventDefault();
    } else if (!e.shiftKey && (document.activeElement === ultimo || document.activeElement === card)) {
      primeiro.focus();
      e.preventDefault();
    }
  }

  // ─── Resize ────────────────────────────────────────────────────────────────

  function onResize() {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      var step = steps[pasoAtual];
      var targetEl = step && step.selector ? document.querySelector(step.selector) : null;
      if (targetEl) positionCard(targetEl); else centerCard();
    }, 120);
  }

  // ─── Renderização do passo ─────────────────────────────────────────────────

  function renderStep(index) {
    if (index >= steps.length) { completeTour(); return; }

    var step = steps[index];
    pasoAtual = index;

    clearHighlight();
    card.innerHTML = buildCardHTML(step, index);
    bindCardEvents(index);
    card.focus({ preventScroll: true });

    var targetEl = step.selector ? document.querySelector(step.selector) : null;
    if (targetEl) { highlightTarget(targetEl); positionCard(targetEl); }
    else          { centerCard(); }

    var prefersReduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (typeof gsap !== 'undefined' && !prefersReduced) {
      gsap.fromTo(card,
        { opacity: 0, scale: 0.94, y: 10 },
        { opacity: 1, scale: 1, y: 0, duration: 0.22, ease: 'power2.out' }
      );
    } else {
      card.style.opacity = '1';
    }

    if (index > 0) saveStep(index);
  }

  // ─── HTML do card ──────────────────────────────────────────────────────────

  function buildCardHTML(step, index) {
    var isLast  = index === steps.length - 1;
    var isFirst = index === 0;

    // Conteúdo do corpo
    var bodyContent = '';
    if (step.checklist) {
      var checkSvg = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>';
      bodyContent = '<ul style="list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:10px">' +
        step.checklist.map(function (item) {
          return '<li style="display:flex;align-items:flex-start;gap:10px;font-size:14px;color:#374151;line-height:1.5">' +
            '<span style="width:20px;height:20px;border-radius:50%;background:#d1fae5;color:#059669;' +
            'display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:1px">' +
            checkSvg + '</span>' +
            '<span>' + escHtml(item) + '</span></li>';
        }).join('') + '</ul>';
    } else if (step.descricao) {
      var desc = step.descricao.replace('{nome}', escHtml(NOME));
      bodyContent = '<p style="margin:0;font-size:14px;line-height:1.65;color:#4b5563">' + desc + '</p>';
    }

    // CTA
    var ctaHTML = '';
    if (step.cta) {
      ctaHTML = '<div style="margin-top:14px">' +
        '<a id="ob-cta" href="' + step.cta.href + '" ' +
        'style="display:inline-flex;align-items:center;gap:6px;padding:10px 18px;border-radius:10px;' +
        'font-size:13px;font-weight:600;background:#1e4a8c;' +
        'color:white;text-decoration:none;transition:opacity 0.15s">' +
        escHtml(step.cta.label) +
        '<svg width="13" height="13" fill="none" stroke="currentColor" viewBox="0 0 24 24">' +
        '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M9 5l7 7-7 7"/></svg>' +
        '</a></div>';
    }

    // Dots de progresso
    var dotsHTML = '<div style="display:flex;gap:5px;align-items:center">';
    for (var i = 0; i < steps.length; i++) {
      var active = i === index;
      dotsHTML += '<div style="height:7px;border-radius:4px;transition:all 0.3s ease;' +
        'width:' + (active ? '20' : '7') + 'px;' +
        'background:' + (active ? '#1e4a8c' : '#e5e7eb') + '"></div>';
    }
    dotsHTML += '</div>';

    var prevBtn = !isFirst
      ? '<button id="ob-prev" style="padding:8px 14px;border:1px solid #e5e7eb;background:white;' +
        'cursor:pointer;font-size:13px;color:#374151;border-radius:8px;font-weight:500;transition:all 0.15s">' +
        escHtml(ui.prev) + '</button>'
      : '';

    var nextBtn = '<button id="ob-next" style="padding:8px 18px;border:none;border-radius:8px;' +
      'cursor:pointer;font-size:13px;font-weight:600;color:white;transition:opacity 0.15s;' +
      'background:#1e4a8c">' +
      escHtml(isLast ? ui.finish : ui.next) + '</button>';

    // Screenshot ilustrativo do passo (opcional) — some silenciosamente se o arquivo
    // ainda não foi capturado (ver scripts/seed_dados_demo_onboarding.py e
    // tests/e2e/test_capture_onboarding_screenshots.py), para o tour nunca quebrar.
    // Sem handler inline (onerror=) — CSP bloqueia; o listener é anexado em
    // bindCardEvents via addEventListener (ver F-48 em tests/test_regression).
    var imageHTML = step.image
      ? '<div style="width:100%;aspect-ratio:16/9;overflow:hidden;background:#f3f4f6" ' +
        'id="ob-image-wrap">' +
        '<img id="ob-image" src="' + IMG_BASE + step.image + '" alt="" loading="lazy" ' +
        'style="width:100%;height:100%;object-fit:cover;display:block">' +
        '</div>'
      : '';

    return (
      imageHTML +
      '<div style="padding:20px 20px 0;display:flex;align-items:flex-start;justify-content:space-between;gap:12px">' +
        '<div style="display:flex;align-items:center;gap:12px">' +
          '<div style="width:44px;height:44px;border-radius:12px;flex-shrink:0;' +
          'background:#eff6ff;border:1px solid #bfdbfe;color:#1e4a8c;' +
          'display:flex;align-items:center;justify-content:center">' +
          (ONBOARDING_ICONS[step.icon] || '') + '</div>' +
          '<h2 style="margin:0;font-size:15px;font-weight:700;color:#111827;line-height:1.35">' +
          escHtml(step.titulo) + '</h2>' +
        '</div>' +
        '<button id="ob-close" aria-label="' + escHtml(ui.skip) + '" ' +
        'style="flex-shrink:0;padding:4px 6px;border:none;background:none;cursor:pointer;' +
        'color:#9ca3af;font-size:20px;line-height:1;border-radius:6px;transition:color 0.15s;margin-top:-2px">×</button>' +
      '</div>' +

      '<div style="padding:14px 20px 20px">' + bodyContent + ctaHTML + '</div>' +

      '<div style="padding:13px 20px;border-top:1px solid #f3f4f6;background:#fafafa;' +
      'border-radius:0 0 20px 20px;display:flex;align-items:center;justify-content:space-between">' +
        dotsHTML +
        '<div style="display:flex;gap:8px;align-items:center">' +
          '<button id="ob-skip" style="padding:7px 11px;border:none;background:none;cursor:pointer;' +
          'font-size:12px;color:#9ca3af;border-radius:7px;font-weight:500;transition:all 0.15s">' +
          escHtml(ui.skip) + '</button>' +
          prevBtn + nextBtn +
        '</div>' +
      '</div>'
    );
  }

  function bindCardEvents(index) {
    var isLast = index === steps.length - 1;

    var close = document.getElementById('ob-close');
    var skip = document.getElementById('ob-skip');
    var next = document.getElementById('ob-next');
    var prev = document.getElementById('ob-prev');
    var cta = document.getElementById('ob-cta');
    var image = document.getElementById('ob-image');

    close.addEventListener('click', skipTour);
    skip.addEventListener('click', skipTour);
    next.addEventListener('click', isLast ? completeTour : nextStep);
    if (prev) prev.addEventListener('click', prevStep);

    // Some o wrapper da screenshot se o arquivo ainda não foi capturado
    // (CSP-safe — no inline onerror=)
    if (image) {
      image.addEventListener('error', function () {
        var wrap = document.getElementById('ob-image-wrap');
        if (wrap) wrap.style.display = 'none';
      });
    }

    // Hover effects (CSP-safe — no inline onmouseover/onmouseout)
    next.addEventListener('mouseenter', function() { next.style.opacity = '0.88'; });
    next.addEventListener('mouseleave', function() { next.style.opacity = '1'; });

    close.addEventListener('mouseenter', function() { close.style.color = '#374151'; });
    close.addEventListener('mouseleave', function() { close.style.color = '#9ca3af'; });

    skip.addEventListener('mouseenter', function() { skip.style.color = '#6b7280'; skip.style.background = '#f3f4f6'; });
    skip.addEventListener('mouseleave', function() { skip.style.color = '#9ca3af'; skip.style.background = 'none'; });

    if (prev) {
      prev.addEventListener('mouseenter', function() { prev.style.borderColor = '#d1d5db'; prev.style.background = '#f9fafb'; });
      prev.addEventListener('mouseleave', function() { prev.style.borderColor = '#e5e7eb'; prev.style.background = 'white'; });
    }

    if (cta) {
      cta.addEventListener('mouseenter', function() { cta.style.opacity = '0.88'; });
      cta.addEventListener('mouseleave', function() { cta.style.opacity = '1'; });
    }
  }

  // ─── Highlight ─────────────────────────────────────────────────────────────

  function highlightTarget(targetEl) {
    var nav = document.querySelector('nav');
    if (nav && nav.contains(targetEl)) {
      nav.style.zIndex = '9000';
      liftedNav = nav;
    }
    targetEl.style.position = targetEl.style.position || 'relative';
    targetEl.style.zIndex = '9000';
    targetEl.style.boxShadow = '0 0 0 3px rgba(30,74,140,0.9), 0 0 24px rgba(30,74,140,0.25)';
    targetEl.style.borderRadius = '10px';
    targetEl.style.pointerEvents = 'none';
    highlightedEl = targetEl;
  }

  function clearHighlight() {
    if (highlightedEl) {
      highlightedEl.style.boxShadow = '';
      highlightedEl.style.borderRadius = '';
      highlightedEl.style.zIndex = '';
      highlightedEl.style.pointerEvents = '';
      highlightedEl = null;
    }
    if (liftedNav) { liftedNav.style.zIndex = ''; liftedNav = null; }
  }

  // ─── Posicionamento ────────────────────────────────────────────────────────

  function positionCard(targetEl) {
    var vw = window.innerWidth;
    if (vw < 640) { bottomSheet(); return; }

    var rect  = targetEl.getBoundingClientRect();
    var cardW = 400;
    var cardH = card.offsetHeight || 240;
    var pad   = 14;
    var vh    = window.innerHeight;

    var top = (rect.bottom + cardH + pad <= vh)
      ? rect.bottom + pad
      : (rect.top - cardH - pad >= 0)
        ? rect.top - cardH - pad
        : Math.max(pad, (vh - cardH) / 2);

    var left = rect.left;
    if (left + cardW > vw - pad) left = vw - cardW - pad;
    if (left < pad) left = pad;

    if (typeof gsap !== 'undefined') {
      gsap.set(card, { xPercent: 0, yPercent: 0, x: 0, y: 0 });
    }
    Object.assign(card.style, {
      top: top + 'px', left: left + 'px',
      bottom: 'auto', right: 'auto', transform: 'none',
      maxWidth: cardW + 'px', width: 'calc(100vw - 32px)',
    });
  }

  function centerCard() {
    if (window.innerWidth < 640) { bottomSheet(); return; }
    Object.assign(card.style, {
      top: '50%', left: '50%', bottom: 'auto', right: 'auto',
      maxWidth: '400px', width: 'calc(100vw - 32px)',
    });
    if (typeof gsap !== 'undefined') {
      gsap.set(card, { xPercent: -50, yPercent: -50, x: 0, y: 0 });
    } else {
      card.style.transform = 'translate(-50%, -50%)';
    }
  }

  function bottomSheet() {
    if (typeof gsap !== 'undefined') {
      gsap.set(card, { xPercent: 0, yPercent: 0, x: 0, y: 0 });
    }
    Object.assign(card.style, {
      top: 'auto', right: 'auto', transform: 'none',
      bottom: '16px', left: '16px',
      width: 'calc(100vw - 32px)', maxWidth: 'none',
    });
  }

  // ─── Navegação ─────────────────────────────────────────────────────────────

  function nextStep() { animateCardOut(function () { renderStep(pasoAtual + 1); }); }
  function prevStep() { if (pasoAtual > 0) animateCardOut(function () { renderStep(pasoAtual - 1); }); }

  function animateCardOut(cb) {
    if (typeof gsap !== 'undefined') {
      gsap.to(card, { opacity: 0, scale: 0.95, duration: 0.2, ease: 'power2.in', onComplete: cb });
    } else { cb(); }
  }

  // ─── Pular / Concluir ──────────────────────────────────────────────────────

  function skipTour() { apiCall(URL_PULAR, {}, destroyTour); }

  function completeTour() {
    apiCall(URL_CONCLUIR, {}, function () {
      clearHighlight();
      card.innerHTML =
        '<div style="padding:36px 28px;text-align:center">' +
          '<div style="width:64px;height:64px;margin:0 auto 14px;border-radius:16px;background:#eff6ff;border:1px solid #bfdbfe;display:flex;align-items:center;justify-content:center;color:#1e4a8c">' +
          '<svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">' +
          '<path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z"></path>' +
          '</svg></div>' +
          '<h2 style="margin:0 0 8px;font-size:18px;font-weight:700;color:#111827">' +
          escHtml(ui.done_title) + '</h2>' +
          '<p style="margin:0;font-size:14px;color:#6b7280;line-height:1.6">' +
          escHtml(ui.done_msg) + '</p>' +
        '</div>';
      centerCard();
      var prefersReduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      if (typeof gsap !== 'undefined' && !prefersReduced) {
        gsap.fromTo(card, { scale: 0.88 }, { scale: 1, duration: 0.25, ease: 'power2.out' });
        setTimeout(function () {
          gsap.to([card, backdrop], { opacity: 0, duration: 0.35, onComplete: destroyTour });
        }, 1600);
      } else { setTimeout(destroyTour, 1800); }
    });
  }

  function destroyTour() {
    clearHighlight();
    document.removeEventListener('keydown', onKeyDown);
    window.removeEventListener('resize', onResize);
    if (backdrop && backdrop.parentNode) backdrop.parentNode.removeChild(backdrop);
    if (card && card.parentNode) card.parentNode.removeChild(card);
    if (root && root.parentNode) root.parentNode.removeChild(root);
  }

  // ─── API ───────────────────────────────────────────────────────────────────

  function saveStep(passo) { apiCall(URL_AVANCAR, { passo: passo }, null); }

  function apiCall(url, body, callback) {
    // Em modo replay ("Rever tour"), não persiste progresso/conclusão no Firestore —
    // é uma reexibição puramente visual do tour já concluído anteriormente.
    if (MODO === 'replay') { if (callback) callback(); return; }
    fetch(url, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
      body: JSON.stringify(body || {}),
    })
      .then(function (r) { return r.json(); })
      .then(function () { if (callback) callback(); })
      .catch(function () { if (callback) callback(); });
  }

  // ─── Utilitário ────────────────────────────────────────────────────────────

  function escHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // ─── Inicializa após as animações da página ────────────────────────────────

  function start() { setTimeout(init, 900); }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }

})();
