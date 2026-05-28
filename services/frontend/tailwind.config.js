/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        mono: ['"JetBrains Mono"', '"Fira Code"', 'monospace'],
        display: ['"DM Mono"', '"JetBrains Mono"', 'monospace'],
      },
      colors: {
        // Perception palette
        ink:    '#0a0b0d',
        panel:  '#0f1114',
        surface:'#161a1f',
        border: '#1e2530',
        muted:  '#2a3340',
        dim:    '#4a5568',
        text:   '#c8d0dc',
        bright: '#e8edf5',
        // Signal colours
        green:  '#00d084',
        amber:  '#f5a623',
        red:    '#e63946',
        blue:   '#3d8ef0',
        purple: '#8b5cf6',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'flow': 'flow 2s linear infinite',
        'slide-in': 'slideIn 0.2s ease-out',
        'fade-in': 'fadeIn 0.3s ease-out',
      },
      keyframes: {
        flow: {
          '0%': { strokeDashoffset: '20' },
          '100%': { strokeDashoffset: '0' },
        },
        slideIn: {
          '0%': { transform: 'translateY(-8px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
      },
    },
  },
  plugins: [],
}
