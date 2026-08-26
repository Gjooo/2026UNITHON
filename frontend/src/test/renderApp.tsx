import { render, screen } from '@testing-library/react'
import type userEvent from '@testing-library/user-event'
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

/** 랜딩을 지나 서비스로 들어간다. 여기서부터 세션이 만들어진다. */
export async function enterService(user: ReturnType<typeof userEvent.setup>) {
  const [start] = await screen.findAllByRole('button', { name: '시작하기' })
  await user.click(start)
}
