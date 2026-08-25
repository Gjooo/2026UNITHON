const krw = new Intl.NumberFormat('ko-KR')

/** 통화 표시는 view layer에서만 한다. API에는 number를 그대로 보낸다. */
export function formatKrw(value: number): string {
  return `₩${krw.format(value)}`
}

export function formatMinutes(value: number): string {
  return `약 ${krw.format(value)}분`
}
