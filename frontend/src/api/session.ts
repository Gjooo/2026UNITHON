import { apiFetch } from './client'

/** 세션이 실제 비용을 발생시킬 수 있는 횟수. 운영 정책 값이며 제품 기능이 아니다. */
export interface ExecutionAllowance {
  used: number
  limit: number
}

export interface SessionResponse {
  expiresAt: string
  executionAllowance: ExecutionAllowance
}

/** 익명 세션을 만들거나 갱신한다. 토큰은 HttpOnly 쿠키로만 오간다. */
export function createSession(signal?: AbortSignal): Promise<SessionResponse> {
  return apiFetch<SessionResponse>('/session', { method: 'POST', signal })
}
