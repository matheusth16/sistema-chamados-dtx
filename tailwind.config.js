/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/templates/**/*.html",
    "./app/static/js/**/*.js",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        display: ['"Plus Jakarta Sans"', 'sans-serif'],
      },

      // ── DTX Blue ── acento único derivado da marca
      colors: {
        dtx: {
          50:  '#EEF4FF',
          100: '#D9E7FF',
          200: '#B3CEFF',
          300: '#7DAEFF',
          400: '#4A8AE8',
          500: '#2E6ACC',
          600: '#1e4a8c', // primary brand
          700: '#163A70',
          800: '#0F2B54',
          900: '#091D38',
        },

        // ── Superfícies ── light-only
        surface: {
          canvas: '#FBFBFA', // page background
          base:   '#FFFFFF', // card / panel
          raised: '#F5F5F4', // hover, zebra
          border: '#EAEAEA', // default border
          muted:  '#D1D5DB', // stronger border / divider
        },

        // ── Status semânticos ── pastéis acessíveis
        status: {
          open: {
            DEFAULT: '#92400E',
            bg:      '#FEF3C7',
            border:  '#FDE68A',
          },
          active: {
            DEFAULT: '#1D4ED8',
            bg:      '#EFF6FF',
            border:  '#BFDBFE',
          },
          done: {
            DEFAULT: '#065F46',
            bg:      '#ECFDF5',
            border:  '#A7F3D0',
          },
          cancelled: {
            DEFAULT: '#9F1239',
            bg:      '#FFF1F2',
            border:  '#FECDD3',
          },
          pending: {
            DEFAULT: '#475569',
            bg:      '#F8FAFC',
            border:  '#E2E8F0',
          },
        },
      },

      // ── Z-index nomeada ── evita magic numbers
      zIndex: {
        nav:      '10',
        dropdown: '20',
        modal:    '30',
        toast:    '50',
      },

      // ── Border radius DTX ── sm=6 / md=8 / lg=12 px
      borderRadius: {
        'dtx-sm': '6px',
        'dtx-md': '8px',
        'dtx-lg': '12px',
      },

      // ── Sombras mínimas ── enterprise clean
      boxShadow: {
        'dtx-sm': '0 1px 2px 0 rgb(0 0 0 / 0.05)',
        'dtx':    '0 1px 3px 0 rgb(0 0 0 / 0.08), 0 1px 2px -1px rgb(0 0 0 / 0.05)',
      },
    },
  },
  plugins: [],
}
