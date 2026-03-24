import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import dyadComponentTagger from '@dyad-sh/react-vite-component-tagger'

const ALLOWED_PUBLIC_VITE_KEYS = new Set([
  'VITE_API_BASE_URL',
  'VITE_DASHBOARD_TOKEN',
])

const SENSITIVE_ENV_HINTS = ['KEY', 'SECRET', 'TOKEN', 'PRIVATE', 'PASSWORD', 'MNEMONIC']

function isForbiddenPublicEnvKey(key) {
  if (!key.startsWith('VITE_')) return false
  if (ALLOWED_PUBLIC_VITE_KEYS.has(key)) return false
  const upperKey = key.toUpperCase()
  return SENSITIVE_ENV_HINTS.some((hint) => upperKey.includes(hint))
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const leakedViteKeys = Object.keys(env).filter(isForbiddenPublicEnvKey)

  if (leakedViteKeys.length > 0) {
    throw new Error(
      `Security error: unsupported sensitive public env vars with VITE_ prefix: ${leakedViteKeys.join(', ')}`
    )
  }

  const dashboardToken =
    env.DASHBOARD_READ_API_KEY ||
    env.DASHBOARD_API_KEY ||
    process.env.DASHBOARD_READ_API_KEY ||
    process.env.DASHBOARD_API_KEY ||
    ''

  const proxyHeaders = dashboardToken ? { 'X-API-Key': dashboardToken } : {}

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
        },
      },
    },
  }
})