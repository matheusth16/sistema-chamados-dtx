/**
 * GSAP Motion - Animações suaves no Sistema de Chamados DTX
 *
 * Plugins: ScrollTrigger (reveal ao rolar), ScrollToPlugin (scroll suave).
 *
 * Uso:
 * - Conteúdo principal: animação de entrada automática em <main>
 * - Flash messages: entrada suave
 * - .gsap-animate: fade + slide up na carga
 * - .gsap-stagger-container + .gsap-stagger: entrada em sequência
 * - .gsap-scroll-reveal: fade + slide quando o elemento entra na viewport
 *
 * API global (window.DTXgsap):
 * - DTXgsap.animateIn(selector, opts)
 * - DTXgsap.stagger(selector, opts)
 * - DTXgsap.scrollTo(target, opts)
 * - DTXgsap.gsap, DTXgsap.ScrollTrigger, DTXgsap.ScrollToPlugin
 */
(function () {
    'use strict';

    if (typeof gsap === 'undefined') return;

    var main = document.querySelector('main');
    var flash = document.getElementById('flash-messages');

    var defaultFrom = { opacity: 0, y: 28 };
    var defaultTo = { opacity: 1, y: 0, duration: 0.55, ease: 'power2.out' };

    // Registra plugins (se carregados)
    if (typeof ScrollTrigger !== 'undefined') {
        gsap.registerPlugin(ScrollTrigger);
    }
    if (typeof ScrollToPlugin !== 'undefined') {
        gsap.registerPlugin(ScrollToPlugin);
    }

    /**
     * Splash Screen animation (login page only).
     * Timeline: logo fade+scale → line grows → text fade → pause → overlay dissolves.
     * Calls callback when complete (to trigger login card animations).
     */
    function splashScreen(callback) {
        var splash = document.getElementById('splash-screen');
        if (!splash) { if (callback) callback(); return; }

        // Hide nav and footer during splash for full-page immersion
        var nav = document.querySelector('nav');
        var footer = document.querySelector('footer');
        if (nav) gsap.set(nav, { opacity: 0, y: -30 });
        if (footer) gsap.set(footer, { opacity: 0 });

        var tl = gsap.timeline({
            onComplete: function () {
                splash.remove();
                // Reveal nav and footer with smooth animation
                if (nav) gsap.to(nav, { opacity: 1, y: 0, duration: 0.5, ease: 'power2.out' });
                if (footer) gsap.to(footer, { opacity: 1, duration: 0.5, ease: 'power2.out', delay: 0.2 });
                if (callback) callback();
            }
        });

        tl.to('#splash-logo', {
            opacity: 1, scale: 1, duration: 0.5, ease: 'back.out(1.7)'
        })
        .fromTo('#splash-line', 
            { width: 0 }, 
            { width: 220, duration: 0.6, ease: 'power2.out' },
            '+=0.15'
        )
        .to('#splash-text', {
            opacity: 1, duration: 0.4, ease: 'power1.out'
        }, '-=0.25')
        .to({}, { duration: 0.7 })  // pausa para impacto visual
        .to(splash, {
            opacity: 0, y: -50, duration: 0.4, ease: 'power2.in'
        });
    }

    /**
     * Inicializa animações na carga da página
     */
    function init() {
        // Conteúdo principal: entrada bem visível (fade + desliza de baixo)
        if (main && !main.classList.contains('gsap-no-motion')) {
            gsap.fromTo(main, { opacity: 0, y: 36 }, { opacity: 1, y: 0, duration: 0.65, ease: 'power2.out', overwrite: 'auto' });
        }

        // Flash messages
        if (flash) {
            var items = flash.querySelectorAll(':scope > div');
            if (items.length) {
                gsap.fromTo(items, { opacity: 0, y: -16 }, {
                    opacity: 1,
                    y: 0,
                    duration: 0.5,
                    stagger: 0.1,
                    ease: 'back.out(1.1)'
                });
            }
        }

        // .gsap-animate: entrada individual
        var animateEls = document.querySelectorAll('.gsap-animate');
        if (animateEls.length) {
            gsap.fromTo(animateEls, defaultFrom, Object.assign({}, defaultTo, { stagger: 0.05 }));
        }

        // .gsap-stagger-container + .gsap-stagger (entrada em sequência, bem visível)
        var staggerContainers = document.querySelectorAll('.gsap-stagger-container');
        staggerContainers.forEach(function (container) {
            var children = container.querySelectorAll(':scope > .gsap-stagger');
            if (children.length) {
                gsap.fromTo(children, defaultFrom, Object.assign({}, defaultTo, { duration: 0.5, stagger: 0.08 }));
            }
        });

        // --- Splash Screen (login page) ---
        var splash = document.getElementById('splash-screen');
        if (splash) {
            splashScreen(function () {
                animateLoginCard();
            });
        } else {
            // Página de login sem splash (ex: após redirect com erro)
            animateLoginCard();
        }

        // Página de login: card com escala + fade
        function animateLoginCard() {
            var loginCard = document.getElementById('login-card');
            if (!loginCard) return;
            gsap.fromTo(loginCard, { opacity: 0, scale: 0.88 }, { opacity: 1, scale: 1, duration: 0.6, ease: 'back.out(1.4)' });
            var loginHeader = loginCard.querySelector('.gsap-login-header');
            var loginForm = loginCard.querySelector('form');
            var loginFooter = loginCard.querySelector('.gsap-login-footer');
            if (loginHeader) gsap.fromTo(loginHeader, { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.5, delay: 0.15, ease: 'power2.out' });
            if (loginForm) gsap.fromTo(loginForm, { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.5, delay: 0.3, ease: 'power2.out' });
            if (loginFooter) gsap.fromTo(loginFooter, { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.4, delay: 0.5 });
        }

        // .gsap-scroll-reveal: animar quando entrar na viewport (requer ScrollTrigger)
        if (typeof ScrollTrigger !== 'undefined') {
            document.querySelectorAll('.gsap-scroll-reveal').forEach(function (el) {
                gsap.fromTo(el, { opacity: 0, y: 48 }, {
                    opacity: 1,
                    y: 0,
                    duration: 0.65,
                    ease: 'power2.out',
                    scrollTrigger: {
                        trigger: el,
                        start: 'top 88%',
                        toggleActions: 'play none none none'
                    }
                });
            });
            document.querySelectorAll('.gsap-scroll-reveal-stagger').forEach(function (container) {
                var children = container.querySelectorAll(':scope > .gsap-scroll-reveal-item');
                if (children.length) {
                    gsap.fromTo(children, { opacity: 0, y: 32 }, {
                        opacity: 1,
                        y: 0,
                        duration: 0.5,
                        stagger: 0.1,
                        ease: 'power2.out',
                        scrollTrigger: {
                            trigger: container,
                            start: 'top 85%',
                            toggleActions: 'play none none none'
                        }
                    });
                }
            });
        }
    }

    function runInit() {
        init();
        try {
            if (typeof window !== 'undefined' && window.DTX_DEBUG) {
                console.log('[DTX] GSAP Motion ativo ✓');
            }
        } catch (e) {}
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', runInit);
    } else {
        runInit();
    }

    function animateIn(selector, opts) {
        var els = document.querySelectorAll(selector);
        if (!els.length) return;
        var options = Object.assign({}, defaultTo, opts || {});
        gsap.fromTo(els, defaultFrom, options);
    }

    function stagger(selector, opts) {
        var els = document.querySelectorAll(selector);
        if (!els.length) return;
        var options = Object.assign({}, defaultTo, { stagger: 0.05 }, opts || {});
        gsap.fromTo(els, defaultFrom, options);
    }

    /**
     * Scroll suave até um elemento ou posição (requer ScrollToPlugin)
     * @param {string|number} target - Seletor CSS, elemento ou número (px)
     * @param {object} opts - { duration, offset }
     */
    function scrollTo(target, opts) {
        if (typeof ScrollToPlugin === 'undefined') {
            if (typeof target === 'number') window.scrollTo(0, target);
            else document.querySelector(target) && document.querySelector(target).scrollIntoView({ behavior: 'smooth' });
            return;
        }
        var options = Object.assign({ duration: 0.8, ease: 'power2.inOut' }, opts || {});
        var y = typeof target === 'number' ? target : (typeof target === 'string' ? target : null);
        if (y === null && target && target.nodeType) {
            y = target;
        }
        gsap.to(window, { duration: options.duration, scrollTo: { y: y, offsetY: options.offsetY || 0 }, ease: options.ease });
    }

    window.DTXgsap = {
        animateIn: animateIn,
        stagger: stagger,
        scrollTo: scrollTo,
        gsap: gsap,
        ScrollTrigger: typeof ScrollTrigger !== 'undefined' ? ScrollTrigger : null,
        ScrollToPlugin: typeof ScrollToPlugin !== 'undefined' ? ScrollToPlugin : null
    };
})();
