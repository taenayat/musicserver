/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#0f0f0f',
        surface: '#1a1a1a',
        card: '#242424',
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
      },
      animation: {
        'slide-up': 'slide-up 0.25s ease-out',
      },
    },
  },
  plugins: [],
};
