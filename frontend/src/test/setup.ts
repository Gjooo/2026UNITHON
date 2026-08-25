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
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
