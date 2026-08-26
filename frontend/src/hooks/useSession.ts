import { useQuery } from '@tanstack/react-query'
import { createSession } from '@/api/session'

/**
 * 제품 소개만 보고 가는 사람에게 쿠키를 심지 않는다.
 * 서비스에 들어온 뒤에야 세션을 만든다.
 */
export function useSession(enabled = true) {
  return useQuery({
    queryKey: ['session'],
    queryFn: ({ signal }) => createSession(signal),
    enabled,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  })
}
