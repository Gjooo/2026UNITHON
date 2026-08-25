import { defineConfig, devices } from '@playwright/test'

const PREVIEW_PORT = 4176
const baseURL = `http://localhost:${PREVIEW_PORT}`

/**
 * 배포된 staging backend(또는 로컬 fake provider 모드)에 붙여 리허설한다.
 * Fake backend를 띄우지 않고 E2E_API_TARGET으로 프록시 대상만 바꾼다.
 * 실제 Provider 호출은 이 명령의 책임이 아니다 — smoke:runpod을 따로 쓴다.
 */
export default defineConfig({
  testDir: './e2e',
  testMatch: /flows\.spec\.ts/,
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: { baseURL, trace: 'off' },
  // Fake backend 전용 제어 endpoint를 쓰는 시나리오는 제외한다.
  grepInvert: /failed_execution_shows_safe_cause/,
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } },
  ],
  webServer: [
    {
      command: `npm run build && npm run preview -- --port ${PREVIEW_PORT} --strictPort`,
      env: {
        VITE_DEV_API_TARGET: process.env.E2E_API_TARGET ?? 'http://127.0.0.1:8000',
      },
      port: PREVIEW_PORT,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
})
