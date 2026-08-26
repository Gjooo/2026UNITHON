import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vitest/config'

export const sharedTestConfig = defineConfig({
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    restoreMocks: true,
  },
})
