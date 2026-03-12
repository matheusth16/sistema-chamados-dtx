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
  var CSRF         = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';
  var URL_AVANCAR  = root.dataset.urlAvancar;
  var URL_CONCLUIR = root.dataset.urlConcluir;
  var URL_PULAR    = root.dataset.urlPular;
  var pasoAtual    = parseInt(root.dataset.passo, 10) || 0;

  // ─── Textos da UI por idioma ───────────────────────────────────────────────

  var UI = {
    pt_BR: { next: 'Próximo →', finish: 'Concluir ✓', prev: '← Anterior', skip: 'Pular tour',
             done_title: 'Pronto para começar!', done_msg: 'O tour foi concluído. Agora é com você!' },
    en:    { next: 'Next →',    finish: 'Finish ✓',   prev: '← Back',     skip: 'Skip tour',
             done_title: 'Ready to start!',      done_msg: 'Tour completed. Now it\'s up to you!' },
    es:    { next: 'Siguiente →', finish: 'Finalizar ✓', prev: '← Atrás', skip: 'Omitir tour',
             done_title: '¡Listo para comenzar!', done_msg: '¡Tour completado. ¡Ahora es tu turno!' },
  };

  // ─── Definição dos tours por perfil e idioma ──────────────────────────────

  var TOURS = {

    // ── SOLICITANTE ──────────────────────────────────────────────────────────
    solicitante: {
      pt_BR: [
        {
          icone: '👋',
          titulo: 'Bem-vindo ao Sistema de Chamados!',
          descricao: 'Olá, {nome}! Este é o sistema de chamados da DTX Aerospace. ' +
                     'Vamos te guiar pelos primeiros passos em menos de um minuto.',
        },
        {
          icone: '➕',
          titulo: 'Abrindo um Novo Chamado',
          descricao: 'Por aqui você abre um novo chamado para suporte. ' +
                     'Preencha as informações e nossa equipe entra em contato rapidamente.',
          selector: 'nav a[href="/"]',
        },
        {
          icone: '📋',
          titulo: 'Acompanhe Seus Chamados',
          descricao: 'Veja todos os chamados que você abriu e o status de cada um em tempo real.',
          selector: 'nav a[href="/meus-chamados"]',
        },
        {
          icone: '💡',
          titulo: 'Dica: Mais detalhes = resposta mais rápida',
          descricao: 'Ao abrir um chamado, adicione uma descrição clara e anexos quando possível. ' +
                     'Quanto mais informação, mais rápida a resolução pela equipe!',
        },
        {
          icone: '🚀',
          titulo: 'Tudo pronto!',
          descricao: 'Que tal abrir seu primeiro chamado agora?',
          selector: 'nav a[href="/"]',
          cta: { label: 'Abrir primeiro chamado', href: '/' },
        },
      ],
      en: [
        {
          icone: '👋',
          titulo: 'Welcome to the Ticket System!',
          descricao: 'Hello, {nome}! This is the DTX Aerospace ticket system. ' +
                     'We\'ll guide you through the first steps in less than a minute.',
        },
        {
          icone: '➕',
          titulo: 'Opening a New Ticket',
          descricao: 'Here you open a new support ticket. ' +
                     'Fill in the details and our team will get in touch quickly.',
          selector: 'nav a[href="/"]',
        },
        {
          icone: '📋',
          titulo: 'Track Your Tickets',
          descricao: 'View all the tickets you\'ve opened and the real-time status of each one.',
          selector: 'nav a[href="/meus-chamados"]',
        },
        {
          icone: '💡',
          titulo: 'Tip: More details = faster response',
          descricao: 'When opening a ticket, add a clear description and attachments when possible. ' +
                     'The more information you provide, the faster the resolution!',
        },
        {
          icone: '🚀',
          titulo: 'All set!',
          descricao: 'How about opening your first ticket right now?',
          selector: 'nav a[href="/"]',
          cta: { label: 'Open first ticket', href: '/' },
        },
      ],
      es: [
        {
          icone: '👋',
          titulo: '¡Bienvenido al Sistema de Tickets!',
          descricao: '¡Hola, {nome}! Este es el sistema de tickets de DTX Aerospace. ' +
                     'Te guiaremos a través de los primeros pasos en menos de un minuto.',
        },
        {
          icone: '➕',
          titulo: 'Abriendo un Nuevo Ticket',
          descricao: 'Aquí puedes abrir un nuevo ticket de soporte. ' +
                     'Completa la información y nuestro equipo se pondrá en contacto rápidamente.',
          selector: 'nav a[href="/"]',
        },
        {
          icone: '📋',
          titulo: 'Seguimiento de Tus Tickets',
          descricao: 'Consulta todos los tickets que has abierto y el estado en tiempo real de cada uno.',
          selector: 'nav a[href="/meus-chamados"]',
        },
        {
          icone: '💡',
          titulo: 'Consejo: Más detalles = respuesta más rápida',
          descricao: 'Al abrir un ticket, añade una descripción clara y archivos adjuntos cuando sea posible. ' +
                     '¡Cuanta más información proporciones, más rápida será la resolución!',
        },
        {
          icone: '🚀',
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
          icone: '👋',
          titulo: 'Bem-vindo, Supervisor!',
          descricao: 'Olá, {nome}! Como supervisor, você gerencia chamados da sua área ' +
                     'e acompanha o desempenho da equipe.',
        },
        {
          icone: '📊',
          titulo: 'Dashboard de Chamados',
          descricao: 'Aqui você vê todos os chamados da sua área em tempo real, ' +
                     'com filtros por status, prioridade e SLA.',
          selector: 'nav a[href="/admin"]',
        },
        {
          icone: '🖱️',
          titulo: 'Interagindo com Chamados',
          descricao: 'Clique em qualquer linha da tabela para abrir os detalhes do chamado ' +
                     'em uma nova aba e atualizar o status.',
        },
        {
          icone: '📈',
          titulo: 'Relatórios e Métricas',
          descricao: 'Acesse métricas de SLA e relatórios semanais da sua área. ' +
                     'Exporte em Excel quando precisar.',
          selector: 'nav a[href*="relatorios"]',
        },
        {
          icone: '⚠️',
          titulo: 'Atenção ao SLA!',
          descricao: 'Use os filtros da tabela para encontrar chamados críticos. ' +
                     'Chamados com SLA em risco são sinalizados em vermelho.',
        },
        {
          icone: '✅',
          titulo: 'Tudo pronto!',
          descricao: 'Comece revisando os chamados em aberto na sua área.',
          selector: 'nav a[href="/admin"]',
          cta: { label: 'Ir para o Dashboard', href: '/admin' },
        },
      ],
      en: [
        {
          icone: '👋',
          titulo: 'Welcome, Supervisor!',
          descricao: 'Hello, {nome}! As a supervisor, you manage tickets for your area ' +
                     'and track team performance.',
        },
        {
          icone: '📊',
          titulo: 'Ticket Dashboard',
          descricao: 'Here you see all tickets for your area in real time, ' +
                     'with filters by status, priority and SLA.',
          selector: 'nav a[href="/admin"]',
        },
        {
          icone: '🖱️',
          titulo: 'Interacting with Tickets',
          descricao: 'Click any row in the table to open the ticket details in a new tab ' +
                     'and update its status.',
        },
        {
          icone: '📈',
          titulo: 'Reports and Metrics',
          descricao: 'Access SLA metrics and weekly reports for your area. ' +
                     'Export to Excel whenever you need.',
          selector: 'nav a[href*="relatorios"]',
        },
        {
          icone: '⚠️',
          titulo: 'Keep an eye on SLA!',
          descricao: 'Use the table filters to find critical tickets quickly. ' +
                     'Tickets with SLA at risk are flagged in red.',
        },
        {
          icone: '✅',
          titulo: 'All set!',
          descricao: 'Start by reviewing the open tickets in your area.',
          selector: 'nav a[href="/admin"]',
          cta: { label: 'Go to Dashboard', href: '/admin' },
        },
      ],
      es: [
        {
          icone: '👋',
          titulo: '¡Bienvenido, Supervisor!',
          descricao: '¡Hola, {nome}! Como supervisor, gestionas los tickets de tu área ' +
                     'y realizas el seguimiento del rendimiento del equipo.',
        },
        {
          icone: '📊',
          titulo: 'Panel de Tickets',
          descricao: 'Aquí ves todos los tickets de tu área en tiempo real, ' +
                     'con filtros por estado, prioridad y SLA.',
          selector: 'nav a[href="/admin"]',
        },
        {
          icone: '🖱️',
          titulo: 'Interactuando con Tickets',
          descricao: 'Haz clic en cualquier fila de la tabla para abrir los detalles ' +
                     'del ticket en una nueva pestaña y actualizar su estado.',
        },
        {
          icone: '📈',
          titulo: 'Informes y Métricas',
          descricao: 'Accede a las métricas de SLA e informes semanales de tu área. ' +
                     'Exporta a Excel cuando lo necesites.',
          selector: 'nav a[href*="relatorios"]',
        },
        {
          icone: '⚠️',
          titulo: '¡Atención al SLA!',
          descricao: 'Usa los filtros de la tabla para encontrar tickets críticos rápidamente. ' +
                     'Los tickets con SLA en riesgo están marcados en rojo.',
        },
        {
          icone: '✅',
          titulo: '¡Todo listo!',
          descricao: 'Comienza revisando los tickets abiertos en tu área.',
          selector: 'nav a[href="/admin"]',
          cta: { label: 'Ir al Panel', href: '/admin' },
        },
      ],
    },

    // ── ADMIN ────────────────────────────────────────────────────────────────
    admin: {
      pt_BR: [
        {
          icone: '👋',
          titulo: 'Bem-vindo, Administrador!',
          descricao: 'Olá, {nome}! Você tem acesso completo ao sistema. ' +
                     'Vamos apresentar as principais funcionalidades.',
        },
        {
          icone: '📊',
          titulo: 'Dashboard Geral',
          descricao: 'Visão consolidada de todos os chamados de todas as áreas, ' +
                     'com métricas de SLA e status em tempo real.',
          selector: 'nav a[href="/admin"]',
        },
        {
          icone: '📈',
          titulo: 'Relatórios Avançados',
          descricao: 'Exporte dados em Excel e gere relatórios semanais automáticos. ' +
                     'Monitore a performance de toda a operação.',
          selector: 'nav a[href*="relatorios"]',
        },
        {
          icone: '👥',
          titulo: 'Gestão de Usuários',
          descricao: 'Crie, edite e gerencie os perfis de acesso de todos os colaboradores. ' +
                     'Acesse pelo menu ☰ no canto superior direito da navegação.',
          selector: '#btn-hamburger',
        },
        {
          icone: '🏷️',
          titulo: 'Categorias e Traduções',
          descricao: 'Configure as categorias dos chamados e os textos do sistema ' +
                     'em PT-BR, EN e ES. Também disponível no menu ☰.',
          selector: '#btn-hamburger',
        },
        {
          icone: '⚙️',
          titulo: 'Configurações Iniciais Recomendadas',
          checklist: [
            'Criar as categorias dos chamados',
            'Cadastrar supervisores por área',
            'Configurar SLA por prioridade',
            'Adicionar os usuários solicitantes',
          ],
        },
        {
          icone: '🚀',
          titulo: 'Tudo pronto para começar!',
          descricao: 'Comece cadastrando os usuários da sua equipe e configurando as áreas.',
          cta: { label: 'Gerenciar Usuários', href: '/usuarios' },
        },
      ],
      en: [
        {
          icone: '👋',
          titulo: 'Welcome, Administrator!',
          descricao: 'Hello, {nome}! You have full access to the system. ' +
                     'Let\'s walk through the main features.',
        },
        {
          icone: '📊',
          titulo: 'General Dashboard',
          descricao: 'Consolidated view of all tickets from all areas, ' +
                     'with SLA metrics and real-time status.',
          selector: 'nav a[href="/admin"]',
        },
        {
          icone: '📈',
          titulo: 'Advanced Reports',
          descricao: 'Export data to Excel and generate automatic weekly reports. ' +
                     'Monitor the performance of the entire operation.',
          selector: 'nav a[href*="relatorios"]',
        },
        {
          icone: '👥',
          titulo: 'User Management',
          descricao: 'Create, edit and manage access profiles for all employees. ' +
                     'Access through the ☰ menu in the top-right corner.',
          selector: '#btn-hamburger',
        },
        {
          icone: '🏷️',
          titulo: 'Categories & Translations',
          descricao: 'Configure ticket categories and system texts in PT-BR, EN and ES. ' +
                     'Also available in the ☰ menu.',
          selector: '#btn-hamburger',
        },
        {
          icone: '⚙️',
          titulo: 'Recommended Initial Settings',
          checklist: [
            'Create ticket categories',
            'Register supervisors by area',
            'Configure SLA by priority',
            'Add requesting users',
          ],
        },
        {
          icone: '🚀',
          titulo: 'All set to get started!',
          descricao: 'Start by registering your team\'s users and setting up the work areas.',
          cta: { label: 'Manage Users', href: '/usuarios' },
        },
      ],
      es: [
        {
          icone: '👋',
          titulo: '¡Bienvenido, Administrador!',
          descricao: '¡Hola, {nome}! Tienes acceso completo al sistema. ' +
                     'Vamos a presentar las principales funcionalidades.',
        },
        {
          icone: '📊',
          titulo: 'Panel General',
          descricao: 'Vista consolidada de todos los tickets de todas las áreas, ' +
                     'con métricas de SLA y estado en tiempo real.',
          selector: 'nav a[href="/admin"]',
        },
        {
          icone: '📈',
          titulo: 'Informes Avanzados',
          descricao: 'Exporta datos a Excel y genera informes semanales automáticos. ' +
                     'Monitorea el rendimiento de toda la operación.',
          selector: 'nav a[href*="relatorios"]',
        },
        {
          icone: '👥',
          titulo: 'Gestión de Usuarios',
          descricao: 'Crea, edita y gestiona los perfiles de acceso de todos los colaboradores. ' +
                     'Accede a través del menú ☰ en la esquina superior derecha.',
          selector: '#btn-hamburger',
        },
        {
          icone: '🏷️',
          titulo: 'Categorías y Traducciones',
          descricao: 'Configura las categorías de los tickets y los textos del sistema ' +
                     'en PT-BR, EN y ES. También disponible en el menú ☰.',
          selector: '#btn-hamburger',
        },
        {
          icone: '⚙️',
          titulo: 'Configuraciones Iniciales Recomendadas',
          checklist: [
            'Crear las categorías de los tickets',
            'Registrar supervisores por área',
            'Configurar SLA por prioridad',
            'Agregar usuarios solicitantes',
          ],
        },
        {
          icone: '🚀',
          titulo: '¡Todo listo para comenzar!',
          descricao: 'Comienza registrando los usuarios de tu equipo y configurando las áreas de trabajo.',
          cta: { label: 'Gestionar Usuarios', href: '/usuarios' },
        },
      ],
    },
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
      background: 'rgba(11,27,61,0.78)',
      zIndex: '8999', pointerEvents: 'auto',
    });

    card = document.createElement('div');
    card.id = 'onboarding-card';
    card.setAttribute('role', 'dialog');
    card.setAttribute('aria-modal', 'true');
    card.setAttribute('aria-label', ui.done_title);
    Object.assign(card.style, {
      position: 'fixed', zIndex: '9001',
      maxWidth: '400px', width: 'calc(100vw - 32px)',
      background: 'white', borderRadius: '20px',
      boxShadow: '0 25px 80px -10px rgba(0,0,0,0.4), 0 0 0 1px rgba(0,0,0,0.06)',
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

    if (typeof gsap !== 'undefined') {
      gsap.fromTo(card,
        { opacity: 0, scale: 0.94, y: 10 },
        { opacity: 1, scale: 1, y: 0, duration: 0.32, ease: 'back.out(1.6)' }
      );
    }

    var targetEl = step.selector ? document.querySelector(step.selector) : null;
    if (targetEl) { highlightTarget(targetEl); positionCard(targetEl); }
    else          { centerCard(); }

    if (index > 0) saveStep(index);
  }

  // ─── HTML do card ──────────────────────────────────────────────────────────

  function buildCardHTML(step, index) {
    var isLast  = index === steps.length - 1;
    var isFirst = index === 0;

    // Conteúdo do corpo
    var bodyContent = '';
    if (step.checklist) {
      bodyContent = '<ul style="list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:10px">' +
        step.checklist.map(function (item) {
          return '<li style="display:flex;align-items:flex-start;gap:10px;font-size:14px;color:#374151;line-height:1.5">' +
            '<span style="width:20px;height:20px;border-radius:50%;background:#d1fae5;color:#059669;' +
            'font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center;' +
            'flex-shrink:0;margin-top:1px">✓</span>' +
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
        '<a href="' + step.cta.href + '" ' +
        'style="display:inline-flex;align-items:center;gap:6px;padding:10px 18px;border-radius:10px;' +
        'font-size:13px;font-weight:600;background:linear-gradient(135deg,#4f46e5,#6366f1);' +
        'color:white;text-decoration:none;transition:opacity 0.15s" ' +
        'onmouseover="this.style.opacity=\'0.88\'" onmouseout="this.style.opacity=\'1\'">' +
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
        'background:' + (active ? '#4f46e5' : '#e5e7eb') + '"></div>';
    }
    dotsHTML += '</div>';

    var prevBtn = !isFirst
      ? '<button id="ob-prev" style="padding:8px 14px;border:1px solid #e5e7eb;background:white;' +
        'cursor:pointer;font-size:13px;color:#374151;border-radius:8px;font-weight:500;transition:all 0.15s" ' +
        'onmouseover="this.style.borderColor=\'#d1d5db\';this.style.background=\'#f9fafb\'" ' +
        'onmouseout="this.style.borderColor=\'#e5e7eb\';this.style.background=\'white\'">' +
        escHtml(ui.prev) + '</button>'
      : '';

    var nextBtn = '<button id="ob-next" style="padding:8px 18px;border:none;border-radius:8px;' +
      'cursor:pointer;font-size:13px;font-weight:600;color:white;transition:opacity 0.15s;' +
      'background:linear-gradient(135deg,#4f46e5,#6366f1)" ' +
      'onmouseover="this.style.opacity=\'0.88\'" onmouseout="this.style.opacity=\'1\'">' +
      escHtml(isLast ? ui.finish : ui.next) + '</button>';

    return (
      '<div style="padding:20px 20px 0;display:flex;align-items:flex-start;justify-content:space-between;gap:12px">' +
        '<div style="display:flex;align-items:center;gap:12px">' +
          '<div style="width:44px;height:44px;border-radius:12px;flex-shrink:0;' +
          'background:linear-gradient(135deg,#ede9fe,#e0e7ff);' +
          'display:flex;align-items:center;justify-content:center;font-size:22px">' +
          step.icone + '</div>' +
          '<h2 style="margin:0;font-size:15px;font-weight:700;color:#111827;line-height:1.35">' +
          escHtml(step.titulo) + '</h2>' +
        '</div>' +
        '<button id="ob-close" aria-label="' + escHtml(ui.skip) + '" ' +
        'style="flex-shrink:0;padding:4px 6px;border:none;background:none;cursor:pointer;' +
        'color:#9ca3af;font-size:20px;line-height:1;border-radius:6px;transition:color 0.15s;margin-top:-2px" ' +
        'onmouseover="this.style.color=\'#374151\'" onmouseout="this.style.color=\'#9ca3af\'">×</button>' +
      '</div>' +

      '<div style="padding:14px 20px 20px">' + bodyContent + ctaHTML + '</div>' +

      '<div style="padding:13px 20px;border-top:1px solid #f3f4f6;background:#fafafa;' +
      'border-radius:0 0 20px 20px;display:flex;align-items:center;justify-content:space-between">' +
        dotsHTML +
        '<div style="display:flex;gap:8px;align-items:center">' +
          '<button id="ob-skip" style="padding:7px 11px;border:none;background:none;cursor:pointer;' +
          'font-size:12px;color:#9ca3af;border-radius:7px;font-weight:500;transition:all 0.15s" ' +
          'onmouseover="this.style.color=\'#6b7280\';this.style.background=\'#f3f4f6\'" ' +
          'onmouseout="this.style.color=\'#9ca3af\';this.style.background=\'none\'">' +
          escHtml(ui.skip) + '</button>' +
          prevBtn + nextBtn +
        '</div>' +
      '</div>'
    );
  }

  function bindCardEvents(index) {
    var isLast = index === steps.length - 1;
    document.getElementById('ob-close').addEventListener('click', skipTour);
    document.getElementById('ob-skip').addEventListener('click', skipTour);
    document.getElementById('ob-next').addEventListener('click', isLast ? completeTour : nextStep);
    var p = document.getElementById('ob-prev');
    if (p) p.addEventListener('click', prevStep);
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
    targetEl.style.boxShadow = '0 0 0 3px rgba(99,102,241,0.9), 0 0 24px rgba(99,102,241,0.35)';
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
      transform: 'translate(-50%, -50%)',
      maxWidth: '400px', width: 'calc(100vw - 32px)',
    });
  }

  function bottomSheet() {
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
          '<div style="font-size:52px;margin-bottom:14px;line-height:1">🎉</div>' +
          '<h2 style="margin:0 0 8px;font-size:18px;font-weight:700;color:#111827">' +
          escHtml(ui.done_title) + '</h2>' +
          '<p style="margin:0;font-size:14px;color:#6b7280;line-height:1.6">' +
          escHtml(ui.done_msg) + '</p>' +
        '</div>';
      centerCard();
      if (typeof gsap !== 'undefined') {
        gsap.fromTo(card, { scale: 0.88 }, { scale: 1, duration: 0.45, ease: 'back.out(2)' });
        setTimeout(function () {
          gsap.to([card, backdrop], { opacity: 0, duration: 0.4, onComplete: destroyTour });
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
