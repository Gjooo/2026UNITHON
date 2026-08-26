import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@/styles/global.css'

export function createAppQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { refetchOnWindowFocus: false } },
  })
}

export function AppProviders({
  queryClient,
  children,
}: {
  queryClient: QueryClient
  children: ReactNode
}) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}
