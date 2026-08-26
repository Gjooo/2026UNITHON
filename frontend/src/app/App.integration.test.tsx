import { describe, expect, it } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw/server'
import { enterService, renderApp } from '@/test/renderApp'
import sessionFixture from '@/test/fixtures/session.json'

describe('App bootstrap', () => {
  it('creates_an_anonymous_session_before_opening_the_service', async () => {
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
    await enterService(user)

    // 세션이 준비되기 전에는 서비스 화면을 열지 않는다.
    await waitFor(() => expect(received).toHaveLength(1))
    expect(screen.queryByLabelText('최대 예산')).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Agent에게 실행안 요청' }),
    ).not.toBeInTheDocument()

    releaseSession()

    expect(await screen.findByLabelText('최대 예산')).toBeInTheDocument()
    expect(received[0].credentials).toBe('include')
    expect(new URL(received[0].url).pathname).toBe('/api/v1/session')
  })

  it('announces_the_anonymous_session_in_the_app_shell', async () => {
    const user = userEvent.setup()
    renderApp()
    await enterService(user)

    expect(screen.getByRole('banner')).toHaveTextContent('UNWORK')
    expect(await screen.findByText('익명 세션')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /로그인/ })).not.toBeInTheDocument()
  })

  it('never_labels_the_product_stage_or_run_type', async () => {
    const user = userEvent.setup()
    renderApp()

    // 제품 단계·실행 성격 라벨은 사용자가 부딪히는 제약을 설명하지 못한다.
    // 제약은 라벨이 아니라 그 자리의 문장으로 밝힌다. 랜딩에도 적용된다.
    const forbidden = /MVP|데모|프로토타입|beta|Beta/
    expect(document.body.textContent).not.toMatch(forbidden)

    await enterService(user)
    await screen.findByText('익명 세션')
    expect(document.body.textContent).not.toMatch(forbidden)
  })
})
