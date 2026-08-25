import { defineConfig, devices } from '@playwright/test'

const PREVIEW_PORT = 4175
const FAKE_PORT = 8788
const baseURL = `http://localhost:${PREVIEW_PORT}`

/** 375 / 768 / 1440에서 화면을 캡처해 이전 기준과 비교한다. */
export default defineConfig({
  testDir: './e2e',
  testMatch: /visual\.spec\.ts/,
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: { baseURL, trace: 'off' },
  expect: { toHaveScreenshot: { maxDiffPixelRatio: 0.01 } },
  projects: [
    { name: 'w375', use: { ...devices['Desktop Chrome'], viewport: { width: 375, height: 900 } } },
    { name: 'w768', use: { ...devices['Desktop Chrome'], viewport: { width: 768, height: 900 } } },
    { name: 'w1440', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } },
  ],
  webServer: [
    {
      command: 'node e2e/fake-backend.mjs',
      env: { FAKE_PORT: String(FAKE_PORT), FAKE_PROVISION_MS: '600000', FAKE_RUN_MS: '600000' },
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
