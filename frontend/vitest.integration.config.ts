import { defineConfig, mergeConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { sharedTestConfig } from './vitest.shared'

export default mergeConfig(
  sharedTestConfig,
  defineConfig({
    plugins: [react()],
    test: {
      name: 'integration',
      include: ['src/**/*.integration.test.{ts,tsx}'],
      exclude: ['**/node_modules/**'],
    },
  }),
)
