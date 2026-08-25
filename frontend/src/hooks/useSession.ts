import { useQuery } from '@tanstack/react-query'
import { createSession } from '@/api/session'

export function useSession() {
  return useQuery({
    queryKey: ['session'],
    queryFn: ({ signal }) => createSession(signal),
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  })
}
