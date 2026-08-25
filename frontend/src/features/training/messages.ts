import { ApiError, NetworkError } from '@/api/errors'

/**
 * 서버가 준 message가 아니라 code로 번역한다.
 * 서버 문구가 바뀌어도 화면이 흔들리지 않고, 기계 판독 값이 화면에 새지 않는다.
 */
const BY_CODE: Record<string, string> = {
  VALIDATION_ERROR: '입력한 예산과 우선순위를 다시 확인해 주세요.',
  NO_ELIGIBLE_PLAN: '이 예산 안에서 실행할 수 있는 GPU 후보가 없습니다.',
  DEMO_BUSY: '지금은 다른 실행이 진행 중입니다. 대기열이 없으니 잠시 후 다시 시도해 주세요.',
  EXECUTION_ALREADY_USED: '이 브라우저에서는 실제 실행을 한 번만 할 수 있습니다.',
  INVALID_JOB_STATE: '이 작업은 현재 이 행동을 할 수 있는 상태가 아닙니다.',
  RUNPOD_UNAVAILABLE: '실행 환경을 시작하거나 확인하지 못했습니다. 잠시 후 다시 확인해 주세요.',
  SESSION_REQUIRED: '세션이 만료됐습니다. 새 세션을 시작해 주세요.',
  SESSION_EXPIRED: '세션이 만료됐습니다. 새 세션을 시작해 주세요.',
  JOB_NOT_FOUND: '이 작업을 찾을 수 없거나 현재 세션에서 볼 수 없습니다.',
}

const FALLBACK = '연결 상태를 확인한 뒤 다시 시도해 주세요.'

export function toUserMessage(error: unknown): string {
  if (error instanceof ApiError) return BY_CODE[error.code] ?? FALLBACK
  if (error instanceof NetworkError) return FALLBACK
  return FALLBACK
}

export const EXECUTION_LIMIT_NOTICE =
  '이 브라우저에서는 실제 실행을 한 번만 할 수 있습니다.'

export const PRIORITY_LABEL: Record<string, string> = {
  CHEAPEST: '저비용',
  BALANCED: '균형',
  FASTEST: '빠른 완료',
}

export const ELIGIBILITY_LABEL: Record<string, string> = {
  ELIGIBLE: '예산 내',
  OVER_BUDGET: '예산 초과',
}

/** priceDataType은 기계 판독 값이므로 화면에는 문구로 바꿔 표시한다. */
export function priceDataTypeLabel(priceDataType: string): string {
  return priceDataType === 'DEMO_SNAPSHOT' ? '사전 검증 스냅샷 가격' : '실시간 가격'
}
