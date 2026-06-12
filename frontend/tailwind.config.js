/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#0f0f0f',
        surface: '#1a1a1a',
        card: '#242424',
        border: '#333333',
        muted: '#888888',
        success: '#22c55e',
        error: '#ef4444',
        warning: '#f59e0b',
        accent: {
          start: '#6c63ff',
          end: '#a855f7',
        },
      },
      backgroundImage: {
        accent: 'linear-gradient(135deg, #6c63ff 0%, #a855f7 100%)',
      },
      maxWidth: {
        app: '480px',
      },
      keyframes: {
        'slide-up': {
          '0%': { transform: 'translateY(100%)' },
          '100%': { transform: 'translateY(0)' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
      },
      animation: {
        'slide-up': 'slide-up 0.25s ease-out',
        'fade-in': 'fade-in 0.2s ease-out',
      },
    },
  },
  plugins: [],
};
