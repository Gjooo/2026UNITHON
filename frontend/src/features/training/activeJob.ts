const ACTIVE_JOB_KEY = 'unwork.activeJobId'

/**
 * 새로고침 복구용 Job ID만 보관한다. 서버의 cookie 소유권 검사가 남아 있으므로
 * 이 값은 인증 정보가 아니다. 401·404이면 즉시 지운다.
 */
export function readActiveJobId(): string | null {
  try {
    return window.localStorage.getItem(ACTIVE_JOB_KEY)
  } catch {
    return null
  }
}

export function writeActiveJobId(jobId: string): void {
  try {
    window.localStorage.setItem(ACTIVE_JOB_KEY, jobId)
  } catch {
    // Storage를 못 쓰는 브라우저에서도 현재 흐름은 계속된다.
  }
}

export function clearActiveJobId(): void {
  try {
    window.localStorage.removeItem(ACTIVE_JOB_KEY)
  } catch {
    // 지우지 못해도 서버 소유권 검사가 남아 있다.
  }
}
