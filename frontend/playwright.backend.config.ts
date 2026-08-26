import { defineConfig, devices } from '@playwright/test'

const PREVIEW_PORT = 4176

/**
 * E2E_BASE_URL을 주면 이미 배포된 주소를 그대로 친다(빌드·preview 없음).
 * 없으면 로컬에서 빌드본을 띄우고 E2E_API_TARGET으로 프록시한다.
 */
const deployed = process.env.E2E_BASE_URL
const baseURL = deployed ?? `http://localhost:${PREVIEW_PORT}`

/**
 * 배포된 staging backend(또는 로컬 fake provider 모드)에 붙여 리허설한다.
 * Fake backend를 띄우지 않고 E2E_API_TARGET으로 프록시 대상만 바꾼다.
 * 실제 Provider 호출은 이 명령의 책임이 아니다 — smoke:runpod을 따로 쓴다.
 */
export default defineConfig({
  testDir: './e2e',
  testMatch: /backend\.spec\.ts/,
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: { baseURL, trace: 'off' },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } },
  ],
  webServer: deployed
    ? []
    : [
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
