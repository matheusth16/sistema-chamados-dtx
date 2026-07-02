/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/templates/**/*.html",
    "./app/static/js/**/*.js",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans:    ['Manrope', 'sans-serif'],
        display: ['Manrope', 'sans-serif'],
        mono:    ['"JetBrains Mono"', 'monospace'],
      },

      colors: {
        // Usando CSS vars definidas em input.css :root (fonte única de verdade, light-only)
        dtx: {
          50:  'var(--color-dtx-50)',
          100: 'var(--color-dtx-100)',
          200: 'var(--color-dtx-200)',
          300: 'var(--color-dtx-300)',
          400: 'var(--color-dtx-400)',
          500: 'var(--color-dtx-500)',
          600: 'var(--color-dtx-600)',
          700: 'var(--color-dtx-700)',
          800: 'var(--color-dtx-800)',
          900: 'var(--color-dtx-900)',
        },

        surface: {
          canvas: 'var(--color-surface-canvas)',
          base:   'var(--color-surface-base)',
          raised: 'var(--color-surface-raised)',
          border: 'var(--color-surface-border)',
          muted:  'var(--color-surface-muted)',
          'muted-text': 'var(--color-text-muted)',
        },

        nav: {
          bg:     'var(--color-nav-bg)',
          border: 'var(--color-nav-border)',
          text:   'var(--color-nav-text)',
          active: 'var(--color-nav-active)',
          accent: 'var(--color-nav-accent)',
        },

        status: {
          open: {
            DEFAULT: 'var(--color-status-open-text)',
            bg:      'var(--color-status-open-bg)',
            border:  'var(--color-status-open-border)',
          },
          active: {
            DEFAULT: 'var(--color-status-active-text)',
            bg:      'var(--color-status-active-bg)',
            border:  'var(--color-status-active-border)',
          },
          done: {
            DEFAULT: 'var(--color-status-done-text)',
            bg:      'var(--color-status-done-bg)',
            border:  'var(--color-status-done-border)',
          },
          cancelled: {
            DEFAULT: 'var(--color-status-cancelled-text)',
            bg:      'var(--color-status-cancelled-bg)',
            border:  'var(--color-status-cancelled-border)',
          },
          pending: {
            DEFAULT: 'var(--color-status-pending-text)',
            bg:      'var(--color-status-pending-bg)',
            border:  'var(--color-status-pending-border)',
          },
        },
      },

      zIndex: {
        // Escala semântica única: nada de z-[200]/z-[9999] soltos nos templates.
        sticky:   '10', // barras/cabeçalhos sticky dentro da página (abaixo da navbar)
        nav:      '20', // navbar fixa no topo
        dropdown: '30', // menus, autocomplete, dropdowns (navbar e formulários)
        modal:    '40', // overlays de modal e loading full-page
        toast:    '50', // flash messages e banners de notificação — sempre por cima
      },

      borderRadius: {
        'dtx-sm': '6px',
        'dtx-md': '8px',
        'dtx-lg': '12px',
        'dtx-xl': '24px',
      },

      boxShadow: {
        'dtx-sm': '0 1px 2px 0 rgb(0 0 0 / 0.05)',
        'dtx':    '0 1px 3px 0 rgb(0 0 0 / 0.08), 0 1px 2px -1px rgb(0 0 0 / 0.05)',
        'dtx-md': '0 4px 12px 0 rgb(0 0 0 / 0.10), 0 2px 4px -1px rgb(0 0 0 / 0.06)',
      },
    },
  },
  plugins: [],
}
