import { defineConfig, devices } from '@playwright/test'

const PREVIEW_PORT = 4174
const FAKE_PORT = 8787
const baseURL = `http://localhost:${PREVIEW_PORT}`

/** 실제 Provider를 호출하지 않는 Fake backend로 사용자 흐름을 리허설한다. */
export default defineConfig({
  testDir: './e2e',
  testMatch: /.*\.spec\.ts/,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: { baseURL, trace: 'off' },
  projects: [
    {
      name: 'desktop',
      testMatch: /flows\.spec\.ts/,
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
    {
      // chromium 기반 모바일 에뮬레이션. 계획서의 375px 하한을 쓴다.
      name: 'mobile',
      testMatch: /mobile\.spec\.ts/,
      use: { ...devices['Pixel 5'], viewport: { width: 375, height: 812 } },
    },
  ],
  webServer: [
    {
      command: `node e2e/fake-backend.mjs`,
      env: { FAKE_PORT: String(FAKE_PORT) },
      port: FAKE_PORT,
      reuseExistingServer: false,
    },
    {
      command: `npm run build && npm run preview -- --port ${PREVIEW_PORT} --strictPort`,
      env: { VITE_DEV_API_TARGET: `http://127.0.0.1:${FAKE_PORT}` },
      port: PREVIEW_PORT,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
})
