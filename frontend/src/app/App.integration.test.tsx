import { describe, expect, it } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw/server'
import { renderApp } from '@/test/renderApp'
import sessionFixture from '@/test/fixtures/session.json'

describe('App bootstrap', () => {
  it('creates_an_anonymous_session_before_enabling_constraint_submission', async () => {
    const user = userEvent.setup()
    const received: Request[] = []
    let releaseSession!: () => void
    const sessionGate = new Promise<void>((resolve) => {
      releaseSession = resolve
    })

    server.use(
      http.post('*/api/v1/session', async ({ request }) => {
        received.push(request)
        await sessionGate
        return HttpResponse.json(sessionFixture, { status: 201 })
      }),
    )

    renderApp()

    const submit = screen.getByRole('button', { name: 'Agent에게 실행안 요청' })
    expect(submit).toBeDisabled()

    await user.type(screen.getByLabelText('최대 예산'), '10000')
    await user.click(screen.getByRole('radio', { name: /저비용/ }))
    expect(submit).toBeDisabled()

    releaseSession()

    await waitFor(() => expect(submit).toBeEnabled())
    expect(received).toHaveLength(1)
    expect(received[0].credentials).toBe('include')
    expect(new URL(received[0].url).pathname).toBe('/api/v1/session')
  })

  it('announces_the_anonymous_demo_session_in_the_app_shell', async () => {
    renderApp()

    expect(screen.getByRole('banner')).toHaveTextContent('UNWORK')
    expect(screen.getByRole('banner')).toHaveTextContent('MVP · SD 1.5 LoRA')
    expect(await screen.findByText('익명 데모 세션')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /로그인/ })).not.toBeInTheDocument()
  })
})
