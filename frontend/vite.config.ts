import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'

// 브라우저 기준 same-origin으로 만들어 CORS와 SameSite=Lax 쿠키 문제를 함께 피한다.
const apiProxy = {
  '/api': {
    target: process.env.VITE_DEV_API_TARGET ?? 'http://127.0.0.1:8000',
    changeOrigin: false,
  },
}

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: { proxy: apiProxy },
  preview: { proxy: apiProxy },
})
