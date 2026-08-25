import { describe, expect, it } from 'vitest'
import { formatElapsed, formatKrw, formatMinutes } from './format'

describe('format', () => {
  it('formats_krw_and_minutes_for_display_only', () => {
    expect(formatKrw(650)).toBe('₩650')
    expect(formatKrw(10000)).toBe('₩10,000')
    expect(formatMinutes(7)).toBe('약 7분')
  })

  it('formats_elapsed_time_from_the_server_start_time', () => {
    const startedAt = '2026-08-25T19:40:35.000Z'
    const at = (seconds: number) => Date.parse(startedAt) + seconds * 1000

    expect(formatElapsed(startedAt, at(0))).toBe('0분 0초')
    expect(formatElapsed(startedAt, at(9))).toBe('0분 9초')
    expect(formatElapsed(startedAt, at(72))).toBe('1분 12초')
    expect(formatElapsed(startedAt, at(600))).toBe('10분 0초')
    // 서버 시계와 어긋나 음수가 나와도 시간이 거꾸로 가지 않는다.
    expect(formatElapsed(startedAt, at(-5))).toBe('0분 0초')
    expect(formatElapsed(null, at(30))).toBe('0분 0초')
  })
})
