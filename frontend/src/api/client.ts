import { NetworkError, toApiError } from './errors'

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL ?? ''

/** same-origin reverse proxy 배포 기본값. */
export const apiBaseUrl = configuredBaseUrl === '' ? '/api/v1' : configuredBaseUrl

function resolveUrl(path: string): string {
  return new URL(`${apiBaseUrl}${path}`, window.location.origin).toString()
}

/**
 * base URL, JSON header, 세션 쿠키 동봉, 공통 오류 파싱만 담당한다.
 * 브라우저에서 Provider 비밀값을 읽거나 저장하지 않는다.
 */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(resolveUrl(path), {
      ...init,
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...init.headers },
    })
  } catch (cause) {
    throw new NetworkError(cause)
  }

  if (!response.ok) throw await toApiError(response)
  if (response.status === 204 || response.headers.get('content-length') === '0') {
    return undefined as T
  }
  return (await response.json()) as T
}
