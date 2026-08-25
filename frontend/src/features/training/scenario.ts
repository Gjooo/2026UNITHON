/**
 * 입력 화면에서만 쓰는 상수. 필요 VRAM·최대 실행 시간처럼 서버 설정으로 바뀌는 값은
 * 여기에 두지 않고 Job 응답의 `scenario`를 그대로 표시한다.
 */
export const PRIORITY_OPTIONS = [
  {
    value: 'CHEAPEST',
    title: '저비용',
    description: '예상 GPU 비용이 가장 낮은 후보를 고릅니다.',
  },
  {
    value: 'BALANCED',
    title: '균형',
    description: '예상 비용과 예상 시간을 함께 고려해 고릅니다.',
  },
  {
    value: 'FASTEST',
    title: '빠른 완료',
    description: '예상 실행 시간이 가장 짧은 후보를 고릅니다.',
  },
] as const

export type Priority = (typeof PRIORITY_OPTIONS)[number]['value']

export const ESTIMATE_DISCLAIMER =
  '예상 비용은 실제 청구액을 제한하지 않으며, Agent는 사전 검증된 실행안 중에서만 선택합니다.'
