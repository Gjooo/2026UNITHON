import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { connectProvider, disconnectProvider, getProviders } from '@/api/providers'

export const RUNPOD = 'runpod'

export function useProviders(enabled: boolean) {
  return useQuery({
    queryKey: ['providers'],
    queryFn: ({ signal }) => getProviders(signal),
    enabled,
    staleTime: Infinity,
  })
}

export function useConnectProvider() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (apiKey: string) => connectProvider(RUNPOD, apiKey),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['providers'] }),
  })
}

export function useDisconnectProvider() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => disconnectProvider(RUNPOD),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['providers'] }),
  })
}
