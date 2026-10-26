import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev server mirrors the production nginx routing (frontend/nginx.conf) so the
// app always talks to same-origin paths. Start the backing services with
// `docker compose up backend cloudwatch-exporter prometheus grafana`.
// (The nginx login gate on /grafana and /prometheus is not applied in dev.)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/grafana': { target: 'http://localhost:3000', changeOrigin: true, ws: true },
      '/prometheus': { target: 'http://localhost:9090', changeOrigin: true },
    },
  },
})
