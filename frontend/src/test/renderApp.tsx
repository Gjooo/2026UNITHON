import { render } from '@testing-library/react'
import { QueryClient } from '@tanstack/react-query'
import { App } from '@/app/App'
import { AppProviders } from '@/app/AppProviders'

export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
}

export function renderApp() {
  const queryClient = createTestQueryClient()
  return {
    queryClient,
    ...render(
      <AppProviders queryClient={queryClient}>
        <App />
      </AppProviders>,
    ),
  }
}
