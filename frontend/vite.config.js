import { fileURLToPath } from 'node:url'
import vue from '@vitejs/plugin-vue'
import { defineConfig, loadEnv } from 'vite'

const projectRoot = fileURLToPath(new URL('../', import.meta.url))

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, projectRoot, [
    'CAREWAYV_API_PORT', 'CAREWAYV_API_TARGET', 'API_V1_PREFIX', 'WAYFINDING_PREFIX',
  ])
  const upstream = env.CAREWAYV_API_TARGET || `http://127.0.0.1:${env.CAREWAYV_API_PORT || 8000}`
  const wayfindingPath = (env.API_V1_PREFIX || '/api/v1') + (env.WAYFINDING_PREFIX || '/wayfinding')
  const proxy = {
    '/gateway/': {
      target: upstream,
      rewrite: (path) => path.replace(/^\/gateway/, wayfindingPath),
    },
  }
  return {
    plugins: [vue()],
    // Hai trang: giới thiệu (index.html) và màn hình kiosk (kiosk.html).
    build: {
      rollupOptions: {
        input: {
          main: fileURLToPath(new URL('index.html', import.meta.url)),
          kiosk: fileURLToPath(new URL('kiosk.html', import.meta.url)),
        },
      },
    },
    server: { host: '127.0.0.1', port: 5173, proxy },
    preview: { host: '127.0.0.1', port: 4173, proxy },
  }
})
