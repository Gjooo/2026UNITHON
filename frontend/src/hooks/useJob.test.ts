import { describe, expect, it } from 'vitest'
import { isInFlight, isTerminal, pollIntervalMs } from './useJob'

describe('폴링 정책', () => {
  it('polls_only_non_terminal_statuses', () => {
    expect(isInFlight('PROVISIONING')).toBe(true)
    expect(isInFlight('RUNNING')).toBe(true)
    // TERMINATING은 최종 상태가 아니다. 자원 종료 확인까지 계속 본다.
    expect(isInFlight('TERMINATING')).toBe(true)

    expect(isInFlight('DRAFT')).toBe(false)
    expect(isInFlight('COMPLETED')).toBe(false)
    expect(isInFlight('FAILED')).toBe(false)
    expect(isInFlight('CANCELLED')).toBe(false)
    expect(isInFlight(undefined)).toBe(false)
  })

  it('treats_draft_as_neither_in_flight_nor_terminal', () => {
    // 비용이 발생하지 않은 상태다. 폴링도 결과 표시도 하지 않는다.
    expect(isInFlight('DRAFT')).toBe(false)
    expect(isTerminal('DRAFT')).toBe(false)

    expect(isTerminal('COMPLETED')).toBe(true)
    expect(isTerminal('FAILED')).toBe(true)
    expect(isTerminal('CANCELLED')).toBe(true)
    // 자원 종료 확인 전이므로 최종이 아니다.
    expect(isTerminal('TERMINATING')).toBe(false)
    expect(isTerminal(undefined)).toBe(false)
  })

  it('backs_off_exponentially_up_to_fifteen_seconds', () => {
    expect(pollIntervalMs(0)).toBe(2500)
    expect(pollIntervalMs(1)).toBe(5000)
    expect(pollIntervalMs(2)).toBe(10_000)
    expect(pollIntervalMs(3)).toBe(15_000)
    expect(pollIntervalMs(9)).toBe(15_000)
  })
})
