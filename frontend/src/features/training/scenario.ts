/** MVP는 사전 검증된 고정 workload 하나만 실행한다. API-spec.md의 scenario 값과 같다. */
export const DEMO_SCENARIO = {
  name: 'Stable Diffusion 1.5 LoRA',
  requiredVramGb: 24,
  maxRuntimeMinutes: 10,
} as const

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
  '예상 비용은 실제 청구액을 제한하지 않으며, Agent는 검증된 데모 실행안 안에서 선택합니다.'
