const krw = new Intl.NumberFormat('ko-KR')

/** 통화 표시는 view layer에서만 한다. API에는 number를 그대로 보낸다. */
export function formatKrw(value: number): string {
  return `₩${krw.format(value)}`
}

export function formatMinutes(value: number): string {
  return `약 ${krw.format(value)}분`
}

/**
 * 표시용 경과 시간. timeout 판단은 서버가 한다.
 * 서버 시계와 어긋나 음수가 나와도 시간이 거꾸로 가지 않는다.
 */
export function formatElapsed(startedAt: string | null, now: number): string {
  if (!startedAt) return '0분 0초'
  const elapsedMs = Math.max(0, now - Date.parse(startedAt))
  const totalSeconds = Math.floor(elapsedMs / 1000)
  return `${Math.floor(totalSeconds / 60)}분 ${totalSeconds % 60}초`
}
