import { apiFetch } from './client'

export interface SessionResponse {
  expiresAt: string
  /** 이 배포에서 실제 GPU 실행을 고를 수 있는지. false면 선택지를 감춘다. */
  realExecutionAvailable: boolean
}

/** 익명 세션을 만들거나 갱신한다. 토큰은 HttpOnly 쿠키로만 오간다. */
export function createSession(signal?: AbortSignal): Promise<SessionResponse> {
  return apiFetch<SessionResponse>('/session', { method: 'POST', signal })
}
