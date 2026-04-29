import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const backendPort = process.env.VITE_BACKEND_PORT || '8001'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': `http://127.0.0.1:${backendPort}`,
      '/ws': {
        target: `ws://127.0.0.1:${backendPort}`,
        ws: true,
      },
    },
  },
})
