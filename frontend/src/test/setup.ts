import '@testing-library/jest-dom/vitest'
import { afterAll, afterEach, beforeAll, vi } from 'vitest'
import { server } from './msw/server'

// @testing-library/dom은 `jest` 전역이 있어야 fake timer를 인식한다. 이 shim이 없으면
// waitFor가 vitest에 의해 faked된 setInterval을 실시간으로 기다리며 멈춘다.
Object.defineProperty(globalThis, 'jest', {
  configurable: true,
  writable: true,
  value: { advanceTimersByTime: (ms: number) => void vi.advanceTimersByTime(ms) },
})

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  server.resetHandlers()
  // 앱이 새로고침 복구에 쓰는 값이라 테스트 사이에 새면 다음 테스트가 엉뚱한 화면에서 시작한다.
  window.localStorage.clear()
})
afterAll(() => server.close())
