import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

export default defineConfig({
  plugins: [react()],
  define: {
    // Inject VITE_DASHBOARD_API_KEY into window for useApi.js
    __DASHBOARD_API_KEY__: JSON.stringify(process.env.VITE_DASHBOARD_API_KEY || ''),
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
        secure: false,
        headers: {
          // Ensure proxy passes auth headers
          'X-API-Key': process.env.VITE_DASHBOARD_API_KEY || ''
        }
      },
      '/metrics': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
        secure: false,
      }
    }
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    }
  }
})