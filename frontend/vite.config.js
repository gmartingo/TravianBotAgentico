import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    port: 5173,
    // host:true expone el dev server en la red local (0.0.0.0) para poder
    // abrirlo desde el móvil en la misma WiFi: http://<IP-del-Mac>:5173
    host: true,
    proxy: {
      // El proxy retira /api antes de redirigir al backend.
      // Frontend usa /api/accounts → backend recibe /accounts en :8000.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
