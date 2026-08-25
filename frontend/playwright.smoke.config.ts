import { defineConfig, devices } from '@playwright/test'

/**
 * 실제 Provider smoke 전용. 배포된 주소를 그대로 친다.
 * 일반 test script와 섞이지 않도록 config를 분리한다.
 */
export default defineConfig({
  testDir: './e2e',
  testMatch: /smoke-real\.spec\.ts/,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  timeout: 25 * 60 * 1000,
  use: {
    baseURL: process.env.SMOKE_BASE_URL ?? 'https://unwork-agent.vercel.app',
    trace: 'off',
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } },
  ],
})
