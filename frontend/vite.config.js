import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// BASE_PATH is "/poketect/" for GitHub Pages, "/" everywhere else.
export default defineConfig({
  plugins: [react()],
  base: process.env.BASE_PATH || '/',
  server: { port: 5173, proxy: { '/api': 'http://127.0.0.1:8000' } },
  optimizeDeps: { exclude: ['onnxruntime-web'] },
  build: { chunkSizeWarningLimit: 1200 },
  test: { environment: 'node' },
})
