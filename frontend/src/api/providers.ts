import { apiFetch } from './client'

export type ConnectionStatus = 'CONNECTED' | 'NOT_CONNECTED'

export interface Provider {
  id: string
  name: string
  connectionStatus: ConnectionStatus
  connectedAt: string | null
}

export interface ProvidersResponse {
  providers: Provider[]
}

export function getProviders(signal?: AbortSignal): Promise<ProvidersResponse> {
  return apiFetch<ProvidersResponse>('/providers', { signal })
}

/**
 * 키는 이 요청의 인자로만 존재한다. 응답 본문은 비어 있고 서버도 되돌려 주지 않는다.
 * 클라이언트는 어디에도 보관하지 않는다.
 */
export function connectProvider(providerId: string, apiKey: string): Promise<void> {
  return apiFetch<void>(`/providers/${providerId}/credential`, {
    method: 'POST',
    body: JSON.stringify({ apiKey }),
  })
}

export function disconnectProvider(providerId: string): Promise<void> {
  return apiFetch<void>(`/providers/${providerId}/credential`, { method: 'DELETE' })
}
