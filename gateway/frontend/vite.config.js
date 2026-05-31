import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

// During `npm run dev`, proxy API + health to the running backend (port 4040)
// so the frontend can be developed without CORS hassle. In production the same
// FastAPI process serves this built bundle, so the proxy is dev-only.
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['icons/icon-192.png', 'icons/icon-512.png'],
      manifest: {
        name: 'Music Gateway',
        short_name: 'MusicGW',
        description: 'Browse and download music from Deezer',
        theme_color: '#0f0f0f',
        background_color: '#0f0f0f',
        display: 'standalone',
        start_url: '/',
        scope: '/',
        icons: [
          { src: 'icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'icons/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: 'icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        // Precache only the app shell. API responses and audio streams are
        // intentionally NOT cached (see denylist + absence of runtimeCaching).
        globPatterns: ['**/*.{js,css,html,svg,png,ico,woff2}'],
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api/, /^\/health/],
        runtimeCaching: [],
      },
    }),
  ],
  server: {
    proxy: {
      '/api': 'http://localhost:4040',
      '/health': 'http://localhost:4040',
    },
  },
});
