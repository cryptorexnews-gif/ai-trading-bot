import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import dyadComponentTagger from '@dyad-sh/react-vite-component-tagger';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const dashboardApiKey = env.DASHBOARD_API_KEY || process.env.DASHBOARD_API_KEY || '';
  const proxyHeaders = dashboardApiKey ? { 'X-API-Key': dashboardApiKey } : {};

  return {
    plugins: [dyadComponentTagger(), react()],
    server: {
      port: 3000,
      proxy: {
        '/api': {
          target: 'http://127.0.0.1:5000',
          changeOrigin: true,
          secure: false,
          headers: proxyHeaders,
        },
        '/metrics': {
          target: 'http://127.0.0.1:5000',
          changeOrigin: true,
          secure: false,
          headers: proxyHeaders,
        },
        '/ws': {
          target: 'ws://127.0.0.1:5000',
          ws: true,
          changeOrigin: true,
          secure: false,
          headers: proxyHeaders,
        }
      }
    }
  };
});