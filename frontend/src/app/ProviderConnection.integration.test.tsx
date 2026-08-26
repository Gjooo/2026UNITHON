import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw/server'
import { enterService, renderApp } from '@/test/renderApp'
import notConnected from '@/test/fixtures/providers/not-connected.json'
import connected from '@/test/fixtures/providers/connected.json'
import invalidCredential from '@/test/fixtures/errors/invalid-provider-credential.json'

const KEY = 'rpa_thisisnotarealkey_0123456789'

beforeEach(() => window.localStorage.clear())
afterEach(() => window.localStorage.clear())

function serveProviders(body: object) {
  server.use(http.get('*/api/v1/providers', () => HttpResponse.json(body)))
}

describe('공급자 연결', () => {
  it('asks_to_connect_a_provider_before_the_service', async () => {
    const user = userEvent.setup()
    serveProviders(notConnected)
    renderApp()
    await enterService(user)

    expect(await screen.findByLabelText('Runpod API 키')).toBeInTheDocument()
    // 연결 전에는 서비스를 쓸 수 없다.
    expect(screen.queryByLabelText('최대 예산')).not.toBeInTheDocument()
  })

  it('never_keeps_the_api_key_in_the_browser', async () => {
    const user = userEvent.setup()
    const sent: unknown[] = []
    serveProviders(notConnected)
    server.use(
      http.post('*/api/v1/providers/:id/credential', async ({ request }) => {
        sent.push(await request.json())
        serveProviders(connected)
        return new HttpResponse(null, { status: 204 })
      }),
    )

    renderApp()
    await enterService(user)
    const field = await screen.findByLabelText('Runpod API 키')

    // 입력값이 화면에 노출되지 않는다.
    expect(field).toHaveAttribute('type', 'password')

    await user.type(field, KEY)
    await user.click(screen.getByRole('button', { name: '연결하기' }))

    expect(await screen.findByLabelText('최대 예산')).toBeInTheDocument()
    expect(sent).toEqual([{ apiKey: KEY }])

    // 남의 계정 키를 브라우저에 남기지 않는다.
    expect(JSON.stringify(window.localStorage)).not.toContain(KEY)
    expect(JSON.stringify(window.sessionStorage)).not.toContain(KEY)
    expect(document.body.innerHTML).not.toContain(KEY)
  })

  it('keeps_the_user_on_the_step_when_the_key_is_rejected', async () => {
    const user = userEvent.setup()
    serveProviders(notConnected)
    server.use(
      http.post('*/api/v1/providers/:id/credential', () =>
        HttpResponse.json(invalidCredential, { status: 401 }),
      ),
    )

    renderApp()
    await enterService(user)
    await user.type(await screen.findByLabelText('Runpod API 키'), KEY)
    await user.click(screen.getByRole('button', { name: '연결하기' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      '이 키로는 Runpod에 연결할 수 없습니다. 키를 다시 확인해 주세요.',
    )
    expect(screen.getByLabelText('Runpod API 키')).toBeInTheDocument()
    expect(screen.queryByLabelText('최대 예산')).not.toBeInTheDocument()
    // 거절된 값을 그대로 두지 않는다.
    expect(screen.getByLabelText('Runpod API 키')).toHaveValue('')
  })

  it('skips_the_step_when_the_session_is_already_connected', async () => {
    const user = userEvent.setup()
    serveProviders(connected)
    renderApp()
    await enterService(user)

    expect(await screen.findByLabelText('최대 예산')).toBeInTheDocument()
    expect(screen.queryByLabelText('Runpod API 키')).not.toBeInTheDocument()
  })

  it('shows_which_account_runs_the_training', async () => {
    const user = userEvent.setup()
    serveProviders(connected)
    renderApp()
    await enterService(user)
    await screen.findByLabelText('최대 예산')

    // 비용이 누구 계정에서 나가는지 계속 보인다.
    const banner = screen.getByRole('banner')
    expect(within(banner).getByText(/Runpod 연결됨/)).toBeInTheDocument()
  })

  it('does_not_open_the_service_when_the_connection_state_is_unknown', async () => {
    const user = userEvent.setup()
    server.use(http.get('*/api/v1/providers', () => HttpResponse.error()))

    renderApp()
    await enterService(user)

    // 연결 상태를 모르는데 열어 주면, 사용자는 승인 단계에서야 막힌다.
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.queryByLabelText('최대 예산')).not.toBeInTheDocument()
  })
})