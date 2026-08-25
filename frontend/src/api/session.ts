import { apiFetch } from './client'

export interface SessionResponse {
  expiresAt: string
}

/** 익명 세션을 만들거나 갱신한다. 토큰은 HttpOnly 쿠키로만 오간다. */
export function createSession(signal?: AbortSignal): Promise<SessionResponse> {
  return apiFetch<SessionResponse>('/session', { method: 'POST', signal })
}
